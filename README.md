# schema-bit-graph

A fact-store for source code. Every class, method, field, parameter, local, call, and type reference becomes a row you can `SELECT`. The relationships are computed at query time — there's no graph stored anywhere; the graph is whatever the SELECT just asked for.

The predicate vocabulary used here came out of a 4-bit CPU built in SQL first ([schema-bit-cpu](https://github.com/everydayquinn/schema-bit-cpu) / [schema-bit-isa](https://github.com/everydayquinn/schema-bit-isa)). It turned out to apply almost unchanged to a real Java codebase, so I pointed it at one.

## What this experiment explores

Representing Java source structure as queryable rows in SQLite. A static indexer walks `.java` files via the `javalang` AST and writes one row per class, method, field, parameter, local, call, and type reference. A separate pattern detector sits on top of those rows and flags mechanical patterns — getters, setters, constants, pure delegations, trivial empties — deterministically, by behavior rather than name.

**What this repo produces.** A SQLite database (`corkboard.db`) with structural rows under `parser_java` and pattern rows under `translator_java`. The working example is cwalk's Cave Game corpus: ~thousands of structural rows and ~200 pattern matches with no parse failures across 18 files.

**How to query it.** Standard SQLite. Example queries in this README cover ranking methods by `Graphics2D` call count to find rendering hot-spots, building a class outline from `SELECT`s alone, and joining structural and pattern rows.

## Relation to other repositories

The other repos in this account — `schema-bit-cpu`, `schema-bit-isa`, `schema-bit-jvm`, `macro-schema-dsl` — are independent experiments that also log or analyze some view of computation into SQLite.

The similarity is limited to:

- they all use SQLite as the storage format
- some use similar column names where the same concept fits (e.g. `predicate`, `subject`, `object`, `traveler`)

There is **no shared architecture**. There is **no execution relationship between repos** — none calls or invokes another, none depends on another at runtime. They are different lenses on computation that happen to converge on SQLite as the storage shape.

## What's in here

**A static indexer for Java source** — `parser_java.py`. Walks `.java` files via the `javalang` AST and emits one row per class, method, field, parameter, local, call, and type reference. Indexes [cwalk/Cave-Game](https://github.com/cwalk/Cave-Game)'s 18 files (a 2D platformer) with zero parse failures, producing several thousand rows of structural facts.

**A pattern detector** — `translator_java.py`. Sits on top of `parser_java`'s rows. Finds getters, setters, constants (with values), pure delegations, and trivial empty methods — *deterministically*, by behavior not by name. Catches `Batman.batBlock()` returning `batShield` even though the names don't match. ~200 patterns across the same 18 Cave Game files, no false positives in spot-checks.

**A class-outline renderer** — `normalize_java.py`. One canned debugger-style view, built entirely from `SELECT`s against the fact-store. No parsing of its own.

The JVM-bytecode and class-load-runtime side of the same story moved out
to its own repo:
[schema-bit-jvm](https://github.com/everydayquinn/schema-bit-jvm).
Same predicate vocabulary; different layer.

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
