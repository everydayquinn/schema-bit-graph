"""
playground.py — guided tour of the whole stack.

Run with:  python3 playground.py

Each numbered step does ONE thing.  Read the comment, see the output,
then edit the values and re-run.  This file is meant to be modified.

Mental model:
  - cpu.db is the shared SQLite database
  - every Python module here reads/writes specific tables in cpu.db
  - your job is to pick which module to call, and in what order
"""

# ==================================================================
# Setup: open cpu.db and rebuild it from schema.sql.
#   build_db() drops the file and recreates it, so each run starts
#   from a clean slate.  Comment out the rebuild if you want to keep
#   state across runs.
# ==================================================================
from cpu import build_db, CPU
conn = build_db()
print("=" * 60)
print("playground starting on a fresh cpu.db")


# ==================================================================
# 1.  INSPECT — what tables live in the database?
#     Try this in DB Browser too — same data, friendlier UI.
# ==================================================================
print("\n[1] tables in cpu.db:")
for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
):
    print("    ", r["name"])


# ==================================================================
# 2.  ASSEMBLE — turn (mnemonic, operand) tuples into raw bytes.
#     This is the lowest-level Python helper.  Try changing the
#     instructions or operands.
# ==================================================================
from asm import assemble

program = assemble([
    ('LDA', 14),    # A <- mem[14]
    ('ADD', 15),    # A <- A + mem[15]
    ('OUT', 0),     # OUT <- A
    ('HLT', 0),     # stop
], conn)

print(f"\n[2] assembled bytes: {[hex(b) for b in program]}")


# ==================================================================
# 3.  LOAD — write the program AND some data into RAM.
#     The program goes at addresses 0..N; data lives elsewhere.
#     Try changing the data values to see step 4 produce a different sum.
# ==================================================================
data_a = 5
data_b = 7

ram = list(program) + [0] * (16 - len(program))
ram[14] = data_a
ram[15] = data_b

conn.execute("DELETE FROM ram")
for addr, val in enumerate(ram):
    conn.execute("INSERT INTO ram(addr, value) VALUES (?, ?)", (addr, val))
conn.commit()

print(f"\n[3] RAM seeded; mem[14]={data_a}, mem[15]={data_b}")


# ==================================================================
# 4.  RUN — clock the CPU until HLT (or max_cycles).
#     The CPU writes one row to state_log per T-state.
# ==================================================================
cpu = CPU(conn)
cpu.run()

print(f"\n[4] CPU halted")
print(f"    A   = {cpu.a}")
print(f"    OUT = {cpu.out}     (expected {data_a + data_b})")
print(f"    cycles ran = {cpu.cycle}")


# ==================================================================
# 5.  MIRROR — rebuild the derived tables (one row per instruction
#     instead of one row per T-state).  These are nicer to read.
# ==================================================================
import mirror
mirror.rebuild(conn)

print("\n[5] one-row-per-instruction trace:")
for r in conn.execute(
    "SELECT cycle, mnemonic, operand, a_before, a_after, out_after "
    "FROM d_instruction_trace"
):
    print(f"    cycle {r['cycle']}:  {r['mnemonic']} {r['operand']:>2}   "
          f"A {r['a_before']:>3} -> {r['a_after']:<3}   OUT {r['out_after']}")


# ==================================================================
# 6.  CHUNKS — define a reusable named pattern, then compose with it.
#     A chunk is a list of (mnemonic, operand) where operand can be
#     a literal int or a $param ref.
# ==================================================================
from compose import compose, insert_chunk, ensure_schema
ensure_schema(conn)                # make sure chunks tables exist

insert_chunk(
    conn, "add_two",
    [('LDA', '$a'), ('ADD', '$b')],     # body: two instructions
    params=['a', 'b'],                  # what params the chunk needs
    description="A <- mem[a] + mem[b]",
)
print("\n[6] defined chunk 'add_two' with params [a, b]")

# Use the chunk to build the same program as step 2:
new_bytes = compose([
    ('add_two', {'a': 14, 'b': 15}),
    ('OUT', 0),
    ('HLT', 0),
], conn)
print(f"    composed bytes: {[hex(b) for b in new_bytes]}")
print(f"    matches step 2: {new_bytes == program}")


# ==================================================================
# 7.  LAB — run the chunk in an isolated, throwaway CPU to see
#     what it does without disturbing anything.  Returns a "fingerprint"
#     dict.
# ==================================================================
from chunk_lab import run_chunk

fp = run_chunk(
    conn, "add_two",
    params      = {'a': 14, 'b': 15},
    initial_ram = {14: 5, 15: 7},
)
print("\n[7] lab fingerprint for add_two(a=14, b=15)  with mem[14]=5, mem[15]=7:")
for k, v in fp.items():
    print(f"    {k:<13} {v}")


# ==================================================================
# Things to try:
#   - change `data_a` and `data_b` in step 3 and re-run
#   - add another instruction to step 2 (e.g. another ('ADD', 14))
#   - change `params=` in step 7 and watch the fingerprint shift
#   - in step 5, query d_memory_access instead of d_instruction_trace
#   - write your own chunk in step 6 and lab it in step 7
#   - put a deliberate REPETITION in step 2's program and then call
#     `from miner import mine; print(mine(conn))` after step 5
# ==================================================================
