# schema-bit-graph

> Most computers hide their architecture in code. Mine lives in a SQL schema — every wire, register, RAM cell, and execution step is a row you can `SELECT`. The same machinery now reads 6502 ROMs and JVM bytecode. The architecture isn't in the program. It's in the database.

Self-taught from manual labor. Three-month SQL course was the only formal training. This is what came out.

---

## The claim

Computation is fact-production. A substrate is anything that produces or consumes facts. Prove it across substrates that have nothing in common — different word sizes, different register counts, different execution models — and the claim becomes a SQL query, not a slogan.

That's the demo. One predicate vocabulary. Four travelers. Three fundamentally different ISA shapes. Same query works on all of them.

## The four substrates currently shipping

| traveler      | ISA shape                              | what it covers                                                                                                                            |
|---------------|----------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| `cpu_4bit`    | 4-bit register machine, in-house       | 13 opcodes (LDA / ADD / SUB / STA / JMP / OUT / HLT / NOP / AND / OR / XOR / NOT / JZ), Z flag, 21 control lines. Microcode lives in SQL tables. The countdown loop runs 5 iterations using `JZ` and halts. |
| `parser_6502` | 8-bit register machine, static         | py65-driven disassembly of 6502 lessons. 14 instructions across two `.s` files.                                                            |
| `sim_6502`    | 8-bit register machine, runtime        | py65 execution trace with `ObservableMemory` hooks. Per-step register diff, `MEM_READ` / `MEM_WRITE` capture, IRQ injection demo.        |
| `parser_jvm`  | JVM stack machine, static              | `javap`-driven bytecode disassembly. Calibration program (`CountUp.java`) exercises 7 target opcodes (iconst / iload / istore / iadd / if_icmpge / goto / ireturn). |

## The proof

```sql
SELECT traveler, predicate, COUNT(*) AS n
FROM v_facts_live
WHERE predicate IN ('AT_INSN', 'HAS_MNEMONIC', 'BRANCH')
GROUP BY traveler, predicate
ORDER BY traveler, predicate;
```

Returns:

```
traveler      predicate     n
cpu_4bit      AT_INSN       17
cpu_4bit      BRANCH        17
cpu_4bit      HAS_MNEMONIC   6
parser_6502   HAS_MNEMONIC  14
parser_jvm    BRANCH         5
parser_jvm    HAS_MNEMONIC  26
sim_6502      AT_INSN       14
sim_6502      BRANCH        15
```

The query has no idea what 4-bit, 6502, or JVM means. It just asks the database. **Substrate-independence isn't asserted; it's queried.**

## A cheat engine for computation

A cheat engine doesn't run the game differently — it reads memory, interprets state, maps relationships between values. This system does the same thing one layer up.

Instead of *"what's HP at memory address X?"*, it answers *"what is the state evolution of step N through cycles M..M+1?"*

It doesn't simulate. It traces and reveals.

## Architecture

The cork-board (`corkboard.db`) is one SQLite file holding:

- **`predicates`** — 48 named relations (`AT_INSN`, `BRANCH`, `STACK_DELTA`, `MEM_WRITE`, …). Each has a definition + canonical examples. **Mandatory and enforced at schema level.**
- **`travelers`** — 7 fact producers, classified `substrate` / `meta` / `external` / `human`. Each substrate traveler emits the predicates that make sense for its ISA; the discipline keeps the vocabulary unified across them.
- **`facts`** — the triple store: `(traveler, subject, predicate, object)` with provenance (`captured_in_context`), nuance (`notes_for_claude` JSON), and supersession (`retracts_id` linking to the prior fact this one replaces). 750+ live facts.
- **`namespaces`** — 17 registered subject prefixes (`insn:`, `step:`, `prog:`, `plan:`, `meta:`, …). A `BEFORE INSERT` trigger rejects subjects that don't match.

Six discipline mechanisms baked into the schema (constraints, not conventions):

1. Mandatory predicate definitions + examples (`NOT NULL`)
2. Namespace registry; trigger rejects unregistered prefixes
3. Mandatory provenance (traveler + context + timestamp)
4. No edits — only retraction with explicit `retracts_id` link; trigger marks the prior fact retracted and links back
5. Encoding tags inside `notes_for_claude` JSON (so future readers know how to parse each piece)
6. Boot protocol reads vocabulary + namespaces FIRST, before any data — so meaning is established before interpretation

Future-me reading this database six months from now can't drift on what predicates mean, can't quietly redefine `AT_INSN`, can't synthesize away competing claims. The schema enforces it.

## Reproducing it

```bash
git clone https://github.com/everydayquinn/schema-bit-graph
cd schema-bit-graph
pip install py65   # only external dep
python seed_corkboard.py
python seed_stress_candidates.py
python seed_progress.py
python cpu_4bit_traveler.py countdown
python parser_6502.py kit_6502_lessons/01_basic.s
python parser_6502.py kit_6502_lessons/02_interrupt.s
python sim_6502.py kit_6502_lessons/01_basic.s
python sim_6502.py kit_6502_lessons/02_interrupt.s --irq-at-step 3 --scenario 02_irq3
javac -d kit_jvm_lessons kit_jvm_lessons/src/CountUp.java
python parser_jvm.py kit_jvm_lessons/CountUp.class
```

Then:

```bash
sqlite3 corkboard.db "SELECT traveler, predicate, COUNT(*) AS n
                      FROM v_facts_live
                      GROUP BY traveler, predicate
                      ORDER BY traveler, predicate;"
```

Verify the discipline mechanisms hold:

```bash
python test_corkboard.py    # 49 tests — schema constraints, retraction, JSON round-trip, substrate-fact correctness
python test_cpu.py          # 31 tests — the 4-bit CPU itself
python test_asm.py          # 12 tests
python test_compose.py      # 18 tests
python test_miner.py        #  8 tests
python test_chunk_lab.py    # 12 tests
python test_generalize.py   # 10 tests
python test_equiv.py        #  7 tests
python test_interrupts.py   # 11 tests
python test_app.py          # 12 tests — the FastAPI web layer
```

182 tests total. They include hand-computed expected facts encoded as assertions, so when I miscount instruction sizes (which happened twice while building this), the test suite catches me.

## Where this is going

The system as it exists is the **tracer** — it captures any computation as queryable structure. The natural next layer is the **generator**: take traced facts and emit code from them. The closed loop is *trace → structure → regeneration*.

Concrete next directions, in roughly increasing scope:

- **Schema-gate replay test.** A `replay_<traveler>.py` that reconstructs execution from the cork-board's facts alone. If replay matches the original run, the schema is empirically complete. Falsifiability for the whole thesis.
- **More substrates.** Python bytecode (dynamic dispatch + frame stack), WebAssembly (cross-platform reproducible), x86 via capstone (variable-length, register-machine real-software shape). Each tests the predicate vocabulary against a different execution model. The architecture is locked; substrates are stress tests, not commitments.
- **C frontend via mined idioms.** A small C parser whose codegen queries the idiom catalog (compressed pattern recognition over `parser_6502` traces) instead of hand-writing emit rules. The same pattern at the microcode layer is the same pattern at the idiom layer is the same pattern at the C layer — each layer is evidence the next is achievable.
- **Multi-DB axis isolation via schemas (not separate files).** Compiler IRs as separate schema namespaces inside one cork-board. The relational equivalent of LLVM's pass infrastructure.

None of these are required for the current claim. They're where the same machinery extends.

## Why these specific substrates

Each substrate exposes a different stress dimension:

- `cpu_4bit` — baseline. In-house, fully controlled. If the architecture doesn't hold here, it's wrong.
- `parser_6502` (static) and `sim_6502` (runtime) — same ISA from two angles. Tests whether static-disassembly facts and runtime-trace facts can share a vocabulary cleanly. The runtime traveler emits `MEM_READ` / `MEM_WRITE` / `CYCLES` / `INTERRUPT` predicates the static parser doesn't; the static parser emits `HAS_BYTES` / `HAS_SIZE` the runtime traveler doesn't. They overlap on the predicates that make sense for both.
- `parser_jvm` — fundamentally different ISA shape. Stack machine, not register machine. The same architecture has to make sense across machine families, not just within one.

Substrates I haven't built yet (Python bytecode, WebAssembly, x86) test additional axes. The framework supports adding them. They're not necessary for the current proof.

## How I think about code

SQL is the load-bearing substrate — deterministic, queryable, durable. Python (or any other language) is the friendly translation layer over it. The schema isn't just storage; **the schema is the program.**

This inverts the typical AI-tooling pitch (AI = smart, code = dumb-but-fast) into a healthier separation: SQL is the truth, the language on top is the interface. You should never have to write SQL to use this. But if you want to, the database is honest about what's there.

## What's NOT in this repo

- A C frontend (named in the trajectory; not yet built).
- A live deployment. The README is the artifact; running locally is straightforward.
- A consumer-facing app. This isn't a product. It's evidence.
- Tutorial code. Every line earns its keep.

## Tools used

- [py65](https://github.com/mnaberez/py65) — 6502 simulator (MIT)
- [`javap`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html) — JVM bytecode disassembler (ships with the JDK)
- SQLite — bundled with Python
- AI assistance for tedium and second opinions (Claude in the IDE for implementation; ChatGPT for stress-testing the architecture). Commit messages name which sessions did what. The thinking is mine; the typing was assisted.

## Contact

[github.com/everydayquinn](https://github.com/everydayquinn) — currently building toward backend / data engineering / contract roles.

---

*Self-taught from manual labor. Three-month SQL course. Built this anyway.*
