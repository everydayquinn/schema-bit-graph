"""
token_render_java.py — pure SQL-driven token block renderer.

Reads corkboard.db and emits a compact, AI-readable structural block for
one Java class, joining parser_java (L1 structural) and translator_java
(L2 patterns) facts. Does not parse Java.

Usage:
    python3 token_render_java.py <ClassName> [corkboard.db]

Block format (default; iterate as needed):
    class:Player extends Canvas              kind=class file=…/Player.java:8
    fields (17):
      isGray                    boolean  [protected]
      isRight,isLeft,isWalk,isRun,isAlive    boolean
      …
    L2 methods (9):
      getX()    → field:Player.x          [getter]
      …
    methods (4):
      initPlayer():
        R   info, icon, x, y
        W   dist, icon, isAlive, name, r, x, y
        →   info.split, Integer.parseInt, …
        ←   Player(), reset()
      render(g2d, left, right, jump, run, walk, yOff):
        …

R = reads-field, W = writes-field, → = calls (out), ← = called-by (in).
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections import defaultdict

import corkboard as cb


HERE       = Path(__file__).parent
DEFAULT_DB = HERE / "corkboard.db"


# ------------------------------------------------------------------
# SQL helpers
# ------------------------------------------------------------------
def _facts(conn, predicate: str, subject_glob: str, traveler: str | None = None
           ) -> list[tuple[str, str]]:
    """Return [(subject, object), ...] for live facts matching predicate
    name and a subject GLOB, ordered by fact id so insertion order is
    preserved (e.g. param declaration order). Optionally pin to one traveler."""
    sql = """
        SELECT f.subject, f.object
          FROM facts f JOIN predicates p ON p.id = f.predicate_id
         WHERE p.name = ?
           AND f.retracted_at IS NULL
           AND f.subject GLOB ?
    """
    args: list = [predicate, subject_glob]
    if traveler is not None:
        sql += " AND f.traveler = ?"
        args.append(traveler)
    sql += " ORDER BY f.id"
    return [(r["subject"], r["object"]) for r in conn.execute(sql, args).fetchall()]


def _facts_by_object(conn, predicate: str, object_glob: str
                     ) -> list[tuple[str, str]]:
    sql = """
        SELECT f.subject, f.object
          FROM facts f JOIN predicates p ON p.id = f.predicate_id
         WHERE p.name = ?
           AND f.retracted_at IS NULL
           AND f.object GLOB ?
    """
    return [(r["subject"], r["object"])
            for r in conn.execute(sql, [predicate, object_glob]).fetchall()]


def _first(items: list[tuple[str, str]]) -> str | None:
    return items[0][1] if items else None


def _by_subject(items: list[tuple[str, str]]) -> dict[str, list[str]]:
    d: dict[str, list[str]] = defaultdict(list)
    for s, o in items:
        d[s].append(o)
    return d


# ------------------------------------------------------------------
# Class-scoped data load
# ------------------------------------------------------------------
def _load(conn, cname: str) -> dict:
    csubj = f"class:{cname}"
    field_glob  = f"field:{cname}.*"
    method_glob = f"method:{cname}.*"
    param_glob  = f"param:{cname}.*"

    # class header
    kind        = _first(_facts(conn, "IS_KIND",         csubj))
    src_file    = _first(_facts(conn, "HAS_SOURCE_FILE", csubj))
    defined_at  = _first(_facts(conn, "DEFINED_AT",      csubj))
    extends     = _first(_facts(conn, "EXTENDS",         csubj))
    implements  = [o for _, o in _facts(conn, "IMPLEMENTS", csubj)]
    cls_mods    = [o for _, o in _facts(conn, "HAS_MODIFIER", csubj)]

    # fields
    field_subjects = sorted({s for s, _ in _facts(conn, "HAS_NAME", field_glob)})
    field_types  = {s: _first(_facts(conn, "HAS_TYPE",     s)) for s in field_subjects}
    field_mods   = {s: [o for _, o in _facts(conn, "HAS_MODIFIER", s)] for s in field_subjects}
    field_const  = {s: _first(_facts(conn, "IS_CONSTANT",  s)) for s in field_subjects}
    field_value  = {s: _first(_facts(conn, "HAS_VALUE",    s)) for s in field_subjects}
    field_lines  = {s: _first(_facts(conn, "DEFINED_AT",   s)) for s in field_subjects}

    # methods
    method_subjects = sorted({s for s, _ in _facts(conn, "HAS_NAME", method_glob)})

    method_returns = {s: _first(_facts(conn, "RETURNS_TYPE", s)) for s in method_subjects}
    method_mods    = {s: [o for _, o in _facts(conn, "HAS_MODIFIER", s)] for s in method_subjects}
    method_lines   = {s: _first(_facts(conn, "DEFINED_AT",   s)) for s in method_subjects}

    # parameters: HAS_PARAM yields method -> param-subject; param has HAS_NAME and HAS_TYPE
    has_param = _by_subject(_facts(conn, "HAS_PARAM", method_glob))
    param_name = {p: _first(_facts(conn, "HAS_NAME", p))
                  for ps in has_param.values() for p in ps}
    param_type = {p: _first(_facts(conn, "HAS_TYPE", p))
                  for ps in has_param.values() for p in ps}

    # L2 patterns
    l2_getter   = {s: _first(_facts(conn, "IS_GETTER_OF",  s)) for s in method_subjects}
    l2_setter   = {s: _first(_facts(conn, "IS_SETTER_OF",  s)) for s in method_subjects}
    l2_deleg    = {s: _first(_facts(conn, "DELEGATES_TO",  s)) for s in method_subjects}
    l2_trivial  = {s: _first(_facts(conn, "IS_TRIVIAL",    s)) for s in method_subjects}
    l2_copies   = {s: _first(_facts(conn, "COPIES_PARAMS_TO_FIELDS", s)) for s in method_subjects}

    # dataflow
    reads_field   = _by_subject(_facts(conn, "READS_FIELD",  method_glob))
    writes_field  = _by_subject(_facts(conn, "WRITES_FIELD", method_glob))
    calls_out     = _by_subject(_facts(conn, "CALLS",        method_glob))
    called_by     = _by_subject(_facts(conn, "CALLED_BY",    method_glob))

    return dict(
        cname=cname, csubj=csubj, kind=kind, src_file=src_file,
        defined_at=defined_at, extends=extends, implements=implements,
        cls_mods=cls_mods,
        field_subjects=field_subjects, field_types=field_types,
        field_mods=field_mods, field_const=field_const, field_value=field_value,
        field_lines=field_lines,
        method_subjects=method_subjects, method_returns=method_returns,
        method_mods=method_mods, method_lines=method_lines,
        has_param=has_param, param_name=param_name, param_type=param_type,
        l2_getter=l2_getter, l2_setter=l2_setter, l2_deleg=l2_deleg,
        l2_trivial=l2_trivial, l2_copies=l2_copies,
        reads_field=reads_field, writes_field=writes_field,
        calls_out=calls_out, called_by=called_by,
    )


# ------------------------------------------------------------------
# Rendering
# ------------------------------------------------------------------
def _short_field(field_subj: str) -> str:
    # field:Class.name -> name
    return field_subj.split(":", 1)[1].split(".", 1)[1]


def _short_method(method_subj: str) -> str:
    # method:Class.name -> Class.name (drop prefix; keep class so cross-class
    # CALLED_BY edges read clearly).
    return method_subj.split(":", 1)[1]


def _line_of(defined_at: str | None) -> str:
    """ '<rel-path>:<line>' -> ':<line>' for a compact suffix; '' if missing."""
    if not defined_at or ":" not in defined_at:
        return ""
    return ":" + defined_at.rsplit(":", 1)[-1]


def _format_class_header(d: dict) -> str:
    bits = [f"class:{d['cname']}"]
    if d["extends"]:
        bits.append(f"extends {d['extends']}")
    if d["implements"]:
        bits.append("implements " + ",".join(d["implements"]))
    suffix = []
    if d["kind"]:     suffix.append(f"kind={d['kind']}")
    if d["src_file"]: suffix.append(f"file={d['src_file']}{_line_of(d['defined_at'])}")
    head = " ".join(bits)
    if suffix:
        head += "    " + " ".join(suffix)
    return head


def _format_fields(d: dict) -> list[str]:
    """Group fields by (type, modifier-set) to compress declaration runs."""
    groups: dict[tuple[str, tuple[str, ...]], list[str]] = defaultdict(list)
    order: list[tuple[str, tuple[str, ...]]] = []
    for fs in d["field_subjects"]:
        ftype = d["field_types"].get(fs) or "?"
        fmods = tuple(sorted(d["field_mods"].get(fs, [])))
        key = (ftype, fmods)
        if key not in groups:
            order.append(key)
        groups[key].append(fs)

    out = [f"fields ({len(d['field_subjects'])}):"]
    for ftype, fmods in order:
        names = [_short_field(fs) for fs in groups[(ftype, fmods)]]
        # If any are constants, render their value inline instead of grouping.
        constants_in_group = [
            fs for fs in groups[(ftype, fmods)] if d["field_const"].get(fs) == "true"
        ]
        if constants_in_group:
            for fs in groups[(ftype, fmods)]:
                name = _short_field(fs)
                val = d["field_value"].get(fs)
                mods_str = ("  [" + ",".join(fmods) + "]") if fmods else ""
                if val is not None:
                    out.append(f"  {name:<20s}  {ftype:<14s}  = {val}{mods_str}")
                else:
                    out.append(f"  {name:<20s}  {ftype:<14s}{mods_str}")
        else:
            mods_str = ("  [" + ",".join(fmods) + "]") if fmods else ""
            joined = ", ".join(names)
            out.append(f"  {joined:<40s}  {ftype}{mods_str}")
    return out


def _signature(d: dict, msubj: str) -> str:
    """Render `name(p1: T1, p2: T2)` style."""
    name = msubj.rsplit(".", 1)[-1]
    params = []
    for psubj in d["has_param"].get(msubj, []):
        pname = d["param_name"].get(psubj) or "?"
        ptype = d["param_type"].get(psubj) or "?"
        params.append(f"{pname}: {ptype}")
    return f"{name}({', '.join(params)})"


def _l2_one_liner(d: dict, msubj: str) -> str | None:
    """Return a compact one-line summary if msubj has an L2 pattern. Else None."""
    if d["l2_getter"].get(msubj):
        target = d["l2_getter"][msubj]
        return f"{_signature(d, msubj):<40s}  → {target}    [getter]"
    if d["l2_setter"].get(msubj):
        target = d["l2_setter"][msubj]
        return f"{_signature(d, msubj):<40s}  → {target}    [setter]"
    if d["l2_deleg"].get(msubj):
        target = d["l2_deleg"][msubj]
        return f"{_signature(d, msubj):<40s}  → {target}    [delegates]"
    if d["l2_trivial"].get(msubj):
        kind = d["l2_trivial"][msubj]
        return f"{_signature(d, msubj):<40s}  [trivial: {kind}]"
    if d["l2_copies"].get(msubj):
        return f"{_signature(d, msubj):<40s}  [ctor: copies-params-to-fields]"
    return None


def _format_methods(d: dict) -> list[str]:
    l2_lines = []
    rich_methods: list[str] = []
    for msubj in d["method_subjects"]:
        line = _l2_one_liner(d, msubj)
        if line is not None:
            l2_lines.append("  " + line)
        else:
            rich_methods.append(msubj)

    out: list[str] = []
    if l2_lines:
        out.append(f"L2 methods ({len(l2_lines)}):")
        out.extend(l2_lines)
    if rich_methods:
        out.append(f"methods ({len(rich_methods)}):")
        for msubj in rich_methods:
            out.extend(_format_rich_method(d, msubj))
    return out


def _format_rich_method(d: dict, msubj: str) -> list[str]:
    rt   = d["method_returns"].get(msubj) or "void"
    sig  = _signature(d, msubj)
    line = _line_of(d["method_lines"].get(msubj))
    head = f"  {sig} -> {rt}{line}"

    out = [head]
    reads  = sorted({_short_field(fs) for fs in d["reads_field"].get(msubj, [])})
    writes = sorted({_short_field(fs) for fs in d["writes_field"].get(msubj, [])})
    calls  = sorted(set(d["calls_out"].get(msubj, [])))
    incoming = sorted({_short_method(m) for m in d["called_by"].get(msubj, [])})

    if reads:
        out.append(f"    R   {', '.join(reads)}")
    if writes:
        out.append(f"    W   {', '.join(writes)}")
    if calls:
        # Truncate if pathological (>10): show first 8 + count
        if len(calls) > 10:
            shown = ", ".join(calls[:8])
            out.append(f"    →   {shown}, … (+{len(calls)-8})")
        else:
            out.append(f"    →   {', '.join(calls)}")
    if incoming:
        out.append(f"    ←   {', '.join(incoming)}")
    if not (reads or writes or calls or incoming):
        out.append("    (no recorded reads/writes/calls/callers)")
    return out


def render(conn, cname: str) -> str:
    d = _load(conn, cname)
    if not d["kind"] and not d["field_subjects"] and not d["method_subjects"]:
        return f"# class:{cname} not found in corkboard.db (no parser_java facts)"
    out = [_format_class_header(d), ""]
    out.extend(_format_fields(d))
    out.append("")
    out.extend(_format_methods(d))
    return "\n".join(out)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cname   = argv[1]
    db_path = Path(argv[2]) if len(argv) >= 3 else DEFAULT_DB
    conn    = cb.bootstrap(db_path)
    print(render(conn, cname))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
