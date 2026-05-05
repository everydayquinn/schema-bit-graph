"""
seed_stress_candidates.py — substrate-stress-test candidates + frame-shift rule.

Records the session-6 reframe: substrate selection is stress-test design,
not pivot management. Each candidate substrate gets a row in the cork-board
under stress:* namespace with status + tractability + stress dimension.

Idempotent: re-running emits identical facts; the unique-live index
prevents duplication.

Usage:
    python3 seed_stress_candidates.py [corkboard.db]
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import corkboard as cb

DB = Path(sys.argv[1]) if len(sys.argv) > 1 else cb.DEFAULT_DB

CTX = {
    "session_marker":  "session_6_2026-05-04",
    "user_correction": "scrawn flagged that I was treating substrate selection as pivot-management when it's actually stress-test design",
    "frame_locked":    "architecture (predicates+travelers+cork-board) is the load-bearing thing; substrates are stress-test cases, not pivots; build several",
}


def main():
    conn = cb.bootstrap(DB)

    # Ensure namespace registered (seed_corkboard.py also registers it; idempotent)
    cb.register_namespace(conn, "stress:",
        "stress-test substrate candidates and their probed dimensions",
        "stress:cave-game")

    # The frame-shift fact (meta-architecture observation)
    cb.emit(conn, "claude_terminal", "meta:substrate-as-stress-test", "ROADMAP_DESCRIPTION",
        "Substrate selection is stress-test design, not pivot management. The architecture is locked: predicates + travelers + cork-board with discipline mechanisms. Substrates are different SHAPES thrown at the architecture to find which axis breaks first. New substrates explore stress dimensions (real-software shape, multi-agent, dynamic dispatch, self-modifying code, etc.). Building each is cheap (cpu_4bit took ~30 min). The pitch becomes 'tested on N substrates; here's what held and here's what broke' — more credible than 'works on the one I picked.'",
        captured_in_context=CTX,
        notes_for_claude={
            "what_this_changes":      "stop running 'is this a pivot?' check on every new substrate proposal. Run 'what does this stress?' instead.",
            "what_this_preserves":    "discipline mechanisms still apply (mandatory predicate definitions, namespace registry, retraction-link). The architecture doesn't loosen.",
            "operational_consequence":"Day 2 becomes parallel substrate probes (port 6502 + clone Cave Game + maybe one more), not 'pick one substrate.'",
            "live_index_file":        "DATABASES.md tracks all stores; stress:* subjects in cork-board track substrate candidates",
        })

    # Codify as a rule so future-Claude doesn't re-litigate substrate-as-pivot
    cb.emit(conn, "claude_terminal", "rule:substrates-are-stress-tests-not-pivots", "RULE_TEXT",
        "Treat substrate selection as stress-test design, not pivot management. Building a new traveler is cheap (~30 min if you have the predicate vocab). Run several in parallel; the ones that surface architectural limits earn their keep. Pivots are about commitments; substrates are experiments.",
        captured_in_context=CTX)
    cb.emit(conn, "claude_terminal", "rule:substrates-are-stress-tests-not-pivots", "RULE_RATIONALE",
        "Earlier in session 6 I kept asking 'is this a pivot?' every time a new substrate (Cave Game, JVM, Colonies-AI) came up. scrawn corrected: same structure different shape. The architecture was already locked; the question was substrate-shape, not commitment. Pivot-anxiety on substrate-shape wastes cycles.",
        captured_in_context=CTX)

    # Stress-test candidates (status, dimension probed, tractability, evidence)
    candidates = [
        ("stress:cpu_4bit",
         "shipped",
         "baseline; toy register machine in-house",
         "trivial",
         "157 facts on countdown loop; 32 corkboard tests pass"),

        ("stress:6502-from-kairos",
         "planned-day-2",
         "real-ROM input; analysis-stack-on-real-data; register machine via py65",
         "low (port not build)",
         "sim_6502.py + populate_6502.py exist in /home/scrawn/C_Compiler Schema/; sigma_6502.db has 14 instructions; 8 travelers in their facts.db"),

        ("stress:jvm-toy",
         "planned-day-3-fallback",
         "stack-machine vocab (PUSHES_STACK, POPS_STACK, READS_LOCAL); minimal cross-substrate proof",
         "low (~7 opcodes via javap)",
         "predicate dictionary already drafted in seed_corkboard.py: iconst/iload/istore/iadd/if_icmpge/goto/ireturn"),

        ("stress:cave-game",
         "candidate-needs-probe",
         "real-legacy-software shape; runtime+bytecode dual-traveler from ONE source; cultural pull for pitch (first version of Minecraft)",
         "unknown — needs build-system probe (LWJGL deps, gradle/maven, modern-Java compatibility)",
         "Minecraft Classic rd-132211 reverse-engineered on GitHub; small Java codebase; first version of MC; visible-running-window demo possible"),

        ("stress:multi-agent-colonies",
         "candidate-trajectory",
         "N concurrent fact producers into one schema; index contention on fact_unique_live? cross-traveler temporal queries?",
         "high (build sim from scratch)",
         "deferred to trajectory; would test predicate-vocab survival under multi-agent runtime"),

        ("stress:python-bytecode",
         "candidate-trajectory",
         "dynamic dispatch, frame stack, generators, exception handlers — schema's handling of dynamic features",
         "medium (dis module + sys.settrace)",
         "could probe runtime + static via single Python source; not in 5-day scope"),

        ("stress:self-modifying-genetic",
         "candidate-trajectory",
         "schema handles code that mutates between generations; bytecode-version axis added to predicates",
         "high (genetic harness + recompile loop)",
         "deferred; named in trajectory; would test temporal queries across versions"),

        ("stress:x86-from-kairos",
         "available-not-yet-ported",
         "variable-length instructions; register machine; real software via capstone",
         "low (port not build)",
         "sigma_x86.db has 48 instructions, 95 reg_effects in Kairos; sim.py uses Unicorn for runtime trace"),
    ]

    for subject, status, dimension, tractability, evidence in candidates:
        cb.emit(conn, "claude_terminal", subject, "ROADMAP_TITLE",
                "Stress-test substrate candidate", captured_in_context=CTX)
        cb.emit(conn, "claude_terminal", subject, "STATUS", status, captured_in_context=CTX)
        cb.emit(conn, "claude_terminal", subject, "ROADMAP_DESCRIPTION", dimension,
                captured_in_context=CTX)
        cb.emit(conn, "claude_terminal", subject, "FALLBACK_PLAN",
                f"tractability: {tractability} | evidence: {evidence}",
                captured_in_context=CTX)

    conn.commit()

    # Verify
    n_candidates = conn.execute(
        "SELECT COUNT(DISTINCT subject) AS c FROM v_facts_live WHERE subject GLOB 'stress:*'"
    ).fetchone()[0]
    print(f"stress candidates: {n_candidates}")
    print(f"frame-shift fact: emitted under meta:substrate-as-stress-test")
    print(f"rule logged: rule:substrates-are-stress-tests-not-pivots")
    conn.close()


if __name__ == "__main__":
    main()
