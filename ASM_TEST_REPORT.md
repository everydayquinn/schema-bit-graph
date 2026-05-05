# asm.py test report  (slice 1)

_Generated: 2026-05-04T17:39:14_

**12/12 passed**

| # | test | claim | expected | actual | result |
|---|------|-------|----------|--------|--------|
| 1 | `ADD program: assembles to the bytes that already pass test_cpu.py` | LDA 14, ADD 15, OUT, HLT -> [0x1E, 0x2F, 0x60, 0xF0] | `[30, 47, 96, 240]` | `[30, 47, 96, 240]` | PASS |
| 2 | `SUB program: matches test_cpu.py SUB bytes` | LDA 14, SUB 15, OUT, HLT -> [0x1E, 0x3F, 0x60, 0xF0] | `[30, 63, 96, 240]` | `[30, 63, 96, 240]` | PASS |
| 3 | `STA round-trip program: matches test_cpu.py bytes` | LDA 14, STA 13, LDA 13, OUT, HLT -> [0x1E,0x4D,0x1D,0x60,0xF0] | `[30, 77, 29, 96, 240]` | `[30, 77, 29, 96, 240]` | PASS |
| 4 | `JMP program: matches test_cpu.py JMP bytes` | JMP 3, ADD 15, HLT, LDA 14, OUT, HLT -> [0x53,0x2F,0xF0,0x1E,0x60,0xF0] | `[83, 47, 240, 30, 96, 240]` | `[83, 47, 240, 30, 96, 240]` | PASS |
| 5 | `NOP program: NOP encodes as 0x00` | NOP -> [0x00] | `[0]` | `[0]` | PASS |
| 6 | `operand: ('OUT',) and ('OUT',0) produce the same byte` | missing operand defaults to 0 | `[96]` | `[96]` | PASS |
| 7 | `case: lowercase mnemonics work` | 'lda' assembles the same as 'LDA' | `[23]` | `[23]` | PASS |
| 8 | `full grid: every (mnemonic, operand) pair encodes correctly` | (opcode<<4)|operand for every mnemonic in opcodes table | `[]` | `[]` | PASS |
| 9 | `error: unknown mnemonic raises ValueError` | asm rejects mnemonics not in the opcodes table | `('raised', 'ValueError')` | `('raised', 'ValueError')` | PASS |
| 10 | `error: operand > 15 raises ValueError` | operand must fit in 4 bits | `('raised', 'ValueError')` | `('raised', 'ValueError')` | PASS |
| 11 | `error: negative operand raises ValueError` | operand must be non-negative | `('raised', 'ValueError')` | `('raised', 'ValueError')` | PASS |
| 12 | `error: malformed entry raises ValueError` | entries must be 1- or 2-tuples | `('raised', 'ValueError')` | `('raised', 'ValueError')` | PASS |
