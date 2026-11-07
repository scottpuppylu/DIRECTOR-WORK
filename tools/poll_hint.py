"""PostToolUse hook: when one session reads the same log file again and again while background work runs, remind it
to wait for the completion notice instead (lesson L-041). It only adds a hint; it never blocks and always exits 0.

A read is a Bash / PowerShell command that runs `tail` or `Get-Content` (`gc`, `cat` and `type` count too, and
`head` / `less`, when the file ends in .log, .out, .err or .txt). The third read of one file by one session within
--window seconds (default 600) prints, as hook output for Claude Code:

  {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "等完成通知 ..."}}

and the count for that file starts again. Each session's reads are kept in a small JSON file under --state-dir
(default: <temp>/dw-poll-hint); nothing else is written. Settings, per project (.claude/settings.local.json):

  "PostToolUse": [{"matcher": "Bash|PowerShell", "hooks": [{"type": "command",
      "command": "\\"<PYTHON>\\" -I -X utf8 \\"<DW>/tools/poll_hint.py\\""}]}]

Report (for the Director's weekly report; only reads):

  poll_hint.py report --log AUDIT.jsonl [--log ...] [--since 2026-11-01 | --days 7] [--sessions MAP.json] [--json]

counts, per session, the Bash / PowerShell lines of the action logs (audit_log.py) that read a log by the rules above:
reads, distinct files, the most-read file, and how many times the hint would have come (--window / --times). --log
takes globs. --sessions (a hook_guard sessions file) adds each session's name. Last line:
  POLL_REPORT: sessions=n log_reads=n hints=n lines=n logs=n since=...
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import pathlib
import re
import shlex
import sys
import tempfile
import time

READERS = re.compile(r"(?:^|[\s;|&(])(tail|get-content|gc|cat|type|head|less|more)(?=\s)", re.I)
ALWAYS = ("tail", "get-content", "gc")  # these count on any file; the others only on log-like files
LOG_LIKE = re.compile(r"\.(log|out|err|txt)$", re.I)
SEPARATORS = re.compile(r"\s*(?:\|\||&&|[;|&])\s*")


def read_targets(command):
    """The files a command reads with a reader verb, lower-cased with forward slashes."""
    targets = set()
    for part in SEPARATORS.split(command or ""):
        m = READERS.search(" " + part)
        if not m:
            continue
        verb = m.group(1).lower()
        rest = (" " + part)[m.end():]
        try:
            words = shlex.split(rest, posix=False)  # posix=True would eat the backslashes of Windows paths
        except ValueError:
            words = rest.split()
        for w in words:
            w = w.strip("'\"")
            if not w or w.startswith("-") or w.isdigit() or w in ("<", ">", "2>&1"):
                continue
            if verb in ALWAYS or LOG_LIKE.search(w):
                targets.add(w.replace("\\", "/").lower())
    return targets


def audit_command(entry):
    """The command of a Bash / PowerShell action-log line (its input is the masked tool input as JSON, maybe cut)."""
    raw = entry.get("input") or ""
    try:
        value = json.loads(raw)
        return str(value.get("command", "")) if isinstance(value, dict) else ""
    except ValueError:
        found = re.match(r'\{"command":\s*"(.*)', raw, re.S)
        return found.group(1).rstrip("\u2026") if found else ""


def report(argv):
    ap = argparse.ArgumentParser(prog="poll_hint.py report", description="log reads per session from action logs")
    ap.add_argument("--log", action="append", required=True, help="action log or glob (repeatable)")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--since", help="ISO date or time (default: all lines)")
    group.add_argument("--days", type=float, help="the last N days")
    ap.add_argument("--sessions", help="hook_guard sessions file, for names")
    ap.add_argument("--window", type=int, default=600)
    ap.add_argument("--times", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    since = None
    try:
        if a.days is not None:
            since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=a.days)
        elif a.since:
            since = datetime.datetime.fromisoformat(a.since.replace("Z", "+00:00"))
            since = since if since.tzinfo else since.astimezone()
    except ValueError:
        print(f"poll_hint report: --since {a.since} is not an ISO date or time", file=sys.stderr)
        return 2
    names = {}
    if a.sessions:
        try:
            data = json.loads(pathlib.Path(a.sessions).read_text(encoding="utf-8-sig"))
            names = {sid: v.get("name") for sid, v in (data.get("sessions") or {}).items() if isinstance(v, dict) and v.get("name")}
        except (OSError, ValueError, AttributeError) as error:
            print(f"poll_hint report: cannot read {a.sessions}: {error}", file=sys.stderr)
            return 2
    paths = []
    for item in a.log:
        found = sorted(glob.glob(item)) if any(c in item for c in "*?[") else [item]
        if not found or not all(os.path.isfile(f) for f in found):
            print(f"poll_hint report: no log at {item}", file=sys.stderr)
            return 2
        paths += [f for f in found if f not in paths]
    reads, lines = [], 0
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for text in fh:
                try:
                    entry = json.loads(text)
                    when = datetime.datetime.fromisoformat(str(entry.get("ts")).replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue
                if since is not None and when < since:
                    continue
                lines += 1
                if entry.get("kind") not in ("result", "failure") or entry.get("tool") not in ("Bash", "PowerShell"):
                    continue
                targets = read_targets(audit_command(entry))
                if targets:
                    reads.append((when.timestamp(), str(entry.get("session_id") or "unknown"), sorted(targets)))
    reads.sort()
    per = {}
    for t, session, targets in reads:
        row = per.setdefault(session, {"reads": 0, "files": {}, "hints": 0, "recent": {}})
        row["reads"] += 1
        for target in targets:
            row["files"][target] = row["files"].get(target, 0) + 1
            times = [x for x in row["recent"].get(target, []) if t - x < a.window] + [t]
            if len(times) >= a.times:
                row["hints"] += 1
                times = []
            row["recent"][target] = times
    rows = []
    for session, row in sorted(per.items(), key=lambda kv: (-kv[1]["reads"], kv[0])):
        top = max(row["files"].items(), key=lambda kv: (kv[1], kv[0]))
        rows.append({"session": session, "name": names.get(session), "log_reads": row["reads"],
                     "files": len(row["files"]), "hints": row["hints"], "top_file": top[0], "top_reads": top[1]})
    total = {"sessions": len(rows), "log_reads": len(reads), "hints": sum(r["hints"] for r in rows), "lines": lines,
             "logs": len(paths), "since": since.isoformat(timespec="seconds") if since else "all"}
    if a.json:
        print(json.dumps({"sessions": rows, "total": total}, ensure_ascii=False, indent=1))
        return 0
    print(f"{'SESSION':38} {'NAME':12} {'READS':>6} {'FILES':>6} {'HINTS':>6}  MOST-READ FILE")
    for r in rows:
        print(f"{r['session'][:38]:38} {(r['name'] or '-')[:12]:12} {r['log_reads']:>6} {r['files']:>6} {r['hints']:>6}  "
              f"{r['top_file']} x{r['top_reads']}")
    print("POLL_REPORT: " + " ".join(f"{k}={v}" for k, v in total.items()))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["report"]:
        return report(argv[1:])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state-dir", default=os.path.join(tempfile.gettempdir(), "dw-poll-hint"))
    ap.add_argument("--window", type=int, default=600, help="seconds (default 600)")
    ap.add_argument("--times", type=int, default=3, help="reads of one file that bring the hint (default 3)")
    a = ap.parse_args(argv)
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace") or "{}")
        if event.get("tool_name") not in ("Bash", "PowerShell"):
            return 0
        targets = read_targets(str((event.get("tool_input") or {}).get("command", "")))
        if not targets:
            return 0
        session = str(event.get("session_id") or "unknown")
        state_dir = pathlib.Path(a.state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / (hashlib.sha256(session.encode()).hexdigest()[:16] + ".json")
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        now = time.time()
        state = {k: [t for t in v if now - t < a.window] for k, v in state.items() if isinstance(v, list)}
        hit = []
        for target in sorted(targets):
            times = state.get(target, []) + [now]
            if len(times) >= a.times:
                hit.append(target)
                times = []
            state[target] = times
        state = {k: v for k, v in state.items() if v}
        with open(state_file, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(state, fh)
        if hit:
            minutes = a.window // 60
            text = (f"等完成通知：{minutes} 分鐘內第 {a.times} 次讀 {', '.join(hit)}。背景工作完成時會通知你；"
                    "先做別的事或結束這一輪，不要再輪詢 log（L-041）。")
            sys.stdout.reconfigure(encoding="utf-8")
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}},
                             ensure_ascii=False))
    except Exception:  # a hint must never break the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
