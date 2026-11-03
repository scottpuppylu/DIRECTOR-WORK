"""PreToolUse hook: block the shell commands that docs/08 reserves for the PO or forbids outright.

Claude Code runs it before every Bash / PowerShell tool call and passes the call as JSON on stdin. A blocked command
gets exit 2 and a one-line reason on stderr, which Claude Code shows to the model instead of running the command.
Everything else exits 0 silently, so it costs no context.

Blocked: git push (any form, also `git -C <dir> push`), git reset --hard, git clean (except -n / --dry-run),
bare git stash / stash pop / drop / clear (`git stash push -m <mark>`, list, show, apply stay allowed),
deleting a worktree, branch or tag, and ending processes by name (taskkill /IM, pkill, killall, Stop-Process -Name).
This is a seat belt, not a security boundary: a command hidden in a script file or built at run time is not seen.
Install with setup_project_settings.py --hooks. A push the PO approved is run by the PO, or after removing the hook.
"""
import json
import re
import shlex
import sys

GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
WRAPPERS = {"sudo", "env", "command", "exec", "nohup", "time", "xargs", "cmd", "cmd.exe", "/c", "/k"}


def words(segment):
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def segments(command):
    """Simple commands of a shell line, including the ones inside quoted strings (bash -c "...")."""
    for part in re.split(r"&&|\|\||[;|&\n()`{}]|\$\(", command):
        part = part.strip()
        if not part:
            continue
        yield part
        for word in words(part):
            if " " in word and word != part:
                yield from segments(word)


def git_reason(args):
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in GIT_OPTS_WITH_VALUE else 1
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1:]
    if sub == "push":
        return "git push needs the PO's approval (docs/08)"
    if sub == "reset" and "--hard" in rest:
        return "git reset --hard is forbidden (docs/08); use a WIP commit or git restore on named files"
    if sub == "clean" and not {"-n", "--dry-run"} & set(rest):
        return "git clean is forbidden (docs/08)"
    if sub == "stash":
        action = rest[0] if rest else ""
        if action in ("", "pop", "drop", "clear", "save") or action.startswith("-"):
            return "bare git stash is forbidden (docs/08); use git stash push -u -m <mark> and git stash apply <sha>"
        if action == "push" and not any(a in ("-m", "--message") or a.startswith("--message=") for a in rest):
            return "git stash push needs -m <unique mark> (docs/08)"
    if sub == "worktree" and rest[:1] in (["remove"], ["prune"]):
        return "deleting a worktree needs the PO's approval (docs/08)"
    if sub == "branch" and {"-d", "-D", "--delete"} & set(rest):
        return "deleting a branch needs the PO's approval (docs/08)"
    if sub == "tag" and {"-d", "--delete"} & set(rest):
        return "deleting a tag needs the PO's approval (docs/08)"
    return None


def reason(command):
    for segment in segments(command):
        args = words(segment)
        while args and (re.fullmatch(r"\w+=.*", args[0]) or args[0].lower() in WRAPPERS):
            args = args[1:]
        if not args:
            continue
        name, rest = re.split(r"[\\/]", args[0])[-1].lower(), args[1:]
        if name in ("git", "git.exe"):
            why = git_reason(rest)
            if why:
                return why
        elif (name in ("pkill", "killall")
              or name in ("taskkill", "taskkill.exe") and any(a.lower() == "/im" for a in rest)
              or name == "stop-process" and any(a.lower().startswith("-n") for a in rest)):
            return "ending processes by name is forbidden (docs/08); stop your own PID"
    return None


def main():
    try:
        call = json.load(sys.stdin)
    except ValueError:
        return 0
    command = (call.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
        return 0
    why = reason(command)
    if why:
        print(f"BLOCKED by hook_guard: {why}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
