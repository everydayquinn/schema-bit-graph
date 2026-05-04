# compose.py test report  (slice 2)

_Generated: 2026-05-03T12:39:42_

**18/18 passed**

| # | test | claim | expected | actual | result |
|---|------|-------|----------|--------|--------|
| 1 | `empty catalog: literals-only compose == asm.assemble` | with no chunks defined, compose is a transparent passthrough to asm | `[30, 47, 96, 240]` | `[30, 47, 96, 240]` | PASS |
| 2 | `ADD program literal: matches the bytes from test_cpu.py` | compose handles literal mnemonics same as the proven asm path | `[30, 47, 96, 240]` | `[30, 47, 96, 240]` | PASS |
| 3 | `zero-param chunk: ('halt',) expands to [HLT]` | a 1-step zero-param chunk produces one byte equal to its instruction | `[240]` | `[240]` | PASS |
| 4 | `zero-param chunk: ('output',) expands to [OUT]` | OUT byte 0x60 equals halt-less compose call | `[96]` | `[96]` | PASS |
| 5 | `single-param chunk: load(addr=14) -> [0x1E]` | $addr is substituted from the params dict | `[30]` | `[30]` | PASS |
| 6 | `multi-step chunk: load_and_output(addr=14) -> [LDA 14, OUT]` | ordered chunk_body rows expand in step order | `[30, 96]` | `[30, 96]` | PASS |
| 7 | `two-param chunk: add_two(a=14,b=15) -> [LDA 14, ADD 15]` | multiple parameters resolve independently | `[30, 47]` | `[30, 47]` | PASS |
| 8 | `pivotal: ADD program from chunks only matches hand-coded bytes` | compose([add_two,output,halt]) == [0x1E,0x2F,0x60,0xF0] | `[30, 47, 96, 240]` | `[30, 47, 96, 240]` | PASS |
| 9 | `mixed: literal + chunk in same program` | compose handles both ref styles in one list | `[30, 47, 96, 240]` | `[30, 47, 96, 240]` | PASS |
| 10 | `expand: returns flat (mnemonic, operand) tuples for asm.py` | expand is the same data asm.assemble would consume | `[('LDA', 14), ('ADD', 15), ('OUT', 0), ('HLT', 0)]` | `[('LDA', 14), ('ADD', 15), ('OUT', 0), ('HLT', 0)]` | PASS |
| 11 | `error: unknown name (neither mnemonic nor chunk) raises` | garbage refs are rejected up-front | `('raised', 'ValueError')` | `('raised', 'ValueError')` | PASS |
| 12 | `error: chunk missing required param raises` | callers must supply every $param the chunk uses | `('raised', 'ValueError')` | `('raised', 'ValueError')` | PASS |
| 13 | `error: literal mnemonic given param dict raises` | passing {a:1} to ('LDA', ...) is a structural error | `('raised', 'ValueError')` | `('raised', 'ValueError')` | PASS |
| 14 | `error: bad operand from chunk surfaces from asm` | asm.py's 4-bit range check still fires on chunk-produced operands | `('raised', 'ValueError')` | `('raised', 'ValueError')` | PASS |
| 15 | `parity: ADD program via compose == hand-coded bytes` | compose -> asm pipeline reproduces every test_cpu.py program | `[30, 47, 96, 240]` | `[30, 47, 96, 240]` | PASS |
| 16 | `parity: SUB program via compose == hand-coded bytes` | compose -> asm pipeline reproduces every test_cpu.py program | `[30, 63, 96, 240]` | `[30, 63, 96, 240]` | PASS |
| 17 | `parity: STA-trip program via compose == hand-coded bytes` | compose -> asm pipeline reproduces every test_cpu.py program | `[30, 77, 29, 96, 240]` | `[30, 77, 29, 96, 240]` | PASS |
| 18 | `parity: JMP program via compose == hand-coded bytes` | compose -> asm pipeline reproduces every test_cpu.py program | `[83, 47, 240, 30, 96, 240]` | `[83, 47, 240, 30, 96, 240]` | PASS |
