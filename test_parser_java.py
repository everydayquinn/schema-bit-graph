"""
test_parser_java.py — verification suite for parser_java's source-level facts.

Indexes parser_probe/{Probe,Counter,Edge}.java into a fresh DB and asserts
hand-computed expected fact tables per method. The probe was built during
session 3's adversarial audit; promoting it into the repo (with these
checked-in expectations) protects the next parser_java edit from silently
regressing the cases the audit covered.

Cases the probe pins:
  - Constructor field writes (Probe.Probe)
  - Compound assignment is read+write (Probe.compoundOps)
  - Param/local shadowing suppresses bare-name field reads/writes
    (Probe.shadowParam, Probe.shadowLocal)
  - Qualifier-head field reads (Probe.readsViaQualifier)
  - Static-call qualifier is not a field read (Probe.staticReads)
  - Mixed read+write within an expression (Probe.mixedRW)
  - Self-recursion produces a self CALLED_BY edge (Probe.selfRecurse)
  - ++/-- on a field emit BOTH READS_FIELD and WRITES_FIELD
    (Edge.postfixField — the bug session 3 caught)
  - Flat-shadow pre-pass sweeps the whole method body, so a local
    declared after a use still shadows the field (Edge.usedThenDeclared)
  - Simple-name CALLED_BY ambiguity skips the edge rather than emitting
    false positives (Counter.value / Edge.value clash)

Each test records: name, claim, expected, actual, pass/fail.
Results print AND write to PARSER_JAVA_TEST_REPORT.md.
"""
from __future__ import annotations

import sqlite3
import traceback
from datetime import datetime
from pathlib import Path

import corkboard as cb
import parser_java


HERE     = Path(__file__).parent
PROBE    = HERE / "parser_probe"
TEST_DB  = HERE / "test_parser_java.db"
REPORT   = HERE / "PARSER_JAVA_TEST_REPORT.md"


# ------------------------------------------------------------------
# fixtures
# ------------------------------------------------------------------
def fresh_indexed_db() -> sqlite3.Connection:
    """Wipe TEST_DB, bootstrap, and run parser_java over the probe dir."""
    if TEST_DB.exists():
        TEST_DB.unlink()
    conn = cb.bootstrap(TEST_DB)
    parser_java.bootstrap_vocab(conn)
    for f in sorted(PROBE.glob("*.java")):
        parser_java.index_file(conn, f, HERE)
    conn.commit()
    parser_java.derive_called_by(conn)
    conn.commit()
    return conn


# ------------------------------------------------------------------
# query helpers
# ------------------------------------------------------------------
def field_set(conn, predicate: str, method_subj: str) -> set[str]:
    """Return the set of bare field names a method emits for the given
    predicate (READS_FIELD / WRITES_FIELD). Strips 'field:Class.' prefix."""
    rows = conn.execute(
        "SELECT object FROM v_facts_live "
        "WHERE traveler='parser_java' AND predicate=? AND subject=?",
        (predicate, method_subj),
    ).fetchall()
    out = set()
    for r in rows:
        obj = r["object"]
        # 'field:Class.name' -> 'name'
        out.add(obj.rsplit(".", 1)[-1])
    return out


def calls_set(conn, method_subj: str) -> set[str]:
    return {r["object"] for r in conn.execute(
        "SELECT object FROM v_facts_live "
        "WHERE traveler='parser_java' AND predicate='CALLS' AND subject=?",
        (method_subj,),
    )}


def called_by_set(conn, method_subj: str) -> set[str]:
    return {r["object"] for r in conn.execute(
        "SELECT object FROM v_facts_live "
        "WHERE traveler='parser_java' AND predicate='CALLED_BY' AND subject=?",
        (method_subj,),
    )}


# ------------------------------------------------------------------
# test registry (mirrors test_corkboard.py)
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
# LAYER 1 — per-method READS_FIELD / WRITES_FIELD expected tables
# ==================================================================
def field_rw_checks(conn):
    print("\n[per-method READS_FIELD / WRITES_FIELD]")

    # Each row: (method_subject, expected_writes, expected_reads, claim)
    cases = [
        ("method:Probe.Probe", {"a", "b"}, set(),
         "ctor: this.a=1; b=2 -> writes {a,b}, no reads"),
        ("method:Probe.compoundOps", {"a", "b", "c"}, {"a", "b", "c"},
         "compound assignments (+=, -=) emit both read and write"),
        ("method:Probe.shadowParam", {"x"}, set(),
         "param x shadows field x: bare x=... is a param assignment, not a "
         "field write/read; only this.x=x writes the field"),
        ("method:Probe.shadowLocal", {"x"}, set(),
         "local x shadows field x: bare x=... is a local assignment; only "
         "this.x=x writes the field"),
        ("method:Probe.readsViaQualifier", set(), {"counter"},
         "counter.increment() and counter.value() each read field counter"),
        ("method:Probe.staticReads", set(), set(),
         "Probe.staticThing() and System.out.println() — neither qualifier "
         "head ('Probe', 'System') is a field, so no field reads"),
        ("method:Probe.mixedRW", {"a", "y"}, {"a", "b", "c", "y"},
         "a = a+b*c; y = this.y*2 -> writes {a,y}, reads {a,b,c,y}"),
        ("method:Probe.selfRecurse", set(), set(),
         "selfRecurse() — bare call, no field reads/writes"),
        ("method:Probe.staticThing", set(), set(),
         "static method body 'return 0;' — no field facts"),
        ("method:Counter.increment", {"n"}, {"n"},
         "n = n + 1 — write n, read n"),
        ("method:Counter.value", set(), {"n"},
         "return this.n — read n only"),
        ("method:Edge.value", set(), {"counter"},
         "return this.counter — read counter only"),
        ("method:Edge.usesValue", set(), set(),
         "Counter c = new Counter(); c.value(); — c is a local, not a "
         "field of Edge, so no field reads"),
        ("method:Edge.postfixField", {"n"}, {"n"},
         "n++; ++n; this.n++; --this.n; — every form emits both READ and "
         "WRITE on field n (regression: this was the session-3 bug)"),
        ("method:Edge.usedThenDeclared", set(), set(),
         "counter=99 BEFORE 'int counter=7' — flat shadow pre-pass sweeps "
         "the whole body, so the field write is suppressed (regression: "
         "documents that the shadow pre-pass is intentionally flat, not "
         "scope-aware)"),
    ]

    for msubj, exp_w, exp_r, claim in cases:
        # bind loop vars into closure
        def fn(_m=msubj, _w=exp_w, _r=exp_r):
            actual_w = field_set(conn, "WRITES_FIELD", _m)
            actual_r = field_set(conn, "READS_FIELD",  _m)
            return (_w, _r), (actual_w, actual_r)
        run(f"{msubj}: WRITES/READS_FIELD",
            claim, fn)


# ==================================================================
# LAYER 2 — CALLS edges per method
# ==================================================================
def calls_checks(conn):
    print("\n[per-method CALLS]")

    cases = [
        ("method:Probe.readsViaQualifier",
         {"counter.increment", "counter.value"},
         "MethodInvocation targets are emitted with qualifier dot member"),
        ("method:Probe.staticReads",
         {"Probe.staticThing", "System.out.println"},
         "static / qualified calls preserve the qualifier in the CALLS string"),
        ("method:Probe.selfRecurse",
         {"selfRecurse"},
         "bare call: target is just the simple name"),
        ("method:Edge.usesValue",
         {"c.value"},
         "local-qualified call: c.value emitted even though c is a local"),
    ]

    for msubj, exp, claim in cases:
        def fn(_m=msubj, _e=exp):
            return _e, calls_set(conn, _m)
        run(f"{msubj}: CALLS",
            claim, fn)


# ==================================================================
# LAYER 3 — CALLED_BY (post-pass)
# ==================================================================
def called_by_checks(conn):
    print("\n[CALLED_BY post-pass]")

    # Positive edges: simple name resolves to exactly one method def
    def t_increment_called_by():
        return ({"method:Probe.readsViaQualifier"},
                called_by_set(conn, "method:Counter.increment"))
    run("method:Counter.increment: CALLED_BY",
        "simple name 'increment' is unambiguous (only Counter.increment); "
        "Probe.readsViaQualifier calls counter.increment() so the edge fires",
        t_increment_called_by)

    def t_self_recurse_called_by():
        return ({"method:Probe.selfRecurse"},
                called_by_set(conn, "method:Probe.selfRecurse"))
    run("method:Probe.selfRecurse: CALLED_BY (self)",
        "self-recursive call resolves and emits a self-edge",
        t_self_recurse_called_by)

    def t_static_thing_called_by():
        return ({"method:Probe.staticReads"},
                called_by_set(conn, "method:Probe.staticThing"))
    run("method:Probe.staticThing: CALLED_BY",
        "qualified call 'Probe.staticThing' resolves by simple name "
        "'staticThing' (unambiguous in this corpus)",
        t_static_thing_called_by)

    # NEGATIVE edges: ambiguous simple names skip rather than fire
    def t_counter_value_no_edge():
        # 'value' is ambiguous (Counter.value AND Edge.value), so the
        # current simple-name policy emits NO edge. This is the
        # non-monotonicity limitation captured in session 3 — the test
        # documents the current behavior so step 3 of the next plan
        # (type-driven CALLED_BY) can flip this to a positive assertion.
        return (set(), called_by_set(conn, "method:Counter.value"))
    run("method:Counter.value: CALLED_BY (ambiguous -> no edge)",
        "with both Counter.value and Edge.value present, simple name "
        "'value' is ambiguous; current policy skips. Documents the "
        "limitation that the type-driven CALLED_BY rewrite will fix.",
        t_counter_value_no_edge)

    def t_edge_value_no_edge():
        return (set(), called_by_set(conn, "method:Edge.value"))
    run("method:Edge.value: CALLED_BY (ambiguous -> no edge)",
        "same ambiguity; Edge.value gets no inbound CALLED_BY either",
        t_edge_value_no_edge)

    # Total CALLED_BY edges across the whole probe
    def t_total_called_by():
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM v_facts_live "
            "WHERE traveler='parser_java' AND predicate='CALLED_BY'"
        ).fetchone()["c"]
        return 3, n
    run("CALLED_BY: total edges across the probe",
        "exactly 3 edges (Counter.increment<-Probe.readsViaQualifier, "
        "Probe.selfRecurse<-Probe.selfRecurse, "
        "Probe.staticThing<-Probe.staticReads)",
        t_total_called_by)


# ==================================================================
# LAYER 4 — sanity / structural checks
# ==================================================================
def structural_checks(conn):
    print("\n[structural sanity]")

    # Every method definition has BELONGS_TO its class
    def t_methods_belong():
        rows = list(conn.execute(
            "SELECT subject FROM v_facts_live "
            "WHERE traveler='parser_java' AND predicate='BELONGS_TO' "
            "AND subject GLOB 'method:*'"
        ))
        # Probe: Probe, compoundOps, shadowParam, shadowLocal,
        #   readsViaQualifier, staticReads, mixedRW, selfRecurse, staticThing (9)
        # Counter: increment, value (2)
        # Edge: value, usesValue, postfixField, usedThenDeclared (4)
        # Patterns: getX, getY, getFlag, negX, notFlag, negY, setX, setNegX (8)
        # = 9 + 2 + 4 + 8 = 23
        return 23, len(rows)
    run("structural: BELONGS_TO edge for every method definition",
        "23 method definitions total across Probe/Counter/Edge/Patterns",
        t_methods_belong)

    # Every field has a HAS_TYPE
    def t_fields_typed():
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM v_facts_live "
            "WHERE traveler='parser_java' AND predicate='HAS_TYPE' "
            "AND subject GLOB 'field:*'"
        ).fetchone()["c"]
        # Probe: a, b, c, x, y, counter (6)
        # Counter: n (1)
        # Edge: counter, n (2)
        # Patterns: x, y, flag (3)
        # = 6 + 1 + 2 + 3 = 12
        return 12, n
    run("structural: every field has HAS_TYPE",
        "12 fields total across the probe",
        t_fields_typed)

    # Probe.shadowParam declares its param 'x' (HAS_PARAM, HAS_TYPE int)
    def t_shadow_param_param():
        rows = list(conn.execute(
            "SELECT object FROM v_facts_live "
            "WHERE traveler='parser_java' AND predicate='HAS_PARAM' "
            "AND subject='method:Probe.shadowParam'"
        ))
        return ["param:Probe.shadowParam.x"], [r["object"] for r in rows]
    run("structural: Probe.shadowParam HAS_PARAM param:Probe.shadowParam.x",
        "shadowing test relies on the param subject existing",
        t_shadow_param_param)


# ==================================================================
# REPORT
# ==================================================================
def write_report():
    n = len(RESULTS)
    p = sum(1 for r in RESULTS if r["ok"])
    f = n - p
    lines = [
        "# parser_java test report",
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
    field_rw_checks(conn)
    calls_checks(conn)
    called_by_checks(conn)
    structural_checks(conn)
    conn.close()
    ok = write_report()
    raise SystemExit(0 if ok else 1)
