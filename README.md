# schema-bit-graph

A fact-store for source code. Every class, method, field, parameter, local, call, and type reference becomes a row you can `SELECT`. The relationships are computed at query time — there's no graph stored anywhere; the graph is whatever the SELECT just asked for.

The predicate vocabulary used here came out of a 4-bit CPU built in SQL first ([schema-bit-cpu](https://github.com/everydayquinn/schema-bit-cpu) / [schema-bit-isa](https://github.com/everydayquinn/schema-bit-isa)). It turned out to apply almost unchanged to a real Java codebase, so I pointed it at one.

## Shared Ontology Model

This repo is one of five independent substrates that share a single **predicate vocabulary** recorded in a SQLite fact-store. They are not layers in an execution stack — none feeds another at runtime. The integration surface is the predicate ontology, not a pipeline.

The five substrates:

- [schema-bit-cpu](https://github.com/everydayquinn/schema-bit-cpu) — 4-bit register machine. Emits execution-trace facts (control-line firings, register/RAM mutations, T-states) into the shared predicate space. The substrate where the vocabulary first took shape.
- [schema-bit-isa](https://github.com/everydayquinn/schema-bit-isa) — 4-bit + 6502 (py65) register machines. Emits normalized instruction-level facts; the vocabulary travels across two distinct ISAs.
- [schema-bit-jvm](https://github.com/everydayquinn/schema-bit-jvm) — JVM bytecode (static, via `javap`) plus class-load runtime traces (via `-Xlog:class+load`). Stack-machine instruction facts and real-runtime observation facts.
- [schema-bit-graph](https://github.com/everydayquinn/schema-bit-graph) *(this repo)* — Java source via `javalang` AST. Emits structural facts into the shared predicate space: classes, methods, fields, calls, type references.
- [macro-schema-dsl](https://github.com/everydayquinn/macro-schema-dsl) — planned future *consumer* of the shared fact-store (query-driven code assembly into existing fact-indexed codebases). Stake in the ground; no code yet.

**Shared predicate vocabulary** (representative): `HAS_MNEMONIC`, `BRANCH`, `MEM_WRITE`, `WRITES_REG`, `AT_ADDRESS`, `IN_PROGRAM`, `INTERRUPT`, `CYCLES`, plus stack-machine specifics (`STACK_DELTA`, `READS_LOCAL`, `WRITES_LOCAL`) and source-side ones (`CALLS`, `READS_FIELD`, `IS_KIND`, `WAS_LOADED`).

**What the shared ontology buys you.** A cross-substrate query like

```sql
SELECT traveler, predicate, COUNT(*) AS n
FROM v_facts_live
WHERE predicate IN ('HAS_MNEMONIC','BRANCH','MEM_WRITE')
GROUP BY traveler, predicate;
```

returns rows from a 4-bit register machine, a 6502, JVM bytecode, and Java source — without modification. The substrate doesn't care; the relations are computed at query time.

This repo is a **substrate-specific emitter** of facts into that shared ontology. It is not part of an execution stack — the siblings above are siblings, not layers.

## What's in here

**A static indexer for Java source** — `parser_java.py`. Walks `.java` files via the `javalang` AST and emits one row per class, method, field, parameter, local, call, and type reference. Indexes [cwalk/Cave-Game](https://github.com/cwalk/Cave-Game)'s 18 files (a 2D platformer) with zero parse failures, producing several thousand rows of structural facts.

**A pattern detector** — `translator_java.py`. Sits on top of `parser_java`'s rows. Finds getters, setters, constants (with values), pure delegations, and trivial empty methods — *deterministically*, by behavior not by name. Catches `Batman.batBlock()` returning `batShield` even though the names don't match. ~200 patterns across the same 18 Cave Game files, no false positives in spot-checks.

**A class-outline renderer** — `normalize_java.py`. One canned debugger-style view, built entirely from `SELECT`s against the fact-store. No parsing of its own.

The JVM-bytecode and class-load-runtime side of the same story moved out
to its own repo:
[schema-bit-jvm](https://github.com/everydayquinn/schema-bit-jvm).
Same predicate vocabulary; different substrate (compiled bytecode vs Java source).

All of this lives in a single SQLite database (`corkboard.db`). The fact-store enforces predicate registration, namespace gating, and explicit retraction through triggers — code can't insert facts using a predicate that hasn't been defined first.

## Why a fact-store rather than reading source

A codebase is normally something you grep through. With this layout it's something you query — every relationship is a `JOIN`, every "where is X used" is a `WHERE`. The pattern detector compresses the boring 80% of any codebase (getters, setters, constants, delegations) into one row each, leaving the parts that actually need a person to think harder about clearly visible.

It also means an AI assistant reading this codebase doesn't have to re-read source every session. It can query the fact-store. Same answers, computed instead of re-grokked, stable across sessions.

The deeper claim, which holds for any relational database: **the relationships aren't stored — they're computed at query time.** A "table" of class-method-field structure isn't sitting somewhere in memory. The query asks the database to compute that view from the underlying tuples. Different SELECTs over the same rows give you different relations. That's what makes the same fact-store accept facts from a 4-bit register machine, a 6502, JVM bytecode, and Java source without modification — the predicates are tuples; the relations between them are functions.

## Reproducing it

```bash
git clone https://github.com/everydayquinn/schema-bit-graph
cd schema-bit-graph
pip install -r requirements.txt

# init the fact-store
python seed_corkboard.py

# the real Java target
git clone --depth 1 https://github.com/cwalk/Cave-Game.git /tmp/cave-game-src
ln -sf run_right.gif /tmp/cave-game-src/img/run_Right.gif    # case-fix for Linux

python parser_java.py /tmp/cave-game-src/caveGame
python translator_java.py /tmp/cave-game-src/caveGame

# render a class outline from the fact-store
python normalize_java.py | head -30
```

A query that asks which methods do the most drawing work, by counting Graphics2D calls:

```sql
SELECT subject AS method, COUNT(*) AS draw_calls
FROM v_facts_live
WHERE traveler='parser_java' AND predicate='CALLS'
  AND (object LIKE 'g2d.draw%' OR object LIKE 'g2d.fill%' OR object LIKE 'g2d.set%')
GROUP BY subject
ORDER BY draw_calls DESC LIMIT 5;
```

Returns the rendering hot-spots without ever opening a `.java` file.

## What's still open

- `translator_java`'s pattern set is the canonical Java boilerplate (getters, setters, constants, delegation, trivial). Larger patterns (state machines, listeners, observers, builder/visitor) require teaching it. The architecture takes additions without schema migration.
- The predicate vocabulary is generic enough to take facts from any other language with classes-and-methods — Python, C#, etc. Untested, but no Java-specific assumptions in the schema.
- The `READS_FIELD` / `INVOKES_ON_FIELD` split — current `parser_java` conflates value-reads and method-dispatch-through-a-field under one predicate. Surfaced via the third-party tic-tac-toe corpus walkthrough on 2026-05-09; tracked as the canonical "bad rule" example for the substrate's calibration discipline.

## Related repositories

- [schema-bit-cpu](https://github.com/everydayquinn/schema-bit-cpu) — the 4-bit CPU as a self-contained artifact, where the predicate vocabulary used here originally took shape.
- [schema-bit-isa](https://github.com/everydayquinn/schema-bit-isa) — the same 4-bit CPU plus a 6502 (py65), demonstrating the predicate vocabulary travels across ISA shapes.
- [schema-bit-jvm](https://github.com/everydayquinn/schema-bit-jvm) — JVM bytecode + class-load runtime; the compiled-and-running side of the Java story. Same predicate vocabulary as this repo.
- [macro-schema-dsl](https://github.com/everydayquinn/macro-schema-dsl) — query-driven code assembly built on top of these fact-stores. Composes code into existing fact-indexed codebases instead of generating blank-slate.

## Contact

[github.com/everydayquinn](https://github.com/everydayquinn) — backend / data engineering / contract roles.
