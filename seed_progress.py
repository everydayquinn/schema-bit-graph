"""
seed_progress.py — session-progress STATUS flips for cork-board deliverables.

Captures which 5-day-plan deliverables have actually shipped during a
session, with notes_for_claude evidence. Gets re-run after the baseline
seeds (seed_corkboard.py + seed_stress_candidates.py) to bring the
cork-board to current session state without losing inline progress.

Idempotent via the unique-live constraint: re-emitting the same
(traveler, subject, predicate, object) is a no-op. Re-emitting a
DIFFERENT object on a 'one' cardinality predicate auto-retracts the prior.

Usage:
    python3 seed_progress.py [corkboard.db]
"""
from __future__ import annotations

import sys
from pathlib import Path

import corkboard as cb

DB = Path(sys.argv[1]) if len(sys.argv) > 1 else cb.DEFAULT_DB

# (subject, status, evidence_notes_dict)
PROGRESS = [
    # ----------- Day 1 -----------
    ("plan:5day:day1:facts-db-port", "shipped",
     "session_6_2026-05-04 EOD Day 1",
     {"shipped_evidence": "corkboard.db live with 16 namespaces, 46 predicates, 7 travelers, 540+ facts; v_contradictions surfaces 3 contradictions; namespace trigger fires on bad subjects; 121 substrate tests + 40 corkboard tests pass",
      "files_added":      ["corkboard_schema.sql", "corkboard.py", "seed_corkboard.py"]}),

    ("plan:5day:day1:cpu-4bit-traveler", "shipped",
     "session_6_2026-05-04 EOD Day 1",
     {"shipped_evidence": "cpu_4bit_traveler.py runs countdown loop, emits 157 facts; cross-traveler query works",
      "files_added":      ["cpu_4bit_traveler.py"],
      "test_evidence":    "12 substrate-fact correctness tests in test_corkboard.py verify cpu_4bit semantics on 'add' and 'countdown' programs"}),

    ("plan:5day:day1:pitch", "in-progress",
     "session_6_2026-05-04 EOD Day 1 — drafts ready, scrawn-pick pending",
     {"drafts": ["pitch:hallway:v1", "pitch:hallway:v2", "pitch:hallway:v3"],
      "pending": "scrawn picks one (or remixes); flip to shipped once locked"}),

    # ----------- Day 2 -----------
    ("plan:5day:day2:port-6502", "shipped",
     "session_6_2026-05-04 EOD Day 2 (compressed into Day 1 same session)",
     {"shipped_evidence": "parser_6502.py + sim_6502.py work end-to-end; 3 substrates (cpu_4bit + parser_6502 + sim_6502) share substrate-vocab predicates; cross-substrate query returns parallel structurally-identical output",
      "files_added":      ["parser_6502.py", "sim_6502.py", "kit_6502_lessons/01_basic.s", "kit_6502_lessons/02_interrupt.s"],
      "fact_count_after": "live: 546+",
      "added_predicates": ["ENTRY_STATE", "STEP_AT_ADDR", "TERMINATED", "MEM_READ", "MEM_WRITE", "INTERRUPT", "CYCLES"],
      "test_coverage":    "8 new tests added in test_corkboard.py (six502_checks); project total 153→161"}),

    ("plan:5day:day2:mine-6502", "planned",
     "session_6_2026-05-04 — pending decision: run miner on parser_6502 facts, or move to trajectory?",
     {"current_status":   "miner.py expects state_log shape (cpu.db) historically; would need a small adapter to read corkboard.db parser_6502 facts",
      "decision_pending": "scrawn call: do we run mining on Day 2 or move to trajectory? Cross-substrate query already proves substrate-independence without mining.",
      "fallback":         "if mining is too noisy or adapter is too much work, the analysis stack stays as-is and we name 'mine the facts.db facts' as a trajectory item"}),

    # ----------- Stress-candidate progress -----------
    ("stress:cpu_4bit", "shipped",
     "session_6_2026-05-04",
     {"facts_emitted": 157, "cross_substrate_query_works": True}),

    ("stress:6502-from-kairos", "shipped",
     "session_6_2026-05-04 — both parser_6502 (static) and sim_6502 (runtime) ported",
     {"parser_6502_facts": 114,  # 26 from 01_basic + 88 from 02_interrupt
      "sim_6502_facts":    106}),  # 28 + 78

    ("stress:cave-game", "probed-tractable",
     "session_6_2026-05-04",
     {"probe_result":     "rd-132211 at https://github.com/thecodeofnotch/rd-132211 (16★, last touched 2021)",
      "build_system":     "Gradle KTS + wrapper; self-contained",
      "dependencies":     "LWJGL 2.9.3 (Maven Central, Linux x86_64 natives bundled); no sound/networking",
      "java_version":     "no toolchain declared; works on JDK 8-17; JDK 21+ may need --add-opens",
      "codebase_size":    "13 .java files; ~1-2 KLOC",
      "estimated_effort": "~half-day to clone + gradle build + verify",
      "demo_payoff":      "running window + live SQL panel = visceral generalist demo",
      "risk_if_blown":    "JDK compat could eat ~3 hours; fallback to trivial Java keeps Day-3 safe"}),
]


def main():
    conn = cb.bootstrap(DB)

    for subject, status, ctx_marker, notes in PROGRESS:
        cb.emit(conn, "claude_terminal", subject, "STATUS", status,
                captured_in_context={"session_marker": ctx_marker},
                notes_for_claude=notes)

    conn.commit()

    # Verify
    import sqlite3
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    print("=== current cork-board state ===")
    print()
    print("Plan deliverables:")
    for r in c.execute("SELECT day, deliverable, status FROM v_plan_today"):
        print(f"  day {r['day']} {r['deliverable']:<40} {r['status']}")
    print()
    n_shipped = c.execute("SELECT COUNT(*) AS c FROM v_facts_live WHERE predicate='STATUS' AND object='shipped'").fetchone()["c"]
    n_inprog  = c.execute("SELECT COUNT(*) AS c FROM v_facts_live WHERE predicate='STATUS' AND object='in-progress'").fetchone()["c"]
    n_planned = c.execute("SELECT COUNT(*) AS c FROM v_facts_live WHERE predicate='STATUS' AND object='planned'").fetchone()["c"]
    print(f"shipped: {n_shipped}, in-progress: {n_inprog}, planned: {n_planned}")
    c.close()


if __name__ == "__main__":
    main()
