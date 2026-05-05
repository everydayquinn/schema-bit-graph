# chunk_lab.py test report  (slice 4)

_Generated: 2026-05-04T18:35:11_

**12/12 passed**

| # | test | claim | expected | actual | result |
|---|------|-------|----------|--------|--------|
| 1 | `load: A <- mem[$addr]` | after running ('LDA', $addr) the A register equals mem[$addr] | `(5, True)` | `(5, True)` | PASS |
| 2 | `add_two: A <- mem[$a] + mem[$b], no RAM writes` | two-step chunk produces the expected accumulator value with no side-effects on RAM | `(7, True, {})` | `(7, True, {})` | PASS |
| 3 | `load_store: STA writes appear in ram_writes` | STA $dst causes mem[$dst] to update; lab records it as a delta | `({10: 99}, 99)` | `({10: 99}, 99)` | PASS |
| 4 | `just_halt: chunk that only halts has zero state changes` | a body of [(HLT,)] preserves all initial registers and RAM | `(42, 99, 0, {}, True)` | `(42, 99, 0, {}, True)` | PASS |
| 5 | `infinite: JMP-to-self is bounded by max_cycles` | the lab does not hang on a non-halting chunk | `(False, 10)` | `(False, 10)` | PASS |
| 6 | `to_output: OUT <- A after LDA + OUT` | OUT register receives the accumulator value when 'OUT' fires | `13` | `13` | PASS |
| 7 | `determinism: identical inputs -> identical outputs` | lab is a pure function of (chunk, params, initial state) | `{'output_a': 7, 'output_b': 4, 'output_out': 0, 'ram_writes': {}, 'halted': True, 'cycles': 3}` | `{'output_a': 7, 'output_b': 4, 'output_out': 0, 'ram_writes': {}, 'halted': True, 'cycles': 3}` | PASS |
| 8 | `isolation: working DB ram is unchanged after lab run` | lab uses an in-memory substrate; user catalog/state untouched | `[(0, 30), (1, 47), (2, 96), (3, 240), (4, 0), (5, 0), (6, 0), (7, 0), (8, 0), (9, 0), (10, 0), (11, 0), (12, 0), (13, 0), (14, 3), (15, 4)]` | `[(0, 30), (1, 47), (2, 96), (3, 240), (4, 0), (5, 0), (6, 0), (7, 0), (8, 0), (9, 0), (10, 0), (11, 0), (12, 0), (13, 0), (14, 3), (15, 4)]` | PASS |
| 9 | `persistence: fingerprint_chunk writes rows we can query back` | chunk_fingerprint table receives one row per scenario with correct outputs | `[('a', 7), ('b', 11)]` | `[('a', 7), ('b', 11)]` | PASS |
| 10 | `equivalence: mined and hand-written chunks with same body share a fingerprint` | the lab confirms that a mined sequence behaves identically to its hand-coded twin | `(7, 4, 0, {}, True)` | `(7, 4, 0, {}, True)` | PASS |
| 11 | `error: chunk too big for RAM is rejected` | lab refuses chunks whose bytes + HLT exceed 16 RAM cells | `('raised', 'ValueError')` | `('raised', 'ValueError')` | PASS |
| 12 | `error: missing chunk param raises ValueError` | compose's missing-param error propagates cleanly through the lab | `('raised', 'ValueError')` | `('raised', 'ValueError')` | PASS |
