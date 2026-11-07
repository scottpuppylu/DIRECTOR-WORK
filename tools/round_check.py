"""Check the fix-round limit (lesson L-032): fix rounds go in sets of 3; before the 4th round of a defect (and after
every later set of 3) a root-cause study must be written, and the next set starts only after it.

RESUME_STATE holds one line per defect that has been fixed more than once:

  FIX_ROUNDS:
  - hair: round=4 set=2 study=ROOT_CAUSE_STUDY.md
  - material: round=2 set=1 study=NONE

  round   the fix round now being worked, counted from 1 over all sets (the study itself is not a round)
  set     (round - 1) // 3 + 1: rounds 1-3 are set 1, rounds 4-6 set 2, ...
  study   the study file (relative to the RESUME_STATE's folder), or NONE while still in set 1

From round 4 on, the study file must exist and hold a `## SET n` section (or `## <defect> SET n`) for every finished
set n, each with filled `WHERE:` (where the problem really is), `ALTERNATIVES:` (ready assets, other methods, a design
change) and `DECISION:` lines. A defect without a FIX_ROUNDS line is not checked; `FIX_ROUNDS: NONE` is fine.

  round_check.py [--dir DIR]          every RESUME_STATE*.md in DIR (default: the current folder)
  round_check.py --resume FILE ...    these files

Prints OK / FAIL per defect and a last line `ROUNDS: PASS|FAIL files=n defects=n failed=n`; exit 1 on any FAIL or
when no RESUME_STATE is found. Only reads. A project's guard_check runs it for each worktree (docs/06b).
"""
import argparse
import pathlib
import re
import sys

SET_SIZE = 3
LINE = re.compile(r"^\s*-\s*(?P<defect>[^:]+?)\s*:\s*(?P<rest>.*)$")
FIELD = re.compile(r"\b(round|set|study)\s*=\s*(\S+)")
PLACEHOLDER = re.compile(r"<[^<>\n]+>")


def fix_rounds(text):
    """(defect, fields, raw line) for each line of the FIX_ROUNDS list; None when the field is absent."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^\s*FIX_ROUNDS\s*:\s*(.*)$", line)
        if not m:
            continue
        rows = []
        for item in lines[i + 1:]:
            if not item.strip():
                continue
            row = LINE.match(item)
            if not row:
                break
            rows.append((row.group("defect"), dict(FIELD.findall(row.group("rest"))), item.strip()))
        return rows if rows or m.group(1).strip().upper() != "NONE" else []
    return None


def study_sections(text, defect):
    """{set number: section text} of the study, for sections naming this defect or no defect."""
    out, current = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(?:(.+?)\s+)?SET\s+(\d+)\b", line, re.I)
        if m:
            name = (m.group(1) or "").strip()
            current = int(m.group(2)) if not name or name.lower() == defect.lower() else None
            if current is not None:
                out[current] = ""
            continue
        if line.startswith("## "):
            current = None
        elif current is not None:
            out[current] += line + "\n"
    return out


def filled_line(section, key):
    m = re.search(rf"^[ \t]*{key}[ \t]*:[ \t]*(.*)$", section, re.M)  # \s would run on into the next line
    value = m.group(1).strip() if m else ""
    return bool(value) and value not in ("...", "…", "NONE") and not PLACEHOLDER.search(value)


def check_defect(defect, fields, folder):
    problems = []
    try:
        rnd, st = int(fields.get("round", "")), int(fields.get("set", ""))
    except ValueError:
        return ["round= and set= must be numbers"]
    if rnd < 1 or st < 1:
        return ["round and set start at 1"]
    want = (rnd - 1) // SET_SIZE + 1
    if st != want:
        problems.append(f"round {rnd} belongs to set {want}, the line says set {st}")
    done = want - 1  # finished sets, each needing a study section
    study = fields.get("study", "")
    if done == 0:
        return problems
    if not study or study.upper() == "NONE":
        return problems + [f"round {rnd} needs a root-cause study after set {done} (ROOT_CAUSE_STUDY.md); none is named"]
    path = (folder / study) if not pathlib.Path(study).is_absolute() else pathlib.Path(study)
    if not path.is_file():
        return problems + [f"study file not found: {study}"]
    sections = study_sections(path.read_text(encoding="utf-8-sig", errors="replace"), defect)
    for n in range(1, done + 1):
        if n not in sections:
            problems.append(f"{study}: no `## SET {n}` section for the study after set {n}")
            continue
        empty = [k for k in ("WHERE", "ALTERNATIVES", "DECISION") if not filled_line(sections[n], k)]
        if empty:
            problems.append(f"{study} SET {n}: {', '.join(empty)} empty or missing")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=".", help="folder whose RESUME_STATE*.md files are checked (default: current)")
    ap.add_argument("--resume", nargs="+", default=[], metavar="FILE")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    files = [pathlib.Path(p) for p in a.resume] or sorted(pathlib.Path(a.dir).glob("RESUME_STATE*.md"))
    defects = failed = 0
    if not files:
        print(f"ROUNDS: FAIL no RESUME_STATE*.md in {a.dir}")
        return 1
    for f in files:
        if not f.is_file():
            failed += 1
            print(f"FAIL {f}: file not found")
            continue
        rows = fix_rounds(f.read_text(encoding="utf-8-sig", errors="replace"))
        if rows is None:
            print(f"OK   {f}: no FIX_ROUNDS field")
            continue
        for defect, fields, raw in rows:
            defects += 1
            problems = check_defect(defect, fields, f.parent)
            failed += bool(problems)
            print(f"{'FAIL' if problems else 'OK  '} {f}: {raw.lstrip('- ')}")
            for p in problems:
                print(f"  - {p}")
    print(f"ROUNDS: {'FAIL' if failed else 'PASS'} files={len(files)} defects={defects} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
