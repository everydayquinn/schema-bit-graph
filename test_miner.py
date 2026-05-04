"""
Tests for miner.py — slice 3.

Verification: exact match of mined chunks vs hand-counted expectations.
The same kind of byte-equality discipline as slices 1 and 2, only here
the unit is "chunks inserted" rather than "bytes emitted."
"""

import sqlite3
import traceback
from datetime import datetime
from pathlib import Path

from cpu     import CPU
from mirror  import rebuild as mirror_rebuild
from compose import compose, ensure_schema
from miner   import mine, _name_for

HERE       = Path(__file__).parent
SCHEMA_SQL = (HERE / "schema.sql").read_text()
TEST_DB    = HERE / "test_miner.db"
REPORT     = HERE / "MINER_TEST_REPORT.md"


def fresh_db():
    if TEST_DB.exists():
        TEST_DB.unlink()
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    ensure_schema(conn)
    conn.commit()
    return conn


def load_and_run(conn, ram_bytes):
    conn.execute("DELETE FROM ram")
    padded = list(ram_bytes) + [0] * (16 - len(ram_bytes))
    for addr, val in enumerate(padded[:16]):
        conn.execute("INSERT INTO ram(addr,value) VALUES (?,?)", (addr, val & 0xFF))
    conn.commit()
    cpu = CPU(conn)
    cpu.run(max_cycles=128)
    mirror_rebuild(conn)
    return cpu


def chunk_count(conn):
    return conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]

def chunk_body(conn, name):
    rows = conn.execute(
        "SELECT mnemonic, operand FROM chunk_body "
        "WHERE chunk_name=? ORDER BY step",
        (name,),
    ).fetchall()
    return [(r["mnemonic"], int(r["operand"])) for r in rows]


RESULTS = []
def record(name, claim, expected, actual, ok, err=None):
    RESULTS.append({"name":name, "claim":claim,
                    "expected":expected, "actual":actual,
                    "ok":ok, "err":err})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not ok and err:
        print("        " + err.replace("\n", "\n        "))

def run(name, claim, fn):
    try:
        expected, actual = fn()
        record(name, claim, expected, actual, expected == actual)
    except AssertionError as e:
        record(name, claim, "(assertion)", "(failed)", False, str(e))
    except Exception:
        record(name, claim, "(no exception)", "(exception)", False, traceback.format_exc())


# ==================================================================
def behaviour():
    print("[miner.py tests]")

    # -------------------------------------------------------------
    # 1. trace with no repetition -> no chunks
    # -------------------------------------------------------------
    def t_no_repeat():
        conn = fresh_db()
        # LDA 14, ADD 15, OUT, HLT — every length-2..5 window unique
        load_and_run(conn, [0x1E, 0x2F, 0x60, 0xF0,
                            0,0,0,0,0,0,0,0,0,0, 3, 4])
        before = chunk_count(conn)
        mine(conn)
        after = chunk_count(conn)
        return (before, before), (before, after)
    run("no repetition: trace with 4 unique instructions yields 0 chunks",
        "miner only inserts sequences that occur >=2 times",
        t_no_repeat)

    # -------------------------------------------------------------
    # 2. one obvious 2-instruction repeat -> exactly one chunk
    # -------------------------------------------------------------
    def t_single_repeat():
        conn = fresh_db()
        # (LDA 14, ADD 15) twice, then OUT HLT
        # cycles: LDA 14, ADD 15, LDA 14, ADD 15, OUT, HLT
        load_and_run(conn, [0x1E, 0x2F, 0x1E, 0x2F, 0x60, 0xF0,
                            0,0,0,0,0,0,0,0, 3, 4])
        inserted = mine(conn)
        # length 2: (LDA,14)(ADD,15) appears twice -> 1 chunk
        # length 3..5: no repeats
        # so exactly one chunk, length 2
        return (1, 2), (len(inserted), inserted[0]["length"] if inserted else None)
    run("single repeat: one length-2 sequence found",
        "(LDA 14, ADD 15) twice produces exactly one mined chunk",
        t_single_repeat)

    # -------------------------------------------------------------
    # 3. body of mined chunk matches the actual repeated sequence
    # -------------------------------------------------------------
    def t_body_matches():
        conn = fresh_db()
        load_and_run(conn, [0x1E, 0x2F, 0x1E, 0x2F, 0x60, 0xF0,
                            0,0,0,0,0,0,0,0, 3, 4])
        mine(conn)
        expected = [("LDA", 14), ("ADD", 15)]
        name = _name_for(expected)
        return expected, chunk_body(conn, name)
    run("body match: chunk_body rows == repeated sub-sequence",
        "the inserted chunk has the exact (mnemonic, operand) pairs that repeated",
        t_body_matches)

    # -------------------------------------------------------------
    # 4. idempotent: running mine() twice doesn't duplicate
    # -------------------------------------------------------------
    def t_idempotent():
        conn = fresh_db()
        load_and_run(conn, [0x1E, 0x2F, 0x1E, 0x2F, 0x60, 0xF0,
                            0,0,0,0,0,0,0,0, 3, 4])
        first = mine(conn);  count_after_first  = chunk_count(conn)
        second = mine(conn); count_after_second = chunk_count(conn)
        # second run inserts nothing; total count unchanged
        return (count_after_first, []), (count_after_second, second)
    run("idempotent: mining twice doesn't duplicate chunks",
        "deterministic naming + insert-if-new keeps the catalog stable",
        t_idempotent)

    # -------------------------------------------------------------
    # 5. multi-length: triple repetition produces chunks at multiple lengths
    # -------------------------------------------------------------
    def t_multi_length():
        conn = fresh_db()
        # (LDA 14, ADD 15) three times, then HLT
        # trace = LDA,ADD,LDA,ADD,LDA,ADD,HLT  (7 cycles)
        # length 2 repeats:
        #   (LDA,ADD) x3  -> 1 chunk
        #   (ADD,LDA) x2  -> 1 chunk
        # length 3 repeats:
        #   (LDA,ADD,LDA) x2 -> 1 chunk
        #   (ADD,LDA,ADD) x2 -> 1 chunk
        # length 4 repeats:
        #   (LDA,ADD,LDA,ADD) x2 -> 1 chunk
        # total: 5 chunks
        load_and_run(conn, [0x1E, 0x2F, 0x1E, 0x2F, 0x1E, 0x2F, 0xF0,
                            0,0,0,0,0,0,0, 3, 4])
        inserted = mine(conn)
        lengths = sorted(c["length"] for c in inserted)
        return (5, [2, 2, 3, 3, 4]), (len(inserted), lengths)
    run("multi-length: triple-repetition program yields 5 chunks across lengths 2,3,4",
        "miner finds repeats at every window size that supports them",
        t_multi_length)

    # -------------------------------------------------------------
    # 6. closed loop: mined chunk reproduces correct bytes via compose
    # -------------------------------------------------------------
    def t_closed_loop():
        conn = fresh_db()
        load_and_run(conn, [0x1E, 0x2F, 0x1E, 0x2F, 0x60, 0xF0,
                            0,0,0,0,0,0,0,0, 3, 4])
        mine(conn)
        # The mined chunk for (LDA 14, ADD 15) has a deterministic name.
        mined_name = _name_for([("LDA", 14), ("ADD", 15)])
        # Compose a new program using the mined chunk:
        #   <mined>, OUT, HLT  ==  [0x1E, 0x2F, 0x60, 0xF0]
        bytes_out = compose([(mined_name,), ('OUT',), ('HLT',)], conn)
        return [0x1E, 0x2F, 0x60, 0xF0], bytes_out
    run("closed loop: compose using a mined chunk produces correct bytes",
        "the loop closes — execution traces become reusable building blocks",
        t_closed_loop)

    # -------------------------------------------------------------
    # 7. min_count threshold filters out singletons
    # -------------------------------------------------------------
    def t_min_count():
        conn = fresh_db()
        # repeat 2x -> one chunk found at min_count=2
        load_and_run(conn, [0x1E, 0x2F, 0x1E, 0x2F, 0x60, 0xF0,
                            0,0,0,0,0,0,0,0, 3, 4])
        # raise threshold to 3 -> nothing should be inserted
        inserted = mine(conn, min_count=3)
        return 0, len(inserted)
    run("threshold: min_count=3 rejects sequences seen only twice",
        "the count threshold is respected",
        t_min_count)

    # -------------------------------------------------------------
    # 8. window length range is respected
    # -------------------------------------------------------------
    def t_length_range():
        conn = fresh_db()
        load_and_run(conn, [0x1E, 0x2F, 0x1E, 0x2F, 0x1E, 0x2F, 0xF0,
                            0,0,0,0,0,0,0, 3, 4])
        # only mine length 2 -> only the 2 length-2 repeats
        inserted = mine(conn, min_length=2, max_length=2)
        lens = sorted({c["length"] for c in inserted})
        return (2, [2]), (len(inserted), lens)
    run("range: min_length/max_length restrict the windows considered",
        "asking for length 2 only returns length-2 chunks",
        t_length_range)


# ==================================================================
def write_report():
    n = len(RESULTS); p = sum(1 for r in RESULTS if r["ok"]); f = n - p
    lines = [
        f"# miner.py test report  (slice 3)",
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
