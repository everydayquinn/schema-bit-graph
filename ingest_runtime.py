"""
ingest_runtime.py — turn `-Xlog:class+load` output into runtime facts.

Closes the calibration loop: parser_java/translator_java produce static
facts; running Cave Game with the JVM's class-load logging produces a
record of which classes ACTUALLY got touched. This script reads that
record and emits one fact per loaded class, joining a runtime view onto
the same fact-store the static views live in.

Lines look like:
    [0.017s][info][class,load] caveGame.CaveGame source: file:/.../CAVE_V1.0.4.jar

Only `caveGame.*` package loads are ingested (filters out the JDK noise).

Usage:
    python3 ingest_runtime.py <classload-log-file> [corkboard.db] [--package PREFIX]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import corkboard as cb


HERE       = Path(__file__).parent
DEFAULT_DB = HERE / "corkboard.db"
TRAVELER   = "runtime_jvm"

LINE = re.compile(
    r"^\[(?P<t>[\d.]+)s\]\[info\]\[class,load\]\s+(?P<fqn>\S+)(?:\s+source:\s*(?P<src>.+))?$"
)


PREDICATES = [
    ("WAS_LOADED",      "class", "literal", "one",
     "Class was loaded by the JVM during the recorded run.",
     ["class:CaveGame WAS_LOADED 'true'"]),

    ("LOADED_AT_TIME",  "class", "literal", "one",
     "Time (seconds since JVM start) when the class was first loaded.",
     ["class:CaveGame LOADED_AT_TIME '0.017'"]),

    ("LOADED_FROM",     "class", "literal", "one",
     "Source URI the class was loaded from (jar, file, module).",
     ["class:CaveGame LOADED_FROM 'file:/.../CAVE_V1.0.4.jar'"]),
]


def bootstrap_vocab(conn):
    cb.register_traveler(
        conn, TRAVELER,
        purpose="Record runtime class-load events from -Xlog:class+load output. "
                "External-source ground truth that complements the static index.",
        role="external",
        source="ingest_runtime.py / -Xlog:class+load",
        note="Captures only first-load time per class; doesn't track unloads "
             "or per-instance creation.",
    )
    for name, domain, range_, card, defn, exs in PREDICATES:
        cb.register_predicate(conn, name, domain, range_, card, defn, exs)


def short_name(fqn: str) -> str:
    """`caveGame.CaveGame` -> `CaveGame`. Inner classes (`A$B`) stay as-is."""
    return fqn.rsplit(".", 1)[-1]


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2

    log_path = Path(argv[1])
    db_path  = DEFAULT_DB
    pkg      = "caveGame."

    args = argv[2:]
    while args:
        if args[0] == "--package" and len(args) >= 2:
            pkg = args[1]
            args = args[2:]
        else:
            db_path = Path(args[0])
            args = args[1:]

    conn = cb.bootstrap(db_path)
    bootstrap_vocab(conn)

    loaded = 0
    skipped = 0
    for raw in log_path.read_text().splitlines():
        m = LINE.match(raw)
        if not m:
            continue
        fqn = m.group("fqn")
        if not fqn.startswith(pkg):
            skipped += 1
            continue
        cls = short_name(fqn)
        # Skip inner classes — they're loaded by enclosing class
        if "$" in cls:
            continue
        subj = f"class:{cls}"
        cb.emit(conn, TRAVELER, subj, "WAS_LOADED",     "true")
        cb.emit(conn, TRAVELER, subj, "LOADED_AT_TIME", m.group("t"))
        src = (m.group("src") or "").strip()
        if src:
            cb.emit(conn, TRAVELER, subj, "LOADED_FROM", src)
        loaded += 1

    conn.commit()
    print(f"loaded {loaded} {pkg!r} class-load events "
          f"(filtered out {skipped} non-package lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
