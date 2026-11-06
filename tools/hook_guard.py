"""PreToolUse hook: block the shell commands that docs/08 reserves for the PO or forbids outright.

Claude Code runs it before every Bash / PowerShell tool call and passes the call as JSON on stdin. A blocked command
gets exit 2 and a one-line reason on stderr, which Claude Code shows to the model instead of running the command.
Everything else exits 0 silently, so it costs no context.

Blocked: git push (any form, also `git -C <dir> push` and C:\\...\\git.exe push), git reset --hard,
git clean (except -n / --dry-run), bare git stash / stash pop / drop / clear (`git stash push -m <mark>`, list, show,
apply stay allowed), deleting a worktree, branch or tag, and ending processes by name (taskkill /IM or /FI, pkill,
killall, Stop-Process without -Id, which also covers `Get-Process x | Stop-Process`).
The line is split only outside quotes, and a quoted string is checked as a command only when a wrapper runs it
(bash / sh -c, cmd /c, powershell -Command, eval, Invoke-Expression) or it holds $(...) / `...`.
Not covered: deleting files (rm -rf, Remove-Item -Recurse), a command hidden in a script file or built at run time.
This is a seat belt, not a security boundary. Install with setup_project_settings.py --hooks. A push the PO approved
is run by the PO, or after removing the hook. A cleaner session that removes worktrees does not install it.

With --protect DIRECTOR_DIR (setup_project_settings.py --protect-director) it also blocks the Write and Edit tools on
DIRECTOR_DIR/orders/** and DIRECTOR_DIR/DIRECTOR_LOG.md, so a worker cannot slip and edit its own work order or the
dispatch log. A relative file_path is taken from the hook's cwd; both paths are resolved (junctions, symlinks, `..`),
8.3 short names are expanded on Windows, and Windows compares without case. On Windows the extended-length prefix of a
drive or UNC path is dropped and an NTFS stream name (`DIRECTOR_LOG.md::$DATA`, `x.md:note`) counts as its file; any
other device path (GLOBALROOT, a dot-device path, a volume GUID) is blocked. A target, or a folder above it, that
already exists is also compared by file identity (volume serial and file id) with DIRECTOR_LOG.md and every file and folder under
orders/, so another name for the same object (UNC alias, hardlink of an existing file) is blocked too.
Without --protect, Write and Edit pass.
This guards against a slip, not against a worker that means to: it does not see a file written by Bash / PowerShell,
MultiEdit, NotebookEdit or an MCP tool, a DIRECTOR_LOG.md or orders/ folder that does not exist yet and is created
through another name (network drive, subst drive letter, UNC share), or a junction whose target does not exist yet.
Protect the folder with OS write permissions when that matters. The Director's own worktree keeps the hook without --protect (--director-worktree).
"""
import argparse
import json
import os
import pathlib
import re
import sys

GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
WRAPPERS = {"sudo", "env", "command", "exec", "nohup", "time", "xargs", "call"}
SEPARATORS = ("&&", "||", "$(", ";", "|", "&", "\n", "(", ")", "{", "}")
# per shell: quote characters, escape character. Bash keeps a backslash unless it escapes a quote, a space or a
# separator, so a Windows path such as C:\Git\bin\git.exe survives.
SHELLS = {"bash": ("'\"", "\\"), "powershell": ("'\"", "`"), "cmd": ('"', "^")}


def matching_end(command, i):
    """Index just past the `...` or (...) that starts at i."""
    if command[i] == "`":
        end = command.find("`", i + 1)
        return len(command) if end < 0 else end + 1
    depth = 0
    for j in range(i, len(command)):
        depth += {"(": 1, ")": -1}.get(command[j], 0)
        if depth == 0:
            return j + 1
    return len(command)


def parse(command, shell="bash"):
    """Simple commands of a shell line as word lists; also the commands inside $(...) / `...` in double quotes."""
    quotes, esc = SHELLS[shell]
    separators = SEPARATORS + ("`",) if shell == "bash" else SEPARATORS
    commands, words, word, quote, i = [], [], None, None, 0
    while i < len(command):
        c, nxt = command[i], command[i + 1:i + 2]
        if quote == "'":
            if c == "'":
                quote = None
            else:
                word += c
        elif quote:
            if c == '"':
                quote = None
            elif c == esc and nxt in ('"', esc, "`", "$"):
                word += nxt
                i += 1
            elif shell != "cmd" and (c == "`" and shell == "bash" or command.startswith("$(", i)):
                end = matching_end(command, i + (c == "$"))
                commands += parse(command[i + 2 - (c == "`"):end - 1], shell)
                i = end
                continue
            else:
                word += c
        elif c in quotes:
            quote, word = c, word or ""
        elif c == esc and nxt and (shell != "bash" or nxt in " \t'\"\\" or nxt in "".join(separators)):
            word = (word or "") + nxt
            i += 1
        elif c in " \t\r" or any(command.startswith(s, i) for s in separators):
            if word is not None:
                words.append(word)
                word = None
            if c not in " \t\r":
                if words:
                    commands.append(words)
                words = []
                i += next(len(s) for s in separators if command.startswith(s, i)) - 1
        else:
            word = (word or "") + c
        i += 1
    if word is not None:
        words.append(word)
    if words:
        commands.append(words)
    return commands


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
            # no <...> in messages: a report quoting one must still pass gate_check
            return "bare git stash is forbidden (docs/08); use git stash push -u -m MARK and git stash apply SHA"
        if action == "push" and not any(a in ("-m", "--message") or a.startswith("--message=") for a in rest):
            return "git stash push needs -m UNIQUE_MARK (docs/08)"
    if sub == "worktree" and rest[:1] in (["remove"], ["prune"]):
        return "deleting a worktree needs the PO's approval (docs/08)"
    if sub == "branch" and {"-d", "-D", "--delete"} & set(rest):
        return "deleting a branch needs the PO's approval (docs/08)"
    if sub == "tag" and {"-d", "--delete"} & set(rest):
        return "deleting a tag needs the PO's approval (docs/08)"
    return None


def kills_by_name(name, args):
    low = [a.lower() for a in args]
    if name in ("pkill", "killall"):
        return True
    if name == "taskkill":
        return any(a in ("/im", "-im", "/fi", "-fi") for a in low)
    if name in ("stop-process", "spps"):  # only an explicit id is allowed; a piped Get-Process is by name
        return not any(a == "-id" or a.startswith("-id:") or re.fullmatch(r"[\d,]+", a) for a in low)
    if name == "kill":  # PowerShell alias of Stop-Process; bash kill takes PIDs
        return any(len(a) > 2 and ("-name".startswith(a) or "-processname".startswith(a)) for a in low)
    return False


def string_run(name, args):
    """The command string a wrapper executes and its shell, or None."""
    low = [a.lower() for a in args]
    if name in ("bash", "sh", "zsh", "dash", "ksh"):
        flag = next((k for k, a in enumerate(args) if re.fullmatch(r"-[a-z]*c[a-z]*", a)), None)
        return None if flag is None or flag + 1 >= len(args) else (args[flag + 1], "bash")
    if name == "cmd":
        flag = next((k for k, a in enumerate(low) if a in ("/c", "/k", "/r")), None)
        return None if flag is None else (" ".join(args[flag + 1:]), "cmd")
    if name in ("powershell", "pwsh"):
        flag = next((k for k, a in enumerate(low) if len(a) > 1 and "-command".startswith(a)), None)
        return None if flag is None else (" ".join(args[flag + 1:]), "powershell")
    if name == "eval":
        return " ".join(args), "bash"
    if name in ("invoke-expression", "iex"):
        return " ".join(a for a in args if not (len(a) > 1 and "-command".startswith(a.lower()))), "powershell"
    return None


def reason(command, shell="bash"):
    for args in parse(command, shell):
        while args and (re.fullmatch(r"\w+=.*", args[0]) or args[0].lower() in WRAPPERS):
            args = args[1:]
        if not args:
            continue
        name, rest = re.sub(r"\.exe$", "", re.split(r"[\\/]", args[0])[-1].lower()), args[1:]
        inner = string_run(name, rest)
        why = (reason(*inner) if inner
               else git_reason(rest) if name == "git"
               else "ending processes by name is forbidden (docs/08); stop your own PID with Stop-Process -Id N"
               if kills_by_name(name, rest) else None)
        if why:
            return why
    return None


def long_path(path):
    """On Windows, the long form of the longest existing part of path (8.3 names expanded); elsewhere path."""
    if os.name != "nt":
        return path
    import ctypes
    head, tail = path, []
    while not head.exists() and head.parent != head:
        head, tail = head.parent, [head.name] + tail
    buf = ctypes.create_unicode_buffer(32768)
    if ctypes.windll.kernel32.GetLongPathNameW(str(head), buf, len(buf)):
        head = pathlib.Path(buf.value)
    return head.joinpath(*tail)


DEVICE = re.compile(r"^(?:[\\/]{2}[?.][\\/]|\\\?\?\\)(.*)$", re.S)


def plain(file_path):
    """file_path as an ordinary Windows path: no extended-length prefix, no NTFS stream names (H01). None for a device
    path that names no drive or UNC share (GLOBALROOT, a dot-device path, a volume GUID), which is not mapped (H02)."""
    if os.name != "nt":
        return file_path
    m = DEVICE.match(file_path)
    if m:
        rest = m.group(1)
        if re.match(r"[A-Za-z]:[\\/]", rest):
            file_path = rest
        elif re.match(r"UNC[\\/]", rest, re.I):
            file_path = "\\\\" + rest[4:]
        else:
            return None
    drive, tail = os.path.splitdrive(file_path)
    parts = re.split(r"([\\/]+)", tail)
    return drive + "".join(part.split(":")[0] if n % 2 == 0 else part for n, part in enumerate(parts))


def identity(path):
    """(volume serial, file id) of an existing file or folder; None when it is missing or has no id."""
    try:
        st = os.stat(path)
    except (OSError, ValueError):
        return None
    return (st.st_dev, st.st_ino) if st.st_ino else None


def same_object(target, root):
    """Whether target, by file identity, is DIRECTOR_LOG.md, a file under orders/, or lies in a folder under orders/."""
    files, folders = {identity(root / "DIRECTOR_LOG.md")}, {identity(root / "orders")}
    for here, subdirs, names in os.walk(root / "orders"):
        folders |= {identity(os.path.join(here, n)) for n in subdirs}
        files |= {identity(os.path.join(here, n)) for n in names}
    files.discard(None)
    folders.discard(None)
    if identity(target) in files:
        return True
    return any(identity(parent) in folders for parent in pathlib.Path(target).parents)


def canonical(path, cwd=None):
    path = pathlib.Path(path)
    if not path.is_absolute():
        path = pathlib.Path(cwd or os.getcwd()) / path
    return os.path.normcase(str(long_path(path.resolve())))


def protected_reason(file_path, cwd, protect):
    file_path = plain(file_path)
    if file_path is None:
        return "a device path (GLOBALROOT, dot-device or volume GUID form) is not checked against the protected folder; use a drive or UNC path"
    target = canonical(file_path, cwd)
    absolute = pathlib.Path(file_path) if pathlib.Path(file_path).is_absolute() else pathlib.Path(cwd or os.getcwd()) / file_path
    for root in protect:
        orders, log = canonical(pathlib.Path(root) / "orders"), canonical(pathlib.Path(root) / "DIRECTOR_LOG.md")
        if target == log or target.startswith(orders + os.sep) or same_object(absolute, pathlib.Path(root)):
            # no <...> in messages: a report quoting one must still pass gate_check
            return "work orders and DIRECTOR_LOG.md are the Director's (docs/02); report BLOCKED with the reason instead"
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--protect", action="append", default=[], help="DIRECTOR folder whose orders/ and DIRECTOR_LOG.md Write / Edit may not touch")
    a = ap.parse_args()
    try:
        call = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(call, dict):
        return 0
    tool_input = call.get("tool_input") or {}
    file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if a.protect and call.get("tool_name") in ("Write", "Edit") and isinstance(file_path, str) and file_path:
        cwd = call.get("cwd") if isinstance(call.get("cwd"), str) else None
        why = protected_reason(file_path, cwd, a.protect)
        if why:
            print(f"BLOCKED by hook_guard: {why}", file=sys.stderr)
            return 2
        return 0
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return 0
    why = reason(command, "powershell" if call.get("tool_name") == "PowerShell" else "bash")
    if why:
        print(f"BLOCKED by hook_guard: {why}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
