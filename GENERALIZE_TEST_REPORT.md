# generalize.py test report  (slice 5)

_Generated: 2026-05-04T18:35:26_

**10/10 passed**

| # | test | claim | expected | actual | result |
|---|------|-------|----------|--------|--------|
| 1 | `empty: no literal chunks -> no generalizations` | generalize is a no-op on an empty catalog | `[]` | `[]` | PASS |
| 2 | `singleton: a lone literal chunk is not generalized` | min_group_size of 2 prevents one-of-a-kind chunks from being abstracted | `[]` | `[]` | PASS |
| 3 | `identical: two chunks with identical bodies are not generalized` | no operand position varies, so there is nothing to parameterize | `[]` | `[]` | PASS |
| 4 | `group: two members differing in both operands -> one generalized chunk` | (LDA 14, ADD 15) and (LDA 6, ADD 7) collapse to (LDA $p0, ADD $p1) | `(1, ['p0', 'p1'])` | `(1, ['p0', 'p1'])` | PASS |
| 5 | `mixed: positions that AGREE stay literal, those that DIFFER become $params` | agree-on-LDA-operand, differ-on-ADD-operand -> [LDA 14, ADD $p0] | `([('LDA', 14), ('ADD', '$p0')], ['p0'], [0], [1])` | `([('LDA', 14), ('ADD', '$p0')], ['p0'], [0], [1])` | PASS |
| 6 | `byte-exact: generalized chunk reproduces every member's bytes` | compose(gen, params=original_operands) == compose(original) | `([30, 47], [22, 39])` | `([30, 47], [22, 39])` | PASS |
| 7 | `behavioral: gen with original params has same fingerprint as original` | lab confirms the abstraction preserves the chunk's observable behavior | `((7, 4, 0, {}, True), (17, 9, 0, {}, True))` | `((7, 4, 0, {}, True), (17, 9, 0, {}, True))` | PASS |
| 8 | `idempotent: re-running generalize produces no duplicates` | deterministic name + insert-if-new keeps the catalog stable | `(1, [], 3)` | `(1, [], 3)` | PASS |
| 9 | `multiple groups: one generalized chunk emitted per mnemonic-sequence group` | (LDA,ADD) and (LDA,SUB) groups generalize independently | `2` | `2` | PASS |
| 10 | `three members: bigger group still produces one generalized chunk` | from_members lists every contributing literal chunk | `(3, ['p0', 'p1'])` | `(3, ['p0', 'p1'])` | PASS |
