"""
Tests for app.py — the FastAPI wrapper.

Uses FastAPI's TestClient to exercise every endpoint in-process.
Same byte-exact / dict-equality discipline as the other slices.
"""

import traceback
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

# Importing app rebuilds cpu.db — that's expected for tests
import app as app_module

HERE   = Path(__file__).parent
REPORT = HERE / "APP_TEST_REPORT.md"


# Each test gets a fresh app state via /api/reset
client = TestClient(app_module.app)


RESULTS = []
def record(name, claim, expected, actual, ok, err=None):
    RESULTS.append({"name":name, "claim":claim,
                    "expected":expected, "actual":actual,
                    "ok":ok, "err":err})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not ok and err:
        print("        " + err.replace("\n", "\n        "))

def run(name, claim, fn):
    # Reset state before each test for isolation
    client.post("/api/reset")
    try:
        expected, actual = fn()
        record(name, claim, expected, actual, expected == actual)
    except AssertionError as e:
        record(name, claim, "(assertion)", "(failed)", False, str(e))
    except Exception:
        record(name, claim, "(no exception)", "(exception)", False, traceback.format_exc())


# ==================================================================
def behaviour():
    print("[app.py tests]")

    # ---- 1. reset returns ok ------------------------------------
    def t_reset():
        r = client.post("/api/reset").json()
        return True, r["ok"]
    run("reset: POST /api/reset returns ok",
        "reset endpoint rebuilds cpu.db cleanly",
        t_reset)

    # ---- 2. state shape ----------------------------------------
    def t_state_shape():
        r = client.get("/api/state").json()
        keys = sorted(r.keys())
        return ["ram", "registers"], keys
    run("state: GET /api/state returns registers + ram",
        "state endpoint shape is stable",
        t_state_shape)

    # ---- 3. opcodes lists 13 -----------------------------------
    def t_opcodes():
        r = client.get("/api/opcodes").json()
        mnems = sorted(o["mnemonic"] for o in r)
        return ['ADD','AND','HLT','JMP','JZ','LDA','NOP','NOT','OR','OUT','STA','SUB','XOR'], mnems
    run("opcodes: every ISA mnemonic is exposed",
        "opcodes endpoint mirrors the full ISA",
        t_opcodes)

    # ---- 4. program: ADD 3+4=7 via API ------------------------
    def t_run_add():
        r = client.post("/api/program", json={
            "instructions": [
                {"mnemonic": "LDA", "operand": 14},
                {"mnemonic": "ADD", "operand": 15},
                {"mnemonic": "OUT", "operand": 0},
                {"mnemonic": "HLT", "operand": 0},
            ],
            "data": {"14": 3, "15": 4},
        }).json()
        return (7, [0x1E, 0x2F, 0x60, 0xF0]), (r["registers"]["out"], r["bytes"])
    run("program: ADD 3+4=7 produces expected bytes and OUT",
        "compose -> assemble -> CPU pipeline survives the JSON round-trip",
        t_run_add)

    # ---- 5. trace contents match expected ---------------------
    def t_trace_shape():
        client.post("/api/program", json={
            "instructions": [
                {"mnemonic":"LDA","operand":14},
                {"mnemonic":"ADD","operand":15},
                {"mnemonic":"OUT","operand":0},
                {"mnemonic":"HLT","operand":0},
            ],
            "data": {"14":3, "15":4},
        })
        r = client.get("/api/trace").json()
        mnems = [row["mnemonic"] for row in r["trace"]]
        return ["LDA","ADD","OUT","HLT"], mnems
    run("trace: GET /api/trace returns one row per executed instruction",
        "mirror layer is reachable through the API",
        t_trace_shape)

    # ---- 6. chunks: add and list ------------------------------
    def t_chunks():
        client.post("/api/chunks", json={
            "name": "load14",
            "body": [{"mnemonic":"LDA","operand":14}],
            "params": [],
            "description": "test chunk",
        })
        r = client.get("/api/chunks").json()
        names = [c["name"] for c in r["chunks"]]
        return "load14" in names, True
    run("chunks: POST then GET round-trips a chunk",
        "chunk catalog is reachable through the API",
        t_chunks)

    # ---- 7. duplicate chunk without replace -> 409 ------------
    def t_chunk_dup():
        client.post("/api/chunks", json={
            "name": "x", "body":[{"mnemonic":"NOP","operand":0}], "params":[]
        })
        r = client.post("/api/chunks", json={
            "name": "x", "body":[{"mnemonic":"NOP","operand":0}], "params":[]
        })
        return 409, r.status_code
    run("chunks: duplicate without replace=true returns 409",
        "ON CONFLICT behavior surfaced as HTTP 409",
        t_chunk_dup)

    # ---- 8. vector + event flow -------------------------------
    def t_vector_event():
        # seed scratch[14] = 7 FIRST (resets the DB, so chunks/vectors must come after)
        client.post("/api/program", json={
            "instructions": [{"mnemonic":"HLT","operand":0}],
            "data": {"14": 7},
        })
        # NOW register chunk + vector (won't be wiped)
        client.post("/api/chunks", json={
            "name": "h",
            "body": [{"mnemonic":"LDA","operand":14}],
            "params": [],
        })
        client.post("/api/vectors", json={
            "event_type": "ev",
            "handler_chunk": "h",
        })
        # fire the event
        r = client.post("/api/event", json={"event_type": "ev"}).json()
        return (True, 7), (r["result"]["handled"], r["registers"]["a"])
    run("dispatcher: register vector + fire event runs handler chunk",
        "the unified architecture works through HTTP — events mutate state",
        t_vector_event)

    # ---- 9. unhandled event returns handled=False -------------
    def t_unhandled():
        r = client.post("/api/event", json={"event_type":"ghost"}).json()
        return False, r["result"]["handled"]
    run("dispatcher: event with no vector returns handled=false",
        "missing handler is logged, not fatal",
        t_unhandled)

    # ---- 10. event_log records firings ------------------------
    def t_event_log():
        client.post("/api/chunks", json={
            "name": "n", "body":[{"mnemonic":"NOP","operand":0}], "params":[]
        })
        client.post("/api/vectors", json={"event_type":"tick","handler_chunk":"n"})
        for _ in range(3):
            client.post("/api/event", json={"event_type":"tick"})
        r = client.get("/api/event_log").json()
        n = sum(1 for e in r["events"] if e["event_type"] == "tick")
        return 3, n
    run("event_log: every fire creates one row",
        "event_log endpoint shows recent dispatch history",
        t_event_log)

    # ---- 11. malformed program -> 400 -------------------------
    def t_bad_mnemonic():
        r = client.post("/api/program", json={
            "instructions": [{"mnemonic":"BLERG","operand":0}],
            "data": {},
        })
        return 400, r.status_code
    run("program: unknown mnemonic surfaces as HTTP 400",
        "ValueError from asm.py becomes a clean 400, not a 500",
        t_bad_mnemonic)

    # ---- 12. integration: counter via tick events -------------
    def t_counter_integration():
        # seed scratch FIRST (rebuilds DB)
        client.post("/api/program", json={
            "instructions": [{"mnemonic":"HLT","operand":0}],
            "data": {"13":1, "14":0},
        })
        # then register counter chunk + vector
        client.post("/api/chunks", json={
            "name": "ci",
            "body": [{"mnemonic":"LDA","operand":14},
                     {"mnemonic":"ADD","operand":13},
                     {"mnemonic":"STA","operand":14}],
            "params": [],
        })
        client.post("/api/vectors", json={"event_type":"tick","handler_chunk":"ci"})
        # fire 5 ticks
        for _ in range(5):
            client.post("/api/event", json={"event_type":"tick"})
        r = client.get("/api/state").json()
        return 5, r["ram"][14]
    run("integration: 5 'tick' events drive scratch[14] from 0 to 5 over HTTP",
        "the unified architecture survives the round-trip through FastAPI",
        t_counter_integration)


# ==================================================================
def write_report():
    n = len(RESULTS); p = sum(1 for r in RESULTS if r["ok"]); f = n - p
    lines = [
        f"# app.py test report  (slice 10 — FastAPI wrapper)",
        f"",
        f"_Generated: {datetime.now().isoformat(timespec='seconds')}_",
        f"",
        f"**{p}/{n} passed**" + ("" if f == 0 else f"  &nbsp;|&nbsp;  **{f} FAILED**"),
        f"",
        f"| # | test | claim | expected | actual | result |",
        f"|---|------|-------|----------|--------|--------|",
    ]
    for i, r in enumerate(RESULTS, 1):
        exp = repr(r["expected"]).replace("|","\\|")
        act = repr(r["actual"]).replace("|","\\|")
        lines.append(
            f"| {i} | `{r['name']}` | {r['claim']} | `{exp}` | `{act}` | "
            f"{'PASS' if r['ok'] else '**FAIL**'} |")
    if f:
        lines += ["", "## failures", ""]
        for r in RESULTS:
            if not r["ok"]:
                lines += [f"### {r['name']}", "", "```", r["err"] or "", "```", ""]
    REPORT.write_text("\n".join(lines) + "\n")
    print(f"\nreport: {REPORT}")
    print(f"summary: {p}/{n} passed" + ("" if f == 0 else f", {f} FAILED"))
    return f == 0


if __name__ == "__main__":
    behaviour()
    ok = write_report()
    raise SystemExit(0 if ok else 1)
