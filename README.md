# schema-bit-graph

> Most computers hide their architecture in code. Mine lives in a SQL schema — every wire, register, RAM cell, and execution step is a row you can `SELECT`. The same machinery now reads 6502 ROMs and JVM bytecode. The architecture isn't in the program. It's in the database.

Self-taught from manual labor. Three-month SQL course was the only formal training.

---

## The claim

Computation is fact-production. A substrate is anything that produces or consumes facts. Prove it across substrates that have nothing in common — different word sizes, different register counts, different execution models — and the claim becomes a SQL query, not a slogan.

One predicate vocabulary. Four travelers. Three fundamentally different ISA shapes. Same query works on all of them.

## The four substrates

| traveler      | ISA shape                              | what it covers                                                                                                                          |
|---------------|----------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| `cpu_4bit`    | 4-bit register machine, in-house       | 13 opcodes, Z flag, 21 control lines. Microcode lives in SQL tables. Countdown loop runs 5 iterations using `JZ` and halts.              |
| `parser_6502` | 8-bit register machine, static         | py65-driven disassembly. 14 instructions across two lesson files.                                                                        |
| `sim_6502`    | 8-bit register machine, runtime        | py65 execution trace. Per-step register diff, memory read/write capture, IRQ injection.                                                  |
| `parser_jvm`  | JVM stack machine, static              | `javap`-driven bytecode disassembly. `CountUp.java` exercises 7 target opcodes (iconst / iload / istore / iadd / if_icmpge / goto / ireturn). |

## Why the same SQL works on three different ISAs

A 4-bit register machine, an 8-bit register machine, and a JVM stack machine are different architectures. So why does one query return parallel results across all three?

Because the predicates were picked at the level of **what happens**, not **how**.

- `AT_INSN` — *an instruction was executed at this step*
- `HAS_MNEMONIC` — *this instruction has this textual name*
- `BRANCH` — *control flow went somewhere (linear / taken:0xHH / return / halt)*

Those describe events that exist on any machine with instructions and control flow. They don't depend on whether you have eight registers or a value stack. They don't care how wide the word is.

Where substrates genuinely diverge, the schema accepts both. `WRITES_REG` only fires for register machines. `STACK_DELTA` only fires for stack machines. They sit alongside each other in the same database; queries focused on the universal predicates work across everything; queries focused on substrate-specific predicates filter naturally.

The result: you don't write three different schemas. You write one, with predicates chosen at the right level of abstraction.

## The proof

```sql
SELECT traveler, predicate, COUNT(*) AS n
FROM v_facts_live
WHERE predicate IN ('AT_INSN', 'HAS_MNEMONIC', 'BRANCH')
GROUP BY traveler, predicate
ORDER BY traveler, predicate;
```

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

The query has no idea what 4-bit, 6502, or JVM means. It just asks the database. Substrate-independence isn't asserted; it's queried.

## A cheat engine for computation

A cheat engine doesn't run the game differently — it reads memory, interprets state, maps relationships between values. This system does the same thing one layer up.

Instead of *"what's HP at memory address X?"*, it answers *"what is the state evolution of step N through cycles M..M+1?"*

It doesn't simulate. It traces and reveals.

## Architecture

Each traveler emits one row per fact into a SQLite database. The schema enforces a few things directly: predicates have to be registered with a definition before any fact can use them, subjects have to match a registered namespace prefix, and supersession is explicit — no edits, only retractions that link to what they replace.

That's the whole architecture. Python coordinates the ingestion. SQL holds the truth.

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

Then run the cross-substrate query above. Or run the test suite:

```bash
python test_corkboard.py    # 49 tests covering schema discipline + substrate facts
python test_cpu.py          # 31 tests for the 4-bit CPU itself
# 7 more substrate suites + the FastAPI layer = 182 tests total
```

The substrate tests encode hand-computed expected facts as assertions, so when the disassembler emits something at the wrong offset (which happened twice during development), the test suite catches it before it ships.

## Where this is going

- **More substrates.** Python bytecode, WebAssembly, x86 via capstone. Each tests the predicate vocabulary against a different execution model.
- **Schema-gate replay.** A small script that reconstructs execution from the database alone. If replay matches the original run, the schema is empirically complete. Falsifiability for the whole thesis.

## How I think about code

SQL is the load-bearing substrate — deterministic, queryable, durable. Python is the interface. The schema isn't just storage; the schema is the program.

## Tools

- [py65](https://github.com/mnaberez/py65) — 6502 simulator (MIT)
- [`javap`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html) — JVM bytecode disassembler (ships with the JDK)
- SQLite — bundled with Python
- AI assistance for tedium and second opinions.

## Contact

[github.com/everydayquinn](https://github.com/everydayquinn) — currently building toward backend / data engineering / contract roles.

---

*Self-taught from manual labor. Three-month SQL course. Built this anyway.*
