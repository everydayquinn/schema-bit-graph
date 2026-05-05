# DATABASES.md — single-file index of every database touched by this project

**Maintained actively by Claude. Edit this file every time a database is created, retired, or restructured.** This is the cork-board for cork-boards: where to find any data, what shape it's in, who writes to it, and how the various stores relate.

If you're future-Claude reading this at session start: **this file + `corkboard.db` together give you the complete substrate map.** Run `python3 corkboard.py corkboard.db` for the live cork-board summary; this file tells you which OTHER stores exist and how they fit.

---

## Maintenance discipline

- **One row per database**, with current row counts when feasible
- **Categorize by ROLE**, not by location (substrate / meta / external / archive)
- **When a DB is retired**, move it to the "Retired" section with a one-line note about why and when — do not delete its row
- **When schema changes**, update the schema-fingerprint summary
- **When a DB grows new tables**, add them to the table list
- **Verify counts on session boot** with the boot snippet at the bottom of this file

---

## SUBSTRATE — fact-producing stores (facts.db pattern; read-heavy at query, append-heavy at emit)

| DB path | role | tables | live rows (last verified) | written by | read by | purpose |
|---|---|---|---|---|---|---|
| `./corkboard.db` | meta-substrate | `namespaces`, `predicates`, `travelers`, `facts` + 6 views (`v_facts_live`, `v_contradictions`, `v_plan_today`, `v_pinned`, `v_trajectory`, `v_competing_plans`) | ~770+ facts (S6 EOD); 17 namespaces; 46 predicates; 7 travelers | `seed_corkboard.py` + `seed_stress_candidates.py` + `seed_progress.py` (vocab + plan + state); `cpu_4bit_traveler.py`, `parser_6502.py`, `sim_6502.py` (substrate fact emission); future `parser_jvm.py` / `parser_cave.py` | `corkboard.py boot_summary`, ad-hoc SQL | The project's gameplan, decisions, contradictions, and substrate facts. Same triple-store as Kairos `facts.db`, extended with discipline mechanisms (mandatory predicate definitions, namespace registry, `notes_for_claude` JSON, retracts_id link). **Rebuild from scratch:** `rm corkboard.db && python seed_corkboard.py && python seed_stress_candidates.py && python seed_progress.py && python cpu_4bit_traveler.py countdown && python parser_6502.py kit_6502_lessons/01_basic.s && python parser_6502.py kit_6502_lessons/02_interrupt.s && python sim_6502.py kit_6502_lessons/01_basic.s && python sim_6502.py kit_6502_lessons/02_interrupt.s --irq-at-step 3 --scenario 02_irq3` |
| `./cpu.db` | substrate (transient) | `control_lines`, `mc_fetch`, `mc_lda`, `mc_add`, `mc_sub`, `mc_sta`, `mc_jmp`, `mc_out`, `mc_hlt`, `mc_nop`, `mc_and`, `mc_or`, `mc_xor`, `mc_not`, `mc_jz`, `opcodes`, `ram`, `registers`, `state_log` + 3 views | rebuilt every CPU run; not a persistent store | `cpu.py CPU.run()`, `mirror.py rebuild()` | `cpu.py show_*`, `cpu_4bit_traveler.py per_cycle_summary` | The 4-bit CPU's working substrate. Microcode tables drive `fire()`; `state_log` is the append-only execution archive that `cpu_4bit_traveler.py` re-emits as facts into corkboard.db. |
| `./test_*.db` | test fixtures (8 files) | mirror of cpu.db / corkboard.db schemas | rebuilt per test-suite run | `test_cpu.py`, `test_asm.py`, `test_compose.py`, `test_miner.py`, `test_chunk_lab.py`, `test_generalize.py`, `test_equiv.py`, `test_interrupts.py`, `test_corkboard.py`, `test_app.py` | the test files themselves | Per-suite isolated state; never committed (in `.gitignore`). |

## META — cross-session memory (persona-level, not project-level)

| DB path | role | tables | live rows | written by | read by | purpose |
|---|---|---|---|---|---|---|
| `~/.claude/projects/-home-scrawn-Desktop-Schema-bit-graph/memory/journal.db` | persona memory | `entities`, `facts`, `relations`, `decisions`, `open_questions`, `lessons`, `sessions`, `session_touches` + 4 views | ~6 sessions, ~22 lessons, ~25 facts, 4 open questions | `MEMORY.md` boot protocol writes; manual SQL inserts during sessions | `MEMORY.md` boot protocol reads at session start | Persona-level memory across sessions of THIS project. User facts, collaboration rules, project arc, cross-session decisions. Schema mirrors the supersession pattern (every fact has `superseded_by`). |

## EXTERNAL — Kairos folder (`~/C_Compiler Schema/`); mirrored read-only at `/mnt/external/Code_StuffnThings/SIGMA/`)

These are the user's prior project's databases. Not modified by this project; **referenced for code/schema lineage and for porting (sim_6502.py, populate_6502.py).**

| DB path | role | tables | live rows | written by | purpose |
|---|---|---|---|---|---|
| `~/C_Compiler Schema/facts.db` | substrate (Kairos) | `travelers`, `predicates`, `facts` + `v_facts_live` | 4643 facts; 8 travelers; 44 predicates | `populate_facts.py`, `populate_6502.py`, `populate_x86.py`, `sim.py`, `sim_6502.py`, `sim_qct0.py`, `populate_roadmap.py`, `populate_claude_ctx.py` | The original facts.db schema this project ported from. **Reference implementation** for the multi-traveler pattern. |
| `~/C_Compiler Schema/sigma_x86.db` | substrate (Kairos) | `programs`, `instructions`, `reg_effects` + `v_insn` | 3 programs / 48 instructions / 95 reg_effects | `populate_x86.py` (capstone) | Canonical x86 disassembly store; populates `parser_x86`-flavoured facts into `facts.db`. |
| `~/C_Compiler Schema/sigma_6502.db` | substrate (Kairos) | `programs`, `instructions` + `v_insn` | 2 programs / 14 instructions | `populate_6502.py` (py65) | Canonical 6502 disassembly store. **The thing we'd port for Day 2.** |
| `~/C_Compiler Schema/compiler_schema.sql` | (postgres dump, not live SQLite) | `architectures`, `assembly_translations`, `c_source_constructs`, `categories`, `compilers`, `optimization_levels` | n/a (dump) | (originally Postgres) | C-compiler-as-database schema; defines the trajectory's C-frontend pipeline. Referenced in README trajectory. |
| `~/C_Compiler Schema/stack.db` | substrate (Kairos) | (kanji-table-derived stack machine) | needs verification | `build_stack_db.py` from `KANJI_TABLE.md` | Stack-machine artifact; possibly relevant if we ever do a JVM-style traveler from scratch. Not currently load-bearing. |

## ARCHIVE / RETIRED

(empty — nothing retired yet)

---

## How the stores relate

```
                         ┌──────────────────────────┐
                         │   journal.db             │  persona memory
                         │   (cross-session, cross- │  (lives in ~/.claude/...)
                         │    project user facts +  │
                         │    collaboration rules)  │
                         └────────────┬─────────────┘
                                      │ MEMORY.md boot protocol
                                      ▼
                         ┌──────────────────────────┐
                         │   corkboard.db           │  THE project's
                         │   (5-day plan,           │  cork-board
                         │    competing AI plans,   │  (this project)
                         │    substrate facts)      │
                         │                          │
                         │   travelers:             │
                         │     cpu_4bit             │
                         │     parser_6502 (Day 2)  │
                         │     parser_jvm  (Day 3)  │
                         │     parser_cave (?)      │
                         │     claude_terminal      │
                         │     claude_web           │
                         │     kairos_session_baton │
                         │     scrawn               │
                         └────────────▲─────────────┘
                                      │
                         emits facts via corkboard.py emit()
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
              ▼                       ▼                       ▼
    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
    │  cpu.db         │    │ (port from      │    │ (planned)       │
    │  (transient;    │    │  ~/C_Compiler   │    │  Cave Game .db  │
    │   state_log →   │    │  Schema/sigma_  │    │  / JVM .class   │
    │   facts via     │    │  6502.db)       │    │  static + run-  │
    │   cpu_4bit_     │    │                 │    │  time           │
    │   traveler.py)  │    │                 │    │                 │
    └─────────────────┘    └─────────────────┘    └─────────────────┘

         ╭──── KAIROS REFERENCE ────╮
         │  ~/C_Compiler Schema/    │   read-only reference;
         │    facts.db              │   we ported the schema +
         │    sigma_x86.db          │   borrow the populate_*.py
         │    sigma_6502.db         │   shape; do not modify.
         │    stack.db              │
         ╰──────────────────────────╯
```

## Stress-test substrate map (what each candidate substrate exposes)

The **architecture** (predicates + travelers + cork-board) is locked. **Substrates are stress-test cases**, not pivots. New substrates explore which architectural limits get exposed first. Track each candidate here so it's clear what's been probed.

| substrate | status | stress dimension | tractability | notes |
|---|---|---|---|---|
| cpu_4bit | shipped Day 1 | baseline; toy register machine | trivial | 157 facts on countdown; 32 tests pass |
| 6502 — parser_6502 (static) | **shipped Day 2** | real-software shape via py65 disassembler | low (port from Kairos) | 114 facts on 01_basic.s + 02_interrupt.s; cross-traveler query verified |
| 6502 — sim_6502 (runtime) | **shipped Day 2** | per-step register diff + memory-read/write + IRQ injection | low (port from Kairos) | 106 facts on 01_basic + 02_irq3; mem-read recursion bug-fix carried over from Kairos S160 |
| JVM toy program (Hello-World style) | planned Day 3 | stack-machine vocab (PUSHES_STACK / POPS_STACK / READS_LOCAL) | low (~7 opcodes via javap) | predicate dict already in seed_corkboard.py |
| Cave Game (Minecraft Classic, JVM) | **probed-tractable Day 2** (Day 3 candidate) | real-legacy-software shape; runtime + bytecode dual-traveler from one source; cultural pull for pitch | low-to-medium — Gradle KTS + LWJGL 2.9.3 (Maven Central, Linux x86_64 natives bundled); 13 .java files / 1-2 KLOC; ~half-day | github.com/thecodeofnotch/rd-132211 (16★, 2021); JDK 8-17 known-good; risk: JDK 21+ may need --add-opens |
| Multi-agent (Colonies-style) | candidate; deferred | N concurrent fact producers into one schema | unknown — any sim with N entities | watch for: contention on `fact_unique_live` index? |
| Python bytecode | candidate; trajectory | dynamic dispatch, frame stack, generators | medium (dis module exists) | could use `sys.settrace` for runtime traveler |
| WebAssembly | candidate; trajectory | stack-machine variant; cross-platform reproducible | medium-high (wabt tools) | not in scope for 5-day |
| Self-modifying / GA-evolved code | candidate; trajectory | schema handles code that mutates between generations | high (build genetic harness) | not in scope; named in trajectory |
| x86 (parser_x86 from Kairos) | available | variable-length, register, real software via capstone | known low (port-not-build) | sigma_x86.db has 48 insns, 95 reg_effects |

---

## Boot-time verification snippet

Run at session start to confirm the index matches reality:

```bash
cd "/home/scrawn/Desktop/Schema bit graph"
echo "=== project DBs (live row counts) ==="
for db in corkboard.db cpu.db; do
  if [ -f "$db" ]; then
    echo "--- $db ---"
    sqlite3 "$db" "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'" | while read t; do
      n=$(sqlite3 "$db" "SELECT COUNT(*) FROM \"$t\"")
      echo "  $t: $n rows"
    done
  fi
done

echo "=== persona memory ==="
sqlite3 "/home/scrawn/.claude/projects/-home-scrawn-Desktop-Schema-bit-graph/memory/journal.db" \
  "SELECT 'sessions:'||COUNT(*) FROM sessions
   UNION ALL SELECT 'lessons:'||COUNT(*) FROM lessons
   UNION ALL SELECT 'facts:'||COUNT(*) FROM facts
   UNION ALL SELECT 'open_questions:'||COUNT(*) FROM open_questions WHERE resolved_on IS NULL"

echo "=== Kairos reference (read-only) ==="
sqlite3 "/home/scrawn/C_Compiler Schema/facts.db" \
  "SELECT 'travelers:'||COUNT(*) FROM travelers
   UNION ALL SELECT 'predicates:'||COUNT(*) FROM predicates
   UNION ALL SELECT 'facts:'||COUNT(*) FROM facts WHERE retracted_at IS NULL"
```

---

_Last updated by Claude during session 6 (2026-05-04) on substrate-stress reframe. Active maintenance — modify whenever DBs change._
