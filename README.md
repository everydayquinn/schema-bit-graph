# schema-bit-graph

Self-taught, manual-labor background, three-month SQL course as my only formal training. I wanted to know how a CPU actually works, so I built one in SQL. Then I wanted to see if the same approach could absorb a real codebase, so I indexed an 18-file open-source Java game.

## What's in here

**A 4-bit CPU whose entire architecture lives in a SQLite database.** 13 opcodes, 21 control lines, microcode as rows in tables, registers and RAM as rows, every cycle of execution as a row. Python is the clock and the bus. SQL is everything else.

**A static indexer for Java source.** Walks `.java` files via the AST, emits one row per class, method, field, parameter, local, call, and type reference. Indexes `cwalk/Cave-Game`'s 18 files with zero parse failures, producing several thousand rows of structural facts.

**A pattern detector that sits on top of the indexer.** Finds getters, setters, constants, pure delegations, and trivial empties — deterministically, by behavior not by name. 198 patterns across the same 18 files. Caught `Batman.batBlock()` returning `batShield` even though the names don't match.

**A runtime tracer using the JVM's own `-Xlog:class+load`.** No code modification. Records which classes Cave Game actually loaded when run. Every class the static indexer claims exists also got loaded at runtime — the static picture and the runtime picture agree.

All four sit in the same SQLite database. A query that joins static facts with runtime facts is one `SELECT`, not a pipeline.

## Verifying the CPU

Tests written by the author against the author's own assumptions are not verification. The 4-bit CPU is verified by hand-tracing a 17-cycle countdown program against the microcode tables in [schema.sql](schema.sql), and by running 13 edge programs (ADD, underflow, AND, OR, XOR, NOT, JZ-taken/not-taken, JMP, STA-then-reload) against expected end-states worked out on paper.

```
python verify_cpu_4bit.py
# all 13 edge programs match hand-computed expectations
```

I caught one of my own bugs writing the harness — an off-by-N in the test data layout. That's the failure mode this verification is designed to catch.

## Reproducing it

```bash
git clone https://github.com/everydayquinn/schema-bit-graph
cd schema-bit-graph
pip install -r requirements.txt

# fact-store + 4-bit CPU
python verify_cpu_4bit.py
python seed_corkboard.py
python cpu_4bit_traveler.py countdown

# JVM bytecode parser on a calibration class
javac -d kit_jvm_lessons kit_jvm_lessons/src/CountUp.java
python parser_jvm.py kit_jvm_lessons/CountUp.class

# real Java target (cwalk/Cave-Game)
git clone --depth 1 https://github.com/cwalk/Cave-Game.git /tmp/cave-game-src
ln -sf run_right.gif /tmp/cave-game-src/img/run_Right.gif    # case-fix for Linux
python parser_java.py /tmp/cave-game-src/caveGame
python translator_java.py /tmp/cave-game-src/caveGame

# runtime trace — JVM's own class-load log
( cd /tmp/cave-game-src && timeout 5 java -Xlog:class+load=info:file=/tmp/load.log -jar CAVE_V1.0.4.jar ) || true
python ingest_runtime.py /tmp/load.log
```

Then this query returns rows for both an in-house 4-bit register machine and a JVM stack machine, using the same predicate vocabulary on each:

```sql
SELECT traveler, predicate, COUNT(*) AS n
FROM v_facts_live
WHERE predicate IN ('HAS_MNEMONIC', 'BRANCH')
GROUP BY traveler, predicate;
```

And this one asks which Cave Game classes the static index claims exist that the JVM didn't actually load:

```sql
SELECT c.subject FROM v_facts_live c
WHERE c.traveler='parser_java' AND c.predicate='IS_KIND'
  AND NOT EXISTS (
    SELECT 1 FROM v_facts_live r
     WHERE r.traveler='runtime_jvm' AND r.predicate='WAS_LOADED'
       AND r.subject = c.subject
  );
```

Returns zero for Cave Game. The static index lines up with what the JVM did at runtime.

## Why this shape

A codebase is normally something you grep through. I wanted it to be something you query — every class, method, and call as a row, the relationships computed at query time. The pattern detector compresses the boring 80% of any codebase (getters, setters, constants, delegations) into one row each, leaving the parts that actually need a person to think harder about clearly visible.

It also means an AI assistant reading this codebase doesn't have to re-read source files every session. It can query the fact-store. Same answers, computed instead of re-grokked.

## What's still open

- The pattern detector handles canonical Java idioms. New patterns (state machines, observer/listener, etc.) require teaching it. The architecture takes additions without schema migration.
- The runtime trace currently captures class-load events only. Per-object instance tracking would need a small JDWP client; not in scope for the current work.
- The predicate vocabulary is generic enough to take facts from any other language with classes-and-methods (or whatever it has). I haven't tested that yet.

## Contact

[github.com/everydayquinn](https://github.com/everydayquinn) — backend / data engineering / contract roles.
