"""
parser_java.py — index Java source files into corkboard.db.

Companion to parser_jvm.py. Where parser_jvm reads .class files via javap
and emits bytecode-level facts, parser_java reads .java files via the
javalang AST and emits source-level facts: classes, methods, fields,
parameters, locals, calls, types referenced.

Subjects:
    class:<ClassName>
    method:<ClassName>.<methodName>
    field:<ClassName>.<fieldName>
    param:<ClassName>.<methodName>.<paramName>
    local:<ClassName>.<methodName>.<localName>
    import:<importing-class>:<imported-fqn>

Predicates emitted (registered idempotently on first run):
    HAS_NAME, DEFINED_AT, HAS_MODIFIER, IS_KIND, HAS_SOURCE_FILE
    BELONGS_TO, RETURNS_TYPE, HAS_PARAM, HAS_TYPE
    EXTENDS, IMPLEMENTS, IMPORTS_FROM
    CALLS, DECLARES_LOCAL, USES_TYPE

Usage:
    python3 parser_java.py <FileOrDir.java> [corkboard.db]

If a directory is passed, every .java file inside is indexed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import javalang

import corkboard as cb


HERE       = Path(__file__).parent
DEFAULT_DB = HERE / "corkboard.db"
TRAVELER   = "parser_java"


# ------------------------------------------------------------------
# Vocabulary registration (idempotent)
# ------------------------------------------------------------------
NAMESPACES = [
    ("class:",  "Java class / interface / enum definitions",
     "class:CountUp"),
    ("method:", "Java method definitions (qualified by enclosing class)",
     "method:CountUp.countTo"),
    ("field:",  "Java field definitions (qualified by enclosing class)",
     "field:CountUp.LOG_TAG"),
    ("param:",  "method parameters (qualified by class.method)",
     "param:CountUp.countTo.n"),
    ("local:",  "method local variables (qualified by class.method)",
     "local:CountUp.countTo.sum"),
    ("import:", "import edges; subject is importing-class:imported-fqn",
     "import:CountUp:java.lang.System"),
]

# (name, domain, range, cardinality, definition, examples)
PREDICATES = [
    ("HAS_NAME",        "any",    "literal", "one",
     "Display name of the entity. Java identifier.",
     ["class:CountUp HAS_NAME 'CountUp'",
      "method:CountUp.countTo HAS_NAME 'countTo'"]),

    ("DEFINED_AT",      "any",    "literal", "one",
     "Source location: '<relative-path>:<line>'.",
     ["class:CountUp DEFINED_AT 'kit_jvm_lessons/src/CountUp.java:18'"]),

    ("HAS_MODIFIER",    "any",    "literal", "many",
     "Java modifier keyword (public, static, final, abstract, etc.).",
     ["method:CountUp.countTo HAS_MODIFIER 'public'",
      "method:CountUp.countTo HAS_MODIFIER 'static'"]),

    ("IS_KIND",         "class",  "literal", "one",
     "Kind of type definition: 'class' | 'interface' | 'enum' | 'annotation'.",
     ["class:CountUp IS_KIND 'class'"]),

    ("HAS_SOURCE_FILE", "class",  "literal", "one",
     "Path to the .java file declaring this class.",
     ["class:CountUp HAS_SOURCE_FILE 'kit_jvm_lessons/src/CountUp.java'"]),

    ("BELONGS_TO",      "any",    "ref",     "one",
     "Member belongs to the named enclosing type.",
     ["method:CountUp.countTo BELONGS_TO class:CountUp",
      "field:CountUp.LOG_TAG BELONGS_TO class:CountUp"]),

    ("RETURNS_TYPE",    "method", "literal", "one",
     "Method's declared return type as a string.",
     ["method:CountUp.countTo RETURNS_TYPE 'int'",
      "method:CountUp.main RETURNS_TYPE 'void'"]),

    ("HAS_PARAM",       "method", "ref",     "many",
     "Method has the named parameter (subject is param:Class.method.name).",
     ["method:CountUp.countTo HAS_PARAM param:CountUp.countTo.n"]),

    ("HAS_TYPE",        "any",    "literal", "one",
     "Declared type of a parameter, local, or field.",
     ["param:CountUp.countTo.n HAS_TYPE 'int'",
      "local:CountUp.countTo.sum HAS_TYPE 'int'"]),

    ("EXTENDS",         "class",  "literal", "one",
     "Superclass name (string FQN or simple name as written in source).",
     ["class:Foo EXTENDS 'Bar'"]),

    ("IMPLEMENTS",      "class",  "literal", "many",
     "Interface implemented by this class.",
     ["class:Foo IMPLEMENTS 'Runnable'"]),

    ("IMPORTS_FROM",    "class",  "literal", "many",
     "Imported FQN as written in the import statement.",
     ["class:CountUp IMPORTS_FROM 'java.util.List'"]),

    ("CALLS",           "method", "literal", "many",
     "Method invocation target as written in source. Unresolved (no "
     "type-checker); useful for grep-replace and join-with-method-defs.",
     ["method:CountUp.main CALLS 'countTo'",
      "method:CountUp.main CALLS 'System.out.println'"]),

    ("DECLARES_LOCAL",  "method", "ref",     "many",
     "Method declares the named local variable.",
     ["method:CountUp.countTo DECLARES_LOCAL local:CountUp.countTo.sum"]),

    ("USES_TYPE",       "method", "literal", "many",
     "A type referenced inside the method body (for joins / where-used).",
     ["method:CountUp.main USES_TYPE 'String'"]),
]


def bootstrap_vocab(conn):
    cb.register_traveler(
        conn, TRAVELER,
        purpose="Index Java source files (AST level): classes, methods, "
                "fields, parameters, locals, calls, types.",
        role="substrate",
        source="parser_java.py",
        note="javalang-driven static AST walk. Calls are unresolved.",
    )
    for prefix, defn, ex in NAMESPACES:
        cb.register_namespace(conn, prefix, defn, ex)
    for name, domain, range_, card, defn, exs in PREDICATES:
        cb.register_predicate(conn, name, domain, range_, card, defn, exs)


# ------------------------------------------------------------------
# AST walking
# ------------------------------------------------------------------
def _line_of(node) -> int | None:
    """javalang nodes carry .position only on top-level declarations
    sometimes. Fall back to None when missing."""
    pos = getattr(node, "position", None)
    return pos.line if pos else None


def _type_string(t) -> str:
    """Render a javalang type node as a readable string."""
    if t is None:
        return "void"
    name = getattr(t, "name", None) or t.__class__.__name__
    suffix = ""
    dims = getattr(t, "dimensions", None) or []
    suffix += "[]" * len(dims)
    args = getattr(t, "arguments", None)
    if args:
        rendered = []
        for a in args:
            sub = getattr(a, "type", None)
            rendered.append(_type_string(sub) if sub else "?")
        return f"{name}<{', '.join(rendered)}>{suffix}"
    return f"{name}{suffix}"


def _emit_class(conn, rel_path: str, cls_node, kind: str):
    cname = cls_node.name
    csubj = f"class:{cname}"
    line = _line_of(cls_node) or 0
    cb.emit(conn, TRAVELER, csubj, "HAS_NAME",        cname)
    cb.emit(conn, TRAVELER, csubj, "DEFINED_AT",      f"{rel_path}:{line}")
    cb.emit(conn, TRAVELER, csubj, "IS_KIND",         kind)
    cb.emit(conn, TRAVELER, csubj, "HAS_SOURCE_FILE", rel_path)
    for m in (cls_node.modifiers or []):
        cb.emit(conn, TRAVELER, csubj, "HAS_MODIFIER", m)
    ext = getattr(cls_node, "extends", None)
    if ext is not None:
        cb.emit(conn, TRAVELER, csubj, "EXTENDS", _type_string(ext))
    for impl in (getattr(cls_node, "implements", None) or []):
        cb.emit(conn, TRAVELER, csubj, "IMPLEMENTS", _type_string(impl))

    # fields
    for f in (cls_node.fields or []):
        ftype = _type_string(f.type)
        for decl in f.declarators:
            fname = decl.name
            fsubj = f"field:{cname}.{fname}"
            cb.emit(conn, TRAVELER, fsubj, "HAS_NAME",   fname)
            cb.emit(conn, TRAVELER, fsubj, "BELONGS_TO", csubj, object_kind="ref")
            cb.emit(conn, TRAVELER, fsubj, "HAS_TYPE",   ftype)
            for m in (f.modifiers or []):
                cb.emit(conn, TRAVELER, fsubj, "HAS_MODIFIER", m)
            fline = _line_of(f) or line
            cb.emit(conn, TRAVELER, fsubj, "DEFINED_AT", f"{rel_path}:{fline}")

    # methods
    for m in (cls_node.methods or []):
        _emit_method(conn, rel_path, cname, m)

    # constructors are stored separately
    for ctor in (getattr(cls_node, "constructors", None) or []):
        _emit_method(conn, rel_path, cname, ctor, ctor_name=cname)


def _emit_method(conn, rel_path: str, cname: str, m, ctor_name: str | None = None):
    mname = ctor_name if ctor_name else m.name
    msubj = f"method:{cname}.{mname}"
    csubj = f"class:{cname}"
    line  = _line_of(m) or 0
    rtype = _type_string(getattr(m, "return_type", None))
    cb.emit(conn, TRAVELER, msubj, "HAS_NAME",     mname)
    cb.emit(conn, TRAVELER, msubj, "BELONGS_TO",   csubj, object_kind="ref")
    cb.emit(conn, TRAVELER, msubj, "DEFINED_AT",   f"{rel_path}:{line}")
    cb.emit(conn, TRAVELER, msubj, "RETURNS_TYPE", rtype)
    for mod in (m.modifiers or []):
        cb.emit(conn, TRAVELER, msubj, "HAS_MODIFIER", mod)

    # parameters
    for p in (m.parameters or []):
        psubj = f"param:{cname}.{mname}.{p.name}"
        ptype = _type_string(p.type)
        cb.emit(conn, TRAVELER, psubj, "HAS_NAME",   p.name)
        cb.emit(conn, TRAVELER, psubj, "BELONGS_TO", msubj, object_kind="ref")
        cb.emit(conn, TRAVELER, psubj, "HAS_TYPE",   ptype)
        cb.emit(conn, TRAVELER, msubj, "HAS_PARAM",  psubj, object_kind="ref")

    # walk method body for locals, calls, type refs
    body = getattr(m, "body", None) or []
    seen_types  = set()
    seen_locals = set()
    for node in _walk(body):
        if isinstance(node, javalang.tree.LocalVariableDeclaration):
            ltype = _type_string(node.type)
            for d in node.declarators:
                lsubj = f"local:{cname}.{mname}.{d.name}"
                if lsubj in seen_locals:
                    continue
                seen_locals.add(lsubj)
                cb.emit(conn, TRAVELER, lsubj, "HAS_NAME",   d.name)
                cb.emit(conn, TRAVELER, lsubj, "BELONGS_TO", msubj, object_kind="ref")
                cb.emit(conn, TRAVELER, lsubj, "HAS_TYPE",   ltype)
                cb.emit(conn, TRAVELER, msubj, "DECLARES_LOCAL", lsubj, object_kind="ref")
                if ltype not in seen_types:
                    seen_types.add(ltype)
                    cb.emit(conn, TRAVELER, msubj, "USES_TYPE", ltype)
        elif isinstance(node, javalang.tree.MethodInvocation):
            # qualifier.member(args) -> 'qualifier.member' or just 'member'
            qual = getattr(node, "qualifier", None)
            target = f"{qual}.{node.member}" if qual else node.member
            cb.emit(conn, TRAVELER, msubj, "CALLS", target)
        elif isinstance(node, javalang.tree.ReferenceType):
            tname = _type_string(node)
            if tname not in seen_types:
                seen_types.add(tname)
                cb.emit(conn, TRAVELER, msubj, "USES_TYPE", tname)


def _walk(obj):
    """Yield every javalang Node found beneath obj (including obj itself).
    obj may be a Node, a list/tuple of nodes, or arbitrary scalar."""
    if isinstance(obj, javalang.ast.Node):
        yield obj
        for attr_name in obj.attrs:
            yield from _walk(getattr(obj, attr_name, None))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _walk(item)


# ------------------------------------------------------------------
# Imports + entry point
# ------------------------------------------------------------------
def _emit_imports(conn, rel_path: str, top_class: str, tree):
    csubj = f"class:{top_class}"
    for imp in (tree.imports or []):
        cb.emit(conn, TRAVELER, csubj, "IMPORTS_FROM", imp.path)


def _path_relative(path: Path, base: Path) -> str:
    """Return path relative to base if possible; otherwise the absolute path."""
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path.resolve())


def index_file(conn, java_path: Path, repo_root: Path) -> int:
    """Parse one .java file and emit facts. Returns count of facts emitted in this call."""
    rel = _path_relative(java_path, repo_root)
    src = java_path.read_text()
    before = conn.execute(
        "SELECT COUNT(*) c FROM facts WHERE traveler=?", (TRAVELER,)
    ).fetchone()["c"]

    tree = javalang.parse.parse(src)
    classes = list(tree.types or [])
    if not classes:
        return 0
    top_name = classes[0].name
    _emit_imports(conn, rel, top_name, tree)

    for t in classes:
        if isinstance(t, javalang.tree.ClassDeclaration):
            kind = "class"
        elif isinstance(t, javalang.tree.InterfaceDeclaration):
            kind = "interface"
        elif isinstance(t, javalang.tree.EnumDeclaration):
            kind = "enum"
        elif isinstance(t, javalang.tree.AnnotationDeclaration):
            kind = "annotation"
        else:
            kind = t.__class__.__name__
        _emit_class(conn, rel, t, kind)

    after = conn.execute(
        "SELECT COUNT(*) c FROM facts WHERE traveler=?", (TRAVELER,)
    ).fetchone()["c"]
    return after - before


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    target  = Path(argv[1]).resolve()
    db_path = Path(argv[2]) if len(argv) >= 3 else DEFAULT_DB

    conn = cb.bootstrap(db_path)
    bootstrap_vocab(conn)

    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = sorted(target.rglob("*.java"))
    else:
        print(f"not found: {target}", file=sys.stderr)
        return 1

    repo_root = HERE
    total_facts = 0
    for f in files:
        try:
            n = index_file(conn, f, repo_root)
            print(f"  {_path_relative(f, repo_root):<60} +{n} facts")
            total_facts += n
        except javalang.parser.JavaSyntaxError as e:
            print(f"  {_path_relative(f, repo_root):<60} parse error: {e}", file=sys.stderr)
        except Exception as e:
            print(f"  {_path_relative(f, repo_root):<60} error: {e}", file=sys.stderr)
    conn.commit()

    live = conn.execute(
        "SELECT COUNT(*) c FROM facts WHERE traveler=? AND retracted_at IS NULL",
        (TRAVELER,),
    ).fetchone()["c"]
    print(f"\nfiles indexed:  {len(files)}")
    print(f"facts emitted:  {total_facts}")
    print(f"parser_java live total in db: {live}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
