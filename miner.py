"""
Miner — slice 3.

Reads d_instruction_trace and writes any (mnemonic, operand) sub-sequence
that appears `min_count` or more times into the chunks catalog as a
literal chunk (no parameter generalization yet — that's a later slice).

Names are deterministic (sha1 of the body), so re-running the miner is
idempotent: the same trace produces the same chunks, no duplicates.

Usage:
    from miner import mine
    inserted = mine(conn)               # default min_count=2, length 2..5
"""

import hashlib
from collections import Counter

from compose import insert_chunk


def _name_for(body):
    """Deterministic chunk name from its body (mnemonic, operand) list."""
    s = ";".join(f"{m}_{o}" for m, o in body)
    h = hashlib.sha1(s.encode()).hexdigest()[:6]
    return f"seq_{len(body)}_{h}"


def mine(conn, min_length=2, max_length=5, min_count=2):
    """
    Slide windows over d_instruction_trace, count occurrences of each
    sub-sequence, and insert any that occur >= min_count times into the
    chunks catalog.  Returns a list of dicts describing what was inserted
    (empty list if nothing new was added).
    """
    trace = [
        (r["mnemonic"], r["operand"])
        for r in conn.execute(
            "SELECT mnemonic, operand FROM d_instruction_trace ORDER BY cycle"
        )
    ]

    inserted = []
    for L in range(min_length, max_length + 1):
        if L > len(trace):
            break
        counts = Counter()
        for i in range(len(trace) - L + 1):
            counts[tuple(trace[i:i + L])] += 1

        for sub, count in counts.items():
            if count < min_count:
                continue
            name = _name_for(sub)
            added = insert_chunk(
                conn, name, list(sub),
                description=f"mined: length={L}, count={count}",
                params=[],
            )
            if added:
                inserted.append({
                    "name": name,
                    "body": list(sub),
                    "count": count,
                    "length": L,
                })
    conn.commit()
    return inserted
