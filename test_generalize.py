"""
Tests for generalize.py — slice 5.

Two layers of verification:
  1. byte-exact:   compose(generalized_chunk, original_operands)
                   == bytes from the original literal chunk
  2. behavioral:   lab fingerprint of generalized chunk with the original
                   operands matches the lab fingerprint of the literal original
"""

import sqlite3
import traceback
from datetime import datetime
from pathlib import Path

from compose    import compose, insert_chunk, ensure_schema as ensure_chunks_schema
from chunk_lab  import run_chunk, ensure_schema as ensure_lab_schema
from generalize import generalize, _name_for as gen_name_for

HERE       = Path(__file__).parent
SCHEMA_SQL = (HERE / "schema.sql").read_text()
TEST_DB    = HERE / "test_generalize.db"
REPORT     = HERE / "GENERALIZE_TEST_REPORT.md"


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
    print("[generalize.py tests]")

    # ---- 1. empty catalog -> nothing produced -------------------
    def t_empty():
        conn = fresh_db()
        return [], generalize(conn)
    run("empty: no literal chunks -> no generalizations",
        "generalize is a no-op on an empty catalog",
        t_empty)

    # ---- 2. one literal chunk -> nothing ------------------------
    def t_solo():
        conn = fresh_db()
        insert_chunk(conn, "solo_a",
                     [('LDA', 14), ('ADD', 15)])
        return [], generalize(conn)
    run("singleton: a lone literal chunk is not generalized",
        "min_group_size of 2 prevents one-of-a-kind chunks from being abstracted",
        t_solo)

    # ---- 3. two identical literal chunks -> nothing -------------
    def t_identical():
        conn = fresh_db()
        insert_chunk(conn, "ident_a",
                     [('LDA', 14), ('ADD', 15)])
        insert_chunk(conn, "ident_b",
                     [('LDA', 14), ('ADD', 15)])
        return [], generalize(conn)
    run("identical: two chunks with identical bodies are not generalized",
        "no operand position varies, so there is nothing to parameterize",
        t_identical)

    # ---- 4. two literal chunks with varying operands -> 1 gen --
    def t_one_group():
        conn = fresh_db()
        insert_chunk(conn, "lit_a",
                     [('LDA', 14), ('ADD', 15)])
        insert_chunk(conn, "lit_b",
                     [('LDA',  6), ('ADD',  7)])
        inserted = generalize(conn)
        return (1, ['p0','p1']), (len(inserted), inserted[0]["params"])
    run("group: two members differing in both operands -> one generalized chunk",
        "(LDA 14, ADD 15) and (LDA 6, ADD 7) collapse to (LDA $p0, ADD $p1)",
        t_one_group)

    # ---- 5. mixed varying / fixed operand positions -------------
    def t_mixed_positions():
        # Both chunks load mem[14] (same operand at pos 0) but ADD different addrs
        conn = fresh_db()
        insert_chunk(conn, "mix_a",
                     [('LDA', 14), ('ADD', 15)])
        insert_chunk(conn, "mix_b",
                     [('LDA', 14), ('ADD',  7)])
        inserted = generalize(conn)
        gen = inserted[0]
        # position 0 should be fixed (both have 14), position 1 should be $p0
        body = gen["body"]
        return (
            ([('LDA', 14), ('ADD', '$p0')], ['p0'], [0], [1]),
            (body, gen["params"], gen["fixed_positions"], gen["varying_positions"]),
        )
    run("mixed: positions that AGREE stay literal, those that DIFFER become $params",
        "agree-on-LDA-operand, differ-on-ADD-operand -> [LDA 14, ADD $p0]",
        t_mixed_positions)

    # ---- 6. byte-exact: gen with original ops produces original bytes
    def t_byte_exact():
        conn = fresh_db()
        insert_chunk(conn, "lit_a",
                     [('LDA', 14), ('ADD', 15)])
        insert_chunk(conn, "lit_b",
                     [('LDA',  6), ('ADD',  7)])
        inserted = generalize(conn)
        gen_name = inserted[0]["name"]

        # bytes of the literal originals
        bytes_a = compose([('lit_a',)], conn)
        bytes_b = compose([('lit_b',)], conn)
        # bytes of the generalized version with each member's params
        bytes_gen_a = compose([(gen_name, {'p0': 14, 'p1': 15})], conn)
        bytes_gen_b = compose([(gen_name, {'p0':  6, 'p1':  7})], conn)
        return (bytes_a, bytes_b), (bytes_gen_a, bytes_gen_b)
    run("byte-exact: generalized chunk reproduces every member's bytes",
        "compose(gen, params=original_operands) == compose(original)",
        t_byte_exact)

    # ---- 7. behavioral: lab fingerprints match -------------------
    def t_behavioral():
        conn = fresh_db()
        insert_chunk(conn, "lit_a",
                     [('LDA', 14), ('ADD', 15)])
        insert_chunk(conn, "lit_b",
                     [('LDA',  6), ('ADD',  7)])
        inserted = generalize(conn)
        gen_name = inserted[0]["name"]

        scenario = {"initial_ram": {14: 3, 15: 4, 6: 8, 7: 9}}

        def fp(d):
            return (d["output_a"], d["output_b"], d["output_out"],
                    d["ram_writes"], d["halted"])

        # original literal chunk vs generalized with matching params
        ra_lit = run_chunk(conn, "lit_a", initial_ram=scenario["initial_ram"])
        ra_gen = run_chunk(conn, gen_name, params={'p0':14,'p1':15},
                           initial_ram=scenario["initial_ram"])
        rb_lit = run_chunk(conn, "lit_b", initial_ram=scenario["initial_ram"])
        rb_gen = run_chunk(conn, gen_name, params={'p0': 6,'p1': 7},
                           initial_ram=scenario["initial_ram"])
        return (fp(ra_lit), fp(rb_lit)), (fp(ra_gen), fp(rb_gen))
    run("behavioral: gen with original params has same fingerprint as original",
        "lab confirms the abstraction preserves the chunk's observable behavior",
        t_behavioral)

    # ---- 8. idempotent ------------------------------------------
    def t_idempotent():
        conn = fresh_db()
        insert_chunk(conn, "lit_a",
                     [('LDA', 14), ('ADD', 15)])
        insert_chunk(conn, "lit_b",
                     [('LDA',  6), ('ADD',  7)])
        first  = generalize(conn)
        second = generalize(conn)
        # second run inserts nothing new; total chunk count unchanged
        n = conn.execute("SELECT COUNT(*) c FROM chunks").fetchone()["c"]
        return (1, [], 3), (len(first), second, n)   # 2 originals + 1 generalized
    run("idempotent: re-running generalize produces no duplicates",
        "deterministic name + insert-if-new keeps the catalog stable",
        t_idempotent)

    # ---- 9. multiple groups in one pass --------------------------
    def t_multi_groups():
        conn = fresh_db()
        # group 1: mnemonic sequence (LDA, ADD)
        insert_chunk(conn, "ga_1", [('LDA', 14), ('ADD', 15)])
        insert_chunk(conn, "ga_2", [('LDA',  6), ('ADD',  7)])
        # group 2: mnemonic sequence (LDA, SUB)
        insert_chunk(conn, "gs_1", [('LDA',  3), ('SUB',  4)])
        insert_chunk(conn, "gs_2", [('LDA',  8), ('SUB',  9)])
        inserted = generalize(conn)
        # one generalized chunk per group
        return 2, len(inserted)
    run("multiple groups: one generalized chunk emitted per mnemonic-sequence group",
        "(LDA,ADD) and (LDA,SUB) groups generalize independently",
        t_multi_groups)

    # ---- 10. group with three members ---------------------------
    def t_three_members():
        conn = fresh_db()
        insert_chunk(conn, "tm_1", [('LDA', 14), ('ADD', 15)])
        insert_chunk(conn, "tm_2", [('LDA',  6), ('ADD',  7)])
        insert_chunk(conn, "tm_3", [('LDA',  1), ('ADD',  2)])
        inserted = generalize(conn)
        gen = inserted[0]
        # all three members listed; both positions parameterized
        return (3, ['p0','p1']), (len(gen["from_members"]), gen["params"])
    run("three members: bigger group still produces one generalized chunk",
        "from_members lists every contributing literal chunk",
        t_three_members)


# ==================================================================
def write_report():
    n = len(RESULTS); p = sum(1 for r in RESULTS if r["ok"]); f = n - p
    lines = [
        f"# generalize.py test report  (slice 5)",
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
