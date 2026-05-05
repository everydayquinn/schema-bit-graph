# CPU test report

_Generated: 2026-05-04T19:12:10_

**31/31 passed**

| # | test | claim | expected | actual | result |
|---|------|-------|----------|--------|--------|
| 1 | `schema: all mc_* tables share canonical columns` | every microcode table has the same columns as mc_fetch | `{'mc_fetch': True, 'mc_nop': True, 'mc_lda': True, 'mc_add': True, 'mc_sub': True, 'mc_sta': True, 'mc_jmp': True, 'mc_out': True, 'mc_hlt': True, 'mc_and': True, 'mc_or': True, 'mc_xor': True, 'mc_not': True, 'mc_jz': True}` | `{'mc_fetch': True, 'mc_nop': True, 'mc_lda': True, 'mc_add': True, 'mc_sub': True, 'mc_sta': True, 'mc_jmp': True, 'mc_out': True, 'mc_hlt': True, 'mc_and': True, 'mc_or': True, 'mc_xor': True, 'mc_not': True, 'mc_jz': True}` | PASS |
| 2 | `bus: at most one output drives the bus per T-state` | no row in any mc_* table has >1 output line asserted | `[]` | `[]` | PASS |
| 3 | `pc: at most one PC writer (ce / j / jc) per T-state` | no row asserts more than one of ce, j, jc | `[]` | `[]` | PASS |
| 4 | `alu: at most one ALU mode bit per T-state` | no row asserts more than one of su, andop, orop, xorop, notop | `[]` | `[]` | PASS |
| 5 | `regA: ai and ao are never both asserted` | no row both loads AND drives the A register | `[]` | `[]` | PASS |
| 6 | `opcodes: every opcode references an existing mc_<instr> table` | no dangling opcode -> microcode pointer | `[]` | `[]` | PASS |
| 7 | `ADD: 3 + 4 = 7` | LDA loads from memory, ADD adds, OUT latches A into output | `7` | `7` | PASS |
| 8 | `SUB: 9 - 5 = 4` | SUB asserts the SU line so the ALU computes A - B | `4` | `4` | PASS |
| 9 | `ADD: 200 + 100 wraps to 44 (8-bit overflow)` | ALU is masked to 8 bits, so 300 % 256 == 44 | `44` | `44` | PASS |
| 10 | `SUB: 5 - 9 wraps to 252 (two's-complement)` | ALU subtraction masked to 8 bits gives 0xFC | `252` | `252` | PASS |
| 11 | `STA: round-trip A -> mem[13] -> A -> OUT` | STA writes A into RAM, subsequent LDA reads it back | `(42, 42)` | `(42, 42)` | PASS |
| 12 | `JMP: control flow skips poisoned instructions` | JMP loads PC from operand, bypassing intermediate code | `99` | `99` | PASS |
| 13 | `HLT: halts the clock after exactly one cycle` | HLT sets the halted flag; run loop exits before cycle 2 | `(True, 1)` | `(True, 1)` | PASS |
| 14 | `NOP: does not disturb registers` | NOP has zero execute T-states, A survives across two NOPs | `55` | `55` | PASS |
| 15 | `AND: 0xCC & 0xAA = 0x88` | AND asserts andop so the ALU produces A & B | `136` | `136` | PASS |
| 16 | `OR: 0x0F | 0xF0 = 0xFF` | OR asserts orop so the ALU produces A | B | `255` | `255` | PASS |
| 17 | `XOR: 0xC3 ^ 0xA5 = 0x66` | XOR asserts xorop so the ALU produces A ^ B | `102` | `102` | PASS |
| 18 | `NOT: ~0x05 = 0xFA` | NOT asserts notop, ignores B, produces ~A & 0xFF | `250` | `250` | PASS |
| 19 | `Z: SUB of equal values sets Z=1` | fi latches Z := (alu == 0) at the SUB execute T-state | `1` | `1` | PASS |
| 20 | `Z: ADD with nonzero result clears Z to 0` | fi sets Z=0 when the ALU output is nonzero | `0` | `0` | PASS |
| 21 | `JZ: taken when Z=1 (skips poisoned code)` | jc loads PC from operand only when Z=1; SUB-of-equals sets Z | `42` | `42` | PASS |
| 22 | `JZ: falls through when Z=0` | jc must NOT load PC when Z=0; ADD with nonzero result keeps Z=0 | `99` | `99` | PASS |
| 23 | `Z: persists across instructions that don't latch fi` | Z is only updated when fi is asserted; LDA leaves it alone | `(99, 1)` | `(99, 1)` | PASS |
| 24 | `AND: zero result also sets Z=1` | AND asserts fi, so a zero result latches Z=1 just like SUB | `(0, 1)` | `(0, 1)` | PASS |
| 25 | `runaway: max_cycles halts an infinite loop` | JMP 0 loops forever; orchestrator must enforce a ceiling | `(False, 20)` | `(False, 20)` | PASS |
| 26 | `state_log: T-states are non-decreasing within a cycle` | execution history is recorded in time order | `[]` | `[]` | PASS |
| 27 | `trace: one row per executed cycle` | d_instruction_trace has exactly one row for each cycle in state_log | `4` | `4` | PASS |
| 28 | `memory: derived access count == raw ri/ro events` | every RAM read or write in the log appears once in d_memory_access | `8` | `8` | PASS |
| 29 | `freq: sum of d_instruction_freq == row count of d_instruction_trace` | every traced instruction is counted exactly once in the frequency table | `4` | `4` | PASS |
| 30 | `trace: OUT cycle shows 0 -> 7 transition` | before/after snapshot in d_instruction_trace matches expected program effect | `(0, 7)` | `(0, 7)` | PASS |
| 31 | `idempotent: rebuilding projections produces the same tables` | the mirror layer is a pure function of the event log | `[(0, 'LDA', 14, 3, 0), (1, 'ADD', 15, 7, 0), (2, 'OUT', 0, 7, 7), (3, 'HLT', 0, 7, 7)]` | `[(0, 'LDA', 14, 3, 0), (1, 'ADD', 15, 7, 0), (2, 'OUT', 0, 7, 7), (3, 'HLT', 0, 7, 7)]` | PASS |
