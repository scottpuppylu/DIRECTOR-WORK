"""Prove a run read its switches, with the right type, before the first frame (DIRECTOR-WORK 2.3.0, F6).

A test run was judged with a switch "on" that the program never read: the launcher passed `1.0` where the code parsed an
integer, the parse failed quietly and the default (off) ran. The rule (templates/CPU_REPRO.md, "Switches"): an integer
switch is parsed as an integer (a value that is not one stops the program); on its first frame the program logs one line
per switch, `flag <NAME> read = <VALUE>`; a run whose log lacks the line is stopped and not judged.

  flag_check.py --flags FLAGS.json --log RUN.log [--before REGEX] [--first-lines N]

  FLAGS.json  {"NAME": value, ...}: the values the test request says the run uses (an int, a bool, a number or text)
  --before    the line must come before the first log line matching REGEX (e.g. `frame 2\\b`, the second frame)
  --first-lines  or within the first N lines of the log (default 400)

Per switch: `OK <NAME> read = <VALUE>`, `WRONG <NAME>: read <x>, the request says <y>`, `TYPE <NAME>: read <x>, not an
integer` (an int switch logged as 1.0 / true / text), `LATE <NAME>`: logged after the first frame, or `MISSING <NAME>`:
no read line - STOP, the run is not judged. Last line `FLAGS: PASS|STOP flags=n ok=n wrong=n missing=n`. Exit 0 PASS,
1 STOP, 2 cannot read the input. Only reads.
"""
import argparse
import json
import pathlib
import re
import sys

READ = re.compile(r"\bflag\s+(?P<name>[A-Za-z0-9_.\-]+)\s+read\s*=\s*(?P<value>\S+)")


def typed_ok(want, got):
    """(same value, right type) for a logged value against the requested one."""
    if isinstance(want, bool):
        return got.lower() in ("true", "1", "on", "yes") if want else got.lower() in ("false", "0", "off", "no"), True
    if isinstance(want, int):
        if not re.fullmatch(r"[+-]?\d+", got):
            return False, False
        return int(got) == want, True
    if isinstance(want, float):
        try:
            return float(got) == want, True
        except ValueError:
            return False, False
    return got == str(want), True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--flags", required=True, help="JSON {NAME: value} the run is meant to use")
    ap.add_argument("--log", required=True, help="the run's log")
    ap.add_argument("--before", help="regex of the line that ends the first frame")
    ap.add_argument("--first-lines", type=int, default=400)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        flags = json.loads(pathlib.Path(a.flags).read_text(encoding="utf-8-sig"))
        if not isinstance(flags, dict) or not flags:
            raise ValueError("--flags must be a JSON object {NAME: value} with at least one switch")
        lines = pathlib.Path(a.log).read_text(encoding="utf-8-sig", errors="replace").splitlines()
        end = re.compile(a.before) if a.before else None
    except (OSError, ValueError, re.error) as error:
        print(f"FLAGS: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        return 2
    limit = a.first_lines
    if end is not None:
        limit = next((i for i, line in enumerate(lines) if end.search(line)), len(lines))
    seen = {}
    for i, line in enumerate(lines):
        m = READ.search(line)
        if m and m.group("name") not in seen:
            seen[m.group("name")] = (i, m.group("value").strip().rstrip(",;"))
    n = {"ok": 0, "wrong": 0, "missing": 0}
    for name, want in flags.items():
        if name not in seen:
            n["missing"] += 1
            print(f"MISSING {name}: no `flag {name} read = ...` line: STOP, the run may not have read it; do not judge it")
            continue
        index, got = seen[name]
        same, right_type = typed_ok(want, got)
        if index >= limit:
            n["wrong"] += 1
            print(f"LATE {name}: read on log line {index + 1}, after the first frame: the first frame ran without it")
        elif not right_type:
            n["wrong"] += 1
            print(f"TYPE {name}: read {got!r}, not an {type(want).__name__} (parse it as one; a bad value must stop the run)")
        elif not same:
            n["wrong"] += 1
            print(f"WRONG {name}: read {got}, the request says {json.dumps(want)}")
        else:
            n["ok"] += 1
            print(f"OK {name} read = {got}")
    stop = n["wrong"] or n["missing"]
    if stop:
        print("STOP: the run did not provably use the requested switches; fix and run again before judging")
    print(f"FLAGS: {'STOP' if stop else 'PASS'} flags={len(flags)} ok={n['ok']} wrong={n['wrong']} missing={n['missing']}")
    return 1 if stop else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, UnicodeError, ValueError) as error:  # one line, never a Traceback
        print(f"FLAGS: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        sys.exit(2)
