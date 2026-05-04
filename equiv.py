"""
Equivalence detector — slice 6.

For every pair of chunks in the catalog, runs both through chunk_lab on
the same battery of scenarios and compares their observable outputs.
Pairs that agree across every scenario tested are recorded in
chunk_equivalence with a confidence equal to the number of scenarios.

Equivalence ignores cycles (timing) — only the observable state matters:
output_a, output_b, output_out, ram_writes, halted.

This is the unique payoff of the lab: structurally different chunks that
do the same thing become discoverable.
"""

import json
from itertools import combinations

from chunk_lab import run_chunk

EQUIV_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunk_equivalence (
    chunk_a    TEXT NOT NULL,
    chunk_b    TEXT NOT NULL,
    confidence INTEGER NOT NULL,         -- number of scenarios that agreed
    PRIMARY KEY (chunk_a, chunk_b),
    CHECK (chunk_a < chunk_b)            -- ordered pairs only, no duplicates
);
"""


def ensure_schema(conn):
    conn.executescript(EQUIV_SCHEMA)
    conn.commit()


# default scenarios: cover several initial states with sensible params
DEFAULT_SCENARIOS = [
    {
        "initial_a": 0,
        "initial_b": 0,
        "initial_ram": {x: (x * 3) & 0xFF for x in range(16)},
        "params": {"addr": 14, "src": 14, "dst": 10,
                   "a": 14, "b": 15,
                   "p0": 14, "p1": 15, "p2": 13},
    },
    {
        "initial_a": 7,
        "initial_b": 11,
        "initial_ram": {x: (16 - x) & 0xFF for x in range(16)},
        "params": {"addr": 14, "src": 14, "dst": 10,
                   "a": 14, "b": 15,
                   "p0": 14, "p1": 15, "p2": 13},
    },
    {
        "initial_a": 5,
        "initial_b": 2,
        "initial_ram": {0: 0, 14: 6, 15: 9},
        "params": {"addr": 15, "src": 15, "dst": 12,
                   "a": 14, "b": 15,
                   "p0": 14, "p1": 15, "p2": 13},
    },
]


def _outputs(r):
    """The observable signature of one lab run, excluding timing."""
    return (
        r["output_a"], r["output_b"], r["output_out"],
        tuple(sorted(r["ram_writes"].items())),
        bool(r["halted"]),
    )


def find_equivalent(conn, scenarios=None):
    """
    Test every chunk pair across `scenarios`; return list of inserted
    equivalence rows.  Chunks whose params can't be filled by a scenario
    drop out of *that scenario only* — they're still tested elsewhere.
    """
    ensure_schema(conn)
    scenarios = scenarios or DEFAULT_SCENARIOS

    names = [r["name"]
             for r in conn.execute("SELECT name FROM chunks ORDER BY name")]

    # Collect each chunk's outputs across all scenarios.
    # `outs[name][i]` is None if scenario i couldn't be run.
    outs = {}
    for name in names:
        params_row = conn.execute(
            "SELECT params FROM chunks WHERE name=?", (name,)
        ).fetchone()
        required = json.loads(params_row["params"] or "[]")

        per_scen = []
        for scen in scenarios:
            try:
                scen_params = {k: scen.get("params", {}).get(k, 0)
                               for k in required}
                r = run_chunk(
                    conn, name,
                    params      = scen_params,
                    initial_a   = scen.get("initial_a", 0),
                    initial_b   = scen.get("initial_b", 0),
                    initial_ram = scen.get("initial_ram"),
                )
                per_scen.append(_outputs(r))
            except Exception:
                per_scen.append(None)
        outs[name] = per_scen

    inserted = []
    for a, b in combinations(names, 2):
        oa, ob = outs[a], outs[b]
        # both must have produced an output in every scenario, and they must agree
        if not all(x is not None and y is not None and x == y
                   for x, y in zip(oa, ob)):
            continue
        existing = conn.execute(
            "SELECT 1 FROM chunk_equivalence WHERE chunk_a=? AND chunk_b=?",
            (a, b),
        ).fetchone()
        if existing:
            continue
        conn.execute(
            "INSERT INTO chunk_equivalence(chunk_a, chunk_b, confidence) "
            "VALUES (?, ?, ?)",
            (a, b, len(scenarios)),
        )
        inserted.append({"chunk_a": a, "chunk_b": b,
                         "confidence": len(scenarios)})
    conn.commit()
    return inserted
