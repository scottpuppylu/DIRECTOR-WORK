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
"""
import argparse
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


def main(argv=None):
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
