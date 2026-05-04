# Architecture map

**Project goal (corrected session 3):** a custom computational architecture
where Python and SQL together form one machine. SQL is the relational truth
layer; Python plays three roles in one event loop — **compiler, interpreter,
interrupt dispatcher**. The CPU and analysis layers are the substrate the
architecture runs on, not the destination. The architecture *is* the project.

## The three Python roles

| role | what it does | file |
|------|--------------|------|
| **compiler**   | mnemonic / chunk-reference → bytes the substrate executes | `asm.py`, `compose.py` |
| **interpreter** | drives `fire()` cycles, reads RAM, mutates registers | `cpu.py` |
| **dispatcher**  | external event → handler chunk → CPU | `interrupts.py` |

All three are now live as of session 3.

## Abstraction stack (low to high)

| # | layer | unit of meaning | substrate (Python) | tables |
|---|---|---|---|---|
| 1 | **wires** | control line (boolean) | — (declarative) | `control_lines`, `mc_<instr>` (13 of them) |
| 2 | **bytes** | instruction word (8-bit) | `asm.py` | `ram`, `opcodes` |
| 3 | **execution** | T-state (clock step) | `cpu.py` | `state_log`, `registers` |
| 4 | **trace** | instruction (cycle) | `mirror.py` | `d_instruction_trace`, `d_memory_access`, `d_instruction_freq` |
| 5 | **chunks** | reusable pattern | `miner.py`, `compose.py` | `chunks`, `chunk_body` |
| 6 | **behavior** | fingerprint (input→output) | `chunk_lab.py` | `chunk_fingerprint` |
| 7 | **abstraction** | parameterized chunk | `generalize.py` | (writes to `chunks`) |
| 8 | **equivalence** | semantic identity | `equiv.py` | `chunk_equivalence` |
| 9 | **dispatcher** | external event → handler | `interrupts.py` | `interrupt_vectors`, `event_log` |
| 10 | **web** | HTTP request → architecture call | `app.py` (FastAPI) + `static/` (HTML/JS) | (no new tables — exposes existing ones) |

## Data flow (full architecture)

```
   external world (keyboard, window, Minecraft, webhook, …)
                       │
                       ▼
   ┌───────────────────────────────────────┐
   │  interrupts.py — DISPATCHER           │
   │   1. lookup interrupt_vectors[event]  │
   │   2. expand chunk via compose         │
   │   3. assemble via asm                 │
   │   4. load bytes into RAM[0..11]       │  ← handler region
   │   5. preserve RAM[12..15]             │  ← persistent scratch
   │   6. preserve A,B,OUT registers       │  ← persistent state
   │   7. set PC=0, run cpu.py             │
   │   8. log to event_log                 │
   └───────────────────┬───────────────────┘
                       │
                       ▼
   schema.sql ──build──▶ cpu.db
                          │
              ┌───────────┼──────────────┐
              ▼           ▼              ▼
          opcodes       ram          mc_<instr>
              │           │              │
              └───────────┼──────────────┘
                          │
                       cpu.py — INTERPRETER (fire-loop)
                          │
                          ▼
                      state_log
                          │
                       mirror.py
                          ▼
        d_instruction_trace ─ d_memory_access ─ d_instruction_freq
                          │
                       miner.py
                          ▼
                  chunks + chunk_body
                          │
              ┌───────────┴───────────────┐
              ▼                           ▼
       compose.py — COMPILER        chunk_lab.py
              │                           │
              ▼                           ▼
            bytes                  chunk_fingerprint
              │                           │
              └─→ load into ram           ▼
                       │           ┌──────┴──────┐
                       │           ▼             ▼
                       │      generalize.py    equiv.py
                       │           │             │
                       │           ▼             ▼
                       │    parameterized   chunk_equivalence
                       │       chunks
                       │
                       └──── (loop closes — composed programs become
                              new traces; miner sees them; catalog grows)
```

## Files

| file | role | tests | passing |
|---|---|---|---|
| `schema.sql` | CPU base schema (wires, microcode, RAM, registers, log) | — | — |
| `chunks_schema.sql` | chunks catalog schema | — | — |
| `interrupts_schema.sql` | interrupt_vectors + event_log | — | — |
| `cpu.py` | execution engine — clock, bus, ALU, Z flag | `test_cpu.py` | 31/31 |
| `mirror.py` | projection layer | (covered in `test_cpu.py`) | — |
| `asm.py` | assembler — `(mnemonic, operand) → byte` | `test_asm.py` | 12/12 |
| `compose.py` | composer — chunk refs + literals → bytes | `test_compose.py` | 18/18 |
| `miner.py` | pattern miner — trace → literal chunks | `test_miner.py` | 8/8 |
| `chunk_lab.py` | behavioral fingerprint lab | `test_chunk_lab.py` | 12/12 |
| `generalize.py` | parameter abstraction | `test_generalize.py` | 10/10 |
| `equiv.py` | equivalence detection | `test_equiv.py` | 7/7 |
| `interrupts.py` | event dispatcher (slice 9) | `test_interrupts.py` | 11/11 |
| `app.py` | FastAPI wrapper exposing every layer over HTTP (slice 10) | `test_app.py` | 12/12 |
| `static/index.html`, `static/app.js`, `static/style.css` | tiny frontend — state panel, program editor, trace table, events | (covered by `test_app.py` integration) | — |

**Total: 121/121.**

## Instruction set

| opcode | mnemonic | semantics                                  | flags |
|--------|----------|--------------------------------------------|-------|
| 0x0    | NOP      | no-op                                      | —     |
| 0x1    | LDA addr | A ← RAM[addr]                              | —     |
| 0x2    | ADD addr | A ← (A + RAM[addr]) & 0xFF                 | Z     |
| 0x3    | SUB addr | A ← (A − RAM[addr]) & 0xFF                 | Z     |
| 0x4    | STA addr | RAM[addr] ← A                              | —     |
| 0x5    | JMP addr | PC ← addr (unconditional)                  | —     |
| 0x6    | OUT      | OUT ← A                                    | —     |
| 0x7    | AND addr | A ← A & RAM[addr]                          | Z     |
| 0x8    | OR  addr | A ← A \| RAM[addr]                         | Z     |
| 0x9    | XOR addr | A ← A ^ RAM[addr]                          | Z     |
| 0xA    | NOT      | A ← (~A) & 0xFF (operand ignored)          | Z     |
| 0xB    | JZ  addr | if Z=1: PC ← addr                          | —     |
| 0xF    | HLT      | halt clock                                 | —     |

The Z (zero) flag is latched only when the `fi` control line is asserted —
i.e. by ADD/SUB/AND/OR/XOR/NOT. LDA/STA do not touch Z, so it survives data movement.

## Interrupt model

Memory layout per event:

```
RAM addr:  0   1   2   3   4   5   6   7   8   9  10  11  12  13  14  15
           └─── handler region (12 bytes) ───┘  └ persistent scratch ┘
           overwritten each event              survives across events
```

Registers (A, B, OUT) **also** persist across events. Each handler runs as
its own complete tiny program ending in HLT; the dispatcher resets PC=0
and `halted` between events.

Payload binding: if you fire an event with a `dict` payload, its entries
become chunk params at expansion time. So one parameterized chunk can serve
many events with different operands, just by passing different payloads.

## What you can already do

- Write a program in raw bytes, assembler tuples, or chunk references
- Run it; every clock-step is logged
- Reverse-engineer the executed program from a single trace via SQL
- Mine repeating sequences; reuse them as named chunks
- Compose new programs from mined chunks + literals
- Fingerprint a chunk's behavior in isolation
- Detect chunks with identical observable effects across scenarios
- **Register handler chunks for event types and fire events that mutate persistent state**
- Verify every layer with byte-exact tests

## Running the web wrapper

```bash
cd "Schema bit graph"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app:app --reload
```

Open `http://127.0.0.1:8000` — the page exposes:
- live CPU state (registers + 16-cell RAM grid colored by handler/scratch region)
- program editor with example one-click loads (ADD, SUB-wrap, JZ-loop, AND-mask)
- execution trace table
- event dispatcher panel: register chunks as handlers, fire events, watch state mutate
- chunks catalog

Endpoints are at `/api/*` — full list: `state`, `program`, `trace`, `chunks`,
`vectors`, `event`, `event_log`, `opcodes`, `reset`.

## How to read the relational diagram

Open `cpu.db` in DBeaver: **Database Navigator → cpu.db → right-click → View
Diagram**. Foreign keys draw the edges; the layout will resemble the data flow
above.
