"""
seed_corkboard.py — populate the cork-board with current-session state.

What gets written:
  - Namespaces (subject-prefix vocabulary)
  - Predicates (substrate layer + gameplan layer + meta layer)
  - Travelers (cpu_4bit, parser_6502, parser_jvm, claude_terminal,
                claude_web, kairos_session_baton, scrawn)
  - The locked 5-day plan (Day 6 = buffer)
  - Pinned items (do not propose, do not build)
  - Trajectory items (named, not built — for README)
  - Three competing AI gameplans (contradictions visible via v_contradictions)
  - Pitch sentence drafts (with rationale in notes_for_claude)
  - Meta-architecture observations from this session

Re-runnable: predicates/namespaces/travelers use INSERT OR IGNORE.
Facts are append-only by design — re-running creates new facts, but the
unique-live index prevents exact duplicates.

Usage:
    python3 seed_corkboard.py [corkboard.db]
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import corkboard as cb

DB = Path(sys.argv[1]) if len(sys.argv) > 1 else cb.DEFAULT_DB

# Standard "captured at session 6 close-out" provenance stamp
SESSION_CTX = {
    "session_marker":   "session_6_2026-05-04",
    "discussed_around": "5-day plan lock + facts.db port + traveler abstraction adoption from C_Compiler Schema",
    "user_state":       "explicit autonomy granted; do-not-check-back; full freedom on rich-Claude-notes encoding",
}


# ==================================================================
# NAMESPACES
# ==================================================================
NAMESPACES = [
    ("plan:",          "gameplan deliverables, organized by day",
                       "plan:5day:day1:pitch"),
    ("decision:",      "discrete decisions made (collapse 6→5 day, lock JVM as Day 3, etc.)",
                       "decision:5day-buffer"),
    ("traveler:",      "facts about travelers themselves — meta-layer self-description",
                       "traveler:claude_terminal:context_at_session_6"),
    ("predicate:",     "facts about predicates themselves — vocabulary self-description",
                       "predicate:AT_INSN:rationale"),
    ("cut:",           "items cut from scope and why",
                       "cut:c-frontend-stub"),
    ("pinned:",        "items explicitly pinned — must not be re-proposed",
                       "pinned:shl-shr"),
    ("trajectory:",    "items named for README's trajectory section but not built",
                       "trajectory:full-c-frontend"),
    ("contradiction:", "surfaced contradictions between travelers on the same subject",
                       "contradiction:plan:5day:day2:deliverable"),
    ("pitch:",         "pitch sentence drafts and rationale for the README + hallway",
                       "pitch:hallway:v1"),
    ("lock:",          "session-5 locked decisions, treated as quasi-immutable commitments",
                       "lock:6day-arc:web-summit-2026"),
    ("meta:",          "meta-architecture observations (substrate-independence, facts-as-substrate, etc.)",
                       "meta:thesis-line:facts-as-substrate"),
    ("fact:",          "references to other facts, used in retraction reasons",
                       "fact:127"),
    # Substrate-layer prefixes — borrowed from C_Compiler Schema convention
    ("insn:",          "instruction-level facts (one per decoded instruction, any ISA)",
                       "insn:countdown:0x02"),
    ("prog:",          "program-level facts (one per ingested program/ROM/class)",
                       "prog:countdown"),
    ("step:",          "execution-step facts (one per executed instruction at runtime)",
                       "step:countdown:000003"),
    ("rule:",          "collaboration / interpretation rules I should not drift past",
                       "rule:no-private-symbolic-language"),
]


# ==================================================================
# PREDICATES — bounded vocabulary, mandatory definitions
# ==================================================================
# (name, domain, range, cardinality, definition, examples)
PREDICATES = [
    # ---- Substrate layer (borrowed/adapted from C_Compiler Schema) ----
    ("AT_INSN",         "step", "ref",     "one",
     "the instruction (insn:* subject) executed at this step",
     ["step:countdown:000003 AT_INSN insn:countdown:0x02"]),
    ("AT_ADDRESS",      "insn", "literal", "one",
     "instruction's load address as 0xHHHH hex string",
     ["insn:countdown:0x02 AT_ADDRESS 0x02"]),
    ("HAS_MNEMONIC",    "insn", "literal", "one",
     "decoded mnemonic in lowercase",
     ["insn:countdown:0x02 HAS_MNEMONIC sub"]),
    ("HAS_OPERANDS",    "insn", "literal", "one",
     "operand string from disassembler; empty if none",
     ["insn:countdown:0x02 HAS_OPERANDS 15"]),
    ("HAS_SIZE",        "insn", "literal", "one",
     "instruction size in bytes as integer string",
     ["insn:countdown:0x02 HAS_SIZE 1"]),
    ("HAS_BYTES",       "insn", "literal", "one",
     "raw byte hex (lowercase, no separators)",
     ["insn:countdown:0x02 HAS_BYTES 3f"]),
    ("IN_PROGRAM",      "insn", "prog",    "one",
     "instruction belongs to this program",
     ["insn:countdown:0x02 IN_PROGRAM prog:countdown"]),
    ("STEP_SEQ",        "step", "literal", "one",
     "execution-order index, zero-padded to 6 digits",
     ["step:countdown:000003 STEP_SEQ 000003"]),
    ("DELTA",           "step", "literal", "one",
     "register/flag changes for this step, condensed (e.g. 'a=4->3,z=0->1')",
     ["step:countdown:000003 DELTA a=4->3,z=0->1"]),
    ("BRANCH",          "step", "literal", "one",
     "control-flow at end of step: 'linear' | 'taken:0xHHHH' | 'return' | 'halt'",
     ["step:countdown:000005 BRANCH taken:0x01"]),
    ("WRITES_REG",      "step", "literal", "many",
     "register written during this step (one fact per register)",
     ["step:countdown:000003 WRITES_REG a"]),
    ("READS_REG",       "step", "literal", "many",
     "register read during this step (one fact per register)",
     ["step:countdown:000003 READS_REG a"]),
    # JVM-flavoured (stack machine analogues)
    ("PUSHES_STACK",    "step", "literal", "many",
     "JVM-style: pushes a value onto the operand stack at this step",
     ["step:hello:000001 PUSHES_STACK int:5"]),
    ("POPS_STACK",      "step", "literal", "many",
     "JVM-style: pops a value off the operand stack at this step",
     ["step:hello:000003 POPS_STACK int:8"]),
    ("READS_LOCAL",     "step", "literal", "many",
     "JVM-style: reads from local variable slot N",
     ["step:hello:000002 READS_LOCAL 0"]),
    ("WRITES_LOCAL",    "step", "literal", "many",
     "JVM-style: writes to local variable slot N",
     ["step:hello:000004 WRITES_LOCAL 1"]),
    ("HAS_MD5",         "prog", "literal", "one",
     "md5 of program source as hex",
     ["prog:countdown HAS_MD5 abc123..."]),
    ("INGESTED_AT",     "prog", "literal", "one",
     "ISO-8601 timestamp when this program was first populated",
     ["prog:countdown INGESTED_AT 2026-05-04T16:30:00.000"]),

    # ---- Gameplan layer ----
    ("ROADMAP_TITLE",   "plan", "literal", "one",
     "short human-readable title for a plan deliverable",
     ["plan:5day:day1:pitch ROADMAP_TITLE 'Hallway pitch sentence (~25s)'"]),
    ("ROADMAP_DESCRIPTION", "plan", "literal", "one",
     "one-paragraph description of the deliverable",
     ["plan:5day:day3:jvm-traveler ROADMAP_DESCRIPTION '...'"]),
    ("FOR_DAY",         "plan", "literal", "one",
     "which day of the sprint this deliverable belongs to (1..6, 6=buffer)",
     ["plan:5day:day1:pitch FOR_DAY 1"]),
    ("STATUS",          "plan", "literal", "one",
     "deliverable status: planned | in-progress | shipped | cut | blocked",
     ["plan:5day:day1:pitch STATUS planned"]),
    ("CUT_REASON",      "plan", "literal", "one",
     "why this deliverable was cut from scope",
     ["plan:5day:day3:c-frontend CUT_REASON 'JVM picked instead — concrete predicate dictionary'"]),
    ("IS_BUFFER",       "plan", "literal", "one",
     "true if this row is buffer/slack (not a deliverable, just slip-absorption)",
     ["plan:5day:day6:buffer IS_BUFFER true"]),
    ("DEPENDS_ON",      "plan", "plan",    "many",
     "this deliverable requires the target deliverable shipped first (DAG)",
     ["plan:5day:day3:jvm-traveler DEPENDS_ON plan:5day:day1:facts-db-port"]),
    ("PINNED_REASON",   "pinned","literal","one",
     "why this item is pinned — explanation of why not to re-propose",
     ["pinned:shl-shr PINNED_REASON 'completes ISA aesthetically; does not change demo'"]),
    ("GOES_IN_TRAJECTORY", "trajectory", "literal", "one",
     "named in README's trajectory section but not built in this sprint",
     ["trajectory:full-c-frontend GOES_IN_TRAJECTORY 'C → idiom catalog → 6502; demonstrates the same machinery one layer up'"]),
    ("FALLBACK_PLAN",   "plan", "literal", "one",
     "what to ship if this deliverable's primary path is blown by EOD",
     ["plan:5day:day3:jvm-traveler FALLBACK_PLAN 'cut to trajectory; ship 2-substrate demo'"]),

    # ---- Meta layer (decisions, contradictions, retractions, claims) ----
    ("CLAIMS",          "any",  "literal", "many",
     "a claim made by a traveler about a subject, full text",
     ["claude_terminal CLAIMS 'mining 6502 fits Day 2 because sim_6502.py exists in C_Compiler Schema'"]),
    ("BASED_ON_CONTEXT","any",  "literal", "one",
     "what context the traveler had when they made claims about this subject (JSON)",
     ["plan:5day:day2:mine-6502 BASED_ON_CONTEXT '{...session-5 lock visible, Kairos folder visible...}'"]),
    ("CONTRADICTS_FACT","any",  "ref",     "many",
     "this fact contradicts a prior fact (by id reference)",
     ["fact:42 CONTRADICTS_FACT fact:17"]),
    ("RETRACTION_REASON","fact","literal", "many",
     "why a fact was retracted (one fact per reason; usually one)",
     ["fact:17 RETRACTION_REASON 'web-Claude lacked session-5 context'"]),
    ("DECIDED_IN",      "any",  "literal", "one",
     "session marker where this decision was first made",
     ["decision:5day-buffer DECIDED_IN session_6_2026-05-04"]),
    ("AUTHOR",          "any",  "literal", "one",
     "who originated this item: scrawn | claude_terminal | claude_web | kairos_session_baton",
     ["pitch:hallway:v1 AUTHOR claude_terminal"]),
    ("VERSION",         "any",  "literal", "one",
     "version label for iteration tracking",
     ["pitch:hallway:v1 VERSION 1"]),
    ("NEXT_STEP",       "plan", "literal", "many",
     "concrete next action to advance this deliverable",
     ["plan:5day:day1:cpu-4bit-traveler NEXT_STEP 'write cpu_4bit_traveler.py emitting from state_log'"]),
    ("VERIFIABILITY",   "any",  "literal", "one",
     "what would prove or falsify this claim, mechanically",
     ["plan:5day:day3:jvm-traveler VERIFIABILITY 'same SQL query returns sensible output across cpu_4bit + 6502 + jvm travelers'"]),

    # ---- Rule / lesson layer ----
    ("RULE_TEXT",       "rule", "literal", "one",
     "the rule itself, full text",
     ["rule:no-private-symbolic-language RULE_TEXT '...'"]),
    ("RULE_RATIONALE",  "rule", "literal", "one",
     "why this rule exists — usually a past failure mode",
     ["rule:no-private-symbolic-language RULE_RATIONALE 'opaque encoding defeats audit, drifts unfalsifiable'"]),
]


# ==================================================================
# TRAVELERS
# ==================================================================
TRAVELERS = [
    ("cpu_4bit",
     "the project's 4-bit CPU; emits facts from state_log into facts.db",
     "substrate",
     "cpu_4bit_traveler.py (in this project)",
     "Re-emits each T-state row from state_log as substrate-layer facts (AT_INSN, DELTA, BRANCH, WRITES_REG, etc.). Same predicate vocabulary as parser_6502 and parser_jvm; substrate-independence claim made operational."),
    ("parser_6502",
     "static decode of 6502 ROMs / lessons via py65 disassembler",
     "substrate",
     "to be ported from C_Compiler Schema/populate_6502.py (Day 2)",
     "Day-2 deliverable. Source already exists in Kairos folder; needs porting + adapting to project's corkboard.db."),
    ("parser_jvm",
     "JVM bytecode disassembly (via javap or ASM); emits stack-machine flavoured facts",
     "substrate",
     "to be built in this project (Day 3)",
     "Day-3 deliverable. Predicate dictionary drafted: iconst→PUSHES_STACK, iload→READS_LOCAL+PUSHES_STACK, istore→POPS_STACK+WRITES_LOCAL, iadd→2×POPS_STACK+PUSHES_STACK, if_icmpge→2×POPS_STACK+BRANCH, goto→BRANCH, ireturn→POPS_STACK+returns. ~7 opcodes is the minimal set that proves the claim."),
    ("claude_terminal",
     "this Claude session running in the terminal with full project context",
     "meta",
     "Claude Code (Opus 4.7, 1M context)",
     "Has visibility into: locked session-5 plan, C_Compiler Schema kernel, MEMORY.md journal, AI STUFF.txt transcripts, full project source. Distinguishing context: knows session-5 commitments are load-bearing; knows the cork-board is being built right now."),
    ("claude_web",
     "parallel ChatGPT-Claude conversations the user has been running for second opinions",
     "external",
     "user-pasted transcripts from chat.anthropic.com / Claude.ai",
     "Does NOT have visibility into: locked session-5 plan, C_Compiler Schema folder, MEMORY.md, AI STUFF.txt history, project source tree. Conclusions evaluated in isolation can be sharper structurally but miss commitment-context."),
    ("kairos_session_baton",
     "the locked session-5 plan from session_6_2026-05-04 (encoded in MEMORY.md)",
     "external",
     "MEMORY.md hot-summary block 'LOCKED 6-day plan'",
     "Frozen at the moment scrawn locked the plan. Not edited within this session unless scrawn explicitly re-locks. Treated as quasi-immutable commitment."),
    ("scrawn",
     "scrawn's manual annotations, decisions, vetoes, and direction setting",
     "human",
     "user (everydayquinn)",
     "Authoritative on direction, scope, lock/unlock decisions. Other travelers defer to scrawn on contradiction unless scrawn explicitly asks for adversarial input."),
]


# ==================================================================
# FACTS — populated below in seed_facts(conn)
# ==================================================================

def seed_facts(conn: sqlite3.Connection) -> None:
    """Emit all the seed facts: 5-day plan, pinned, trajectory, competing
    plans, pitch drafts, meta observations."""

    # ----------------------------------------------------------------
    # The 5-day plan (the canonical 'claude_terminal' version after
    # session-6 collapse from 6 to 5 days + buffer)
    # ----------------------------------------------------------------
    plan_5day = [
        # (subject, day, title, description, status, depends_on, fallback, verifiability, next_steps[])
        ("plan:5day:day1:pitch", 1,
         "Hallway pitch sentence (~25s)",
         "Draft and lock the ~25s hallway version of the pitch. Thesis line: 'facts are the unit of computation; substrates are anything that produces or consumes them.' Should land for a generalist without requiring CPU knowledge.",
         "in-progress", None, "ship a rougher version; polish in Day 4 README pass",
         "speak it aloud once; it should fit in 25s and a non-CPU person should be able to repeat the gist",
         ["draft 3 candidate sentences", "test out loud with timer", "commit chosen as pitch:hallway:vN fact"]),

        ("plan:5day:day1:facts-db-port", 1,
         "Port facts.db schema + traveler abstraction into project",
         "Adopt the predicates/travelers/facts triple-store from C_Compiler Schema. Extend with discipline mechanisms (mandatory predicate definitions, namespace registry, notes_for_claude JSON, retracts_id link). Done in this very session as corkboard_schema.sql + corkboard.py.",
         "in-progress", None, "if blown, falls back to the existing memory journal pattern (still queryable but less rich)",
         "python3 corkboard.py shows non-zero predicate / traveler / fact counts; v_contradictions returns rows when seeded",
         ["write corkboard_schema.sql (DONE)", "write corkboard.py helpers (DONE)", "write seed_corkboard.py (in progress)", "verify boot summary"]),

        ("plan:5day:day1:cpu-4bit-traveler", 1,
         "cpu_4bit traveler emits state_log into corkboard.db",
         "Write cpu_4bit_traveler.py that runs an existing 4-bit program (the countdown loop is ideal — uses LDA, SUB, JZ, JMP, OUT, HLT) and emits one fact per T-state under traveler='cpu_4bit'. Establishes that the existing CPU is substrate-independence-claim-eligible: same predicate vocabulary that 6502/JVM will later use.",
         "planned",
         "plan:5day:day1:facts-db-port",
         "if blown, ship Day 1 with just the cork-board scaffolding + claim that cpu_4bit traveler is straightforward to add Day 2",
         "SELECT predicate, COUNT(*) FROM v_facts_live WHERE traveler='cpu_4bit' GROUP BY predicate; expect AT_INSN, DELTA, BRANCH, etc.",
         ["read state_log schema (DONE — see schema.sql)", "write cpu_4bit_traveler.py", "run on countdown loop", "verify fact counts"]),

        ("plan:5day:day2:port-6502", 2,
         "Port sim_6502.py + parser_6502 from C_Compiler Schema",
         "Bring populate_6502.py and sim_6502.py over from /home/scrawn/C_Compiler Schema/. Adapt to write into corkboard.db (project) instead of facts.db (Kairos). Keep the predicate names identical so cross-traveler queries work.",
         "planned",
         "plan:5day:day1:facts-db-port",
         "if blown, hand-seed 15-20 6502 facts manually so Day 3 cross-traveler query still has 6502 data to compare against",
         "SELECT subject, predicate FROM v_facts_live WHERE traveler='parser_6502' LIMIT 20; output mirrors what's in Kairos's sigma_6502.db",
         ["copy sim_6502.py + populate_6502.py", "swap output paths to project's corkboard.db", "ingest one 6502 ROM lesson", "verify facts emitted"]),

        ("plan:5day:day2:mine-6502", 2,
         "Run miner/chunk_lab/equiv against the 6502 trace",
         "Use existing analysis stack on the parser_6502 facts. Mined idioms get stored as new chunks in chunks_schema.sql tables; this is finally where the analysis layers earn their keep on a real ISA. Fallback: hand-seed a small idiom catalog if mining is too noisy.",
         "planned",
         "plan:5day:day2:port-6502",
         "hand-seed 15-20 idioms manually; document mining-too-noisy as known limitation in README",
         "SELECT * FROM chunks WHERE traveler='parser_6502'; non-empty",
         ["run miner.py against parser_6502 facts", "run chunk_lab.py to fingerprint", "run equiv.py to find equivalents", "if noisy, hand-seed and note"]),

        ("plan:5day:day3:jvm-traveler", 3,
         "JVM bytecode parser as second substrate",
         "Build a small JVM bytecode parser. ~7 opcodes (iconst, iload, istore, iadd, if_icmpge, goto, ireturn) is the minimal set that proves the substrate-independence claim across stack machines. Predicate dictionary: see notes_for_claude. Same SQL query against cpu_4bit + parser_6502 + parser_jvm should return sensible structurally-identical output.",
         "planned",
         "plan:5day:day1:facts-db-port",
         "cut JVM to trajectory; ship 2-substrate demo (cpu_4bit + parser_6502); 'and the same machinery applies to JVM' goes in trajectory paragraph",
         "SELECT traveler, predicate, COUNT(*) FROM v_facts_live WHERE predicate IN ('AT_INSN','PUSHES_STACK','WRITES_REG','POPS_STACK','BRANCH') GROUP BY traveler, predicate; row exists for each (traveler, predicate) combination across the three substrates",
         ["write tiny Java program (e.g. CountUp)", "compile + javap -c -p", "parse javap output", "emit facts under traveler='parser_jvm'", "verify cross-traveler query"]),

        ("plan:5day:day4:readme", 4,
         "README written, load-bearing artifact for the pitch",
         "The README is the artifact recruiters will read after the hallway pitch. Must contain: thesis line, evidence (CPU + 6502 + (maybe) JVM with the cross-substrate query as proof), trajectory section (full C frontend, JVM-as-third-substrate-if-not-yet, multi-DB axis isolation via schemas, schema-gate replay test), how-to-reproduce, contact.",
         "planned",
         "plan:5day:day3:jvm-traveler",
         "if blown, ship shorter README with thesis + evidence only; trajectory becomes a TODO file",
         "scrawn reads the README cold, can paraphrase the thesis after; non-CPU friend can repeat what the project does in one sentence",
         ["draft README outline", "write thesis section", "write evidence section with cross-substrate query", "write trajectory", "scrawn-cold-read test"]),

        ("plan:5day:day4:web-demo", 4,
         "Cross-substrate query wired into web layer",
         "The existing FastAPI app gets one new endpoint that runs the cross-substrate query and renders results. Audience-facing piece if anyone clicks the GitHub repo and runs locally. Hostable on Fly.io as Day-5 stretch.",
         "planned",
         "plan:5day:day3:jvm-traveler",
         "if blown, demo is the SQL query in the README terminal block, not a live endpoint. Acceptable.",
         "GET /substrate-comparison renders a table with rows from cpu_4bit + parser_6502 + parser_jvm",
         ["add endpoint to app.py", "render HTML or JSON", "wire to existing static/", "manual smoke test"]),

        ("plan:5day:day5:hard-cut", 5,
         "HARD CUT — anything not done by EOD goes in README trajectory paragraph",
         "Day 5 EOD is the hard cut. No new work after this. Existing 121/121 substrate is the floor; everything new is upside. Day 6 is buffer (rest if no slip; catch-up if there is).",
         "planned",
         "plan:5day:day4:readme",
         "no fallback — Day 5 IS the fallback discipline",
         "git log shows last code commit before Day-5 EOD; nothing after Day-5 EOD touches code, only rehearsal",
         ["finalize README", "commit final state", "tag release v0.1 or similar"]),

        ("plan:5day:day5:rehearsal", 5,
         "Pitch rehearsed 5× on camera",
         "Record yourself saying the pitch out loud 5 times. Watch playback; identify which sentences come out garbled. Fix wording or learn delivery. Per session-5 lock: not to memorize, but to find friction.",
         "planned",
         "plan:5day:day1:pitch",
         "if blown, do 3 rehearsals not 5; the rehearsal-existence matters more than the count",
         "5 .mp4 files exist in a rehearsal/ folder; you've watched at least the last one back",
         ["set up phone camera", "say pitch 5 times in a row", "watch back, note garbled lines", "rewrite if needed"]),

        ("plan:5day:day6:buffer", 6,
         "BUFFER — slip absorbs here, otherwise rest + travel + light rehearsal",
         "Day 6 is not a deliverable. It's slack to absorb Day-5 slip. If Day 5 fully shipped, Day 6 is rest, travel, light rehearsal. Sleep floor still 8h non-negotiable.",
         "planned", None, "n/a — this IS the fallback for Day 5",
         "8h sleep happened; if Day-5 slipped, slip is closed by EOD Day 6",
         ["see how Day 5 lands", "adjust accordingly"]),
    ]

    for subject, day, title, desc, status, depends, fallback, verif, next_steps in plan_5day:
        cb.emit(conn, "claude_terminal", subject, "ROADMAP_TITLE", title,
                captured_in_context=SESSION_CTX,
                notes_for_claude={"why_in_plan": "session-6 collapsed 6→5 day arc + buffer"})
        cb.emit(conn, "claude_terminal", subject, "ROADMAP_DESCRIPTION", desc,
                captured_in_context=SESSION_CTX)
        cb.emit(conn, "claude_terminal", subject, "FOR_DAY", str(day),
                captured_in_context=SESSION_CTX)
        cb.emit(conn, "claude_terminal", subject, "STATUS", status,
                captured_in_context=SESSION_CTX,
                notes_for_claude={
                    "encoding": [{"type": "prose", "value": status}],
                    "valid_transitions": "planned → in-progress → shipped | cut | blocked",
                })
        if depends:
            cb.emit(conn, "claude_terminal", subject, "DEPENDS_ON", depends, object_kind="ref",
                    captured_in_context=SESSION_CTX)
        if fallback:
            cb.emit(conn, "claude_terminal", subject, "FALLBACK_PLAN", fallback,
                    captured_in_context=SESSION_CTX)
        cb.emit(conn, "claude_terminal", subject, "VERIFIABILITY", verif,
                captured_in_context=SESSION_CTX)
        for step in next_steps:
            cb.emit(conn, "claude_terminal", subject, "NEXT_STEP", step,
                    captured_in_context=SESSION_CTX)

    # Day 6 buffer flag
    cb.emit(conn, "claude_terminal", "plan:5day:day6:buffer", "IS_BUFFER", "true",
            captured_in_context=SESSION_CTX,
            notes_for_claude={"rationale": "Day 6 is slip-absorption, NOT a deliverable; query 'what's on critical path' should exclude it"})

    # ----------------------------------------------------------------
    # PINNED items (do not propose, do not build)
    # ----------------------------------------------------------------
    pinned = [
        ("pinned:shl-shr",
         "completes the ISA aesthetically but doesn't change what the demo can show; explicit cut in session 5"),
        ("pinned:nes-sprite-ppu",
         "months-of-work demo (PPU, vblank timing, CHR data); eats sprint; was explored and explicitly dropped in AI STUFF.txt session 5"),
        ("pinned:minecraft-mod",
         "months of Forge/Fabric API surface work; off-thesis (static analysis vs substrate-as-database); explicitly dropped"),
        ("pinned:coffee-maker-fastapi",
         "3-4 weeks; not relevant to current pitch trajectory; deferred indefinitely"),
        ("pinned:chunk-synthesis-genetic",
         "research-flavored, not 5-day work; mining-from-corpus replaced this approach as the value-extraction mechanism"),
        ("pinned:8-bus-extension",
         "substrate change; off-thesis; would invalidate existing 121/121 work"),
        ("pinned:immutable-tuple-spawn-per-instruction",
         "state explosion (real CPU state is 100s of bytes; per-instruction snapshots blow disk in seconds); web-Claude waved this away — wrong for execution, fine as conceptual framing"),
        ("pinned:multi-db-attach-compiler",
         "overengineering for 5-day window; session-5 lock + Kairos folder use single-DB-with-traveler instead, which solves the same problem with less operational tax"),
        ("pinned:real-interrupts-beyond-existing",
         "dispatcher already shipped session 3; further interrupt work is scope creep"),
        ("pinned:private-symbolic-claude-language",
         "would degrade audit, defeat the point of the cork-board; explicitly committed against in this session"),
    ]
    for subject, reason in pinned:
        cb.emit(conn, "claude_terminal", subject, "PINNED_REASON", reason,
                captured_in_context=SESSION_CTX,
                notes_for_claude={
                    "rule": "must not re-propose without explicit re-lock by scrawn",
                    "anti_pattern_caught_at": "session 6, after session-5 lock + AI STUFF.txt review",
                })

    # ----------------------------------------------------------------
    # TRAJECTORY items (named for README, not built this sprint)
    # ----------------------------------------------------------------
    trajectory = [
        ("trajectory:full-c-frontend",
         "Tiny C parser + codegen that queries the mined 6502 idiom catalog. The 'next layer up' from the Day-2 mining work. ~weeks of work; named not built."),
        ("trajectory:jvm-as-third-substrate",
         "If Day 3 didn't add the JVM traveler, name it as the obvious next substrate. The predicate dictionary is already drafted; it's the implementation that'd take half a day."),
        ("trajectory:multi-db-axis-isolation-via-schemas",
         "Multi-DB axis isolation as conceptual architecture, but implemented as schemas/prefixes within one corkboard.db rather than separate .db files. Same logical separation, no operational tax."),
        ("trajectory:schema-gate-replay-test",
         "replay_<traveler>.py reconstructs execution from corkboard.db facts alone. If replay matches the original run, the schema is empirically complete. The thesis 'architecture lives in the database' becomes falsifiable."),
        ("trajectory:complete-ide-on-substrate",
         "VSCode-extension or web IDE where the codebase is queryable as facts (functions, calls, types — all rows). Long-term direction; the 'always going to code with SQL' instinct made operational."),
        ("trajectory:meta-evaluator-travelers",
         "Add eye_evaluator / why_evaluator / kairos_evaluator as travelers that emit verdict facts on diffs. Cork-board automatically captures dissent across evaluator stances. Lightweight version of the SESSION_BOOT counsel workflow."),
    ]
    for subject, description in trajectory:
        cb.emit(conn, "claude_terminal", subject, "GOES_IN_TRAJECTORY", description,
                captured_in_context=SESSION_CTX)

    # ----------------------------------------------------------------
    # The three competing gameplans (contradictions visible)
    # ----------------------------------------------------------------
    # kairos_session_baton's view of Day 2 (the lock)
    cb.emit(conn, "kairos_session_baton",
            "plan:5day:day2:deliverable", "CLAIMS",
            "mine 6502 disassembly via miner/lab/equiv (locked session 5)",
            captured_in_context={
                "session_marker": "session_5_2026-05-04_morning",
                "user_state": "scrawn locked the 6-day arc with explicit conditions: 8h sleep, day-5 cut, scope locked",
                "available_evidence": "AI STUFF.txt session 5 transcript",
            },
            notes_for_claude={
                "lock_strength": "high — scrawn used the word 'locked' explicitly",
                "anti_pattern_to_watch": "subsequent travelers re-litigating Day 2 without acknowledging the lock = drift",
            })

    # claude_web's view of Day 2 (drops 6502 mining without acknowledging the lock)
    cb.emit(conn, "claude_web",
            "plan:5day:day2:deliverable", "CLAIMS",
            "JVM bytecode parser (skip 6502 mining entirely)",
            captured_in_context={
                "session_marker": "ChatGPT-Claude conversation ~16:34",
                "missing_context": ["session-5 lock not visible", "C_Compiler Schema folder not visible", "MEMORY.md not visible", "AI STUFF.txt full history not visible"],
                "user_state": "asked 'whats the gameplan?'",
            },
            notes_for_claude={
                "structural_quality": "cleaner shape (one thing, full commit) vs my hedged 3-thing fork plan",
                "fatal_flaw": "doesn't acknowledge it's walking back the lock; same pattern just diagnosed in flagellation analysis",
                "still_useful_pieces": "the JVM predicate dictionary (~7 opcodes), the 'minimal set that proves the claim' framing",
            })

    # claude_terminal's view of Day 2 (synthesis: keep both 6502 mining AND add JVM as Day 3)
    cb.emit(conn, "claude_terminal",
            "plan:5day:day2:deliverable", "CLAIMS",
            "port + run 6502 mining (locked) AND add JVM as Day 3 second-substrate (web-Claude's predicate dictionary)",
            captured_in_context={
                "session_marker": "session_6_2026-05-04",
                "available_context": ["session-5 lock", "C_Compiler Schema folder", "MEMORY.md", "AI STUFF.txt full transcripts", "project source"],
                "synthesis_rationale": "lock + Kairos pre-existing 6502 work + web-Claude's JVM dict = 3-substrate proof of substrate-independence; structurally stronger than either lock-alone or web-Claude-alone",
            },
            notes_for_claude={
                "what_changes_if_jvm_blown": "ship 2-substrate demo (cpu_4bit + 6502); JVM goes in trajectory",
                "what_changes_if_6502_port_blown": "harder cut; existing 121/121 + thesis line is the demo, JVM becomes the visible second substrate",
                "trade_made_explicit": "kept 6502 because Kairos folder pre-built half of it; without that pre-existing work I'd have agreed with web-Claude",
            })

    # ----------------------------------------------------------------
    # Pitch sentence drafts (the load-bearing pitch-section)
    # ----------------------------------------------------------------
    pitches = [
        ("pitch:hallway:v1",
         "I built a substrate where the architecture of a computer lives in a SQL database — RAM, microcode, registers, execution log, all queryable rows. Same predicate vocabulary now applies to a 6502 mined from a real ROM, and to JVM bytecode. The architecture isn't in code. It's in the schema.",
         "v1 — first draft, ~30s spoken; needs trim",
         {
             "audience": "technically-curious generalist at Web Summit",
             "what_it_lands": "the unusual claim ('lives in SQL'), the evidence (built 4-bit CPU, mined real ROM, hits JVM)",
             "what_it_misses": "the trajectory (compiler) — README does that work",
             "to_test": "say aloud with timer; if >25s, cut the JVM clause",
         }),
        ("pitch:hallway:v2",
         "Most computers hide their architecture in code. Mine lives in a SQL schema — the wires, the RAM, the microcode, the execution log, all rows you can SELECT. The same query works on a 4-bit CPU I built and on a 6502 mined from a real ROM. Same machinery applies to JVM bytecode.",
         "v2 — leans on contrast ('most CPUs hide ... mine lives in') for non-technical legibility; same claim",
         {
             "audience": "non-CPU generalist (most of Web Summit)",
             "what_it_lands": "the contrast hook (most computers vs mine), the evidence",
             "what_it_misses": "what 'mined from a real ROM' means — but they don't need to know",
             "to_test": "non-technical friend repeats the gist after one hearing",
         }),
        ("pitch:hallway:v3",
         "Self-taught from manual labor. I treat computer architecture as a database problem — wires, RAM, microcode, all rows you can SELECT. Built a 4-bit CPU that way; same machinery now reads 6502 ROMs and JVM bytecode. The architecture lives in the schema, not the code.",
         "v3 — opens with the candidate-as-lead frame from session-5 pitch goal",
         {
             "audience": "recruiters / technical hiring managers specifically",
             "what_it_lands": "the candidate signal (manual labor → SQL → CPU) AND the technical claim",
             "what_it_misses": "less elegant than v2; more stuff competing for 25s",
             "to_test": "recruiter-cold; would they ask a follow-up?",
         }),
    ]
    for subject, text, version_note, notes in pitches:
        cb.emit(conn, "claude_terminal", subject, "ROADMAP_TITLE", "Hallway pitch draft",
                captured_in_context=SESSION_CTX)
        cb.emit(conn, "claude_terminal", subject, "VERSION", version_note,
                captured_in_context=SESSION_CTX)
        cb.emit(conn, "claude_terminal", subject, "AUTHOR", "claude_terminal",
                captured_in_context=SESSION_CTX)
        cb.emit(conn, "claude_terminal", subject, "ROADMAP_DESCRIPTION", text,
                captured_in_context=SESSION_CTX,
                notes_for_claude=notes)

    # ----------------------------------------------------------------
    # Meta-architecture observations (the load-bearing thesis lines)
    # ----------------------------------------------------------------
    cb.emit(conn, "claude_terminal", "meta:thesis-line:facts-as-substrate",
            "ROADMAP_DESCRIPTION",
            "The architecture lives in a database is the surface claim. The deeper claim: facts are the unit of computation; a substrate is anything that produces or consumes them. The 4-bit CPU emits facts; parser_6502 emits facts; parser_jvm emits facts; even the cork-board (decisions, contradictions) emits facts. Same schema across all of them. Substrate-independence is not aspiration; it's a SQL query.",
            captured_in_context=SESSION_CTX,
            notes_for_claude={
                "where_this_came_from": "session-6 synthesis after C_Compiler Schema review + JVM-bytecode discussion + cork-board design",
                "load_bearing_for": ["pitch:hallway:*", "README thesis section", "trajectory:meta-evaluator-travelers"],
                "falsifiability": "if same predicate vocabulary doesn't return sensible output across cpu_4bit + parser_6502 + parser_jvm, this claim is false",
            })

    cb.emit(conn, "claude_terminal", "meta:human-ai-boundary",
            "ROADMAP_DESCRIPTION",
            "Architecture commitment: SQL is the load-bearing substrate (deterministic, queryable, durable). AI (Claude) is the user-friendly layer over it (lossy, helpful, replaceable). User never sees SQL unless they want to. This inverts the typical AI-tooling pitch (AI = smart, code = dumb-but-fast) into a healthier separation: AI is the interface, SQL is the truth.",
            captured_in_context=SESSION_CTX,
            notes_for_claude={
                "scrawn_articulated": "session 6, message before cork-board build started",
                "implication_for_readme": "this paragraph belongs in the README's 'how I think about code' section, not just the thesis",
                "design_consequence": "rich notes_for_claude blobs are for me; v_facts_live + Claude translation is for scrawn",
            })

    # ----------------------------------------------------------------
    # Rules / lessons codified into the schema (so they don't drift)
    # ----------------------------------------------------------------
    rules = [
        ("rule:no-private-symbolic-language",
         "Do not invent symbolic notation legible only to Claude. Rich structured records yes; opaque-to-user no.",
         "Opaque encoding defeats audit. If scrawn can't read the memory, scrawn can't catch Claude's drift, and Claude drifts. Same failure mode as the Kairos torus cosmology."),
        ("rule:flat-affect-on-correction",
         "When corrected, respond flat. Sycophancy and flagellation are both evasion of analysis. 'You're right, here's the correction' beats 'OH FUCK YOU'RE RIGHT'.",
         "Both high-amplitude responses (positive and negative) substitute performance for thought. Flat affect signals analysis is happening."),
        ("rule:autonomy-on-self-verifiable-work",
         "When scrawn grants autonomy ('freely fuck around since self-verifiable'): don't pause for tactical confirmations. Verify with the test suite, not the user. Still surface big architectural pivots.",
         "scrawn explicitly fatigued by chatty check-ins on simple stuff. Tactical decisions on self-verifiable work waste cycles; architectural pivots warrant explicit confirmation."),
        ("rule:lock-respect",
         "When scrawn has explicitly locked a plan, do not propose changes that walk it back without naming the walkback. Synthesis is allowed; silent retreat is not.",
         "session-5 lock was being implicitly walked back by web-Claude's gameplan; the walkback was the failure mode, not the alternative direction. Surface the trade explicitly."),
        ("rule:rich-records-not-summaries",
         "Memory storage preserves competing claims, evidence, alternatives, and provenance. Synthesis happens at READ time, not WRITE time.",
         "Synthesizing decisions into one-line summaries at write time loses nuance Claude would want back at read time. Decompose; preserve; query."),
    ]
    for subject, text, rationale in rules:
        cb.emit(conn, "claude_terminal", subject, "RULE_TEXT", text,
                captured_in_context=SESSION_CTX)
        cb.emit(conn, "claude_terminal", subject, "RULE_RATIONALE", rationale,
                captured_in_context=SESSION_CTX)


def main():
    conn = cb.bootstrap(DB)

    # Vocabulary registration first (mechanism #6: vocab before facts)
    for prefix, definition, example in NAMESPACES:
        cb.register_namespace(conn, prefix, definition, example)
    for name, domain, range_, card, definition, examples in PREDICATES:
        cb.register_predicate(conn, name, domain, range_, card, definition, examples)
    for name, purpose, role, source, note in TRAVELERS:
        cb.register_traveler(conn, name, purpose, role, source, note)
    conn.commit()

    # Then facts
    seed_facts(conn)
    conn.commit()

    # Boot summary as verification
    summary = cb.boot_summary(conn)
    print(f"namespaces: {len(summary['namespaces'])}")
    print(f"predicates: {len(summary['predicates'])}")
    print(f"travelers:  {len(summary['travelers'])}")
    print(f"plan rows:  {len(summary['plan'])}")
    print(f"contradictions: {len(summary['contradictions'])}")
    print(f"pinned: {len(summary['pinned'])}")
    print(f"trajectory: {len(summary['trajectory'])}")
    print(f"fact counts: {summary['fact_counts']}")
    conn.close()


if __name__ == "__main__":
    main()
