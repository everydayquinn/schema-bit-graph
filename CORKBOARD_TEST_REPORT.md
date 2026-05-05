# Cork-board test report

_Generated: 2026-05-04T17:48:18_

**32/32 passed**

| # | test | claim | expected | actual | result |
|---|------|-------|----------|--------|--------|
| 1 | `ns_trigger: bad-namespace insert raises` | subject not matching any registered prefix is rejected by trigger | `'raises'` | `'raises'` | PASS |
| 2 | `unknown_predicate: emit() raises ValueError` | predicate not registered → emit refuses | `'raises'` | `'raises'` | PASS |
| 3 | `predicate.definition NOT NULL is enforced` | schema rejects predicate without definition | `'raises'` | `'raises'` | PASS |
| 4 | `namespace prefix CHECK rejects 'NoColon'` | namespace prefix must match GLOB '[a-z][a-z_0-9]*:' | `'raises'` | `'raises'` | PASS |
| 5 | `cardinality CHECK rejects values outside one|many` | predicates.cardinality is bounded enum | `'raises'` | `'raises'` | PASS |
| 6 | `retraction_trigger: fires on retracts_id, sets retracted_by_id` | AFTER INSERT trigger marks the retracted fact and links back | `('retracted', 2)` | `('retracted', 2)` | PASS |
| 7 | `auto_retract: emit() of 'one' cardinality with new value retracts old` | documented behaviour from emit() docstring | `[('beta',)]` | `[('beta',)]` | PASS |
| 8 | `'many' cardinality: facts accumulate without retraction` | additive predicates allow multiple live values | `['a', 'b', 'c']` | `['a', 'b', 'c']` | PASS |
| 9 | `unique-live: identical (traveler, subject, predicate, object) cannot duplicate while live` | fact_unique_live partial index enforces this | `1` | `1` | PASS |
| 10 | `v_contradictions: hides contradictions involving retracted facts` | view filters retracted_at IS NULL on both sides | `(1, 0)` | `(1, 0)` | PASS |
| 11 | `notes_for_claude: dict round-trips losslessly through JSON` | emit() serializes; SELECT returns parseable JSON; equality preserved | `{'encoding': [{'type': 'prose', 'value': 'test'}, {'type': 'code', 'lang': 'python', 'value': 'x = 1'}], 'evidence': ['src.py:42', 'src.py:88'], 'confidence': 0.95}` | `{'encoding': [{'type': 'prose', 'value': 'test'}, {'type': 'code', 'lang': 'python', 'value': 'x = 1'}], 'evidence': ['src.py:42', 'src.py:88'], 'confidence': 0.95}` | PASS |
| 12 | `captured_in_context: dict round-trips losslessly` | JSON serialization is symmetric | `{'session': 'test', 'discussed': ['a', 'b'], 'n': 7}` | `{'session': 'test', 'discussed': ['a', 'b'], 'n': 7}` | PASS |
| 13 | `emit(object=dict): object_kind defaults to 'json', object is serialized` | ergonomic: pass a dict, get JSON storage automatically | `('json', {'k': 'v'})` | `('json', {'k': 'v'})` | PASS |
| 14 | `retraction_chain: three supersessions form a clean chain` | each new value retracts the immediately-prior; chain links via retracts_id | `[(4, 'a', None, 1), (5, 'b', 4, 1), (6, 'c', 5, 0)]` | `[(4, 'a', None, 1), (5, 'b', 4, 1), (6, 'c', 5, 0)]` | PASS |
| 15 | `boot_summary: returns all 8 expected top-level keys` | interface contract for session-boot consumption | `['contradictions', 'fact_counts', 'namespaces', 'pinned', 'plan', 'predicates', 'trajectory', 'travelers']` | `['contradictions', 'fact_counts', 'namespaces', 'pinned', 'plan', 'predicates', 'trajectory', 'travelers']` | PASS |
| 16 | `boot_summary.fact_counts: live + retracted + total match raw query` | the dict-comprehension code path returns honest numbers | `{'live': 4, 'retracted': 2, 'total': 6}` | `{'live': 4, 'retracted': 2, 'total': 6}` | PASS |
| 17 | `add: produces 4 cycles (LDA, ADD, OUT, HLT)` | the 'add' demo program runs to completion in 4 fetch-execute cycles | `4` | `4` | PASS |
| 18 | `add: final OUT register = 7` | ADD instruction performed 3+4 correctly | `7` | `7` | PASS |
| 19 | `add: 4 unique insns at addresses 0x00..0x03` | linear program; each instruction at a distinct address | `4` | `4` | PASS |
| 20 | `add: HAS_MNEMONIC matches the 'add' program disassembly` | opcode high-nybble decodes correctly via OP_MNEMONIC | `{'0x00': 'lda', '0x01': 'add', '0x02': 'out', '0x03': 'hlt'}` | `{'0x00': 'lda', '0x01': 'add', '0x02': 'out', '0x03': 'hlt'}` | PASS |
| 21 | `add: LDA at 0x00 has operand 14 (RAM addr to load from)` | operand low-nybble extracted from IR byte 0x1E | `'14'` | `'14'` | PASS |
| 22 | `add: 4 BRANCH facts (one per cycle)` | BRANCH cardinality='one' with 4 cycles → 4 facts | `4` | `4` | PASS |
| 23 | `add: final cycle's BRANCH is 'halt' (HLT instruction fired)` | HLT detected via 'hlt' signal in execute T-state | `'halt'` | `'halt'` | PASS |
| 24 | `add: zero 'taken:0xXX' branches (program is linear)` | no JMP or JZ in the add program | `0` | `0` | PASS |
| 25 | `countdown: 17 cycles total (LDA + 5×SUB + 5×JZ + 4×JMP + OUT + HLT)` | loop runs 5 iterations; on iter-5 JZ takes; total cycle count | `17` | `17` | PASS |
| 26 | `countdown: 4×JMP back to 0x01, 1×JZ to 0x04` | loop body fires 5 times; on the last iteration JZ takes (Z=1) and JMP doesn't run | `{'taken:0x01': 4, 'taken:0x04': 1}` | `{'taken:0x01': 4, 'taken:0x04': 1}` | PASS |
| 27 | `countdown: cycle-0 DELTA mentions 'a=' (LDA wrote A)` | first instruction loads RAM[14]=5 into A; A changes from 0 to 5 | `True` | `True` | PASS |
| 28 | `countdown: 'a' is written ≥6 times (LDA + 5×SUB)` | WRITES_REG 'many' cardinality accumulates per cycle | `True` | `True` | PASS |
| 29 | `substrate vocab: cpu_4bit emits the full ISA-agnostic predicate set` | same predicates that parser_6502 + parser_jvm will use; substrate-independence claim grounded | `['AT_ADDRESS', 'AT_INSN', 'BRANCH', 'DELTA', 'HAS_BYTES', 'HAS_MD5', 'HAS_MNEMONIC', 'HAS_OPERANDS', 'HAS_SIZE', 'INGESTED_AT', 'IN_PROGRAM', 'STEP_SEQ', 'WRITES_REG']` | `['AT_ADDRESS', 'AT_INSN', 'BRANCH', 'DELTA', 'HAS_BYTES', 'HAS_MD5', 'HAS_MNEMONIC', 'HAS_OPERANDS', 'HAS_SIZE', 'INGESTED_AT', 'IN_PROGRAM', 'STEP_SEQ', 'WRITES_REG']` | PASS |
| 30 | `AT_INSN refs all resolve to existing insn:* subjects with AT_ADDRESS` | application-layer referential integrity; ref objects point to real subjects | `[]` | `[]` | PASS |
| 31 | `bootstrap: re-running on an existing DB preserves data` | schema 'DROP IF EXISTS' is gated by _schema_needs_apply | `1` | `1` | PASS |
| 32 | `seed: re-running register_* helpers is idempotent (INSERT OR IGNORE)` | running the seed twice doesn't multiply vocabulary | `15` | `15` | PASS |
