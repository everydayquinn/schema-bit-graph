"""
test_corkboard.py — verification suite for the cork-board substrate.

Three layers (matches the project's testing convention from test_cpu.py):
  1. Schema/discipline checks: every constraint and trigger fires correctly
  2. Helper checks: emit/retract/register behave as documented
  3. Substrate-fact checks: cpu_4bit traveler facts match reality on a
     program whose execution we can independently compute.

Each test records: name, claim, expected, actual, pass/fail.
Results print AND write to CORKBOARD_TEST_REPORT.md.
"""
from __future__ import annotations

import json
import os
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path

import corkboard as cb
import cpu_4bit_traveler as t4

HERE       = Path(__file__).parent
TEST_DB    = HERE / "test_corkboard.db"
REPORT     = HERE / "CORKBOARD_TEST_REPORT.md"


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------
def fresh_db() -> sqlite3.Connection:
    if TEST_DB.exists():
        TEST_DB.unlink()
    return cb.bootstrap(TEST_DB)


def seed_minimal(conn):
    """Just enough vocab to run substrate-fact tests (no gameplan)."""
    cb.register_namespace(conn, "test:", "test fixtures", "test:foo")
    cb.register_namespace(conn, "insn:", "instruction-level facts", "insn:demo:0x00")
    cb.register_namespace(conn, "step:", "execution-step facts",   "step:demo:000000")
    cb.register_namespace(conn, "prog:", "program-level facts",     "prog:demo")
    cb.register_predicate(conn, "TEST_ONE", "test", "literal", "one",
                          "single-value test predicate", ["test:x TEST_ONE 5"])
    cb.register_predicate(conn, "TEST_MANY","test", "literal", "many",
                          "multi-value test predicate", ["test:x TEST_MANY a"])
    for name, dom, rng, card, defn, ex in [
        ("AT_INSN",     "step", "ref",     "one",  "step's executed insn", ["step:demo:000000 AT_INSN insn:demo:0x00"]),
        ("AT_ADDRESS",  "insn", "literal", "one",  "insn address",         ["insn:demo:0x00 AT_ADDRESS 0x00"]),
        ("HAS_MNEMONIC","insn", "literal", "one",  "decoded mnemonic",     ["insn:demo:0x00 HAS_MNEMONIC lda"]),
        ("HAS_OPERANDS","insn", "literal", "one",  "operand string",       ["insn:demo:0x00 HAS_OPERANDS 14"]),
        ("HAS_SIZE",    "insn", "literal", "one",  "size in bytes",        ["insn:demo:0x00 HAS_SIZE 1"]),
        ("HAS_BYTES",   "insn", "literal", "one",  "raw bytes hex",        ["insn:demo:0x00 HAS_BYTES 1e"]),
        ("IN_PROGRAM",  "insn", "prog",    "one",  "containing program",   ["insn:demo:0x00 IN_PROGRAM prog:demo"]),
        ("STEP_SEQ",    "step", "literal", "one",  "step sequence",        ["step:demo:000000 STEP_SEQ 000000"]),
        ("DELTA",       "step", "literal", "one",  "register changes",     ["step:demo:000000 DELTA a=0->5"]),
        ("BRANCH",      "step", "literal", "one",  "control-flow",         ["step:demo:000005 BRANCH halt"]),
        ("WRITES_REG",  "step", "literal", "many", "register written",     ["step:demo:000000 WRITES_REG a"]),
        ("HAS_MD5",     "prog", "literal", "one",  "program md5",          ["prog:demo HAS_MD5 abc"]),
        ("INGESTED_AT", "prog", "literal", "one",  "ingest timestamp",     ["prog:demo INGESTED_AT 2026-05-04..."]),
    ]:
        cb.register_predicate(conn, name, dom, rng, card, defn, ex)
    cb.register_traveler(conn, "test_traveler", "fixture",      "meta")
    cb.register_traveler(conn, "cpu_4bit",      "the 4-bit CPU","substrate")
    conn.commit()


# ------------------------------------------------------------------
# test registry
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
        record(name, claim, "(no exception)", "(exception)", False, traceback.format_exc())


def expect_raises(exc_type, fn, *args, **kw):
    """Helper: assert callable raises exc_type. Returns (True, True) on pass."""
    try:
        fn(*args, **kw)
    except exc_type:
        return True, True
    except Exception as e:
        return True, f"raised {type(e).__name__}({e}) instead of {exc_type.__name__}"
    return True, "no exception raised"


# ==================================================================
# LAYER 1 — schema / discipline checks
# ==================================================================
def schema_checks():
    print("\n[schema / discipline checks]")
    conn = fresh_db()
    seed_minimal(conn)

    # 1. namespace trigger rejects unregistered prefix
    def t_ns_trigger():
        try:
            cb.emit(conn, "test_traveler", "no_ns:foo", "TEST_ONE", "x")
            conn.commit()
            return "raises", "no error"
        except sqlite3.IntegrityError as e:
            return "raises", "raises" if "namespace" in str(e) else f"raises wrong: {e}"
    run("ns_trigger: bad-namespace insert raises",
        "subject not matching any registered prefix is rejected by trigger",
        t_ns_trigger)

    # 2. unregistered predicate raises ValueError (helper check)
    def t_unknown_predicate():
        try:
            cb.emit(conn, "test_traveler", "test:x", "NONEXISTENT_PRED", "1")
            return "raises", "no error"
        except ValueError:
            return "raises", "raises"
    run("unknown_predicate: emit() raises ValueError",
        "predicate not registered → emit refuses",
        t_unknown_predicate)

    # 3. predicates require definition (NOT NULL)
    def t_predicate_definition_required():
        try:
            conn.execute(
                "INSERT INTO predicates(name, domain, range, cardinality, definition, examples) "
                "VALUES ('NO_DEF','x','y','one',NULL,'[]')"
            )
            return "raises", "no error"
        except sqlite3.IntegrityError as e:
            return "raises", "raises" if "definition" in str(e) or "NOT NULL" in str(e) else f"raises wrong: {e}"
    run("predicate.definition NOT NULL is enforced",
        "schema rejects predicate without definition",
        t_predicate_definition_required)

    # 4. namespace prefix CHECK constraint (must end in ':')
    def t_ns_prefix_check():
        try:
            conn.execute("INSERT INTO namespaces(prefix, definition, example) VALUES ('NoColon','x','y')")
            return "raises", "no error"
        except sqlite3.IntegrityError:
            return "raises", "raises"
    run("namespace prefix CHECK rejects 'NoColon'",
        "namespace prefix must match GLOB '[a-z][a-z_0-9]*:'",
        t_ns_prefix_check)

    # 5. cardinality CHECK only allows 'one'|'many'
    def t_cardinality_check():
        try:
            conn.execute(
                "INSERT INTO predicates(name, domain, range, cardinality, definition, examples) "
                "VALUES ('BAD_CARD','x','y','some',':)','[]')"
            )
            return "raises", "no error"
        except sqlite3.IntegrityError:
            return "raises", "raises"
    run("cardinality CHECK rejects values outside one|many",
        "predicates.cardinality is bounded enum",
        t_cardinality_check)

    # 6. retraction trigger fires when retracts_id is set
    def t_retraction_trigger():
        # First fact
        f1 = cb.emit(conn, "test_traveler", "test:r", "TEST_ONE", "first")
        # Second fact retracting the first explicitly via retracts_id
        f2 = cb.emit(conn, "test_traveler", "test:r", "TEST_ONE", "second",
                     retracts_id=f1, retracts_reason="explicit test")
        # Trigger should mark f1 retracted with retracted_by_id=f2
        row = conn.execute(
            "SELECT retracted_at, retracted_by_id FROM facts WHERE id=?", (f1,)
        ).fetchone()
        return ("retracted", f2), ("retracted" if row["retracted_at"] else "live", row["retracted_by_id"])
    run("retraction_trigger: fires on retracts_id, sets retracted_by_id",
        "AFTER INSERT trigger marks the retracted fact and links back",
        t_retraction_trigger)

    # 7. auto-retract on 'one' cardinality (no explicit retracts_id needed)
    def t_auto_retract_one():
        cb.emit(conn, "test_traveler", "test:auto", "TEST_ONE", "alpha")
        f2 = cb.emit(conn, "test_traveler", "test:auto", "TEST_ONE", "beta")
        # Both facts exist; old one should be retracted
        live = conn.execute(
            "SELECT object FROM v_facts_live WHERE subject='test:auto' AND predicate='TEST_ONE'"
        ).fetchall()
        return [("beta",)], [tuple(r) for r in live]
    run("auto_retract: emit() of 'one' cardinality with new value retracts old",
        "documented behaviour from emit() docstring",
        t_auto_retract_one)

    # 8. 'many' cardinality does NOT auto-retract — values accumulate
    def t_many_accumulates():
        cb.emit(conn, "test_traveler", "test:many", "TEST_MANY", "a")
        cb.emit(conn, "test_traveler", "test:many", "TEST_MANY", "b")
        cb.emit(conn, "test_traveler", "test:many", "TEST_MANY", "c")
        live = sorted(r["object"] for r in conn.execute(
            "SELECT object FROM v_facts_live WHERE subject='test:many' AND predicate='TEST_MANY'"
        ))
        return ["a", "b", "c"], live
    run("'many' cardinality: facts accumulate without retraction",
        "additive predicates allow multiple live values",
        t_many_accumulates)

    # 9. unique-live index prevents duplicate live facts
    def t_unique_live():
        cb.emit(conn, "test_traveler", "test:dup", "TEST_MANY", "x")
        # Re-emit identical fact — should be ignored or unique-constraint blocks it
        try:
            cb.emit(conn, "test_traveler", "test:dup", "TEST_MANY", "x")
            n = conn.execute(
                "SELECT COUNT(*) AS c FROM v_facts_live WHERE subject='test:dup' AND predicate='TEST_MANY'"
            ).fetchone()["c"]
            return 1, n
        except sqlite3.IntegrityError:
            # acceptable: unique-live index blocks the second insert outright
            return 1, 1
    run("unique-live: identical (traveler, subject, predicate, object) cannot duplicate while live",
        "fact_unique_live partial index enforces this",
        t_unique_live)

    # 10. v_contradictions surfaces only between LIVE facts
    def t_contradiction_view_filters_retracted():
        # Two travelers disagree on test:contra
        cb.register_traveler(conn, "another", "fixture",  "meta")
        cb.emit(conn, "test_traveler", "test:contra", "TEST_ONE", "x")
        f2 = cb.emit(conn, "another",        "test:contra", "TEST_ONE", "y")
        n_before = conn.execute("SELECT COUNT(*) AS c FROM v_contradictions WHERE subject='test:contra'").fetchone()["c"]
        # Now retract the second one → contradiction should disappear
        conn.execute("UPDATE facts SET retracted_at = strftime('%Y-%m-%dT%H:%M:%f','now') WHERE id=?", (f2,))
        n_after = conn.execute("SELECT COUNT(*) AS c FROM v_contradictions WHERE subject='test:contra'").fetchone()["c"]
        return (1, 0), (n_before, n_after)
    run("v_contradictions: hides contradictions involving retracted facts",
        "view filters retracted_at IS NULL on both sides",
        t_contradiction_view_filters_retracted)

    conn.close()


# ==================================================================
# LAYER 2 — helper / round-trip checks
# ==================================================================
def helper_checks():
    print("\n[helper / round-trip checks]")
    conn = fresh_db()
    seed_minimal(conn)

    # 11. notes_for_claude round-trips as JSON
    def t_notes_roundtrip():
        notes = {
            "encoding": [{"type": "prose", "value": "test"},
                         {"type": "code", "lang": "python", "value": "x = 1"}],
            "evidence": ["src.py:42", "src.py:88"],
            "confidence": 0.95,
        }
        fid = cb.emit(conn, "test_traveler", "test:json", "TEST_ONE", "v",
                      notes_for_claude=notes)
        row = conn.execute("SELECT notes_for_claude FROM facts WHERE id=?", (fid,)).fetchone()
        decoded = json.loads(row["notes_for_claude"])
        return notes, decoded
    run("notes_for_claude: dict round-trips losslessly through JSON",
        "emit() serializes; SELECT returns parseable JSON; equality preserved",
        t_notes_roundtrip)

    # 12. captured_in_context round-trips as JSON
    def t_ctx_roundtrip():
        ctx = {"session": "test", "discussed": ["a", "b"], "n": 7}
        fid = cb.emit(conn, "test_traveler", "test:ctx", "TEST_ONE", "v",
                      captured_in_context=ctx)
        row = conn.execute("SELECT captured_in_context FROM facts WHERE id=?", (fid,)).fetchone()
        return ctx, json.loads(row["captured_in_context"])
    run("captured_in_context: dict round-trips losslessly",
        "JSON serialization is symmetric",
        t_ctx_roundtrip)

    # 13. emit() with dict object auto-sets object_kind='json'
    def t_dict_object_kind():
        fid = cb.emit(conn, "test_traveler", "test:obj", "TEST_ONE", {"k": "v"})
        row = conn.execute("SELECT object_kind, object FROM facts WHERE id=?", (fid,)).fetchone()
        return ("json", {"k": "v"}), (row["object_kind"], json.loads(row["object"]))
    run("emit(object=dict): object_kind defaults to 'json', object is serialized",
        "ergonomic: pass a dict, get JSON storage automatically",
        t_dict_object_kind)

    # 14. Multi-level retraction chain (3 supersessions)
    def t_chain_retraction():
        f1 = cb.emit(conn, "test_traveler", "test:chain", "TEST_ONE", "a")
        f2 = cb.emit(conn, "test_traveler", "test:chain", "TEST_ONE", "b")
        f3 = cb.emit(conn, "test_traveler", "test:chain", "TEST_ONE", "c")
        rows = list(conn.execute(
            "SELECT id, object, retracts_id, retracted_at IS NOT NULL AS is_retracted "
            "FROM facts WHERE subject='test:chain' AND predicate_id=("
            "  SELECT id FROM predicates WHERE name='TEST_ONE') ORDER BY id"
        ))
        # Expect: f1 retracted, f2 retracted, f3 live
        # f2.retracts_id == f1, f3.retracts_id == f2
        return [
            (f1, "a", None,  1),
            (f2, "b", f1,    1),
            (f3, "c", f2,    0),
        ], [tuple(r) for r in rows]
    run("retraction_chain: three supersessions form a clean chain",
        "each new value retracts the immediately-prior; chain links via retracts_id",
        t_chain_retraction)

    # 15. boot_summary structure is well-formed
    def t_boot_summary_structure():
        s = cb.boot_summary(conn)
        keys = sorted(s.keys())
        return ["contradictions","fact_counts","namespaces","pinned","plan",
                "predicates","trajectory","travelers"], keys
    run("boot_summary: returns all 8 expected top-level keys",
        "interface contract for session-boot consumption",
        t_boot_summary_structure)

    # 16. boot_summary fact_counts is correct (sanity check on the weird code)
    def t_boot_summary_counts():
        s = cb.boot_summary(conn)
        live = conn.execute("SELECT COUNT(*) AS c FROM v_facts_live").fetchone()["c"]
        retracted = conn.execute("SELECT COUNT(*) AS c FROM facts WHERE retracted_at IS NOT NULL").fetchone()["c"]
        total = conn.execute("SELECT COUNT(*) AS c FROM facts").fetchone()["c"]
        return {"live": live, "retracted": retracted, "total": total}, s["fact_counts"]
    run("boot_summary.fact_counts: live + retracted + total match raw query",
        "the dict-comprehension code path returns honest numbers",
        t_boot_summary_counts)

    conn.close()


# ==================================================================
# LAYER 3 — substrate-fact correctness checks
# ==================================================================
def substrate_checks():
    """Run cpu_4bit traveler on a known program and verify each emitted
    fact matches what the CPU actually did. Hand-computed expected values."""
    print("\n[substrate-fact correctness — cpu_4bit]")
    conn = fresh_db()
    seed_minimal(conn)

    # Run the 'add' program (3 + 4 = 7); 3 cycles + HLT cycle = 4 cycles total
    counts = t4.emit_program(conn, "add", t4.PROGRAMS["add"]["bytes"],
                              t4.PROGRAMS["add"]["description"])
    conn.commit()

    # 17. cycle count matches expectation
    def t_add_cycles():
        return 4, counts["cycles"]
    run("add: produces 4 cycles (LDA, ADD, OUT, HLT)",
        "the 'add' demo program runs to completion in 4 fetch-execute cycles",
        t_add_cycles)

    # 18. final OUT register == 7 (3 + 4)
    def t_add_result():
        return 7, counts["final_out"]
    run("add: final OUT register = 7",
        "ADD instruction performed 3+4 correctly",
        t_add_result)

    # 19. 4 unique addresses (one per opcode in the linear program)
    def t_add_unique_insns():
        return 4, counts["unique_insns"]
    run("add: 4 unique insns at addresses 0x00..0x03",
        "linear program; each instruction at a distinct address",
        t_add_unique_insns)

    # 20. mnemonics decoded correctly for each insn
    def t_add_mnemonics():
        rows = list(conn.execute(
            "SELECT subject, object FROM v_facts_live "
            "WHERE traveler='cpu_4bit' AND predicate='HAS_MNEMONIC' "
            "ORDER BY subject"
        ))
        actual = {r["subject"].split(":")[-1]: r["object"] for r in rows}
        return {"0x00": "lda", "0x01": "add", "0x02": "out", "0x03": "hlt"}, actual
    run("add: HAS_MNEMONIC matches the 'add' program disassembly",
        "opcode high-nybble decodes correctly via OP_MNEMONIC",
        t_add_mnemonics)

    # 21. operand of LDA at 0x00 is 14 (loads from RAM[14]=3)
    def t_add_lda_operand():
        row = conn.execute(
            "SELECT object FROM v_facts_live "
            "WHERE traveler='cpu_4bit' AND subject='insn:add:0x00' "
            "  AND predicate='HAS_OPERANDS'"
        ).fetchone()
        return "14", row["object"]
    run("add: LDA at 0x00 has operand 14 (RAM addr to load from)",
        "operand low-nybble extracted from IR byte 0x1E",
        t_add_lda_operand)

    # 22. each cycle has exactly one BRANCH fact
    def t_add_branches():
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM v_facts_live "
            "WHERE traveler='cpu_4bit' AND predicate='BRANCH'"
        ).fetchone()["c"]
        return 4, n
    run("add: 4 BRANCH facts (one per cycle)",
        "BRANCH cardinality='one' with 4 cycles → 4 facts",
        t_add_branches)

    # 23. last cycle's BRANCH is 'halt'
    def t_add_halt():
        rows = list(conn.execute(
            "SELECT object FROM v_facts_live "
            "WHERE traveler='cpu_4bit' AND predicate='BRANCH' "
            "  AND subject GLOB 'step:add:*' "
            "ORDER BY subject"
        ))
        return "halt", rows[-1]["object"]
    run("add: final cycle's BRANCH is 'halt' (HLT instruction fired)",
        "HLT detected via 'hlt' signal in execute T-state",
        t_add_halt)

    # 24. no 'taken' branches in 'add' (linear control flow)
    def t_add_no_taken():
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM v_facts_live "
            "WHERE traveler='cpu_4bit' AND predicate='BRANCH' "
            "  AND subject GLOB 'step:add:*' AND object LIKE 'taken:%'"
        ).fetchone()["c"]
        return 0, n
    run("add: zero 'taken:0xXX' branches (program is linear)",
        "no JMP or JZ in the add program",
        t_add_no_taken)

    # ---- Now a richer countdown trace: known-good branch shape ----
    counts_cd = t4.emit_program(conn, "countdown", t4.PROGRAMS["countdown"]["bytes"],
                                 t4.PROGRAMS["countdown"]["description"])
    conn.commit()

    # 25. countdown: 17 cycles
    def t_cd_cycles():
        return 17, counts_cd["cycles"]
    run("countdown: 17 cycles total (LDA + 5×SUB + 5×JZ + 4×JMP + OUT + HLT)",
        "loop runs 5 iterations; on iter-5 JZ takes; total cycle count",
        t_cd_cycles)

    # 26. countdown: 4 'taken:0x01' (JMP back) + 1 'taken:0x04' (JZ taken)
    def t_cd_taken_branches():
        rows = list(conn.execute(
            "SELECT object, COUNT(*) AS n FROM v_facts_live "
            "WHERE traveler='cpu_4bit' AND predicate='BRANCH' "
            "  AND subject GLOB 'step:countdown:*' AND object LIKE 'taken:%' "
            "GROUP BY object ORDER BY object"
        ))
        actual = {r["object"]: r["n"] for r in rows}
        return {"taken:0x01": 4, "taken:0x04": 1}, actual
    run("countdown: 4×JMP back to 0x01, 1×JZ to 0x04",
        "loop body fires 5 times; on the last iteration JZ takes (Z=1) and JMP doesn't run",
        t_cd_taken_branches)

    # 27. countdown: DELTA on cycle 0 mentions 'a=' (LDA loads 5)
    def t_cd_first_delta():
        row = conn.execute(
            "SELECT object FROM v_facts_live "
            "WHERE traveler='cpu_4bit' AND predicate='DELTA' "
            "  AND subject='step:countdown:000000'"
        ).fetchone()
        return True, "a=" in row["object"]
    run("countdown: cycle-0 DELTA mentions 'a=' (LDA wrote A)",
        "first instruction loads RAM[14]=5 into A; A changes from 0 to 5",
        t_cd_first_delta)

    # 28. countdown: WRITES_REG facts include 'a' (multiple times, since SUB writes A 5x)
    def t_cd_writes_a():
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM v_facts_live "
            "WHERE traveler='cpu_4bit' AND predicate='WRITES_REG' "
            "  AND subject GLOB 'step:countdown:*' AND object='a'"
        ).fetchone()["c"]
        # LDA writes a (1), SUB writes a (5x), OUT doesn't write a directly
        return True, n >= 6  # at least LDA + 5 SUBs
    run("countdown: 'a' is written ≥6 times (LDA + 5×SUB)",
        "WRITES_REG 'many' cardinality accumulates per cycle",
        t_cd_writes_a)

    # 29. countdown: cross-traveler shape — predicates used by cpu_4bit
    # match the predicate names that parser_6502 / parser_jvm will use.
    def t_cd_cross_predicates():
        cpu_preds = sorted(r["predicate"] for r in conn.execute(
            "SELECT DISTINCT predicate FROM v_facts_live WHERE traveler='cpu_4bit'"
        ))
        # Compare to the substrate-vocab subset that future travelers will share
        substrate_subset = sorted([
            "AT_INSN","AT_ADDRESS","HAS_MNEMONIC","HAS_OPERANDS","HAS_SIZE",
            "HAS_BYTES","IN_PROGRAM","STEP_SEQ","DELTA","BRANCH","WRITES_REG",
            "HAS_MD5","INGESTED_AT",
        ])
        return substrate_subset, cpu_preds
    run("substrate vocab: cpu_4bit emits the full ISA-agnostic predicate set",
        "same predicates that parser_6502 + parser_jvm will use; substrate-independence claim grounded",
        t_cd_cross_predicates)

    # 30. AT_INSN refs point to existing insn:* subjects (referential integrity
    # at the application layer — the schema doesn't enforce ref-as-FK)
    def t_cd_at_insn_refs_resolve():
        rows = list(conn.execute(
            "SELECT step.object AS insn_subj "
            "FROM v_facts_live step "
            "WHERE step.traveler='cpu_4bit' AND step.predicate='AT_INSN' "
            "  AND step.subject GLOB 'step:countdown:*'"
        ))
        unresolved = []
        for r in rows:
            insn_subj = r["insn_subj"]
            n = conn.execute(
                "SELECT COUNT(*) AS c FROM v_facts_live WHERE subject=? AND predicate='AT_ADDRESS'",
                (insn_subj,)
            ).fetchone()["c"]
            if n == 0:
                unresolved.append(insn_subj)
        return [], unresolved
    run("AT_INSN refs all resolve to existing insn:* subjects with AT_ADDRESS",
        "application-layer referential integrity; ref objects point to real subjects",
        t_cd_at_insn_refs_resolve)

    conn.close()


# ==================================================================
# LAYER 4 — re-run / idempotency checks
# ==================================================================
def idempotency_checks():
    print("\n[idempotency]")

    # 31. bootstrap is idempotent (re-applying the schema doesn't crash)
    def t_bootstrap_idempotent():
        if TEST_DB.exists(): TEST_DB.unlink()
        conn1 = cb.bootstrap(TEST_DB)
        seed_minimal(conn1)
        cb.emit(conn1, "test_traveler", "test:idem", "TEST_ONE", "v")
        conn1.commit(); conn1.close()
        # Re-bootstrap on the already-populated DB; should not wipe existing data
        conn2 = cb.bootstrap(TEST_DB)
        n = conn2.execute(
            "SELECT COUNT(*) AS c FROM v_facts_live WHERE subject='test:idem'"
        ).fetchone()["c"]
        conn2.close()
        return 1, n
    run("bootstrap: re-running on an existing DB preserves data",
        "schema 'DROP IF EXISTS' is gated by _schema_needs_apply",
        t_bootstrap_idempotent)

    # 32. seed re-run is idempotent (no duplicate predicates / namespaces)
    def t_seed_rerun_idempotent():
        if TEST_DB.exists(): TEST_DB.unlink()
        conn = cb.bootstrap(TEST_DB)
        seed_minimal(conn)
        n_before = conn.execute("SELECT COUNT(*) AS c FROM predicates").fetchone()["c"]
        seed_minimal(conn)  # re-run
        n_after = conn.execute("SELECT COUNT(*) AS c FROM predicates").fetchone()["c"]
        conn.close()
        return n_before, n_after
    run("seed: re-running register_* helpers is idempotent (INSERT OR IGNORE)",
        "running the seed twice doesn't multiply vocabulary",
        t_seed_rerun_idempotent)


# ==================================================================
# REPORT
# ==================================================================
def write_report():
    n = len(RESULTS)
    p = sum(1 for r in RESULTS if r["ok"])
    f = n - p
    lines = [
        "# Cork-board test report",
        "",
        f"_Generated: {datetime.now().isoformat(timespec='seconds')}_",
        "",
        f"**{p}/{n} passed**" + ("" if f == 0 else f"  &nbsp;|&nbsp;  **{f} FAILED**"),
        "",
        "| # | test | claim | expected | actual | result |",
        "|---|------|-------|----------|--------|--------|",
    ]
    for i, r in enumerate(RESULTS, 1):
        exp = repr(r["expected"]).replace("|", "\\|").replace("\n", "↵")[:200]
        act = repr(r["actual"]).replace("|", "\\|").replace("\n", "↵")[:200]
        lines.append(
            f"| {i} | `{r['name']}` | {r['claim']} | `{exp}` | `{act}` | "
            f"{'PASS' if r['ok'] else '**FAIL**'} |"
        )
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
    schema_checks()
    helper_checks()
    substrate_checks()
    idempotency_checks()
    ok = write_report()
    raise SystemExit(0 if ok else 1)
