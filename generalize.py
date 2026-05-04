"""
Generalizer — slice 5.

Reads the chunks catalog and finds groups of literal-operand chunks
that share a mnemonic sequence but differ in their operand values.
For each such group, emits one parameterized chunk that captures the
shared structure with $-prefixed operand placeholders.

Mechanical and byte-exact:
  - mnemonic order is preserved
  - operand positions where members AGREE stay literal in the generalized chunk
  - operand positions where members DISAGREE become $p0, $p1, …

Originals are NOT deleted — they remain in the catalog for traceability.

Verification (in tests):
  - byte-exact:   compose(gen, params=original_operands) == compose(original)
  - behavioral:   chunk_lab fingerprint of gen with original params == fingerprint of original
"""

import hashlib
from collections import defaultdict

from compose import insert_chunk


def _read_literal_chunks(conn):
    """Return [(name, body)] for chunks whose operands are all integer literals.
       body is a list of (mnemonic, int_operand).  Skips chunks that already
       use $param refs."""
    out = []
    for r in conn.execute("SELECT name FROM chunks ORDER BY name"):
        body = []
        ok = True
        for b in conn.execute(
            "SELECT mnemonic, operand FROM chunk_body "
            "WHERE chunk_name=? ORDER BY step",
            (r["name"],),
        ):
            op_text = b["operand"]
            if op_text is not None and op_text.startswith("$"):
                ok = False
                break
            try:
                op = int(op_text) if op_text not in (None, "") else 0
            except ValueError:
                ok = False
                break
            body.append((b["mnemonic"], op))
        if ok and body:
            out.append((r["name"], body))
    return out


def _name_for(body):
    s = ";".join(f"{m}({o})" for m, o in body)
    h = hashlib.sha1(s.encode()).hexdigest()[:6]
    return f"gen_{len(body)}_{h}"


def generalize(conn, min_group_size=2):
    """
    Find every group of literal chunks sharing a mnemonic sequence.
    For each group of size >= min_group_size with at least one varying
    operand position, insert one parameterized chunk.
    Returns list of dicts describing what was inserted.
    """
    chunks = _read_literal_chunks(conn)

    # group by mnemonic-only sequence
    groups = defaultdict(list)
    for name, body in chunks:
        key = tuple(m for m, _ in body)
        groups[key].append((name, body))

    inserted = []
    for mnem_seq, members in groups.items():
        if len(members) < min_group_size:
            continue
        n_pos = len(mnem_seq)

        # which positions vary across members?
        varies = []
        for pos in range(n_pos):
            ops = {body[pos][1] for _, body in members}
            varies.append(len(ops) > 1)

        if not any(varies):
            # all members are literally identical — nothing to abstract
            continue

        # build parameterized body
        param_names = []
        gen_body = []
        for pos, mnem in enumerate(mnem_seq):
            if varies[pos]:
                pname = f"p{len(param_names)}"
                param_names.append(pname)
                gen_body.append((mnem, f"${pname}"))
            else:
                # fixed operand — every member has the same value here
                fixed = members[0][1][pos][1]
                gen_body.append((mnem, fixed))

        gen_name = _name_for(gen_body)
        added = insert_chunk(
            conn, gen_name, gen_body,
            description=f"generalized from {len(members)} literal chunks: "
                        f"{', '.join(m[0] for m in members)}",
            params=param_names,
        )
        if added:
            inserted.append({
                "name":         gen_name,
                "body":         gen_body,
                "params":       param_names,
                "from_members": [m[0] for m in members],
                "fixed_positions":  [i for i, v in enumerate(varies) if not v],
                "varying_positions":[i for i, v in enumerate(varies) if v],
            })
    conn.commit()
    return inserted
