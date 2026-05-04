"""
Interrupt dispatcher — the third Python role.

This is what unifies Python+SQL into one architecture.  Python plays:
  1. compiler   — asm.py + compose.py (mnemonic/chunk -> bytes)
  2. interpreter — cpu.py fire() loop drives execution from RAM
  3. dispatcher  — THIS FILE: external events route into handler chunks

Flow when an event fires:
  1. lookup handler chunk in interrupt_vectors
  2. expand+assemble the chunk (params come from event payload if dict)
  3. load handler bytes into RAM[0..11]; PRESERVE RAM[12..15] (persistent scratch)
  4. PRESERVE registers (A, B, OUT, halted-cleared); set PC=0
  5. run CPU until HLT or max_cycles
  6. log the outcome to event_log
  7. return outcome dict to caller

Persistent scratch convention:
  RAM[12..15] survive across events; handlers can read/write here for state
  RAM[0..11]  are scratch for the handler bytecode itself
"""

import json
import sqlite3
from pathlib import Path

from asm     import assemble
from compose import expand
from cpu     import CPU

HERE = Path(__file__).parent
INTERRUPTS_SCHEMA_SQL = (HERE / "interrupts_schema.sql").read_text()

HLT_BYTE         = 0xF0
HANDLER_REGION   = range(0, 12)     # bytes 0..11 reserved for handler code
SCRATCH_REGION   = range(12, 16)    # bytes 12..15 persist across events
MAX_HANDLER_BYTES = len(HANDLER_REGION)


def ensure_schema(conn):
    """Apply interrupts_schema.sql.  Safe to call repeatedly."""
    conn.executescript(INTERRUPTS_SCHEMA_SQL)
    conn.commit()


# ------------------------------------------------------------------
# Vector table management
# ------------------------------------------------------------------
def register(conn, event_type, handler_chunk, description=None):
    """Register or replace the handler chunk for an event type."""
    conn.execute(
        "INSERT INTO interrupt_vectors (event_type, handler_chunk, description) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT(event_type) DO UPDATE SET "
        "  handler_chunk=excluded.handler_chunk, "
        "  description=excluded.description",
        (event_type, handler_chunk, description),
    )
    conn.commit()


def unregister(conn, event_type):
    conn.execute("DELETE FROM interrupt_vectors WHERE event_type=?", (event_type,))
    conn.commit()


def list_vectors(conn):
    return [dict(r) for r in conn.execute(
        "SELECT event_type, handler_chunk, description FROM interrupt_vectors "
        "ORDER BY event_type"
    )]


# ------------------------------------------------------------------
# Event firing
# ------------------------------------------------------------------
def fire_event(conn, cpu, event_type, payload=None, max_cycles=64):
    """
    Fire one event.  Returns dict describing the outcome.

    `cpu` is a live CPU instance whose registers persist across events.
    `payload` is optional; if it's a dict, its entries become chunk params.
    """
    payload_json = json.dumps(payload) if payload is not None else None

    # Lookup
    row = conn.execute(
        "SELECT handler_chunk FROM interrupt_vectors WHERE event_type=?",
        (event_type,),
    ).fetchone()

    if row is None:
        conn.execute(
            "INSERT INTO event_log (event_type, payload_json, halted_clean, error) "
            "VALUES (?, ?, 0, ?)",
            (event_type, payload_json, "no handler registered"),
        )
        conn.commit()
        return {"event_type": event_type, "handled": False,
                "reason": "no handler registered"}

    handler_chunk = row["handler_chunk"]

    # Expand chunk -> assemble bytes
    try:
        params = payload if isinstance(payload, dict) else {}
        ref = (handler_chunk, params) if params else (handler_chunk,)
        flat = expand([ref], conn)
        handler_bytes = assemble(flat, conn)
    except Exception as e:
        conn.execute(
            "INSERT INTO event_log (event_type, payload_json, handler_chunk, halted_clean, error) "
            "VALUES (?, ?, ?, 0, ?)",
            (event_type, payload_json, handler_chunk, str(e)),
        )
        conn.commit()
        return {"event_type": event_type, "handled": False,
                "reason": f"expand/assemble failed: {e}"}

    program_bytes = handler_bytes + [HLT_BYTE]
    if len(program_bytes) > MAX_HANDLER_BYTES:
        msg = (f"handler {handler_chunk!r} + HLT = {len(program_bytes)} bytes, "
               f"exceeds handler region ({MAX_HANDLER_BYTES})")
        conn.execute(
            "INSERT INTO event_log (event_type, payload_json, handler_chunk, halted_clean, error) "
            "VALUES (?, ?, ?, 0, ?)",
            (event_type, payload_json, handler_chunk, msg),
        )
        conn.commit()
        raise ValueError(msg)

    # Snapshot scratch RAM (persistent region) before overwriting handler region
    scratch_now = {
        addr: conn.execute("SELECT value FROM ram WHERE addr=?", (addr,)).fetchone()["value"]
        for addr in SCRATCH_REGION
    }

    # Build new RAM: handler bytes in 0..11 (zero-padded), scratch preserved in 12..15
    new_ram = {addr: 0 for addr in HANDLER_REGION}
    for addr, val in enumerate(program_bytes):
        new_ram[addr] = val
    for addr, val in scratch_now.items():
        new_ram[addr] = val

    conn.execute("DELETE FROM ram")
    for addr, val in new_ram.items():
        conn.execute("INSERT INTO ram (addr, value) VALUES (?, ?)", (addr, val & 0xFF))
    conn.commit()

    # Preserve A, B, OUT; reset PC + halted + cycle counter
    cpu.pc      = 0
    cpu.halted  = False
    cycles_pre  = cpu.cycle
    cpu.run(max_cycles=max_cycles)
    cycles_used = cpu.cycle - cycles_pre

    # Persist register snapshot (so other tools can see post-event state)
    cpu.sync_registers()

    # Log
    conn.execute(
        """INSERT INTO event_log
           (event_type, payload_json, handler_chunk, cycles_used, halted_clean,
            output_a, output_b, output_out)
           VALUES (?,?,?,?,?,?,?,?)""",
        (event_type, payload_json, handler_chunk, cycles_used,
         int(cpu.halted), cpu.a, cpu.b, cpu.out),
    )
    conn.commit()

    return {
        "event_type":   event_type,
        "handler":      handler_chunk,
        "handled":      True,
        "halted_clean": bool(cpu.halted),
        "cycles":       cycles_used,
        "output_a":     cpu.a,
        "output_b":     cpu.b,
        "output_out":   cpu.out,
        "scratch_after": {addr: conn.execute(
            "SELECT value FROM ram WHERE addr=?", (addr,)
        ).fetchone()["value"] for addr in SCRATCH_REGION},
    }


# ------------------------------------------------------------------
# Convenience: a tiny REPL-style event loop
# ------------------------------------------------------------------
def event_loop_keyboard(conn, cpu):
    """
    Minimal interactive event loop driven by stdin lines.
    Each line typed becomes an event_type.  Empty line exits.
    """
    print("interrupt event loop (empty line to quit)")
    while True:
        try:
            line = input("event> ").strip()
        except EOFError:
            break
        if not line:
            break
        result = fire_event(conn, cpu, line)
        print(f"  -> {result}")
