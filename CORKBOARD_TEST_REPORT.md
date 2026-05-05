# Cork-board test report

_Generated: 2026-05-04T19:11:32_

**49/49 passed**

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
| 31 | `parser_6502: 01_basic.s emits 4 insns` | lesson has 4 hex-byte lines (LDA, ADC, STA, BRK) | `4` | `4` | PASS |
| 32 | `parser_6502: mnemonics match disassembly via py65` | py65 disassembler decodes A9/69/8D/00 → LDA/ADC/STA/BRK | `{'0x0600': 'lda', '0x0602': 'adc', '0x0604': 'sta', '0x0607': 'brk'}` | `{'0x0600': 'lda', '0x0602': 'adc', '0x0604': 'sta', '0x0607': 'brk'}` | PASS |
| 33 | `parser_6502: instruction sizes match (LDA imm=2, ADC imm=2, STA abs=3, BRK=1)` | py65 reports correct byte-widths for each addressing mode | `{'0x0600': 2, '0x0602': 2, '0x0604': 3, '0x0607': 1}` | `{'0x0600': 2, '0x0602': 2, '0x0604': 3, '0x0607': 1}` | PASS |
| 34 | `sim_6502: 01_basic produces 4 steps (LDA, ADC, STA, BRK)` | linear program runs to BRK termination | `4` | `4` | PASS |
| 35 | `sim_6502: STA $0200 emits MEM_WRITE 0x0200=0x08` | after LDA #$05 + ADC #$03, A=8; STA writes 8 to address 0x0200 | `['0x0200=0x08']` | `['0x0200=0x08']` | PASS |
| 36 | `sim_6502: BRK at 0x0607 terminates the run` | after 7 bytes of code (LDA #$05=2, ADC #$03=2, STA $0200=3) starting at 0x0600, BRK is at 0x0607 | `'brk@0x0607'` | `'brk@0x0607'` | PASS |
| 37 | `sim_6502: ADC step's DELTA mentions a:0x05->0x08` | after LDA #$05 (step 0), ADC #$03 (step 1) brings A to 0x08 | `True` | `True` | PASS |
| 38 | `cross-substrate query: same predicate works across travelers` | the substrate-independence claim made operational | `['parser_6502']` | `['parser_6502']` | PASS |
| 39 | `parser_jvm: countTo() has exactly 18 instructions` | loop body 13 + setup 4 (iconst_0/istore_1/iconst_0/istore_2) + condition 3 (iload_2/iload_0/if_icmpge) + return-prep+return 2 (iload_1/ireturn) = 18 (verified via javap; sum of opcode distribution in test 42 also = 18) | `18` | `18` | PASS |
| 40 | `parser_jvm: countTo() opcode counts exactly match javap output` | 11 distinct opcodes summing to 17 instructions | `{'iconst_0': 2, 'iconst_1': 1, 'istore_1': 2, 'istore_2': 2, 'iload_0': 1, 'iload_1': 2, 'iload_2': 3, 'iadd': 2, 'if_icmpge': 1, 'goto': 1, 'ireturn': 1}` | `{'goto': 1, 'iadd': 2, 'iconst_0': 2, 'iconst_1': 1, 'if_icmpge': 1, 'iload_0': 1, 'iload_1': 2, 'iload_2': 3, 'ireturn': 1, 'istore_1': 2, 'istore_2': 2}` | PASS |
| 41 | `parser_jvm: iadd STACK_DELTA is '-2+1' at both occurrences` | iadd pops two ints and pushes one (the sum) | `[('insn:CountUp:countTo:11', '-2+1'), ('insn:CountUp:countTo:15', '-2+1')]` | `[('insn:CountUp:countTo:11', '-2+1'), ('insn:CountUp:countTo:15', '-2+1')]` | PASS |
| 42 | `parser_jvm: BRANCH semantics exactly match for if_icmpge / goto / ireturn` | loop control flow encoded with target offsets and branch kind | `{'insn:CountUp:countTo:6': 'conditional:20', 'insn:CountUp:countTo:17': 'unconditional:4', 'insn:CountUp:countTo:21': 'return'}` | `{'insn:CountUp:countTo:6': 'conditional:20', 'insn:CountUp:countTo:17': 'unconditional:4', 'insn:CountUp:countTo:21': 'return'}` | PASS |
| 43 | `parser_jvm: WRITES_LOCAL fires at the 4 istore_N sites with correct slots` | loop body writes sum (slot 1) and i (slot 2) at each iteration | `[('insn:CountUp:countTo:1', '1'), ('insn:CountUp:countTo:12', '1'), ('insn:CountUp:countTo:16', '2'), ('insn:CountUp:countTo:3', '2')]` | `[('insn:CountUp:countTo:1', '1'), ('insn:CountUp:countTo:12', '1'), ('insn:CountUp:countTo:16', '2'), ('insn:CountUp:countTo:3', '2')]` | PASS |
| 44 | `parser_jvm: READS_LOCAL fires at the 6 iload_N sites with correct slots` | loop body reads n (slot 0), sum (slot 1), i (slot 2) | `[('insn:CountUp:countTo:10', '2'), ('insn:CountUp:countTo:13', '2'), ('insn:CountUp:countTo:20', '1'), ('insn:CountUp:countTo:4', '2'), ('insn:CountUp:countTo:5', '0'), ('insn:CountUp:countTo:9', '1')` | `[('insn:CountUp:countTo:10', '2'), ('insn:CountUp:countTo:13', '2'), ('insn:CountUp:countTo:20', '1'), ('insn:CountUp:countTo:4', '2'), ('insn:CountUp:countTo:5', '0'), ('insn:CountUp:countTo:9', '1')` | PASS |
| 45 | `parser_jvm: every STACK_DELTA parses as signed-counts string (or '0')` | format invariant: '+N' / '-N' / sequences thereof / '0' | `[]` | `[]` | PASS |
| 46 | `parser_jvm: every countTo insn links to method 'CountUp.countTo' via IN_METHOD` | method nesting captured even though encoded in subject | `18` | `18` | PASS |
| 47 | `cross-substrate: HAS_MNEMONIC appears for all 3 travelers (cpu_4bit + parser_6502 + parser_jvm)` | the same predicate vocabulary works across 4-bit register / 8-bit register / JVM stack — substrate-independence empirically verified | `['cpu_4bit', 'parser_6502', 'parser_jvm']` | `['cpu_4bit', 'parser_6502', 'parser_jvm']` | PASS |
| 48 | `bootstrap: re-running on an existing DB preserves data` | schema 'DROP IF EXISTS' is gated by _schema_needs_apply | `1` | `1` | PASS |
| 49 | `seed: re-running register_* helpers is idempotent (INSERT OR IGNORE)` | running the seed twice doesn't multiply vocabulary | `15` | `15` | PASS |
