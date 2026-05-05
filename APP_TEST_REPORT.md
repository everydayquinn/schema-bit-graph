# app.py test report  (slice 10 — FastAPI wrapper)

_Generated: 2026-05-04T18:37:08_

**12/12 passed**

| # | test | claim | expected | actual | result |
|---|------|-------|----------|--------|--------|
| 1 | `reset: POST /api/reset returns ok` | reset endpoint rebuilds cpu.db cleanly | `True` | `True` | PASS |
| 2 | `state: GET /api/state returns registers + ram` | state endpoint shape is stable | `['ram', 'registers']` | `['ram', 'registers']` | PASS |
| 3 | `opcodes: every ISA mnemonic is exposed` | opcodes endpoint mirrors the full ISA | `['ADD', 'AND', 'HLT', 'JMP', 'JZ', 'LDA', 'NOP', 'NOT', 'OR', 'OUT', 'STA', 'SUB', 'XOR']` | `['ADD', 'AND', 'HLT', 'JMP', 'JZ', 'LDA', 'NOP', 'NOT', 'OR', 'OUT', 'STA', 'SUB', 'XOR']` | PASS |
| 4 | `program: ADD 3+4=7 produces expected bytes and OUT` | compose -> assemble -> CPU pipeline survives the JSON round-trip | `(7, [30, 47, 96, 240])` | `(7, [30, 47, 96, 240])` | PASS |
| 5 | `trace: GET /api/trace returns one row per executed instruction` | mirror layer is reachable through the API | `['LDA', 'ADD', 'OUT', 'HLT']` | `['LDA', 'ADD', 'OUT', 'HLT']` | PASS |
| 6 | `chunks: POST then GET round-trips a chunk` | chunk catalog is reachable through the API | `True` | `True` | PASS |
| 7 | `chunks: duplicate without replace=true returns 409` | ON CONFLICT behavior surfaced as HTTP 409 | `409` | `409` | PASS |
| 8 | `dispatcher: register vector + fire event runs handler chunk` | the unified architecture works through HTTP — events mutate state | `(True, 7)` | `(True, 7)` | PASS |
| 9 | `dispatcher: event with no vector returns handled=false` | missing handler is logged, not fatal | `False` | `False` | PASS |
| 10 | `event_log: every fire creates one row` | event_log endpoint shows recent dispatch history | `3` | `3` | PASS |
| 11 | `program: unknown mnemonic surfaces as HTTP 400` | ValueError from asm.py becomes a clean 400, not a 500 | `400` | `400` | PASS |
| 12 | `integration: 5 'tick' events drive scratch[14] from 0 to 5 over HTTP` | the unified architecture survives the round-trip through FastAPI | `5` | `5` | PASS |
