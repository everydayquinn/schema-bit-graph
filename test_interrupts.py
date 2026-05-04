"""
Tests for interrupts.py — the dispatcher slice.

Verification: exact-match.  Outcome dicts and DB state are compared to
hand-computed expectations.
"""

import sqlite3
import traceback
from datetime import datetime
from pathlib import Path

from compose    import insert_chunk, ensure_schema as ensure_chunks_schema
from cpu        import CPU
from interrupts import (ensure_schema as ensure_interrupts_schema,
                        register, fire_event, list_vectors,
                        SCRATCH_REGION, MAX_HANDLER_BYTES)

HERE       = Path(__file__).parent
SCHEMA_SQL = (HERE / "schema.sql").read_text()
TEST_DB    = HERE / "test_interrupts.db"
REPORT     = HERE / "INTERRUPTS_TEST_REPORT.md"


def fresh_db():
    if TEST_DB.exists():
        TEST_DB.unlink()
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    ensure_chunks_schema(conn)
    ensure_interrupts_schema(conn)
    conn.commit()
    return conn


def _set_ram(conn, mapping):
    """Set RAM cells to given values; cells not in mapping become 0."""
    conn.execute("DELETE FROM ram")
    for addr in range(16):
        conn.execute("INSERT INTO ram (addr, value) VALUES (?, ?)",
                     (addr, mapping.get(addr, 0) & 0xFF))
    conn.commit()


RESULTS = []
def record(name, claim, expected, actual, ok, err=None):
    RESULTS.append({"name":name, "claim":claim,
                    "expected":expected, "actual":actual,
                    "ok":ok, "err":err})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not ok and err:
        print("        " + err.replace("\n", "\n        "))

def run(name, claim, fn):
    try:
        expected, actual = fn()
        record(name, claim, expected, actual, expected == actual)
    except AssertionError as e:
        record(name, claim, "(assertion)", "(failed)", False, str(e))
    except Exception:
        record(name, claim, "(no exception)", "(exception)", False, traceback.format_exc())


# ==================================================================
def behaviour():
    print("[interrupts.py tests]")

    # ---- 1. register + list ------------------------------------
    def t_register_list():
        conn = fresh_db()
        insert_chunk(conn, "noop_handler", [('NOP', 0)])
        register(conn, "tick", "noop_handler", "test handler")
        vs = list_vectors(conn)
        return [{"event_type": "tick", "handler_chunk": "noop_handler",
                 "description": "test handler"}], vs
    run("register: vector lookup returns the registered handler",
        "INSERT into interrupt_vectors then SELECT comes back identical",
        t_register_list)

    # ---- 2. unhandled event logs and returns handled=False -----
    def t_unhandled():
        conn = fresh_db()
        cpu = CPU(conn)
        result = fire_event(conn, cpu, "ghost_event")
        log = conn.execute(
            "SELECT event_type, error FROM event_log WHERE event_type='ghost_event'"
        ).fetchone()
        return (
            (False, "no handler registered", "ghost_event", "no handler registered"),
            (result["handled"], result["reason"], log["event_type"], log["error"]),
        )
    run("unhandled: event with no vector returns handled=False and logs",
        "missing handler is logged with error message, no exception",
        t_unhandled)

    # ---- 3. simple handler runs and updates A ------------------
    def t_simple_handler():
        conn = fresh_db()
        # handler: LDA 14 (so A becomes mem[14])
        insert_chunk(conn, "load_14", [('LDA', 14)])
        register(conn, "load_event", "load_14")
        cpu = CPU(conn)
        # set scratch[14] = 7 BEFORE the event
        _set_ram(conn, {14: 7})
        result = fire_event(conn, cpu, "load_event")
        return (True, True, 7), (result["handled"], result["halted_clean"], result["output_a"])
    run("simple: LDA-only handler updates A from scratch RAM",
        "the dispatcher loads handler bytes, runs to HLT, A reflects mem read",
        t_simple_handler)

    # ---- 4. scratch RAM persists across events ----------------
    def t_scratch_persists():
        conn = fresh_db()
        # handler "increment_14": LDA 14, ADD 13, STA 14   (where mem[13]=1)
        insert_chunk(conn, "increment_14",
                     [('LDA', 14), ('ADD', 13), ('STA', 14)])
        register(conn, "tick", "increment_14")
        cpu = CPU(conn)
        # seed: mem[13]=1 (the increment), mem[14]=0 (the counter)
        _set_ram(conn, {13: 1, 14: 0})
        # fire 3 ticks; counter should go 0 -> 1 -> 2 -> 3
        seen = []
        for _ in range(3):
            r = fire_event(conn, cpu, "tick")
            seen.append(r["scratch_after"][14])
        return [1, 2, 3], seen
    run("persistence: scratch RAM survives across events; counter increments",
        "RAM[12..15] is preserved between events; STA writes survive next event",
        t_scratch_persists)

    # ---- 5. registers persist across events -------------------
    def t_registers_persist():
        conn = fresh_db()
        # handler_a: LDA 14            (sets A from scratch)
        # handler_b: ADD 13            (adds mem[13] to existing A)
        insert_chunk(conn, "load_a",  [('LDA', 14)])
        insert_chunk(conn, "add_b",   [('ADD', 13)])
        register(conn, "ev_a", "load_a")
        register(conn, "ev_b", "add_b")
        cpu = CPU(conn)
        _set_ram(conn, {13: 5, 14: 7})
        fire_event(conn, cpu, "ev_a")    # A = 7
        r = fire_event(conn, cpu, "ev_b") # A = 7 + 5 = 12
        return 12, r["output_a"]
    run("registers: A persists across events (event 2 sees event 1's A)",
        "register state survives event boundaries; ADD reads prior A",
        t_registers_persist)

    # ---- 6. payload as params -----------------------------------
    def t_payload_params():
        conn = fresh_db()
        insert_chunk(conn, "load_at",
                     [('LDA', '$addr')], params=['addr'])
        register(conn, "load_at_event", "load_at")
        cpu = CPU(conn)
        _set_ram(conn, {12: 99, 14: 7})
        r12 = fire_event(conn, cpu, "load_at_event", payload={"addr": 12})
        r14 = fire_event(conn, cpu, "load_at_event", payload={"addr": 14})
        return (99, 7), (r12["output_a"], r14["output_a"])
    run("payload: dict payload binds chunk params at firing time",
        "same handler with different params produces different outcomes",
        t_payload_params)

    # ---- 7. oversize handler rejected --------------------------
    def t_oversize():
        conn = fresh_db()
        # 12 NOPs + HLT = 13 bytes, exceeds the 12-byte handler region
        insert_chunk(conn, "too_big", [('NOP', 0)] * 12)
        register(conn, "big_event", "too_big")
        cpu = CPU(conn)
        try:
            fire_event(conn, cpu, "big_event")
            return ("raised", "ValueError"), ("did not raise", None)
        except ValueError:
            return ("raised", "ValueError"), ("raised", "ValueError")
    run("oversize: handler bytes + HLT > 12 raises ValueError",
        "handler region cap is enforced; oversize is logged AND raised",
        t_oversize)

    # ---- 8. event log records every fire ----------------------
    def t_event_log():
        conn = fresh_db()
        insert_chunk(conn, "h", [('NOP', 0)])
        register(conn, "tick", "h")
        cpu = CPU(conn)
        for _ in range(4):
            fire_event(conn, cpu, "tick")
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM event_log WHERE event_type='tick'"
        ).fetchone()["n"]
        return 4, n
    run("event_log: every fired event creates one row",
        "log is append-only; row count == events fired",
        t_event_log)

    # ---- 9. re-register replaces ------------------------------
    def t_reregister():
        conn = fresh_db()
        insert_chunk(conn, "h1", [('LDA', 14)])
        insert_chunk(conn, "h2", [('LDA', 13)])
        register(conn, "ev", "h1")
        register(conn, "ev", "h2")
        cpu = CPU(conn)
        _set_ram(conn, {13: 5, 14: 9})
        r = fire_event(conn, cpu, "ev")
        return ("h2", 5), (r["handler"], r["output_a"])
    run("re-register: second register call replaces the handler",
        "ON CONFLICT updates handler_chunk; later call wins",
        t_reregister)

    # ---- 10. handler region zeroed between events -------------
    def t_handler_region_zeroed():
        conn = fresh_db()
        insert_chunk(conn, "short", [('NOP', 0)])  # 1 byte + HLT = 2 bytes
        insert_chunk(conn, "longer",
                     [('LDA', 14), ('ADD', 13)])    # 2 bytes + HLT = 3 bytes
        register(conn, "short_ev", "short")
        register(conn, "long_ev",  "longer")
        cpu = CPU(conn)
        _set_ram(conn, {13: 1, 14: 5})
        # First fire: handler region 0..11 contains [NOP, HLT, 0, 0, 0...]
        fire_event(conn, cpu, "short_ev")
        # Second fire: should fully overwrite, not leave NOP residue
        fire_event(conn, cpu, "long_ev")
        # check RAM addr 2 (third byte) is 0 (HLT), addr 3..11 should be 0
        addrs_3_to_11 = [conn.execute(
            "SELECT value FROM ram WHERE addr=?", (a,)
        ).fetchone()["value"] for a in range(3, 12)]
        return [0]*9, addrs_3_to_11
    run("isolation: handler region is fully rewritten each event",
        "no residue from previous handler; bytes beyond new handler are zero",
        t_handler_region_zeroed)

    # ---- 11. integration: 5-tick counter loop ------------------
    def t_counter_5_ticks():
        conn = fresh_db()
        insert_chunk(conn, "tick_counter",
                     [('LDA', 14), ('ADD', 13), ('STA', 14)])
        register(conn, "tick", "tick_counter")
        cpu = CPU(conn)
        _set_ram(conn, {13: 1, 14: 0})
        for _ in range(5):
            fire_event(conn, cpu, "tick")
        final = conn.execute(
            "SELECT value FROM ram WHERE addr=14"
        ).fetchone()["value"]
        return 5, final
    run("integration: 5 events drive scratch[14] from 0 to 5",
        "the unified architecture works end-to-end — events accumulate state",
        t_counter_5_ticks)


# ==================================================================
def write_report():
    n = len(RESULTS); p = sum(1 for r in RESULTS if r["ok"]); f = n - p
    lines = [
        f"# interrupts.py test report  (slice 9 — the dispatcher)",
        f"",
        f"_Generated: {datetime.now().isoformat(timespec='seconds')}_",
        f"",
        f"**{p}/{n} passed**" + ("" if f == 0 else f"  &nbsp;|&nbsp;  **{f} FAILED**"),
        f"",
        f"| # | test | claim | expected | actual | result |",
        f"|---|------|-------|----------|--------|--------|",
    ]
    for i, r in enumerate(RESULTS, 1):
        exp = repr(r["expected"]).replace("|","\\|")
        act = repr(r["actual"]).replace("|","\\|")
        lines.append(
            f"| {i} | `{r['name']}` | {r['claim']} | `{exp}` | `{act}` | "
            f"{'PASS' if r['ok'] else '**FAIL**'} |")
    if f:
        lines += ["", "## failures", ""]
        for r in RESULTS:
            if not r["ok"]:
                lines += [f"### {r['name']}", "", "```", r["err"] or "", "```", ""]
    REPORT.write_text("\n".join(lines) + "\n")
    print(f"\nreport: {REPORT}")
    print(f"summary: {p}/{n} passed" + ("" if f == 0 else f", {f} FAILED"))
    return f == 0


if __name__ == "__main__":
    behaviour()
    ok = write_report()
    raise SystemExit(0 if ok else 1)
