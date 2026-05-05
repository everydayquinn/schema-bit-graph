# miner.py test report  (slice 3)

_Generated: 2026-05-04T17:39:28_

**8/8 passed**

| # | test | claim | expected | actual | result |
|---|------|-------|----------|--------|--------|
| 1 | `no repetition: trace with 4 unique instructions yields 0 chunks` | miner only inserts sequences that occur >=2 times | `(0, 0)` | `(0, 0)` | PASS |
| 2 | `single repeat: one length-2 sequence found` | (LDA 14, ADD 15) twice produces exactly one mined chunk | `(1, 2)` | `(1, 2)` | PASS |
| 3 | `body match: chunk_body rows == repeated sub-sequence` | the inserted chunk has the exact (mnemonic, operand) pairs that repeated | `[('LDA', 14), ('ADD', 15)]` | `[('LDA', 14), ('ADD', 15)]` | PASS |
| 4 | `idempotent: mining twice doesn't duplicate chunks` | deterministic naming + insert-if-new keeps the catalog stable | `(1, [])` | `(1, [])` | PASS |
| 5 | `multi-length: triple-repetition program yields 5 chunks across lengths 2,3,4` | miner finds repeats at every window size that supports them | `(5, [2, 2, 3, 3, 4])` | `(5, [2, 2, 3, 3, 4])` | PASS |
| 6 | `closed loop: compose using a mined chunk produces correct bytes` | the loop closes — execution traces become reusable building blocks | `[30, 47, 96, 240]` | `[30, 47, 96, 240]` | PASS |
| 7 | `threshold: min_count=3 rejects sequences seen only twice` | the count threshold is respected | `0` | `0` | PASS |
| 8 | `range: min_length/max_length restrict the windows considered` | asking for length 2 only returns length-2 chunks | `(2, [2])` | `(2, [2])` | PASS |
