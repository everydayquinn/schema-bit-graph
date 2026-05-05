"""
parser_jvm.py — static-decode JVM .class files into corkboard.db.

Third substrate after cpu_4bit (4-bit register) and parser_6502 (8-bit
register). JVM is a stack machine — different ISA shape, same predicate
vocabulary. Cross-substrate query that worked on cpu_4bit + parser_6502
also works on parser_jvm.

Driver: shells out to `javap -c -p <classfile>`, parses the output,
emits one fact per instruction under traveler='parser_jvm'.

Subjects:
    prog:<class>                              one per .class
    insn:<class>:<method>:<offset>            one per bytecode instruction

Predicates emitted:
    prog:*    HAS_MD5, INGESTED_AT
    insn:*    IN_PROGRAM, IN_METHOD, AT_ADDRESS, HAS_MNEMONIC,
              HAS_OPERANDS, HAS_SIZE (always 1 'instruction', not bytes —
              JVM offsets count bytes but each disasm row is one logical
              instruction; we still report HAS_SIZE for cross-substrate
              query parity), HAS_BYTES (omitted for now — javap doesn't
              show raw bytes by default)
    insn:*    STACK_DELTA       e.g. '+1', '-1', '-2+1', '0'
    insn:*    READS_LOCAL N      for iload_N / aload_N etc.
    insn:*    WRITES_LOCAL N     for istore_N / astore_N etc.
    insn:*    BRANCH s            for goto / if_*: 'unconditional:N',
                                  'conditional:N'; for ireturn: 'return'

This is the static analog of cpu_4bit's per-cycle WRITES_REG/BRANCH facts.
A future sim_jvm (runtime instrumentation via Java agent) would emit per-
step facts; that's deferred.

Usage:
    python3 parser_jvm.py <ClassFile.class> [corkboard.db]
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import corkboard as cb

HERE       = Path(__file__).parent
DEFAULT_DB = HERE / "corkboard.db"


# ------------------------------------------------------------------
# Opcode → (stack_delta, locals_read[], locals_written[], branch_kind)
# stack_delta is a signed-counts string: '-2+1' (pops 2, pushes 1) etc.
# locals_read/written: list of slot numbers (extracted from mnemonic suffix
# for short forms like iload_2, or from operand for long form iload N).
# branch_kind: None | 'unconditional' | 'conditional' | 'return'
# Coverage: the 7 target opcodes from the calibration program + a few
# adjacent ones we'll see in main()/<init>.
# ------------------------------------------------------------------

# The opcodes we emit predicates for. Anything not listed gets only the
# basic AT_ADDRESS/HAS_MNEMONIC/HAS_OPERANDS/IN_PROGRAM/IN_METHOD fact set.
OPCODE_INFO = {
    # iconst_<N>: push int constant N
    "iconst_0":   {"delta": "+1"},
    "iconst_1":   {"delta": "+1"},
    "iconst_2":   {"delta": "+1"},
    "iconst_3":   {"delta": "+1"},
    "iconst_4":   {"delta": "+1"},
    "iconst_5":   {"delta": "+1"},
    "iconst_m1":  {"delta": "+1"},
    # iload_<N>: push local var N
    "iload_0":    {"delta": "+1", "reads_local": [0]},
    "iload_1":    {"delta": "+1", "reads_local": [1]},
    "iload_2":    {"delta": "+1", "reads_local": [2]},
    "iload_3":    {"delta": "+1", "reads_local": [3]},
    "iload":      {"delta": "+1", "reads_local_from_operand": True},
    # istore_<N>: pop, store in local N
    "istore_0":   {"delta": "-1", "writes_local": [0]},
    "istore_1":   {"delta": "-1", "writes_local": [1]},
    "istore_2":   {"delta": "-1", "writes_local": [2]},
    "istore_3":   {"delta": "-1", "writes_local": [3]},
    "istore":     {"delta": "-1", "writes_local_from_operand": True},
    # arithmetic
    "iadd":       {"delta": "-2+1"},
    "isub":       {"delta": "-2+1"},
    "imul":       {"delta": "-2+1"},
    "idiv":       {"delta": "-2+1"},
    # control flow
    "if_icmpge":  {"delta": "-2", "branch": "conditional"},
    "if_icmplt":  {"delta": "-2", "branch": "conditional"},
    "if_icmpeq":  {"delta": "-2", "branch": "conditional"},
    "if_icmpne":  {"delta": "-2", "branch": "conditional"},
    "if_icmpgt":  {"delta": "-2", "branch": "conditional"},
    "if_icmple":  {"delta": "-2", "branch": "conditional"},
    "ifeq":       {"delta": "-1", "branch": "conditional"},
    "ifne":       {"delta": "-1", "branch": "conditional"},
    "iflt":       {"delta": "-1", "branch": "conditional"},
    "ifge":       {"delta": "-1", "branch": "conditional"},
    "ifgt":       {"delta": "-1", "branch": "conditional"},
    "ifle":       {"delta": "-1", "branch": "conditional"},
    "goto":       {"delta": "0",  "branch": "unconditional"},
    "ireturn":    {"delta": "-1", "branch": "return"},
    "return":     {"delta": "0",  "branch": "return"},
    # object/method (best-effort; not all of these are exercised by CountUp)
    "aload_0":    {"delta": "+1", "reads_local": [0]},
    "aload_1":    {"delta": "+1", "reads_local": [1]},
    "aload":      {"delta": "+1", "reads_local_from_operand": True},
    "invokespecial": {"delta": "?"},   # depends on signature; can't compute statically without method ref resolution
    "invokestatic":  {"delta": "?"},
    "invokevirtual": {"delta": "?"},
    "getstatic":     {"delta": "+1"},
    "putstatic":     {"delta": "-1"},
}


# javap output format we parse. After the "Code:" header, lines look like:
#         0: iconst_0
#         1: istore_1
#         6: if_icmpge     20
#        16: istore_2
#        17: goto          4
#         3: iconst_5
#         4: invokestatic  #13                 // Method countTo:(I)I
INSN_LINE_RE = re.compile(
    r'^\s*(?P<offset>\d+):\s+(?P<mnemonic>\S+)(?:\s+(?P<operands>.+?))?\s*(?://\s*.*)?$'
)
METHOD_HEADER_RE = re.compile(
    r'^\s*(?:public|private|protected|static|final|abstract|synchronized|native|\s)*'
    r'.*?(?P<name>\S+)\s*\(.*?\).*?(?:throws|;|\{|$)'
)


def run_javap(classfile: Path) -> str:
    """Return the full -c -p output for the given .class file."""
    if not classfile.exists():
        raise FileNotFoundError(f"no class file at {classfile}")
    result = subprocess.run(
        ["javap", "-c", "-p", str(classfile)],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def parse_javap(output: str) -> tuple[str, list[dict]]:
    """Parse javap output into (class_name, [method_dict, ...]).

    Each method_dict has:
        name           e.g. "countTo" or "<init>"
        signature_raw  the full declaration line as printed
        instructions   list of {offset, mnemonic, operands, raw_line}
    """
    lines = output.splitlines()
    class_name = None
    methods = []
    cur_method = None
    in_code = False

    for raw_line in lines:
        # class header: "public class CountUp {"
        if class_name is None:
            m = re.search(r'\bclass\s+(\S+)\s*\{', raw_line)
            if m:
                class_name = m.group(1)
                continue

        line = raw_line.rstrip()
        # method declaration line: contains ( and ) and is not indented past
        # what method declarations are at (they live at the class-body indent
        # in javap output, typically 2 spaces).
        # Heuristic: line ends with ');' or has "(...)\n" and no leading "Code:"
        stripped = line.lstrip()
        if (stripped.endswith(';') and '(' in stripped and ')' in stripped
            and not stripped.startswith(('public ', 'private ', 'static '))) :
            # not a method
            pass

        if stripped.startswith("Code:"):
            in_code = True
            continue

        # Method declaration: starts with a modifier or returns to an empty
        # state between methods. javap 26 output places method declarations
        # on a line ending with ');' inside the class body.
        if (stripped.endswith(');')
            and ('(' in stripped) and (' = ' not in stripped)
            and not raw_line.startswith('         ')):  # 9-space indent = code
            # Looks like a method declaration. Extract the method name.
            # Match the last identifier before '('.
            m = re.search(r'(\S+)\s*\(', stripped)
            if m:
                cur_method = {
                    "name": m.group(1).split('.')[-1],  # strip 'java.lang.String' style
                    "signature_raw": stripped,
                    "instructions": [],
                }
                methods.append(cur_method)
                in_code = False
                continue

        # Instruction line inside a Code: block
        if in_code and cur_method is not None:
            insn_match = INSN_LINE_RE.match(raw_line)
            if insn_match:
                cur_method["instructions"].append({
                    "offset":   int(insn_match.group("offset")),
                    "mnemonic": insn_match.group("mnemonic"),
                    "operands": (insn_match.group("operands") or "").strip(),
                    "raw_line": raw_line,
                })
                continue

        # End of code block (blank line after instructions, or new method)
        if in_code and not stripped:
            in_code = False

    if class_name is None:
        raise ValueError("could not find class header in javap output")
    return class_name, methods


def extract_local_slot_from_operand(operands: str) -> int | None:
    """For long-form iload/istore, the operand is a number. Return it or None."""
    if not operands:
        return None
    m = re.match(r'^(\d+)', operands.strip())
    return int(m.group(1)) if m else None


def extract_branch_target(operands: str) -> int | None:
    """For goto/if_*, the operand is the target offset. Return it or None."""
    if not operands:
        return None
    m = re.match(r'^(\d+)', operands.strip())
    return int(m.group(1)) if m else None


def ensure_traveler(conn) -> None:
    cb.register_traveler(conn, "parser_jvm",
        "static decode of JVM .class files via javap -c -p",
        "substrate",
        source="parser_jvm.py (built fresh; web-Claude predicate dictionary as starting point)",
        note="Stack-machine substrate. Static analyzer, not runtime tracer. Same predicate vocabulary as cpu_4bit and parser_6502 (AT_ADDRESS, HAS_MNEMONIC, HAS_OPERANDS, IN_PROGRAM) plus stack-effect predicates (STACK_DELTA, READS_LOCAL, WRITES_LOCAL, BRANCH).")


def populate(conn, classfile: Path) -> dict:
    """javap a .class file and emit facts. Returns counts dict."""
    if not classfile.exists():
        raise FileNotFoundError(f"no class file at {classfile}")

    ensure_traveler(conn)

    md5 = hashlib.md5(classfile.read_bytes()).hexdigest()
    ts  = datetime.now().isoformat(timespec="milliseconds")

    output = run_javap(classfile)
    class_name, methods = parse_javap(output)

    ctx = {
        "session_marker":   "session_6_2026-05-04",
        "via":              "parser_jvm.py — Day 3 calibration substrate",
        "classfile":        str(classfile),
        "md5":              md5,
        "method_count":     len(methods),
    }

    prog_subj = f"prog:{class_name}"
    cb.emit(conn, "parser_jvm", prog_subj, "HAS_MD5",     md5, captured_in_context=ctx)
    cb.emit(conn, "parser_jvm", prog_subj, "INGESTED_AT", ts,  captured_in_context=ctx)

    n_insns = 0
    for method in methods:
        method_id = f"{class_name}.{method['name']}"
        for insn in method["instructions"]:
            insn_subj = f"insn:{class_name}:{method['name']}:{insn['offset']}"
            cb.emit(conn, "parser_jvm", insn_subj, "IN_PROGRAM",   prog_subj, object_kind="ref", captured_in_context=ctx)
            cb.emit(conn, "parser_jvm", insn_subj, "IN_METHOD",    method_id,                    captured_in_context=ctx)
            cb.emit(conn, "parser_jvm", insn_subj, "AT_ADDRESS",   str(insn["offset"]),          captured_in_context=ctx)
            cb.emit(conn, "parser_jvm", insn_subj, "HAS_MNEMONIC", insn["mnemonic"].lower(),     captured_in_context=ctx)
            cb.emit(conn, "parser_jvm", insn_subj, "HAS_OPERANDS", insn["operands"],             captured_in_context=ctx)
            cb.emit(conn, "parser_jvm", insn_subj, "HAS_SIZE",     "1",                          captured_in_context=ctx,
                    notes_for_claude={"note": "JVM bytecode 'size' is debatable — instructions span variable bytes, but javap shows one logical insn per row. Reporting 1 for cross-substrate query parity; see HAS_OPERANDS for actual operand bytes."})

            # Look up opcode info for stack/local/branch effects
            info = OPCODE_INFO.get(insn["mnemonic"].lower())
            if info is None:
                continue  # unknown opcode — only basic facts emitted

            if "delta" in info:
                cb.emit(conn, "parser_jvm", insn_subj, "STACK_DELTA", info["delta"],
                        captured_in_context=ctx)

            for slot in info.get("reads_local", []):
                cb.emit(conn, "parser_jvm", insn_subj, "READS_LOCAL", str(slot),
                        captured_in_context=ctx)
            if info.get("reads_local_from_operand"):
                slot = extract_local_slot_from_operand(insn["operands"])
                if slot is not None:
                    cb.emit(conn, "parser_jvm", insn_subj, "READS_LOCAL", str(slot),
                            captured_in_context=ctx)

            for slot in info.get("writes_local", []):
                cb.emit(conn, "parser_jvm", insn_subj, "WRITES_LOCAL", str(slot),
                        captured_in_context=ctx)
            if info.get("writes_local_from_operand"):
                slot = extract_local_slot_from_operand(insn["operands"])
                if slot is not None:
                    cb.emit(conn, "parser_jvm", insn_subj, "WRITES_LOCAL", str(slot),
                            captured_in_context=ctx)

            branch_kind = info.get("branch")
            if branch_kind == "return":
                cb.emit(conn, "parser_jvm", insn_subj, "BRANCH", "return",
                        captured_in_context=ctx)
            elif branch_kind in ("conditional", "unconditional"):
                target = extract_branch_target(insn["operands"])
                if target is not None:
                    cb.emit(conn, "parser_jvm", insn_subj, "BRANCH",
                            f"{branch_kind}:{target}", captured_in_context=ctx)

            n_insns += 1

    return {
        "classfile":   str(classfile),
        "class_name":  class_name,
        "method_count":len(methods),
        "instructions":n_insns,
        "md5":         md5,
    }


def main():
    if len(sys.argv) < 2:
        sys.exit(f"usage: python3 {sys.argv[0]} <ClassFile.class> [corkboard.db]")
    classfile = Path(sys.argv[1])
    db        = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_DB

    conn = cb.bootstrap(db)
    info = populate(conn, classfile)
    conn.commit()

    n_live = conn.execute(
        "SELECT COUNT(*) FROM facts WHERE traveler='parser_jvm' AND retracted_at IS NULL"
    ).fetchone()[0]

    print(f"classfile:     {info['classfile']}")
    print(f"class:         {info['class_name']} ({info['method_count']} methods, {info['instructions']} insns)")
    print(f"md5:           {info['md5'][:16]}...")
    print(f"parser_jvm facts (live): {n_live}")
    conn.close()


if __name__ == "__main__":
    main()
