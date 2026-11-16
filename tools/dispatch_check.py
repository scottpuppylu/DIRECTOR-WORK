"""Check the Director's dispatch records before and after dispatching (2.5.0). Only reads; warns by default.

Effort per dispatch (N1, lesson: work was dispatched without setting effort by difficulty). Every DISPATCH line in
DIRECTOR_LOG.md names the difficulty class and the effort it set, in its `| basis` column:

  DISPATCH WO-012 rev=1 sha=<64 hex> | class=dev effort=high model=opus

The default table (docs/05; levels as in the official Claude Code effort docs: low medium high xhigh max):

  routine                                  medium high
  dev, ui                                  high
  root_cause, fix_after_fail, realism, core_engine   xhigh
  repeated_failure                         xhigh max    (max only after repeated failure, then back down)

A record without class= or effort=, an unknown class or level, or an effort outside the table prints
`~ WARN EFFORT <WO-ID> line <n>: ...`. `--table FILE` replaces the table (JSON {"class": ["level", ...]}).

  dispatch_check.py --log DIRECTOR_LOG.md [--table FILE] [--strict]

Last line `DISPATCH_CHECK: OK|WARN records=n warnings=n`.

Duplicate dispatch (N4, lesson: the same work was dispatched twice). Before dispatching, compare the new task's
title / scope words with the open NEXT_STEP lines of the work lines' RESUME_STATE files and the recent commit subjects
of their repositories (token Jaccard: shared words / all words; CJK text counts in character pairs):

  dispatch_check.py --dup "<title and scope>" [--resume GLOB ...] [--repo DIR ...] [--since "14 days ago"]
                    [--threshold 0.5]

Prints `~ WARN DUP <score> <source>: <text>` for each line at or above the threshold, best first, and a last line
`DUP_CHECK: OK|WARN compared=n matches=n threshold=x`. Look before dispatching; it may be a false alarm.

Exit 0 (warnings included) unless --strict, then 1 on a warning; 2 on an input error (missing file, bad table, no
--log and no --dup, a --repo that git cannot read).
"""
import argparse
import glob
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

LEVELS = ("low", "medium", "high", "xhigh", "max")
TABLE = {
    "routine": ["medium", "high"],
    "dev": ["high"],
    "ui": ["high"],
    "root_cause": ["xhigh"],
    "fix_after_fail": ["xhigh"],
    "realism": ["xhigh"],
    "core_engine": ["xhigh"],
    "repeated_failure": ["xhigh", "max"],
}
# a DISPATCH event line as gate_check reads it: optional `<date> |` column, the event, optional `| basis` columns
DISPATCH = re.compile(r"^(?:[^|`]*\|[ \t]*)?DISPATCH[ \t]+([^\s|`]+?)(?:\.md)?[ \t]+rev=\d+[ \t]+sha=[0-9a-fA-F]{64}"
                      r"[ \t]*(\|[^`]*)?$")
FIELD = re.compile(r"\b(class|effort|model)\s*=\s*([^\s|]+)")


def load_table(path):
    if not path:
        return TABLE
    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict) or not raw or not all(
            isinstance(k, str) and isinstance(v, list) and v and all(x in LEVELS for x in v) for k, v in raw.items()):
        raise ValueError('want {"class": ["level", ...]} with levels from ' + " ".join(LEVELS))
    return raw


def dispatch_records(text):
    """(line number, order id, {class, effort, model}) for every DISPATCH event line."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        m = DISPATCH.match(line.rstrip())
        if m:
            out.append((n, m.group(1), {k.lower(): v.lower() for k, v in FIELD.findall(m.group(2) or "")}))
    return out


def effort_warnings(records, table):
    warns = []
    for n, wo, fields in records:
        cls, effort = fields.get("class"), fields.get("effort")
        where = f"{wo} line {n}"
        if not cls or not effort:
            missing = " and ".join(k + "=" for k in ("class", "effort") if not fields.get(k))
            warns.append(f"~ WARN EFFORT {where}: no {missing} (write `| class=<class> effort=<level>` on the DISPATCH line)")
        elif cls not in table:
            warns.append(f"~ WARN EFFORT {where}: unknown class={cls} (known: {' '.join(table)})")
        elif effort not in LEVELS:
            warns.append(f"~ WARN EFFORT {where}: unknown effort={effort} (levels: {' '.join(LEVELS)})")
        elif effort not in table[cls]:
            warns.append(f"~ WARN EFFORT {where}: class={cls} wants effort {'/'.join(table[cls])}, got {effort}")
    return warns


WORD = re.compile(r"[0-9a-z_]+|[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]+")
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")
STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "be", "by", "at", "it", "this"}


def tokens(text):
    """Lower-case words (2+ characters, a few stop words left out); a run of CJK characters gives its character pairs
    (a single character stays itself), since CJK has no spaces between words."""
    out = set()
    for w in WORD.findall(text.lower()):
        if CJK.match(w):
            out.update(w[i:i + 2] for i in range(len(w) - 1)) if len(w) > 1 else out.add(w)
        elif len(w) >= 2 and w not in STOP:
            out.add(w)
    return out


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def next_steps(patterns):
    """(source, text) of every NEXT_STEP line in the files the globs match."""
    out = []
    for f in sorted({f for g in patterns for f in glob.glob(g, recursive=True) if os.path.isfile(f)}):
        for n, line in enumerate(pathlib.Path(f).read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
            m = re.match(r"^\s*\**NEXT_STEP\**\s*[:：]\s*(.+)$", line)
            if m and m.group(1).strip().upper() not in ("NONE", "-"):
                out.append((f"{f}:{n}", m.group(1).strip()))
    return out


def commit_subjects(repos, since):
    git = shutil.which("git")
    if repos and not git:
        raise ValueError("--repo needs git on PATH")
    out = []
    for repo in repos:
        done = subprocess.run([git, "-C", repo, "log", "--all", f"--since={since}", "--format=%h %s"],
                              capture_output=True, encoding="utf-8", errors="replace")
        if done.returncode != 0:
            raise ValueError(f"--repo {repo}: {done.stderr.strip()[:200]}")
        for line in done.stdout.splitlines():
            sha, _, subject = line.partition(" ")
            out.append((f"{repo}@{sha}", subject))
    return out


def dup_warnings(task, candidates, threshold):
    mine = tokens(task)
    scored = sorted(((jaccard(mine, tokens(text)), source, text) for source, text in candidates), reverse=True)
    return [f"~ WARN DUP {score:.2f} {source}: {text[:120]}" for score, source, text in scored if score >= threshold]


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Check dispatch records: effort per difficulty class (warn only).",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--log", metavar="FILE", help="DIRECTOR_LOG.md with the DISPATCH lines")
    ap.add_argument("--table", metavar="FILE", help='JSON {"class": ["level", ...]} replacing the default table')
    ap.add_argument("--dup", metavar="TEXT", help="the new task's title and scope: warn on similar open work")
    ap.add_argument("--resume", action="append", default=[], metavar="GLOB", help="RESUME_STATE files (repeatable)")
    ap.add_argument("--repo", action="append", default=[], metavar="DIR", help="repository whose recent commits count")
    ap.add_argument("--since", default="14 days ago", help="commit window for --repo (git log --since; default 14 days ago)")
    ap.add_argument("--threshold", type=float, default=0.5, help="Jaccard score that warns (default 0.5)")
    ap.add_argument("--strict", action="store_true", help="exit 1 when there is a warning")
    a = ap.parse_args(argv)
    if not a.log and a.dup is None:
        print("FAIL input: give --log (effort check) and/or --dup (duplicate check)")
        return 2
    warned = False
    if a.log:
        try:
            table = load_table(a.table)
            text = pathlib.Path(a.log).read_text(encoding="utf-8-sig")
        except (OSError, ValueError) as error:
            print(f"FAIL input: {type(error).__name__}: {error}")
            return 2
        records = dispatch_records(text)
        warns = effort_warnings(records, table)
        for w in warns:
            print(w)
        print(f"DISPATCH_CHECK: {'WARN' if warns else 'OK'} records={len(records)} warnings={len(warns)}")
        warned = bool(warns)
    if a.dup is not None:
        try:
            pool = next_steps(a.resume) + commit_subjects(a.repo, a.since)
        except (OSError, ValueError) as error:
            print(f"FAIL input: {error}")
            return 2
        if not a.resume and not a.repo:
            print("~ WARN nothing compared: give --resume and/or --repo")
        dups = dup_warnings(a.dup, pool, a.threshold)
        for w in dups:
            print(w)
        print(f"DUP_CHECK: {'WARN' if dups else 'OK'} compared={len(pool)} matches={len(dups)} threshold={a.threshold:g}")
        warned = warned or bool(dups)
    return 1 if warned and a.strict else 0


if __name__ == "__main__":
    sys.exit(main())
