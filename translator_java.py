"""
translator_java.py — pre-digest mechanical Java patterns into L2 facts.

Sits on top of parser_java's L1 structural facts. Detects deterministic,
unambiguous patterns (getters, setters, constants, pure delegation,
constructor-copy initializers) and emits one L2 fact per pattern.

The point: Claude shouldn't have to interpret 18 trivial getters. Python
finds them mechanically; Claude reads one fact per match and saves judgment
budget for code that actually requires it.

Reads sources via javalang (same as parser_java) but emits ONLY high-level
pattern facts. Does not duplicate L1 work.

Usage:
    python3 translator_java.py <FileOrDir.java> [corkboard.db]
"""
from __future__ import annotations

import sys
from pathlib import Path

import javalang

import corkboard as cb


HERE       = Path(__file__).parent
DEFAULT_DB = HERE / "corkboard.db"
TRAVELER   = "translator_java"


# ------------------------------------------------------------------
# L2 predicate vocabulary
# ------------------------------------------------------------------
PREDICATES = [
    ("IS_GETTER_OF",   "method", "ref",     "one",
     "Method body is a single 'return field;' — equivalent to direct read.",
     ["method:Player.getX IS_GETTER_OF field:Player.x"]),

    ("IS_SETTER_OF",   "method", "ref",     "one",
     "Method body is a single 'this.field = param;' — equivalent to direct write.",
     ["method:Player.setX IS_SETTER_OF field:Player.x"]),

    ("IS_CONSTANT",    "field",  "literal", "one",
     "Field has 'static final' modifiers; treat as a name for a fixed value.",
     ["field:CountUp.MAX_N IS_CONSTANT 'true'"]),

    ("HAS_VALUE",      "field",  "literal", "one",
     "Field's initializer expression as written in source.",
     ["field:CaveGame.WIDTH HAS_VALUE '1024'"]),

    ("DELEGATES_TO",   "method", "literal", "one",
     "Body is a single forwarding call `target.method(args)` (no extra logic).",
     ["method:GameContainer.addKeyListener DELEGATES_TO 'frame.addKeyListener'"]),

    ("COPIES_PARAMS_TO_FIELDS", "method", "literal", "one",
     "Constructor body is exclusively `this.x = x;` assignments matching parameters.",
     ["method:Player.<init> COPIES_PARAMS_TO_FIELDS 'all'"]),

    ("IS_TRIVIAL",     "method", "literal", "one",
     "Method has no body (abstract/interface) or body is empty `{}`.",
     ["method:KeyListener.keyTyped IS_TRIVIAL 'empty-body'"]),
]


def bootstrap_vocab(conn):
    cb.register_traveler(
        conn, TRAVELER,
        purpose="L2 derived facts: mechanical Java patterns over parser_java's "
                "L1 structural facts. Removes interpretation burden from Claude.",
        role="meta",
        source="translator_java.py",
        note="Pure pattern detector — reads .java files but only emits "
             "high-level pattern facts.",
    )
    for name, domain, range_, card, defn, exs in PREDICATES:
        cb.register_predicate(conn, name, domain, range_, card, defn, exs)


# ------------------------------------------------------------------
# Pattern detectors
# ------------------------------------------------------------------
def _is_field_read(expr, class_name: str) -> str | None:
    """If expr is `field` or `this.field`, return field name. Else None."""
    if isinstance(expr, javalang.tree.MemberReference):
        # qualifier=None means a bare name; this handles `return foo;`.
        # qualifier='this' would also hit but javalang typically uses This().
        if not expr.qualifier:
            return expr.member
    if isinstance(expr, javalang.tree.This):
        # This().selectors[0].member would catch `this.foo` — handle below.
        sels = getattr(expr, "selectors", None) or []
        if len(sels) == 1 and isinstance(sels[0], javalang.tree.MemberReference):
            return sels[0].member
    return None


def _detect_getter(m, class_name: str) -> str | None:
    """If method m is a no-arg, non-void method whose body is a single
    `return field;`, return the field name."""
    if (m.parameters or []) != []:
        return None
    if m.return_type is None:
        return None
    body = m.body
    if not body or len(body) != 1:
        return None
    stmt = body[0]
    if not isinstance(stmt, javalang.tree.ReturnStatement):
        return None
    return _is_field_read(stmt.expression, class_name)


def _detect_setter(m, class_name: str) -> str | None:
    """If method m is single-arg void method whose body is a single
    `this.field = param;` (or just `field = param;`), return the field name."""
    params = m.parameters or []
    if len(params) != 1:
        return None
    if m.return_type is not None:
        return None
    body = m.body
    if not body or len(body) != 1:
        return None
    stmt = body[0]
    if not isinstance(stmt, javalang.tree.StatementExpression):
        return None
    expr = stmt.expression
    if not isinstance(expr, javalang.tree.Assignment):
        return None
    if expr.type != "=":
        return None
    # RHS must be a bare reference to the parameter
    rhs = expr.value
    if not isinstance(rhs, javalang.tree.MemberReference) or rhs.qualifier:
        return None
    if rhs.member != params[0].name:
        return None
    # LHS: either `this.field` or bare field name
    lhs = expr.expressionl
    field_name = _is_field_read(lhs, class_name)
    return field_name


def _detect_pure_delegation(m, class_name: str) -> str | None:
    """If method body is a single forwarding call `obj.method(args)` with
    no transformation, return 'qualifier.member' as the delegation target."""
    body = m.body
    if not body or len(body) != 1:
        return None
    stmt = body[0]

    # Two shapes count:
    #   void:    foo.doX(args);             -> StatementExpression(MethodInvocation)
    #   non-void: return foo.doX(args);     -> ReturnStatement(MethodInvocation)
    if isinstance(stmt, javalang.tree.StatementExpression):
        if m.return_type is not None:
            return None
        invocation = stmt.expression
    elif isinstance(stmt, javalang.tree.ReturnStatement):
        if m.return_type is None:
            return None
        invocation = stmt.expression
    else:
        return None

    if not isinstance(invocation, javalang.tree.MethodInvocation):
        return None

    # Method must forward the same args (or no args) — strict shape.
    invo_args = invocation.arguments or []
    method_params = [p.name for p in (m.parameters or [])]
    if len(invo_args) != len(method_params):
        return None
    for arg, pname in zip(invo_args, method_params):
        if not isinstance(arg, javalang.tree.MemberReference) or arg.qualifier:
            return None
        if arg.member != pname:
            return None

    qual = invocation.qualifier or ""
    target = f"{qual}.{invocation.member}" if qual else invocation.member
    return target


def _detect_copies_params(m, class_name: str) -> bool:
    """Constructor where body is exclusively `this.x = x` for each parameter."""
    body = m.body
    if not body:
        return False
    params = [p.name for p in (m.parameters or [])]
    if not params:
        return False
    assigned = []
    for stmt in body:
        if not isinstance(stmt, javalang.tree.StatementExpression):
            return False
        expr = stmt.expression
        if not isinstance(expr, javalang.tree.Assignment) or expr.type != "=":
            return False
        lhs_field = _is_field_read(expr.expressionl, class_name)
        if lhs_field is None:
            return False
        rhs = expr.value
        if (not isinstance(rhs, javalang.tree.MemberReference)
            or rhs.qualifier
            or rhs.member != lhs_field):
            return False
        assigned.append(lhs_field)
    # Every parameter must be copied (order doesn't matter for the L2 claim)
    return set(assigned) == set(params)


def _detect_trivial(m) -> str | None:
    """Empty body or no body."""
    body = getattr(m, "body", None)
    if body is None:
        return "no-body"
    if isinstance(body, list) and len(body) == 0:
        return "empty-body"
    return None


# ------------------------------------------------------------------
# Field-level detectors
# ------------------------------------------------------------------
def _expr_to_source(expr) -> str | None:
    """Best-effort render of a javalang expression as a source-like string."""
    if expr is None:
        return None
    if isinstance(expr, javalang.tree.Literal):
        return str(expr.value)
    if isinstance(expr, javalang.tree.MemberReference):
        if expr.qualifier:
            return f"{expr.qualifier}.{expr.member}"
        return expr.member
    return expr.__class__.__name__  # fallback


# ------------------------------------------------------------------
# Walk + emit
# ------------------------------------------------------------------
def _process_class(conn, cls_node):
    cname = cls_node.name
    csubj = f"class:{cname}"

    # ---- fields: constants ----
    for f in (cls_node.fields or []):
        mods = set(f.modifiers or [])
        is_const = "static" in mods and "final" in mods
        for d in f.declarators:
            fsubj = f"field:{cname}.{d.name}"
            if is_const:
                cb.emit(conn, TRAVELER, fsubj, "IS_CONSTANT", "true")
            init = getattr(d, "initializer", None)
            value = _expr_to_source(init)
            if value is not None:
                cb.emit(conn, TRAVELER, fsubj, "HAS_VALUE", value)

    # ---- methods ----
    methods = list(cls_node.methods or [])
    for m in methods:
        msubj = f"method:{cname}.{m.name}"

        # trivial body
        triv = _detect_trivial(m)
        if triv:
            cb.emit(conn, TRAVELER, msubj, "IS_TRIVIAL", triv)
            continue

        getter_field = _detect_getter(m, cname)
        if getter_field:
            cb.emit(conn, TRAVELER, msubj, "IS_GETTER_OF",
                    f"field:{cname}.{getter_field}", object_kind="ref")
            continue

        setter_field = _detect_setter(m, cname)
        if setter_field:
            cb.emit(conn, TRAVELER, msubj, "IS_SETTER_OF",
                    f"field:{cname}.{setter_field}", object_kind="ref")
            continue

        deleg_target = _detect_pure_delegation(m, cname)
        if deleg_target:
            cb.emit(conn, TRAVELER, msubj, "DELEGATES_TO", deleg_target)

    # ---- constructors ----
    for c in (getattr(cls_node, "constructors", None) or []):
        # constructor's "name" attribute = class name; we use <init> form for subject
        msubj = f"method:{cname}.{c.name}"
        if _detect_copies_params(c, cname):
            cb.emit(conn, TRAVELER, msubj, "COPIES_PARAMS_TO_FIELDS", "all")


def index_file(conn, java_path: Path) -> int:
    src = java_path.read_text()
    before = conn.execute(
        "SELECT COUNT(*) c FROM facts WHERE traveler=?", (TRAVELER,)
    ).fetchone()["c"]
    tree = javalang.parse.parse(src)
    for t in (tree.types or []):
        if isinstance(t, (javalang.tree.ClassDeclaration,
                          javalang.tree.InterfaceDeclaration,
                          javalang.tree.EnumDeclaration)):
            _process_class(conn, t)
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

    total = 0
    for f in files:
        try:
            n = index_file(conn, f)
            print(f"  {f.name:<32} +{n} L2 facts")
            total += n
        except javalang.parser.JavaSyntaxError as e:
            print(f"  {f.name:<32} parse error: {e}", file=sys.stderr)
        except Exception as e:
            print(f"  {f.name:<32} error: {e}", file=sys.stderr)
    conn.commit()

    print(f"\nfiles processed: {len(files)}")
    print(f"L2 facts emitted: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
