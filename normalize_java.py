"""
normalize_java.py — produce a readable class outline from parser_java facts.

Closes the loop: .java -> indexed SQL facts -> readable presentation, all
driven by SELECTs against corkboard.db. The presentation function does no
parsing of its own; it asks the database what it needs.

Usage:
    python3 normalize_java.py [corkboard.db]
"""
from __future__ import annotations

import sys
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent


def fetch(conn, sql, *args):
    return conn.execute(sql, args).fetchall()


def fetchone(conn, sql, *args):
    row = conn.execute(sql, args).fetchone()
    return row[0] if row else None


def render(db_path: Path) -> str:
    conn = sqlite3.connect(db_path)
    out: list[str] = []

    classes = fetch(conn,
        "SELECT subject, object FROM v_facts_live "
        "WHERE traveler='parser_java' AND predicate='IS_KIND' "
        "ORDER BY subject")

    for csubj, kind in classes:
        cname = fetchone(conn,
            "SELECT object FROM v_facts_live "
            "WHERE traveler='parser_java' AND subject=? AND predicate='HAS_NAME'",
            csubj)
        defined = fetchone(conn,
            "SELECT object FROM v_facts_live "
            "WHERE traveler='parser_java' AND subject=? AND predicate='DEFINED_AT'",
            csubj)
        modifiers = [r[0] for r in fetch(conn,
            "SELECT object FROM v_facts_live "
            "WHERE traveler='parser_java' AND subject=? AND predicate='HAS_MODIFIER' "
            "ORDER BY object",
            csubj)]
        extends = fetchone(conn,
            "SELECT object FROM v_facts_live "
            "WHERE traveler='parser_java' AND subject=? AND predicate='EXTENDS'",
            csubj)
        implements = [r[0] for r in fetch(conn,
            "SELECT object FROM v_facts_live "
            "WHERE traveler='parser_java' AND subject=? AND predicate='IMPLEMENTS'",
            csubj)]

        head = " ".join(modifiers + [kind, cname or csubj])
        if extends:
            head += f" extends {extends}"
        if implements:
            head += f" implements {', '.join(implements)}"
        head += f"   [{defined}]"
        out.append(head)
        out.append("─" * min(80, len(head)))

        # fields
        fields = fetch(conn,
            "SELECT subject FROM v_facts_live "
            "WHERE traveler='parser_java' AND predicate='BELONGS_TO' AND object=? "
            "  AND subject LIKE 'field:%' ORDER BY subject",
            csubj)
        for (fsubj,) in fields:
            fname = fetchone(conn, "SELECT object FROM v_facts_live "
                "WHERE traveler='parser_java' AND subject=? AND predicate='HAS_NAME'", fsubj)
            ftype = fetchone(conn, "SELECT object FROM v_facts_live "
                "WHERE traveler='parser_java' AND subject=? AND predicate='HAS_TYPE'", fsubj)
            fmods = [r[0] for r in fetch(conn,
                "SELECT object FROM v_facts_live "
                "WHERE traveler='parser_java' AND subject=? AND predicate='HAS_MODIFIER' "
                "ORDER BY object", fsubj)]
            out.append(f"  field   {' '.join(fmods + [ftype or '?', fname])}")

        # methods
        methods = fetch(conn,
            "SELECT subject FROM v_facts_live "
            "WHERE traveler='parser_java' AND predicate='BELONGS_TO' AND object=? "
            "  AND subject LIKE 'method:%' ORDER BY subject",
            csubj)
        for (msubj,) in methods:
            mname = fetchone(conn, "SELECT object FROM v_facts_live "
                "WHERE traveler='parser_java' AND subject=? AND predicate='HAS_NAME'", msubj)
            rtype = fetchone(conn, "SELECT object FROM v_facts_live "
                "WHERE traveler='parser_java' AND subject=? AND predicate='RETURNS_TYPE'", msubj)
            mmods = [r[0] for r in fetch(conn,
                "SELECT object FROM v_facts_live "
                "WHERE traveler='parser_java' AND subject=? AND predicate='HAS_MODIFIER' "
                "ORDER BY object", msubj)]
            params = fetch(conn,
                "SELECT object FROM v_facts_live "
                "WHERE traveler='parser_java' AND subject=? AND predicate='HAS_PARAM' "
                "ORDER BY object", msubj)
            param_strs = []
            for (psubj,) in params:
                pname = fetchone(conn, "SELECT object FROM v_facts_live "
                    "WHERE traveler='parser_java' AND subject=? AND predicate='HAS_NAME'", psubj)
                ptype = fetchone(conn, "SELECT object FROM v_facts_live "
                    "WHERE traveler='parser_java' AND subject=? AND predicate='HAS_TYPE'", psubj)
                param_strs.append(f"{ptype} {pname}")
            sig = f"{' '.join(mmods)} {rtype} {mname}({', '.join(param_strs)})".strip()
            mloc = fetchone(conn, "SELECT object FROM v_facts_live "
                "WHERE traveler='parser_java' AND subject=? AND predicate='DEFINED_AT'", msubj)
            out.append(f"  method  {sig}   [{mloc}]")

            # locals + calls under this method (indented further)
            locals_ = fetch(conn,
                "SELECT object FROM v_facts_live "
                "WHERE traveler='parser_java' AND subject=? AND predicate='DECLARES_LOCAL' "
                "ORDER BY object", msubj)
            for (lsubj,) in locals_:
                lname = fetchone(conn, "SELECT object FROM v_facts_live "
                    "WHERE traveler='parser_java' AND subject=? AND predicate='HAS_NAME'", lsubj)
                ltype = fetchone(conn, "SELECT object FROM v_facts_live "
                    "WHERE traveler='parser_java' AND subject=? AND predicate='HAS_TYPE'", lsubj)
                out.append(f"    local   {ltype} {lname}")

            calls = [r[0] for r in fetch(conn,
                "SELECT object FROM v_facts_live "
                "WHERE traveler='parser_java' AND subject=? AND predicate='CALLS' "
                "ORDER BY object", msubj)]
            for tgt in calls:
                out.append(f"    calls   {tgt}")

        out.append("")

    return "\n".join(out)


def main(argv):
    db_path = Path(argv[1]) if len(argv) >= 2 else HERE / "corkboard.db"
    print(render(db_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
