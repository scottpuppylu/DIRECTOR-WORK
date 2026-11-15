"""One call, one work line: board entry, git state, newest result, log tail (DIRECTOR-WORK 2.3.0, N7).

To see where one work line stands, a lead read the board, ran git status in the line's worktree, opened the newest
RESULT file and tailed the run log: four or five tool calls per line, every sweep. This prints the four in one call,
short enough to read whole.

  line_brief.py LINE --config STATUS.json        the line's paths from the "lines" section of a status_gen config
  line_brief.py LINE [--board FILE] [--repo DIR] [--results DIR] [--glob RESULT*.md] [--log FILE]

Config ("lines" in the status_gen.py JSON config; status_gen accepts and ignores it; paths relative to the config's
folder):

  "lines": {"line-a": {"board": "board/STATUS.md", "match": "line-a", "repo": "../line-a-worktree",
                       "results": "../line-a-worktree/out", "glob": "RESULT*.md", "log": "../line-a-worktree/run.log"}}

Sections, each one header and a few lines (a part that is not configured says `not configured`, one that is
missing says `MISSING`):
  BOARD    the board lines that mention the line (regex `match`, default the line name; at most --board-lines)
  GIT      `git status -sb` (first --git-lines lines) and the last commit `<hash> <date> <subject>`
  RESULT   the newest file matching glob in results (by modification time): its name, age and first --result-lines
  LOG      the last --log-lines lines of the log, with its age
Last line `LINE_BRIEF: <line> board=n git=ok|MISSING result=<name>|none log=ok|MISSING`. Exit 0; 1 when a configured
part is missing; 2 when the config cannot be read. Only reads (git status and git log are read-only).
"""
import argparse
import datetime
import json
import pathlib
import re
import subprocess
import sys
import time

FIELDS = ("board", "match", "repo", "results", "glob", "log")


def age(path):
    minutes = (time.time() - path.stat().st_mtime) / 60
    return f"{minutes:.0f} min ago" if minutes < 120 else f"{minutes / 60:.1f} h ago"


def tail(path, count):
    with open(path, "rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - 65536))
        data = fh.read().decode("utf-8", errors="replace")
    return data.splitlines()[-count:]


def line_settings(a):
    conf = {k: getattr(a, k) for k in FIELDS}
    if a.config:
        data = json.loads(pathlib.Path(a.config).read_text(encoding="utf-8-sig"))
        lines = data.get("lines") if isinstance(data, dict) else None
        if not isinstance(lines, dict) or a.line not in lines or not isinstance(lines[a.line], dict):
            names = ", ".join(sorted(lines)) if isinstance(lines, dict) else "none"
            raise ValueError(f"no lines.{a.line} in {a.config} (lines there: {names})")
        unknown = sorted(set(lines[a.line]) - set(FIELDS))
        if unknown:
            raise ValueError(f"lines.{a.line}: unknown key(s) {', '.join(unknown)}")
        base = pathlib.Path(a.config).resolve().parent
        for key, value in lines[a.line].items():
            if conf[key] is None:
                conf[key] = value if key in ("match", "glob") else str((base / value).resolve())
    return conf


def git(repo, *args):
    done = subprocess.run(["git", "-C", repo, *args], capture_output=True, encoding="utf-8", errors="replace")
    return done.returncode, done.stdout.strip() or done.stderr.strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("line", help="the work line's name")
    ap.add_argument("--config", help="a status_gen JSON config with a \"lines\" section")
    ap.add_argument("--board", help="the board / status file")
    ap.add_argument("--match", help="regex for the line's board lines (default: the line name)")
    ap.add_argument("--repo", help="the line's worktree")
    ap.add_argument("--results", help="folder of the line's RESULT / report files")
    ap.add_argument("--glob", help="result file pattern (default RESULT*.md)")
    ap.add_argument("--log", help="the line's run log")
    ap.add_argument("--board-lines", type=int, default=5)
    ap.add_argument("--git-lines", type=int, default=6)
    ap.add_argument("--result-lines", type=int, default=12)
    ap.add_argument("--log-lines", type=int, default=15)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        conf = line_settings(a)
        pattern = re.compile(conf["match"] or re.escape(a.line), re.I)
    except (OSError, ValueError, re.error) as error:
        print(f"LINE_BRIEF: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        return 2
    missing, summary = 0, {}
    print(f"# {a.line}  ({datetime.datetime.now().astimezone():%Y-%m-%d %H:%M})")

    print("BOARD")
    board = pathlib.Path(conf["board"]) if conf["board"] else None
    if board is None:
        print("  not configured")
        summary["board"] = "-"
    elif not board.is_file():
        print(f"  MISSING {board.as_posix()}")
        missing += 1
        summary["board"] = "MISSING"
    else:
        hits = [l.rstrip() for l in board.read_text(encoding="utf-8-sig", errors="replace").splitlines() if pattern.search(l)]
        for l in hits[:a.board_lines]:
            print(f"  {l[:200]}")
        if len(hits) > a.board_lines:
            print(f"  ~ {len(hits) - a.board_lines} more line(s)")
        if not hits:
            print(f"  ~ no line matches {pattern.pattern!r}")
        summary["board"] = str(len(hits))

    print("GIT")
    if not conf["repo"]:
        print("  not configured")
        summary["git"] = "-"
    else:
        code, status = git(conf["repo"], "status", "-sb")
        if code:
            print(f"  MISSING {conf['repo']}: {status.splitlines()[0][:200] if status else 'git failed'}")
            missing += 1
            summary["git"] = "MISSING"
        else:
            rows = status.splitlines()
            for l in rows[:a.git_lines]:
                print(f"  {l}")
            if len(rows) > a.git_lines:
                print(f"  ~ {len(rows) - a.git_lines} more changed path(s)")
            code, last = git(conf["repo"], "log", "-1", "--format=%h %ci %s")
            print(f"  last commit: {last if not code else 'none'}")
            summary["git"] = "ok"

    print("RESULT")
    if not conf["results"]:
        print("  not configured")
        summary["result"] = "-"
    else:
        folder = pathlib.Path(conf["results"])
        found = sorted((p for p in folder.glob(conf["glob"] or "RESULT*.md") if p.is_file()),
                       key=lambda p: p.stat().st_mtime) if folder.is_dir() else []
        if not folder.is_dir():
            print(f"  MISSING {folder.as_posix()}")
            missing += 1
            summary["result"] = "MISSING"
        elif not found:
            print(f"  ~ no {conf['glob'] or 'RESULT*.md'} in {folder.as_posix()}")
            summary["result"] = "none"
        else:
            newest = found[-1]
            print(f"  {newest.name} ({age(newest)}; {len(found)} file(s))")
            for l in newest.read_text(encoding="utf-8-sig", errors="replace").splitlines()[:a.result_lines]:
                print(f"  | {l[:200]}")
            summary["result"] = newest.name

    print("LOG")
    if not conf["log"]:
        print("  not configured")
        summary["log"] = "-"
    else:
        log = pathlib.Path(conf["log"])
        if not log.is_file():
            print(f"  MISSING {log.as_posix()}")
            missing += 1
            summary["log"] = "MISSING"
        else:
            print(f"  {log.name} ({age(log)})")
            for l in tail(log, a.log_lines):
                print(f"  | {l[:200]}")
            summary["log"] = "ok"
    print(f"LINE_BRIEF: {a.line} board={summary['board']} git={summary['git']} result={summary['result']} "
          f"log={summary['log']}")
    return 1 if missing else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, UnicodeError, ValueError) as error:  # one line, never a Traceback
        print(f"LINE_BRIEF: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        sys.exit(2)
