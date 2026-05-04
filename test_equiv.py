"""
Tests for equiv.py — slice 6.

Verification: exact-match.  If two chunks should be equivalent, the
equivalence row appears.  If they shouldn't, it doesn't.
"""

import sqlite3
import traceback
from datetime import datetime
from pathlib import Path

from compose import insert_chunk, ensure_schema as ensure_chunks_schema
from chunk_lab import ensure_schema as ensure_lab_schema
from equiv   import find_equivalent, ensure_schema as ensure_equiv_schema

HERE       = Path(__file__).parent
SCHEMA_SQL = (HERE / "schema.sql").read_text()
TEST_DB    = HERE / "test_equiv.db"
REPORT     = HERE / "EQUIV_TEST_REPORT.md"


def fresh_db():
    if TEST_DB.exists():
        TEST_DB.unlink()
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    ensure_chunks_schema(conn)
    ensure_lab_schema(conn)
    ensure_equiv_schema(conn)
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
    print("[equiv.py tests]")

    # ---- 1. identical bodies, different names: equivalent --------
    def t_identical_bodies():
        conn = fresh_db()
        insert_chunk(conn, "alpha", [('LDA', 14)])
        insert_chunk(conn, "beta",  [('LDA', 14)])
        inserted = find_equivalent(conn)
        return [("alpha","beta")], [(r["chunk_a"], r["chunk_b"]) for r in inserted]
    run("identical bodies: two chunks with same body are equivalent",
        "the lab confirms outputs match across all default scenarios",
        t_identical_bodies)

    # ---- 2. NOP-padded body: still equivalent --------------------
    def t_nop_padded():
        conn = fresh_db()
        insert_chunk(conn, "plain",   [('LDA', 14)])
        insert_chunk(conn, "padded",  [('LDA', 14), ('NOP', 0)])
        insert_chunk(conn, "padded2", [('LDA', 14), ('NOP', 0), ('NOP', 0)])
        inserted = find_equivalent(conn)
        # all three are pairwise equivalent: 3 pairs total
        names = sorted(tuple(sorted((r["chunk_a"], r["chunk_b"]))) for r in inserted)
        expected = [("padded","padded2"), ("padded","plain"), ("padded2","plain")]
        return sorted(expected), names
    run("nop padding: chunks differing only in trailing NOPs are equivalent",
        "NOP doesn't change observable state, so padded variants match the original",
        t_nop_padded)

    # ---- 3. genuinely different chunks: NOT equivalent -----------
    def t_distinct():
        conn = fresh_db()
        insert_chunk(conn, "load_a",  [('LDA', 14)])
        insert_chunk(conn, "load_b",  [('LDA', 15)])  # loads from different addr
        inserted = find_equivalent(conn)
        return [], inserted
    run("distinct: chunks loading different addresses are not equivalent",
        "scenarios with different mem[14] vs mem[15] catch the difference",
        t_distinct)

    # ---- 4. a chunk that writes vs one that doesn't -------------
    def t_write_vs_no_write():
        conn = fresh_db()
        insert_chunk(conn, "load_only",
                     [('LDA', 14)])
        insert_chunk(conn, "load_and_store",
                     [('LDA', 14), ('STA', 10)])
        inserted = find_equivalent(conn)
        return [], inserted
    run("side-effect: chunk with STA is not equivalent to one without",
        "the STA chunk shows ram_writes, the other doesn't",
        t_write_vs_no_write)

    # ---- 5. confidence equals number of scenarios -----------------
    def t_confidence():
        conn = fresh_db()
        insert_chunk(conn, "x", [('LDA', 14)])
        insert_chunk(conn, "y", [('LDA', 14)])
        inserted = find_equivalent(conn)
        # default scenarios are 3
        return 3, inserted[0]["confidence"]
    run("confidence: matches the number of scenarios that agreed",
        "the count is the number of scenarios run, not 1",
        t_confidence)

    # ---- 6. idempotent ------------------------------------------
    def t_idempotent():
        conn = fresh_db()
        insert_chunk(conn, "x", [('LDA', 14)])
        insert_chunk(conn, "y", [('LDA', 14)])
        first  = find_equivalent(conn)
        second = find_equivalent(conn)
        n = conn.execute("SELECT COUNT(*) c FROM chunk_equivalence").fetchone()["c"]
        return (1, [], 1), (len(first), second, n)
    run("idempotent: re-running find_equivalent produces no duplicates",
        "INSERT-or-skip on (chunk_a, chunk_b) keeps the table stable",
        t_idempotent)

    # ---- 7. ordered pairs only (a < b) -------------------------
    def t_ordering():
        conn = fresh_db()
        insert_chunk(conn, "z_chunk", [('LDA', 14)])
        insert_chunk(conn, "a_chunk", [('LDA', 14)])
        inserted = find_equivalent(conn)
        # pair must be (a_chunk, z_chunk), not (z_chunk, a_chunk)
        return ("a_chunk", "z_chunk"), (inserted[0]["chunk_a"], inserted[0]["chunk_b"])
    run("ordering: equivalence pairs are stored as (lex_smaller, lex_larger)",
        "no duplicate (b,a) row when (a,b) is already present",
        t_ordering)


# ==================================================================
def write_report():
    n = len(RESULTS); p = sum(1 for r in RESULTS if r["ok"]); f = n - p
    lines = [
        f"# equiv.py test report  (slice 6)",
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
