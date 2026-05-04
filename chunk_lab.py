"""
Chunk lab — slice 4.

Runs each chunk in an isolated, fresh CPU substrate and records its
behavioral fingerprint: register/memory/output deltas given controlled
initial state.

Two functions:

    run_chunk(conn, name, params=..., initial_a=..., initial_b=...,
              initial_ram=..., max_cycles=...)
        -> dict           # ephemeral, does NOT persist

    fingerprint_chunk(conn, name, scenarios, params=...)
        -> list[dict]     # persists rows in chunk_fingerprint

Key isolation rule: the lab uses an in-memory SQLite for the CPU
substrate, so chunk execution never pollutes the user's working DB.
The catalog (chunks, chunk_body) and the persisted fingerprints stay
in the user's `conn`.
"""

import json
import sqlite3
from pathlib import Path

from cpu     import CPU
from asm     import assemble
from compose import expand_chunk

HERE       = Path(__file__).parent
SCHEMA_SQL = (HERE / "schema.sql").read_text()

LAB_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunk_fingerprint (
    chunk_name      TEXT    NOT NULL,
    scenario_id     TEXT    NOT NULL,
    input_a         INTEGER NOT NULL,
    input_b         INTEGER NOT NULL,
    input_ram_json  TEXT    NOT NULL,
    params_json     TEXT    NOT NULL,
    output_a        INTEGER NOT NULL,
    output_b        INTEGER NOT NULL,
    output_out      INTEGER NOT NULL,
    ram_writes_json TEXT    NOT NULL,
    halted          INTEGER NOT NULL,
    cycles          INTEGER NOT NULL,
    PRIMARY KEY (chunk_name, scenario_id)
);
"""

HLT_BYTE = 0xF0


def ensure_schema(conn):
    conn.executescript(LAB_SCHEMA)
    conn.commit()


# ------------------------------------------------------------------
# Internal: build a fresh isolated CPU substrate
# ------------------------------------------------------------------
def _fresh_lab_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


# ------------------------------------------------------------------
# Single ephemeral run
# ------------------------------------------------------------------
def run_chunk(conn, chunk_name, params=None, initial_a=0, initial_b=0,
              initial_ram=None, max_cycles=64):
    """
    Execute one chunk in isolation and return a delta dict.

    `conn` is the working DB (where the chunk catalog lives — it's read
    from but never written to by this function).
    """
    params      = params or {}
    initial_ram = initial_ram or {}

    # 1. expand chunk body via the catalog
    flat = expand_chunk(chunk_name, params, conn)

    # 2. assemble + append HLT so the chunk always terminates if reached
    program_bytes = assemble(flat, conn) + [HLT_BYTE]
    if len(program_bytes) > 16:
        raise ValueError(
            f"chunk {chunk_name!r} + HLT = {len(program_bytes)} bytes, exceeds 16 RAM cells"
        )

    # 3. fresh substrate, fresh CPU
    lab = _fresh_lab_conn()

    # 4. seed initial RAM:
    #    zero everywhere → caller's initial_ram → program bytes (low addrs win)
    full_initial = {addr: 0 for addr in range(16)}
    for addr, val in initial_ram.items():
        if not (0 <= addr <= 15):
            raise ValueError(f"initial_ram address {addr} out of range 0..15")
        full_initial[addr] = val & 0xFF
    for addr, val in enumerate(program_bytes):
        full_initial[addr] = val & 0xFF

    lab.execute("DELETE FROM ram")
    for addr, val in full_initial.items():
        lab.execute("INSERT INTO ram(addr, value) VALUES (?, ?)", (addr, val))
    lab.commit()

    # 5. set initial register state, run
    cpu = CPU(lab)
    cpu.a = initial_a & 0xFF
    cpu.b = initial_b & 0xFF
    cpu.run(max_cycles=max_cycles)

    # 6. compute deltas
    final_ram = {r["addr"]: r["value"]
                 for r in lab.execute("SELECT addr, value FROM ram")}
    ram_writes = {addr: final_ram[addr]
                  for addr in range(16)
                  if final_ram[addr] != full_initial[addr]}
    lab.close()

    return {
        "chunk_name":  chunk_name,
        "params":      dict(params),
        "initial_a":   initial_a & 0xFF,
        "initial_b":   initial_b & 0xFF,
        "initial_ram": dict(initial_ram),
        "output_a":    cpu.a,
        "output_b":    cpu.b,
        "output_out":  cpu.out,
        "ram_writes":  ram_writes,
        "halted":      bool(cpu.halted),
        "cycles":      cpu.cycle,
    }


# ------------------------------------------------------------------
# Persisted fingerprints across multiple scenarios
# ------------------------------------------------------------------
def fingerprint_chunk(conn, chunk_name, scenarios, params=None):
    """
    Run a chunk across `scenarios` (list of dicts) and persist results
    in chunk_fingerprint.  Returns the list of result dicts.

    Each scenario may carry: scenario_id, initial_a, initial_b,
    initial_ram, params (overrides the function-level `params`).
    """
    ensure_schema(conn)
    out = []
    for i, scen in enumerate(scenarios):
        scen_id     = scen.get("scenario_id", f"s{i}")
        scen_params = scen.get("params", params)
        r = run_chunk(
            conn, chunk_name,
            params      = scen_params,
            initial_a   = scen.get("initial_a", 0),
            initial_b   = scen.get("initial_b", 0),
            initial_ram = scen.get("initial_ram"),
        )
        conn.execute(
            """INSERT OR REPLACE INTO chunk_fingerprint
                 (chunk_name, scenario_id,
                  input_a, input_b, input_ram_json, params_json,
                  output_a, output_b, output_out, ram_writes_json,
                  halted, cycles)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                chunk_name, scen_id,
                r["input_a"] if "input_a" in r else r["initial_a"],
                r["input_b"] if "input_b" in r else r["initial_b"],
                json.dumps(r["initial_ram"]),
                json.dumps(r["params"]),
                r["output_a"], r["output_b"], r["output_out"],
                json.dumps(r["ram_writes"]),
                int(r["halted"]),
                r["cycles"],
            ),
        )
        out.append(r)
    conn.commit()
    return out


# ------------------------------------------------------------------
# Convenience: fingerprint every chunk in the catalog with a default scenario
# ------------------------------------------------------------------
def fingerprint_all(conn, default_scenarios=None):
    """Apply a single scenario list to every chunk in the catalog."""
    ensure_schema(conn)
    default_scenarios = default_scenarios or [{"scenario_id": "default"}]
    rows = conn.execute("SELECT name, params FROM chunks").fetchall()
    for r in rows:
        try:
            params = {p: 0 for p in json.loads(r["params"] or "[]")}
            scens = [{**s, "params": s.get("params") or params}
                     for s in default_scenarios]
            fingerprint_chunk(conn, r["name"], scens)
        except Exception as e:
            # Surface as a dedicated row so consumers can see the failure
            conn.execute(
                """INSERT OR REPLACE INTO chunk_fingerprint
                     (chunk_name, scenario_id,
                      input_a, input_b, input_ram_json, params_json,
                      output_a, output_b, output_out, ram_writes_json,
                      halted, cycles)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (r["name"], "ERROR", 0, 0, "{}", "{}",
                 0, 0, 0, json.dumps({"error": str(e)}), 0, 0),
            )
    conn.commit()
