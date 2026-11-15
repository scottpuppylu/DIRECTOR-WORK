"""Hash compares that cannot pass by omission, and build freshness by content (DIRECTOR-WORK 2.3.0, F2 + F3 + F4).

Three lessons: a hash compare said PASS because the run had skipped a case and the compare only looked at the cases
present (F2); a build was taken as fresh because its file time was newer than the sources, after a checkout had given
an old source a new time (F3); a CPU reproduction compiled every file the project's default glob found, not the ones
the test meant, and nobody could tell which assembly had run (F4, see templates/CPU_REPRO.md).

  hash_check.py compare --expected EXPECTED.json --actual ACTUAL.json [--allow-extra]
  hash_check.py stamp   --sources PATH ... [--build PATH ...] --out STAMP.json
  hash_check.py fresh   --stamp STAMP.json [--sources PATH ...] [--build PATH ...]
  hash_check.py show    PATH ...

  compare  EXPECTED and ACTUAL are JSON objects {case: hash} (or {"cases": {...}}). Every expected case must be in
           ACTUAL with the same hash: a MISSING case is FAIL, never a skip; a different hash is FAIL; a case only
           ACTUAL has is `~ EXTRA` (FAIL unless --allow-extra). Last line
           `HASH_COMPARE: PASS|FAIL expected=n same=n differ=n missing=n extra=n`.
  stamp    writes the SHA-256 of every source file (folders are walked) and of every build output, after a build.
  fresh    hashes the sources again (the stamp's list unless --sources is given) and compares contents with the stamp:
           any changed, added or removed source makes the build STALE, whatever the file times say; with --build the
           build outputs must also still be the stamped ones. Last line `FRESH: PASS|STALE changed=n added=n removed=n
           build_changed=n`. File modification times are never used.
  show     prints `<absolute path> sha256=<hash> bytes=<n>` for each file: the line a CPU reproduction prints for the
           assembly / executable it actually ran.

Exit 0 PASS, 1 FAIL / STALE, 2 the input cannot be read. Only reads, except stamp --out.
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import sys

SCHEMA = "build-stamp-v1"


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def hashes(paths):
    """{posix path: sha256} for files, walking folders (sorted; skips .git)."""
    out = {}
    for item in paths:
        p = pathlib.Path(item)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and ".git" not in f.parts:
                    out[f.as_posix()] = digest(f)
        elif p.is_file():
            out[p.as_posix()] = digest(p)
        else:
            raise ValueError(f"not found: {item}")
    return out


def cases(path):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    data = data.get("cases", data) if isinstance(data, dict) else data
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object {{case: hash}}")
    return {str(k): str(v) for k, v in data.items()}


def compare(expected, actual, allow_extra):
    lines, n = [], {"same": 0, "differ": 0, "missing": 0, "extra": 0}
    for case in sorted(expected):
        if case not in actual:
            n["missing"] += 1
            lines.append(f"MISSING {case}: expected {expected[case][:16]}, the run has no such case (FAIL, not a skip)")
        elif actual[case] != expected[case]:
            n["differ"] += 1
            lines.append(f"DIFFER  {case}: expected {expected[case][:16]}, got {actual[case][:16]}")
        else:
            n["same"] += 1
    for case in sorted(set(actual) - set(expected)):
        n["extra"] += 1
        lines.append(f"~ EXTRA {case}: not in the expected set" + ("" if allow_extra else " (FAIL; --allow-extra)"))
    failed = n["differ"] or n["missing"] or (n["extra"] and not allow_extra)
    return lines, n, failed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("compare", "stamp", "fresh", "show"))
    ap.add_argument("paths", nargs="*", help="show: the files")
    ap.add_argument("--expected")
    ap.add_argument("--actual")
    ap.add_argument("--allow-extra", action="store_true")
    ap.add_argument("--sources", nargs="+", default=[])
    ap.add_argument("--build", nargs="+", default=[])
    ap.add_argument("--stamp")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        if a.action == "compare":
            if not (a.expected and a.actual):
                ap.error("compare needs --expected and --actual")
            lines, n, failed = compare(cases(a.expected), cases(a.actual), a.allow_extra)
            for line in lines:
                print(line)
            print(f"HASH_COMPARE: {'FAIL' if failed else 'PASS'} expected={len(cases(a.expected))} same={n['same']} "
                  f"differ={n['differ']} missing={n['missing']} extra={n['extra']}")
            return 1 if failed else 0
        if a.action == "show":
            if not a.paths:
                ap.error("show needs one or more files")
            for item in a.paths:
                p = pathlib.Path(item).resolve()
                print(f"{p.as_posix()} sha256={digest(p)} bytes={p.stat().st_size}")
            return 0
        if a.action == "stamp":
            if not (a.sources and a.out):
                ap.error("stamp needs --sources and --out")
            stamp = {"schema": SCHEMA, "time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                     "source_roots": a.sources, "sources": hashes(a.sources), "build": hashes(a.build)}
            pathlib.Path(a.out).write_text(json.dumps(stamp, indent=1) + "\n", encoding="utf-8")
            print(f"STAMP {a.out}: sources={len(stamp['sources'])} build={len(stamp['build'])}")
            return 0
        if not a.stamp:
            ap.error("fresh needs --stamp")
        stamp = json.loads(pathlib.Path(a.stamp).read_text(encoding="utf-8-sig"))
        if not isinstance(stamp, dict) or stamp.get("schema") != SCHEMA:
            raise ValueError(f"{a.stamp} is not a {SCHEMA} stamp (write one with stamp)")
        now = hashes(a.sources or stamp.get("source_roots") or [])
        old = stamp.get("sources", {})
        changed = sorted(p for p in now if p in old and now[p] != old[p])
        added, removed = sorted(set(now) - set(old)), sorted(set(old) - set(now))
        build_changed = []
        if a.build:
            built = hashes(a.build)
            build_changed = sorted(p for p in set(built) | set(stamp.get("build", {}))
                                   if built.get(p) != stamp.get("build", {}).get(p))
        for label, items in (("CHANGED", changed), ("ADDED", added), ("REMOVED", removed), ("BUILD_CHANGED", build_changed)):
            for p in items:
                print(f"{label} {p}")
        stale = changed or added or removed or build_changed
        if stale:
            print("STALE: the build does not match the current source contents: rebuild before the test")
        print(f"FRESH: {'STALE' if stale else 'PASS'} changed={len(changed)} added={len(added)} removed={len(removed)} "
              f"build_changed={len(build_changed)}")
        return 1 if stale else 0
    except (OSError, ValueError) as error:
        print(f"HASH_CHECK: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, UnicodeError, ValueError) as error:  # one line, never a Traceback
        print(f"HASH_CHECK: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        sys.exit(2)
