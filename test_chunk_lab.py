"""
Tests for chunk_lab.py — slice 4.

Verification: exact-match on observable outputs (output_a, output_b,
output_out, ram_writes, halted, cycles).  No fuzzy semantics.
"""

import sqlite3
import traceback
from datetime import datetime
from pathlib import Path

from compose    import insert_chunk, ensure_schema as ensure_chunks_schema
from cpu        import CPU
from mirror     import rebuild as mirror_rebuild
from miner      import mine, _name_for as miner_name_for
from chunk_lab  import run_chunk, fingerprint_chunk, ensure_schema as ensure_lab_schema

HERE       = Path(__file__).parent
SCHEMA_SQL = (HERE / "schema.sql").read_text()
TEST_DB    = HERE / "test_chunk_lab.db"
REPORT     = HERE / "CHUNK_LAB_TEST_REPORT.md"


def fresh_db():
    if TEST_DB.exists():
        TEST_DB.unlink()
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    ensure_chunks_schema(conn)
    ensure_lab_schema(conn)
    conn.commit()
    return conn


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
    print("[chunk_lab.py tests]")
    conn = fresh_db()

    # Seed chunks the lab will exercise
    insert_chunk(conn, "load",
                 [('LDA', '$addr')], params=['addr'])
    insert_chunk(conn, "add_two",
                 [('LDA', '$a'), ('ADD', '$b')], params=['a','b'])
    insert_chunk(conn, "load_store",
                 [('LDA', '$src'), ('STA', '$dst')], params=['src','dst'])
    insert_chunk(conn, "just_halt",
                 [('HLT', 0)])
    insert_chunk(conn, "infinite",
                 [('JMP', 0)])
    insert_chunk(conn, "to_output",
                 [('LDA', '$src'), ('OUT', 0)], params=['src'])

    # ---- 1. load chunk: A receives RAM value -------------------
    def t_load():
        r = run_chunk(conn, "load", params={"addr": 14},
                      initial_ram={14: 5})
        return (5, True), (r["output_a"], r["halted"])
    run("load: A <- mem[$addr]",
        "after running ('LDA', $addr) the A register equals mem[$addr]",
        t_load)

    # ---- 2. add_two chunk: A = mem[a] + mem[b] -----------------
    def t_add_two():
        r = run_chunk(conn, "add_two",
                      params={"a": 14, "b": 15},
                      initial_ram={14: 3, 15: 4})
        return (7, True, {}), (r["output_a"], r["halted"], r["ram_writes"])
    run("add_two: A <- mem[$a] + mem[$b], no RAM writes",
        "two-step chunk produces the expected accumulator value with no side-effects on RAM",
        t_add_two)

    # ---- 3. load_store: ram_writes captures the change ---------
    def t_load_store():
        r = run_chunk(conn, "load_store",
                      params={"src": 14, "dst": 10},
                      initial_ram={14: 99})
        return ({10: 99}, 99), (r["ram_writes"], r["output_a"])
    run("load_store: STA writes appear in ram_writes",
        "STA $dst causes mem[$dst] to update; lab records it as a delta",
        t_load_store)

    # ---- 4. just_halt: zero side effects regardless of inputs --
    def t_halt_clean():
        r = run_chunk(conn, "just_halt",
                      initial_a=42, initial_b=99,
                      initial_ram={5: 7})
        return (42, 99, 0, {}, True), (
            r["output_a"], r["output_b"], r["output_out"],
            r["ram_writes"], r["halted"],
        )
    run("just_halt: chunk that only halts has zero state changes",
        "a body of [(HLT,)] preserves all initial registers and RAM",
        t_halt_clean)

    # ---- 5. infinite loop is caught by max_cycles -------------
    def t_infinite():
        r = run_chunk(conn, "infinite", max_cycles=10)
        return (False, 10), (r["halted"], r["cycles"])
    run("infinite: JMP-to-self is bounded by max_cycles",
        "the lab does not hang on a non-halting chunk",
        t_infinite)

    # ---- 6. to_output: OUT register receives a value ----------
    def t_to_output():
        r = run_chunk(conn, "to_output",
                      params={"src": 12},
                      initial_ram={12: 13})
        return 13, r["output_out"]
    run("to_output: OUT <- A after LDA + OUT",
        "OUT register receives the accumulator value when 'OUT' fires",
        t_to_output)

    # ---- 7. determinism: same inputs -> identical fingerprint -
    def t_determinism():
        r1 = run_chunk(conn, "add_two",
                       params={"a": 14, "b": 15},
                       initial_ram={14: 3, 15: 4})
        r2 = run_chunk(conn, "add_two",
                       params={"a": 14, "b": 15},
                       initial_ram={14: 3, 15: 4})
        keep = lambda d: {k: d[k] for k in
                          ("output_a","output_b","output_out",
                           "ram_writes","halted","cycles")}
        return keep(r1), keep(r2)
    run("determinism: identical inputs -> identical outputs",
        "lab is a pure function of (chunk, params, initial state)",
        t_determinism)

    # ---- 8. isolation: lab does not pollute the working DB ----
    def t_isolation():
        # capture working-DB ram BEFORE lab runs
        before = sorted(
            (r["addr"], r["value"]) for r in
            conn.execute("SELECT addr, value FROM ram"))
        run_chunk(conn, "load_store",
                  params={"src": 14, "dst": 10},
                  initial_ram={14: 99})
        after = sorted(
            (r["addr"], r["value"]) for r in
            conn.execute("SELECT addr, value FROM ram"))
        return before, after
    run("isolation: working DB ram is unchanged after lab run",
        "lab uses an in-memory substrate; user catalog/state untouched",
        t_isolation)

    # ---- 9. fingerprint persistence ---------------------------
    def t_persist():
        scenarios = [
            {"scenario_id":"a", "initial_ram":{14:3, 15:4},
             "params":{"a":14,"b":15}},
            {"scenario_id":"b", "initial_ram":{14:5, 15:6},
             "params":{"a":14,"b":15}},
        ]
        fingerprint_chunk(conn, "add_two", scenarios)
        rows = conn.execute(
            "SELECT scenario_id, output_a FROM chunk_fingerprint "
            "WHERE chunk_name='add_two' ORDER BY scenario_id"
        ).fetchall()
        return [("a", 7), ("b", 11)], [(r["scenario_id"], r["output_a"]) for r in rows]
    run("persistence: fingerprint_chunk writes rows we can query back",
        "chunk_fingerprint table receives one row per scenario with correct outputs",
        t_persist)

    # ---- 10. mined chunk has the same fingerprint as a hand
    #          chunk with the same body ---------------------------
    def t_mined_matches_handwritten():
        # Use an in-memory DB so we don't disturb the shared test_chunk_lab.db
        # that later tests still depend on.
        conn2 = sqlite3.connect(":memory:")
        conn2.row_factory = sqlite3.Row
        conn2.executescript(SCHEMA_SQL)
        ensure_chunks_schema(conn2)
        ensure_lab_schema(conn2)
        insert_chunk(conn2, "literal_la_a",
                     [('LDA', 14), ('ADD', 15)])
        # build trace
        conn2.execute("DELETE FROM ram")
        prog = [0x1E,0x2F,0x1E,0x2F,0x60,0xF0,0,0,0,0,0,0,0,0,3,4]
        for addr,val in enumerate(prog):
            conn2.execute("INSERT INTO ram(addr,value) VALUES (?,?)", (addr,val))
        conn2.commit()
        cpu = CPU(conn2); cpu.run()
        mirror_rebuild(conn2)
        mine(conn2)

        mined_name = miner_name_for([('LDA',14),('ADD',15)])

        scenario = {"initial_ram":{14:3, 15:4}}
        # hand-written chunk runs same body
        rh = run_chunk(conn2, "literal_la_a",
                       initial_ram=scenario["initial_ram"])
        rm = run_chunk(conn2, mined_name,
                       initial_ram=scenario["initial_ram"])
        keep = lambda d: (d["output_a"], d["output_b"], d["output_out"],
                          d["ram_writes"], d["halted"])
        return keep(rh), keep(rm)
    run("equivalence: mined and hand-written chunks with same body share a fingerprint",
        "the lab confirms that a mined sequence behaves identically to its hand-coded twin",
        t_mined_matches_handwritten)

    # ---- 11. error: chunk + HLT > 16 bytes is rejected --------
    def t_oversize():
        # 16 instructions of NOP would be 16 bytes; +HLT = 17 bytes
        big = [('NOP', 0)] * 16
        insert_chunk(conn, "too_big", big)
        try:
            run_chunk(conn, "too_big")
            return ("raised","ValueError"), ("did not raise","")
        except ValueError:
            return ("raised","ValueError"), ("raised","ValueError")
    run("error: chunk too big for RAM is rejected",
        "lab refuses chunks whose bytes + HLT exceed 16 RAM cells",
        t_oversize)

    # ---- 12. error: missing param surfaces from compose -------
    def t_missing_param():
        try:
            run_chunk(conn, "add_two", params={"a": 14})  # missing b
            return ("raised","ValueError"), ("did not raise","")
        except ValueError:
            return ("raised","ValueError"), ("raised","ValueError")
    run("error: missing chunk param raises ValueError",
        "compose's missing-param error propagates cleanly through the lab",
        t_missing_param)

    conn.close()


# ==================================================================
def write_report():
    n = len(RESULTS); p = sum(1 for r in RESULTS if r["ok"]); f = n - p
    lines = [
        f"# chunk_lab.py test report  (slice 4)",
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
