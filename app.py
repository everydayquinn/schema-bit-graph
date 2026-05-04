"""
FastAPI wrapper — slice 10.

Exposes the unified Python+SQL architecture as a tiny web service:
  - load and run programs
  - inspect CPU state and execution trace
  - register chunks
  - register interrupt vectors and fire events
  - list everything in the catalog

Single-tenant, ephemeral by default — `cpu.db` rebuilds on /api/reset.
No auth (it's a demo).  The frontend at / drives all of this.

Run locally:
    .venv/bin/uvicorn app:app --reload
    open http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from cpu        import build_db, CPU
import mirror
from asm        import assemble
from compose    import compose, expand, insert_chunk, ensure_schema as ensure_chunks_schema
from interrupts import (ensure_schema as ensure_interrupts_schema,
                        register as register_vector,
                        fire_event,
                        list_vectors)


HERE  = Path(__file__).parent
DB    = HERE / "cpu.db"
STATIC = HERE / "static"


# ------------------------------------------------------------------
# state — one CPU instance + one DB connection per process
# ------------------------------------------------------------------
class AppState:
    def __init__(self):
        self.conn: sqlite3.Connection | None = None
        self.cpu:  CPU | None = None

    def reset(self):
        # drop and rebuild cpu.db; re-apply chunks + interrupts schemas.
        # Uvicorn dispatches requests on worker threads, so the connection
        # must be opened with check_same_thread=False.  build_db() creates
        # its own connection (single-thread); we close it and reopen here.
        initial = build_db()
        initial.close()
        self.conn = sqlite3.connect(str(DB), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        ensure_chunks_schema(self.conn)
        ensure_interrupts_schema(self.conn)
        self.conn.commit()
        self.cpu = CPU(self.conn)


state = AppState()
state.reset()


# ------------------------------------------------------------------
# Pydantic models
# ------------------------------------------------------------------
class Instruction(BaseModel):
    mnemonic: str
    operand:  int = 0


class ProgramRequest(BaseModel):
    instructions: list[Instruction]
    data: dict[int, int] = Field(default_factory=dict)
    max_cycles: int = 64
    reset_first: bool = True


class ChunkRequest(BaseModel):
    name:        str
    body:        list[Instruction]
    params:      list[str] = Field(default_factory=list)
    description: str | None = None
    replace:     bool = False


class VectorRequest(BaseModel):
    event_type:    str
    handler_chunk: str
    description:   str | None = None


class EventRequest(BaseModel):
    event_type: str
    payload:    dict[str, int] | None = None


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------
def _registers_dict() -> dict[str, int]:
    return {r["name"]: r["value"]
            for r in state.conn.execute("SELECT name, value FROM registers")}


def _ram_list() -> list[int]:
    rows = state.conn.execute("SELECT addr, value FROM ram ORDER BY addr").fetchall()
    out = [0] * 16
    for r in rows:
        out[r["addr"]] = r["value"]
    return out


def _trace_rows() -> list[dict[str, Any]]:
    rows = state.conn.execute(
        "SELECT cycle, mnemonic, operand, "
        "       a_before, a_after, out_before, out_after, t_states "
        "FROM   d_instruction_trace ORDER BY cycle"
    ).fetchall()
    return [dict(r) for r in rows]


def _chunks_list() -> list[dict[str, Any]]:
    out = []
    for r in state.conn.execute(
        "SELECT name, description, params FROM chunks ORDER BY name"
    ):
        body = state.conn.execute(
            "SELECT step, mnemonic, operand FROM chunk_body "
            "WHERE chunk_name=? ORDER BY step",
            (r["name"],),
        ).fetchall()
        out.append({
            "name":        r["name"],
            "description": r["description"],
            "params":      json.loads(r["params"] or "[]"),
            "body":        [{"step": b["step"], "mnemonic": b["mnemonic"], "operand": b["operand"]}
                            for b in body],
        })
    return out


def _event_log(limit: int = 20) -> list[dict[str, Any]]:
    rows = state.conn.execute(
        "SELECT id, event_type, fired_at, handler_chunk, halted_clean, "
        "       cycles_used, output_a, output_out, error "
        "FROM   event_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------
# FastAPI app
# ------------------------------------------------------------------
app = FastAPI(title="Schema-bit-graph CPU", version="0.10")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text()


@app.get("/api/state")
def get_state():
    return {
        "registers": _registers_dict(),
        "ram":       _ram_list(),
    }


@app.post("/api/reset")
def reset():
    state.reset()
    return {"ok": True, "message": "rebuilt cpu.db, fresh CPU instance"}


@app.get("/api/opcodes")
def opcodes():
    rows = state.conn.execute(
        "SELECT opcode, mnemonic FROM opcodes ORDER BY opcode"
    ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/program")
def run_program(req: ProgramRequest):
    """Assemble instructions, load into RAM, run CPU, return trace + state."""
    if req.reset_first:
        state.reset()

    try:
        bytes_out = assemble(
            [(i.mnemonic, i.operand) for i in req.instructions],
            state.conn,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"assemble error: {e}")

    # Load program bytes at addr 0; data fills the rest
    ram_init = {addr: 0 for addr in range(16)}
    for addr, val in enumerate(bytes_out):
        if addr >= 16:
            raise HTTPException(status_code=400,
                                detail=f"program too long: {len(bytes_out)} bytes (max 16)")
        ram_init[addr] = val
    for addr, val in (req.data or {}).items():
        addr = int(addr)
        if not 0 <= addr <= 15:
            raise HTTPException(status_code=400, detail=f"bad data addr {addr}")
        ram_init[addr] = int(val) & 0xFF

    state.conn.execute("DELETE FROM ram")
    for addr, val in ram_init.items():
        state.conn.execute("INSERT INTO ram (addr, value) VALUES (?, ?)",
                           (addr, val & 0xFF))
    state.conn.commit()

    state.cpu = CPU(state.conn)
    state.cpu.run(max_cycles=req.max_cycles)
    mirror.rebuild(state.conn)

    return {
        "bytes":     bytes_out,
        "registers": _registers_dict(),
        "ram":       _ram_list(),
        "trace":     _trace_rows(),
        "halted":    bool(state.cpu.halted),
        "cycles":    state.cpu.cycle,
    }


@app.get("/api/trace")
def get_trace():
    mirror.rebuild(state.conn)
    return {"trace": _trace_rows()}


@app.get("/api/chunks")
def list_chunks():
    return {"chunks": _chunks_list()}


@app.post("/api/chunks")
def add_chunk(req: ChunkRequest):
    body = [(i.mnemonic, i.operand if not isinstance(i.operand, str) else i.operand)
            for i in req.body]
    inserted = insert_chunk(
        state.conn, req.name, body,
        description=req.description,
        params=req.params,
        replace=req.replace,
    )
    if not inserted:
        raise HTTPException(status_code=409,
                            detail=f"chunk {req.name!r} already exists (set replace=true)")
    return {"ok": True, "name": req.name}


@app.get("/api/vectors")
def get_vectors():
    return {"vectors": list_vectors(state.conn)}


@app.post("/api/vectors")
def add_vector(req: VectorRequest):
    # Validate handler exists
    exists = state.conn.execute(
        "SELECT 1 FROM chunks WHERE name=?", (req.handler_chunk,)
    ).fetchone()
    if not exists:
        raise HTTPException(status_code=400,
                            detail=f"handler chunk {req.handler_chunk!r} not found")
    register_vector(state.conn, req.event_type, req.handler_chunk, req.description)
    return {"ok": True}


@app.post("/api/event")
def fire(req: EventRequest):
    try:
        result = fire_event(state.conn, state.cpu,
                            req.event_type, payload=req.payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "result":    result,
        "registers": _registers_dict(),
        "ram":       _ram_list(),
    }


@app.get("/api/event_log")
def get_event_log(limit: int = 20):
    return {"events": _event_log(limit)}
