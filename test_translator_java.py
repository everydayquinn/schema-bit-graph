"""
test_translator_java.py — verification suite for translator_java's L2 patterns.

Indexes parser_probe/Patterns.java into a fresh DB and asserts the L2
pattern detector emits the right IS_GETTER_OF / IS_SETTER_OF facts —
including NEGATIVE assertions for the unary-operator cases that the
current detector mis-classifies (Player.isDead-style `return !this.x`,
setter `this.x = -v`).

The negative rows START failing on this file before the translator_java
fix lands, then flip to green once `_is_field_read` and the setter RHS
check reject prefix/postfix operators. That sequence is the contract:
the test captures the bug; the fix makes the test pass.

Each row records: name, claim, expected, actual, pass/fail.
Results print AND write to TRANSLATOR_JAVA_TEST_REPORT.md.
"""
from __future__ import annotations

import sqlite3
import traceback
from datetime import datetime
from pathlib import Path

import corkboard as cb
import parser_java
import translator_java


HERE     = Path(__file__).parent
PROBE    = HERE / "parser_probe"
TEST_DB  = HERE / "test_translator_java.db"
REPORT   = HERE / "TRANSLATOR_JAVA_TEST_REPORT.md"


# ------------------------------------------------------------------
# fixtures
# ------------------------------------------------------------------
def fresh_indexed_db() -> sqlite3.Connection:
    """Fresh DB. Run parser_java to register namespaces and populate the
    structural facts translator_java's L2 emissions reference, then run
    translator_java over the same files."""
    if TEST_DB.exists():
        TEST_DB.unlink()
    conn = cb.bootstrap(TEST_DB)
    parser_java.bootstrap_vocab(conn)
    translator_java.bootstrap_vocab(conn)
    files = sorted(PROBE.glob("*.java"))
    for f in files:
        parser_java.index_file(conn, f, HERE)
    conn.commit()
    parser_java.derive_called_by(conn)
    for f in files:
        translator_java.index_file(conn, f)
    conn.commit()
    return conn


# ------------------------------------------------------------------
# query helpers
# ------------------------------------------------------------------
def getter_field(conn, method_subj: str) -> str | None:
    """Return the bare field name in IS_GETTER_OF for this method, or None
    if no such fact exists. (IS_GETTER_OF is cardinality 'one'.)"""
    row = conn.execute(
        "SELECT object FROM v_facts_live "
        "WHERE traveler='translator_java' AND predicate='IS_GETTER_OF' "
        "AND subject=?",
        (method_subj,),
    ).fetchone()
    if row is None:
        return None
    return row["object"].rsplit(".", 1)[-1]


def setter_field(conn, method_subj: str) -> str | None:
    row = conn.execute(
        "SELECT object FROM v_facts_live "
        "WHERE traveler='translator_java' AND predicate='IS_SETTER_OF' "
        "AND subject=?",
        (method_subj,),
    ).fetchone()
    if row is None:
        return None
    return row["object"].rsplit(".", 1)[-1]


# ------------------------------------------------------------------
# test registry (mirrors test_corkboard.py / test_parser_java.py)
# ------------------------------------------------------------------
RESULTS = []


def record(name, claim, expected, actual, ok, err=None):
    RESULTS.append({"name": name, "claim": claim,
                    "expected": expected, "actual": actual,
                    "ok": ok, "err": err})
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {name}")
    if not ok and err:
        print("        " + err.replace("\n", "\n        "))


def run(name, claim, fn):
    try:
        expected, actual = fn()
        record(name, claim, expected, actual, expected == actual)
    except AssertionError as e:
        record(name, claim, "(assertion)", "(failed)", False, str(e))
    except Exception:
        record(name, claim, "(no exception)", "(exception)", False,
               traceback.format_exc())


# ==================================================================
# LAYER 1 — IS_GETTER_OF positive + negative cases
# ==================================================================
def getter_checks(conn):
    print("\n[IS_GETTER_OF positive + negative]")

    cases_positive = [
        ("method:Patterns.getX", "x",
         "this-form `return this.x;` is a clean getter"),
        ("method:Patterns.getY", "y",
         "bare-form `return y;` is a clean getter"),
        ("method:Patterns.getFlag", "flag",
         "boolean variant `return this.flag;` is a clean getter"),
    ]
    for msubj, exp_field, claim in cases_positive:
        def fn(_m=msubj, _f=exp_field):
            return _f, getter_field(conn, _m)
        run(f"{msubj}: IS_GETTER_OF (positive)", claim, fn)

    cases_negative = [
        ("method:Patterns.negX",
         "`return -this.x;` — prefix '-' on This; the unary operator "
         "negates the value, so this is NOT a getter"),
        ("method:Patterns.notFlag",
         "`return !this.flag;` — prefix '!' on This (the actual "
         "Player.isDead bug from the cwalk corpus); inverts the value, "
         "NOT a getter"),
        ("method:Patterns.negY",
         "`return -y;` — prefix '-' on bare MemberReference; same "
         "rejection rule applies to bare-form returns"),
    ]
    for msubj, claim in cases_negative:
        def fn(_m=msubj):
            return None, getter_field(conn, _m)
        run(f"{msubj}: IS_GETTER_OF (negative — must be absent)",
            claim, fn)


# ==================================================================
# LAYER 2 — IS_SETTER_OF positive + negative cases
# ==================================================================
def setter_checks(conn):
    print("\n[IS_SETTER_OF positive + negative]")

    def t_setX_positive():
        return "x", setter_field(conn, "method:Patterns.setX")
    run("method:Patterns.setX: IS_SETTER_OF (positive)",
        "`this.x = v;` with param `v` is a clean setter",
        t_setX_positive)

    def t_setNegX_negative():
        # `this.x = -v` — RHS prefix '-' on the param; the assignment
        # negates the value, so the method is NOT a pure setter.
        return None, setter_field(conn, "method:Patterns.setNegX")
    run("method:Patterns.setNegX: IS_SETTER_OF (negative — must be absent)",
        "`this.x = -v;` — RHS unary '-' transforms the value before "
        "assignment, so this is NOT a setter equivalent to a direct write",
        t_setNegX_negative)


# ==================================================================
# LAYER 3 — totals + non-Patterns sanity
# ==================================================================
def totals_checks(conn):
    print("\n[totals across Patterns]")

    def t_total_getters_in_patterns():
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM v_facts_live "
            "WHERE traveler='translator_java' AND predicate='IS_GETTER_OF' "
            "AND subject GLOB 'method:Patterns.*'"
        ).fetchone()["c"]
        return 3, n
    run("totals: exactly 3 IS_GETTER_OF in Patterns",
        "3 positives (getX, getY, getFlag); the 3 negatives must NOT fire",
        t_total_getters_in_patterns)

    def t_total_setters_in_patterns():
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM v_facts_live "
            "WHERE traveler='translator_java' AND predicate='IS_SETTER_OF' "
            "AND subject GLOB 'method:Patterns.*'"
        ).fetchone()["c"]
        return 1, n
    run("totals: exactly 1 IS_SETTER_OF in Patterns",
        "1 positive (setX); setNegX must NOT fire",
        t_total_setters_in_patterns)

    # Sanity: translator should still detect Counter.value as a getter
    # of n (return this.n;) — the existing behavior must not regress.
    def t_counter_value_still_getter():
        return "n", getter_field(conn, "method:Counter.value")
    run("regression: Counter.value still detected as IS_GETTER_OF n",
        "the unary fix must not break the plain-getter case the "
        "translator already handled before",
        t_counter_value_still_getter)

    def t_edge_value_still_getter():
        return "counter", getter_field(conn, "method:Edge.value")
    run("regression: Edge.value still detected as IS_GETTER_OF counter",
        "another plain-getter case (this-form) that must keep firing",
        t_edge_value_still_getter)


# ==================================================================
# REPORT
# ==================================================================
def write_report():
    n = len(RESULTS)
    p = sum(1 for r in RESULTS if r["ok"])
    f = n - p
    lines = [
        "# translator_java test report",
        "",
        f"_Generated: {datetime.now().isoformat(timespec='seconds')}_",
        "",
        f"**{p}/{n} passed**" + ("" if f == 0 else f"  &nbsp;|&nbsp;  **{f} FAILED**"),
        "",
        "| # | test | claim | expected | actual | result |",
        "|---|------|-------|----------|--------|--------|",
    ]
    for i, r in enumerate(RESULTS, 1):
        exp = repr(r["expected"]).replace("|", "\\|").replace("\n", "↵")[:240]
        act = repr(r["actual"]).replace("|", "\\|").replace("\n", "↵")[:240]
        lines.append(
            f"| {i} | `{r['name']}` | {r['claim']} | `{exp}` | `{act}` | "
            f"{'PASS' if r['ok'] else '**FAIL**'} |"
        )
    if f:
        lines += ["", "## failures", ""]
        for r in RESULTS:
            if not r["ok"]:
                lines += [f"### {r['name']}", "",
                          f"- expected: `{r['expected']!r}`",
                          f"- actual:   `{r['actual']!r}`",
                          "```", r["err"] or "", "```", ""]
    REPORT.write_text("\n".join(lines) + "\n")
    print(f"\nreport: {REPORT}")
    print(f"summary: {p}/{n} passed" + ("" if f == 0 else f", {f} FAILED"))
    return f == 0


if __name__ == "__main__":
    conn = fresh_indexed_db()
    getter_checks(conn)
    setter_checks(conn)
    totals_checks(conn)
    conn.close()
    ok = write_report()
    raise SystemExit(0 if ok else 1)
