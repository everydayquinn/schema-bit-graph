# schema-bit-graph

A fact-store for source code. Every class, method, field, parameter, local, call, and type reference becomes a row you can `SELECT`. The relationships are computed at query time — there's no graph stored anywhere; the graph is whatever the SELECT just asked for.

The predicate vocabulary used here came out of a 4-bit CPU built in SQL first ([schema-bit-cpu](https://github.com/everydayquinn/schema-bit-cpu) / [schema-bit-isa](https://github.com/everydayquinn/schema-bit-isa)). It turned out to apply almost unchanged to a real Java codebase, so I pointed it at one.

## What's in here

**A static indexer for Java source** — `parser_java.py`. Walks `.java` files via the `javalang` AST and emits one row per class, method, field, parameter, local, call, and type reference. Indexes [cwalk/Cave-Game](https://github.com/cwalk/Cave-Game)'s 18 files (a 2D platformer) with zero parse failures, producing several thousand rows of structural facts.

**A pattern detector** — `translator_java.py`. Sits on top of `parser_java`'s rows. Finds getters, setters, constants (with values), pure delegations, and trivial empty methods — *deterministically*, by behavior not by name. Catches `Batman.batBlock()` returning `batShield` even though the names don't match. ~200 patterns across the same 18 Cave Game files, no false positives in spot-checks.

**A JVM bytecode parser** — `parser_jvm.py`. Reads `.class` files via `javap`. Same predicate vocabulary as the Java source side, applied to the compiled-bytecode layer.

**A runtime tracer** — `ingest_runtime.py`. Captures the JVM's own `-Xlog:class+load` output and turns each class load into a fact. No source modification; the JVM does the work, this just ingests. Lets you cross-query the static index against what actually loaded at runtime.

**A class-outline renderer** — `normalize_java.py`. One canned debugger-style view, built entirely from `SELECT`s against the fact-store. No parsing of its own.

All of this lives in a single SQLite database (`corkboard.db`). The fact-store enforces predicate registration, namespace gating, and explicit retraction through triggers — code can't insert facts using a predicate that hasn't been defined first.

## Why a fact-store rather than reading source

A codebase is normally something you grep through. With this layout it's something you query — every relationship is a `JOIN`, every "where is X used" is a `WHERE`. The pattern detector compresses the boring 80% of any codebase (getters, setters, constants, delegations) into one row each, leaving the parts that actually need a person to think harder about clearly visible.

It also means an AI assistant reading this codebase doesn't have to re-read source every session. It can query the fact-store. Same answers, computed instead of re-grokked, stable across sessions.

The deeper claim, which holds for any relational database: **the relationships aren't stored — they're computed at query time.** A "table" of class-method-field structure isn't sitting somewhere in memory. The query asks the database to compute that view from the underlying tuples. Different SELECTs over the same rows give you different relations. That's what makes the same fact-store accept facts from a 4-bit register machine *and* JVM bytecode *and* Java source without modification — the predicates are tuples; the relations between them are functions.

## Reproducing it

```bash
git clone https://github.com/everydayquinn/schema-bit-graph
cd schema-bit-graph
pip install -r requirements.txt

# init the fact-store
python seed_corkboard.py

# JVM bytecode parser on a calibration class
javac -d kit_jvm_lessons kit_jvm_lessons/src/CountUp.java
python parser_jvm.py kit_jvm_lessons/CountUp.class

# the real Java target
git clone --depth 1 https://github.com/cwalk/Cave-Game.git /tmp/cave-game-src
ln -sf run_right.gif /tmp/cave-game-src/img/run_Right.gif    # case-fix for Linux

python parser_java.py /tmp/cave-game-src/caveGame
python translator_java.py /tmp/cave-game-src/caveGame

# runtime trace — JVM's own class-load logging
( cd /tmp/cave-game-src && timeout 5 java -Xlog:class+load=info:file=/tmp/load.log -jar CAVE_V1.0.4.jar ) || true
python ingest_runtime.py /tmp/load.log

# render a class outline from the fact-store
python normalize_java.py | head -30
```

A query that takes the static index and the runtime log and asks where they disagree — *which classes the indexer claims exist that the JVM didn't actually load*:

```sql
SELECT c.subject FROM v_facts_live c
WHERE c.traveler='parser_java' AND c.predicate='IS_KIND'
  AND NOT EXISTS (
    SELECT 1 FROM v_facts_live r
     WHERE r.traveler='runtime_jvm' AND r.predicate='WAS_LOADED'
       AND r.subject = c.subject
  );
```

Returns zero rows for Cave Game. The static picture and the runtime picture agree.

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
- The runtime tracer captures class-load events. Per-object instance tracking needs a small JDWP client (the JVM's debug protocol); not in scope for the current work but the path is clear.
- The predicate vocabulary is generic enough to take facts from any other language with classes-and-methods — Python, C#, etc. Untested, but no Java-specific assumptions in the schema.

## Related repositories

- [schema-bit-cpu](https://github.com/everydayquinn/schema-bit-cpu) — the 4-bit CPU as a self-contained artifact, where the predicate vocabulary used here originally took shape.
- [schema-bit-isa](https://github.com/everydayquinn/schema-bit-isa) — the same 4-bit CPU plus a 6502 (py65), demonstrating the predicate vocabulary travels across ISA shapes.

## Contact

[github.com/everydayquinn](https://github.com/everydayquinn) — backend / data engineering / contract roles.
