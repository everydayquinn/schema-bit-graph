# equiv.py test report  (slice 6)

_Generated: 2026-05-04T17:39:56_

**7/7 passed**

| # | test | claim | expected | actual | result |
|---|------|-------|----------|--------|--------|
| 1 | `identical bodies: two chunks with same body are equivalent` | the lab confirms outputs match across all default scenarios | `[('alpha', 'beta')]` | `[('alpha', 'beta')]` | PASS |
| 2 | `nop padding: chunks differing only in trailing NOPs are equivalent` | NOP doesn't change observable state, so padded variants match the original | `[('padded', 'padded2'), ('padded', 'plain'), ('padded2', 'plain')]` | `[('padded', 'padded2'), ('padded', 'plain'), ('padded2', 'plain')]` | PASS |
| 3 | `distinct: chunks loading different addresses are not equivalent` | scenarios with different mem[14] vs mem[15] catch the difference | `[]` | `[]` | PASS |
| 4 | `side-effect: chunk with STA is not equivalent to one without` | the STA chunk shows ram_writes, the other doesn't | `[]` | `[]` | PASS |
| 5 | `confidence: matches the number of scenarios that agreed` | the count is the number of scenarios run, not 1 | `3` | `3` | PASS |
| 6 | `idempotent: re-running find_equivalent produces no duplicates` | INSERT-or-skip on (chunk_a, chunk_b) keeps the table stable | `(1, [], 1)` | `(1, [], 1)` | PASS |
| 7 | `ordering: equivalence pairs are stored as (lex_smaller, lex_larger)` | no duplicate (b,a) row when (a,b) is already present | `('a_chunk', 'z_chunk')` | `('a_chunk', 'z_chunk')` | PASS |
