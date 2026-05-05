# interrupts.py test report  (slice 9 — the dispatcher)

_Generated: 2026-05-04T17:40:15_

**11/11 passed**

| # | test | claim | expected | actual | result |
|---|------|-------|----------|--------|--------|
| 1 | `register: vector lookup returns the registered handler` | INSERT into interrupt_vectors then SELECT comes back identical | `[{'event_type': 'tick', 'handler_chunk': 'noop_handler', 'description': 'test handler'}]` | `[{'event_type': 'tick', 'handler_chunk': 'noop_handler', 'description': 'test handler'}]` | PASS |
| 2 | `unhandled: event with no vector returns handled=False and logs` | missing handler is logged with error message, no exception | `(False, 'no handler registered', 'ghost_event', 'no handler registered')` | `(False, 'no handler registered', 'ghost_event', 'no handler registered')` | PASS |
| 3 | `simple: LDA-only handler updates A from scratch RAM` | the dispatcher loads handler bytes, runs to HLT, A reflects mem read | `(True, True, 7)` | `(True, True, 7)` | PASS |
| 4 | `persistence: scratch RAM survives across events; counter increments` | RAM[12..15] is preserved between events; STA writes survive next event | `[1, 2, 3]` | `[1, 2, 3]` | PASS |
| 5 | `registers: A persists across events (event 2 sees event 1's A)` | register state survives event boundaries; ADD reads prior A | `12` | `12` | PASS |
| 6 | `payload: dict payload binds chunk params at firing time` | same handler with different params produces different outcomes | `(99, 7)` | `(99, 7)` | PASS |
| 7 | `oversize: handler bytes + HLT > 12 raises ValueError` | handler region cap is enforced; oversize is logged AND raised | `('raised', 'ValueError')` | `('raised', 'ValueError')` | PASS |
| 8 | `event_log: every fired event creates one row` | log is append-only; row count == events fired | `4` | `4` | PASS |
| 9 | `re-register: second register call replaces the handler` | ON CONFLICT updates handler_chunk; later call wins | `('h2', 5)` | `('h2', 5)` | PASS |
| 10 | `isolation: handler region is fully rewritten each event` | no residue from previous handler; bytes beyond new handler are zero | `[0, 0, 0, 0, 0, 0, 0, 0, 0]` | `[0, 0, 0, 0, 0, 0, 0, 0, 0]` | PASS |
| 11 | `integration: 5 events drive scratch[14] from 0 to 5` | the unified architecture works end-to-end — events accumulate state | `5` | `5` | PASS |
