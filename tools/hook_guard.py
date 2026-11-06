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

With --rules FILE (tools/guard_rules.json) and --profile worker|director (setup_project_settings.py --guard-profile),
every tool call is also checked against the rules: shell commands by their words (the same split as above, also inside
bash -c / cmd /c / powershell -Command / eval / iex), Write / Edit / MultiEdit / NotebookEdit by the resolved path, MCP
tools by the action part of their name (the text after the last __). An MCP action that starts with get, list, read,
search, query or status never matches, and SendMessage / mcp__ccd_session_mgmt__send_message (the internal report
channel) never match. The strictest decision wins: deny (exit 2, "BLOCKED by hook_guard [ID]: reason" on stderr), then
the checks above, then ask (exit 0 and a PreToolUse permissionDecision "ask" JSON on stdout). Between equal decisions
the lowest ID wins, so the result does not depend on the order of rules, the time, the network or a model. Otherwise it
exits 0 with no output: it never answers allow, so Claude Code's own permission rules still apply. A rules file that
cannot be read or is malformed gives exit 1 (install with "onFailure": "block" so that blocks). Rule G00 is built in:
Write / Edit of the rules file in use, of guard_rules.json beside this script or of this script is denied for a
worker and asked for a Director, and so is a shell command that writes one of them (named by file name, in any
word): a > whose target names it, or sed / perl -i, tee, cp, mv, rm, Set-Content, Out-File, git checkout / restore,
[IO.File]::WriteAllText and the like with the name among their words. Reading them (cat, git diff, running the hook,
git log -p ... > elsewhere) passes. A name kept in a variable, or a file written by code that a command runs
(python -c, a script), is not seen.
With --pause-flag FILE (needs --rules; tools/pause_ctl.py on|off) every tool call is first checked against the
flag: while FILE exists, a call is denied (exit 2, "PAUSED by WHO at TIME: REASON; ..." on stderr) unless the rules
file's "pause" section lets it through: its allow_tools, read-only MCP actions, the internal report channel, Write /
Edit of an allow_write path (progress files) and a shell line whose every simple command fully matches one of the
profile's allow_shell regexes (tested on the command name and its words joined by single spaces) and that sends no
output to a file (any unquoted >, >>, 2>, &>; 2>&1 is fine). A Bash call with run_in_background is always denied while paused. A call the pause lets through is then checked by the rules as usual.
The flag stops new tool calls only; a program already running keeps running.
Without --rules the output is the same as before, byte for byte.
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


PROFILES = ("worker", "director")
DECISIONS = ("deny", "ask", "none")
KINDS = {"shell": ("cmd",), "path": ("tools", "globs"), "mcp": ("words",)}
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
PATH_FIELDS = ("file_path", "notebook_path", "path")
PATTERN_FIELDS = {"Grep": "glob", "Glob": "pattern"}  # a file pattern under the search path, checked like a path
OPTS_WITH_VALUE = {"git": GIT_OPTS_WITH_VALUE, "gh": {"-R", "--repo"}, "aws": {"--profile", "--region", "--output", "--endpoint-url"},
                   "az": {"--subscription", "--output", "-o", "--query"}, "gcloud": {"--project", "--account", "--configuration"}}
SELF_RULE = {"id": "G00", "decision": {"worker": "deny", "director": "ask"},
             "reason": "the guard rules and hook_guard.py are changed by the PO or the Director, not by a guarded session; report the change you need"}


class RulesError(Exception):
    pass


def string_list(value, empty=False):
    return isinstance(value, list) and (empty or value) and all(isinstance(v, str) and v for v in value)


def rule_problems(rule, seen):
    """What is wrong with one rule, as a list of strings."""
    if not isinstance(rule, dict):
        return ["a rule is not an object"]
    rid = rule.get("id")
    if not (isinstance(rid, str) and re.fullmatch(r"G\d{2,}", rid)) or rid == "G00":
        return [f"rule id {rid!r} is not G01, G02, ... (G00 is built in)"]
    out = [f"{rid}: duplicate id"] if rid in seen else []
    seen.add(rid)
    decision = rule.get("decision")
    if not (isinstance(decision, dict) and set(decision) == set(PROFILES) and all(d in DECISIONS for d in decision.values())):
        out.append(f"{rid}: decision must give worker and director each deny, ask or none")
    text = rule.get("reason")
    if not (isinstance(text, str) and text.strip()) or re.search(r"[<>]", text or ""):
        out.append(f"{rid}: reason must be text without angle brackets")
    if not isinstance(rule.get("category"), str):
        out.append(f"{rid}: category missing")
    matches = rule.get("match")
    matches = [matches] if isinstance(matches, dict) else matches
    if not (isinstance(matches, list) and matches):
        out.append(f"{rid}: match must be an object or a list of objects")
        matches = []
    for m in matches:
        if not isinstance(m, dict) or m.get("kind") not in KINDS:
            out.append(f"{rid}: match kind must be one of {', '.join(KINDS)}")
            continue
        out += [f"{rid}: match {m['kind']} needs a list {key}" for key in KINDS[m["kind"]] if not string_list(m.get(key))]
        if "args" in m and not (isinstance(m["args"], list) and all(string_list(alts) for alts in m["args"])):
            out.append(f"{rid}: args must be a list of word lists")
        if "bare" in m and not isinstance(m["bare"], bool):
            out.append(f"{rid}: bare must be true or false")
        for key in ("path_args", "path_except"):
            if key in m and not string_list(m[key], empty=key == "path_except"):
                out.append(f"{rid}: {key} must be a list of globs")
        for key in ("cmd", "arg_search") if m["kind"] == "shell" else ():
            if not string_list(m.get(key, []), empty=True):
                out.append(f"{rid}: {key} must be a list of regexes")
                continue
            for pattern in m.get(key, []):
                try:
                    re.compile(pattern)
                except re.error as error:
                    out.append(f"{rid}: {key} {pattern!r} is not a regex: {error}")
        for key in ("flags", "not_flags", "except"):
            if key not in m:
                continue
            if not string_list(m[key], empty=True):
                out.append(f"{rid}: {key} must be a list of strings")
                continue
            for flag in m[key] if key != "except" else []:
                try:
                    re.compile(flag)
                except re.error as error:
                    out.append(f"{rid}: flag {flag!r} is not a regex: {error}")
    for key in ("example_block", "example_allow"):
        examples = rule.get(key)
        examples = [examples] if isinstance(examples, dict) else examples
        if not (isinstance(examples, list) and examples and all(isinstance(e, dict) for e in examples)):
            out.append(f"{rid}: {key} must be a hook input or a list of them")
    if "permissions" in rule and not string_list(rule["permissions"]):
        out.append(f"{rid}: permissions must be a list of permission rules")
    return out


PAUSE_LINE = re.compile(r"^PAUSE by (?P<by>.+?) at (?P<at>\S+): (?P<reason>.*)$")  # written by pause_ctl.py on


def pause_problems(pause):
    """What is wrong with the rules file's "pause" section."""
    if not isinstance(pause, dict):
        return ["pause must be an object"]
    out = []
    if not (isinstance(pause.get("reason"), str) and pause["reason"].strip()) or re.search(r"[<>]", str(pause.get("reason"))):
        out.append("pause: reason must be text without angle brackets")
    for key in ("allow_tools", "allow_write"):
        if not string_list(pause.get(key, []), empty=True):
            out.append(f"pause: {key} must be a list of strings")
    if not isinstance(pause.get("allow_mcp_read_only", False), bool):
        out.append("pause: allow_mcp_read_only must be true or false")
    shell = pause.get("allow_shell")
    if not (isinstance(shell, dict) and set(shell) == set(PROFILES) and all(string_list(v, empty=True) for v in shell.values())):
        return out + ["pause: allow_shell must give worker and director each a list of regexes"]
    for pattern in [x for v in shell.values() for x in v]:
        try:
            re.compile(pattern)
        except re.error as error:
            out.append(f"pause: allow_shell {pattern!r} is not a regex: {error}")
    return out


def pause_state(flag):
    """None when the flag file is absent, else (by, at, reason) with no angle brackets; unreadable parts are unknown."""
    path = pathlib.Path(flag)
    if not path.exists():
        return None
    try:
        first = (path.read_text(encoding="utf-8", errors="replace").splitlines() or [""])[0]
    except OSError:
        first = ""
    found = PAUSE_LINE.match(first)
    parts = (found["by"], found["at"], found["reason"]) if found else ("unknown", "unknown", first.strip() or "unknown")
    return tuple(re.sub(r"\s+", " ", x).replace("<", "(").replace(">", ")") for x in parts)


FD_DUP = re.compile(r"[\d*]?>&(\d+|-)")  # 2>&1, *>&1, >&2, 3>&-: joins or closes a stream, writes no file


def has_redirect(command, shell="bash"):
    """True when the line sends output to a file: an unquoted > / >> / &> / >| / >(...), also inside $(...) or `...`
    in double quotes. Stream joins such as 2>&1 do not count."""
    quotes, esc = SHELLS[shell]
    quote, i = None, 0
    while i < len(command):
        c = command[i]
        if quote == "'":
            quote = None if c == "'" else quote
        elif quote:
            if c == '"':
                quote = None
            elif c == esc:
                i += 1
            elif shell != "cmd" and (c == "`" and shell == "bash" or command.startswith("$(", i)):
                end = matching_end(command, i + (c == "$"))
                if has_redirect(command[i + 2 - (c == "`"):end - 1], shell):
                    return True
                i = end
                continue
        elif c in quotes:
            quote = c
        elif c == esc:
            i += 1
        elif c == ">":
            dup = FD_DUP.match(command, i - 1 if i and command[i - 1] in "0123456789*" else i)
            if not dup or dup.end() <= i:
                return True
            i = dup.end()
            continue
        i += 1
    return False


def redirect_word(word):
    """A word of a parsed command that holds a > other than a stream join (quotes are already gone, so err on blocking)."""
    return ">" in word and not FD_DUP.fullmatch(word)


# commands that change the files they name; sed / perl only with -i, git only with these subcommands
WRITE_VERBS = {"tee", "tee-object", "cp", "copy", "copy-item", "cpi", "mv", "move", "move-item", "mi", "ren", "rename",
               "rename-item", "rni", "rm", "del", "erase", "remove-item", "ri", "unlink", "truncate", "dd", "install", "ln",
               "touch", "chmod", "attrib", "icacls", "set-content", "sc", "add-content", "ac", "out-file", "clear-content",
               "clc", "new-item", "ni", "set-item", "si", "xcopy", "robocopy", "rsync", "scp"}
GIT_WRITES = {"checkout", "restore", "rm", "mv"}


DOTNET_WRITE = re.compile(r"::(write|append|copy|move|delete|replace|create)", re.I)


def writes_file(name, rest):
    if name in WRITE_VERBS:
        return True
    if name in ("sed", "gsed", "perl") and any(re.fullmatch(r"-[a-zA-Z]*i.*|--in-place.*", a) for a in rest):
        return True
    return name == "git" and positional("git", rest)[:1] in [[w] for w in GIT_WRITES]


def self_write(commands, names):
    """True when a command writes a guarded file (named by file name in any word): a write verb that names it, a >
    whose target names it, or a .NET write call ([IO.File]::WriteAllText) on a line that names it. A > with no target
    in its command (>| splits there) counts when the line names the file."""
    named = lambda words: any(n in w.lower() for n in names for w in words)
    line_named = any(named([n] + list(r)) for n, r in commands)
    if line_named and any(DOTNET_WRITE.search(n) for n, _ in commands):
        return True  # the ( of the call splits it from its path
    for name, rest in commands:
        words = [name] + list(rest)
        if named(words) and writes_file(name, rest):
            return True
        for k, word in enumerate(words):
            if redirect_word(word):
                target = word.rsplit(">", 1)[1] or (words[k + 1] if k + 1 < len(words) else None)
                if named([target]) if target is not None else line_named:
                    return True
    return False


def pause_allows(data, profile, call):
    """True when the pause section lets this call through while the flag is on."""
    pause = data["pause"]
    tool = call.get("tool_name") if isinstance(call.get("tool_name"), str) else ""
    tool_input = call.get("tool_input") if isinstance(call.get("tool_input"), dict) else {}
    cwd = call.get("cwd") if isinstance(call.get("cwd"), str) else None
    if tool in pause.get("allow_tools", []) or tool in data.get("internal_report_tools", []):
        return True
    if tool.startswith("mcp__") and pause.get("allow_mcp_read_only"):
        read_only = data.get("read_only_mcp_prefixes", ["get", "list", "read", "search", "query", "status"])
        return mcp_action(tool).split("_")[0] in read_only
    if tool in WRITE_TOOLS:
        value = next((tool_input[f] for f in PATH_FIELDS if isinstance(tool_input.get(f), str) and tool_input[f]), None)
        home = rule_path(str(pathlib.Path.home()), None)
        return bool(value) and globs_match(pause.get("allow_write", []), [], rule_path(value, cwd), home)
    command = tool_input.get("command")
    if tool not in ("Bash", "PowerShell") or not isinstance(command, str) or tool_input.get("run_in_background"):
        return False
    if has_redirect(command, "powershell" if tool == "PowerShell" else "bash"):
        return False  # git log > a.py writes a file; 2>&1 is not a redirect to a file
    commands = list(simple_commands(FD_DUP.sub(" ", command), "powershell" if tool == "PowerShell" else "bash"))
    allowed = pause["allow_shell"][profile]
    return bool(commands) and all(any(re.fullmatch(r, " ".join([n] + list(rest)), re.I | re.S) for r in allowed)
                                  for n, rest in commands)


def load_rules(path):
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise RulesError(f"cannot read {path}: {error}")
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("rules"), list) or not data["rules"]:
        raise RulesError(f"{path}: needs schema_version 1 and a non-empty rules list")
    seen, problems = set(), []
    for rule in data["rules"]:
        problems += rule_problems(rule, seen)
    for key in ("internal_report_tools", "read_only_mcp_prefixes"):
        if key in data and not string_list(data[key], empty=True):
            problems.append(f"{key} must be a list of strings")
    if "pause" in data:
        problems += pause_problems(data["pause"])
    if problems:
        raise RulesError(f"{path}: " + "; ".join(problems))
    return data


def as_list(value):
    return [value] if isinstance(value, dict) else list(value)


def command_name(word):
    return re.sub(r"\.exe$", "", re.split(r"[\\/]", word)[-1].lower())


def simple_commands(command, shell="bash", depth=0):
    """(name, args) of every simple command of a line, also those a wrapper runs (bash -c, cmd /c, eval, ...)."""
    for args in parse(command, shell):
        while args and (re.fullmatch(r"\w+=.*", args[0]) or args[0].lower() in WRAPPERS):
            if args[0].lower() == "env" and all(re.fullmatch(r"-.*|\w+=.*", a) for a in args[1:]):
                break  # env with no command after it prints the environment
            args = args[1:]
        if not args:
            continue
        name, rest = command_name(args[0]), args[1:]
        yield name, rest
        inner = string_run(name, rest)
        if inner and depth < 8:
            yield from simple_commands(*inner, depth + 1)


def positional(name, rest):
    """The words of a command that are not options (git -C dir / gh -R repo skip their value too), lower case."""
    out, i, with_value = [], 0, OPTS_WITH_VALUE.get(name, set())
    while i < len(rest):
        if rest[i].startswith("-") and len(rest[i]) > 1:
            i += 2 if rest[i] in with_value else 1
        else:
            out.append(rest[i].lower())
            i += 1
    return out


def shell_match(m, name, rest, cwd=None, home=""):
    """cmd: regexes for the whole command name (lower case); args: the first non-option words in turn; flags /
    not_flags: regexes, some / no word must match whole; bare: no words at all; arg_search: a regex found in some word;
    path_args: some non-option word, as a path from the hook cwd, matches a glob (and no path_except glob)."""
    if not any(re.fullmatch(c, name, re.I) for c in m["cmd"]):
        return False
    words = positional(name, rest)
    if len(words) < len(m.get("args", [])) or any(words[k] not in [w.lower() for w in alts] for k, alts in enumerate(m.get("args", []))):
        return False
    if m.get("bare") and rest:
        return False
    if m.get("arg_search") and not any(re.search(r, a) for r in m["arg_search"] for a in rest):
        return False
    if m.get("path_args") and not any(globs_match(m["path_args"], m.get("path_except", []), arg_path(a, cwd), home)
                                      for a in rest if not a.startswith("-")):
        return False
    hit = lambda key: any(re.fullmatch(f, a, re.I) for f in m.get(key, []) for a in rest)
    return (not m.get("flags") or hit("flags")) and not hit("not_flags")


def arg_path(word, cwd):
    """A command word as rule_path gives it: $VAR, ${VAR}, %VAR% and PowerShell $env:VAR expanded first."""
    word = re.sub(r"\$env:(\w+)", lambda v: os.environ.get(v.group(1), v.group(0)), word, flags=re.I)
    return rule_path(os.path.expandvars(word), cwd)


def rule_path(value, cwd):
    """A tool's path as an absolute, resolved path with / separators (lower case on Windows)."""
    text = os.path.expanduser(plain(value) or value)
    try:
        full = canonical(text, cwd)
    except (OSError, ValueError, RuntimeError):
        full = os.path.normcase(os.path.abspath(os.path.join(cwd or os.getcwd(), text)))
    return full.replace("\\", "/")


def glob_regex(glob, home):
    """~/x is under the home folder, **/x at any depth, anything else is a whole absolute path; * stays in one folder."""
    glob, prefix = glob.replace("\\", "/"), ""
    if glob.startswith("~/"):
        glob, prefix = glob[2:], re.escape(home.rstrip("/")) + "/"
    out, i = prefix, 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif glob.startswith("**", i):
            out, i = out + ".*", i + 2
        else:
            out, i = out + {"*": "[^/]*", "?": "[^/]"}.get(glob[i], re.escape(glob[i])), i + 1
    return re.compile(out, re.I if os.name == "nt" else 0)


def globs_match(globs, excepts, target, home):
    hit = lambda patterns: any(glob_regex(g, home).fullmatch(target) for g in patterns)
    return hit(globs) and not hit(excepts)


def path_match(m, tool, targets, home):
    return tool in m["tools"] and any(globs_match(m["globs"], m.get("except", []), t, home) for t in targets if t)


def mcp_action(tool):
    """The action part of an MCP tool name as lower-case words joined by _ (createPullRequest -> create_pull_request)."""
    action = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", tool.rsplit("__", 1)[-1])
    return re.sub(r"[^a-z0-9]+", "_", action.lower()).strip("_")


def mcp_match(m, action, read_only):
    if action is None:
        return False
    words = action.split("_")
    if words[0] in read_only:
        return False
    return any(f"_{w}_" in f"_{action}_" if "_" in w else w in words for w in m["words"])


def decide(data, profile, call, rules_path):
    """All (decision, id, reason) the rules give for one hook input; empty when none applies."""
    tool = call.get("tool_name") if isinstance(call.get("tool_name"), str) else ""
    if tool in data.get("internal_report_tools", []):
        return []
    tool_input = call.get("tool_input") if isinstance(call.get("tool_input"), dict) else {}
    cwd = call.get("cwd") if isinstance(call.get("cwd"), str) else None
    command = tool_input.get("command")
    # 2>&1 is dropped first: its & would otherwise split the line and leave "2>" looking like a redirect
    commands = (list(simple_commands(FD_DUP.sub(" ", command), "powershell" if tool == "PowerShell" else "bash"))
                if tool in ("Bash", "PowerShell") and isinstance(command, str) else [])
    value = next((tool_input[f] for f in PATH_FIELDS if isinstance(tool_input.get(f), str) and tool_input[f]), None)
    target = rule_path(value, cwd) if value else None
    pattern = tool_input.get(PATTERN_FIELDS.get(tool, ""))
    targets = [target] + ([rule_path(os.path.join(value or cwd or os.getcwd(), pattern), cwd)]
                          if isinstance(pattern, str) and pattern else [])
    home = rule_path(str(pathlib.Path.home()), None)
    action = mcp_action(tool) if tool.startswith("mcp__") else None
    read_only = data.get("read_only_mcp_prefixes", ["get", "list", "read", "search", "query", "status"])
    hits = []
    own = pathlib.Path(__file__)
    guarded = {rule_path(str(rules_path), None), rule_path(str(own), None), rule_path(str(own.with_name("guard_rules.json")), None)}
    names = {pathlib.Path(str(rules_path)).name.lower(), "guard_rules.json", own.name.lower()}
    if tool in WRITE_TOOLS and target in guarded or self_write(commands, names):
        hits.append((SELF_RULE["decision"][profile], "G00", SELF_RULE["reason"]))
    for rule in data["rules"]:
        decision = rule["decision"][profile]
        if decision == "none":
            continue
        for m in as_list(rule["match"]):
            if (m["kind"] == "shell" and any(shell_match(m, n, r, cwd, home) for n, r in commands)
                    or m["kind"] == "path" and path_match(m, tool, targets, home)
                    or m["kind"] == "mcp" and mcp_match(m, action, read_only)):
                hits.append((decision, rule["id"], rule["reason"]))
                break
    return hits


def first(hits, decision):
    """The hit with the lowest id among those with this decision, or None."""
    found = sorted((h for h in hits if h[0] == decision), key=lambda h: int(h[1][1:]))
    return found[0] if found else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--protect", action="append", default=[], help="DIRECTOR folder whose orders/ and DIRECTOR_LOG.md Write / Edit may not touch")
    ap.add_argument("--rules", help="rules file (tools/guard_rules.json): check every tool call against it")
    ap.add_argument("--profile", choices=PROFILES, default="worker", help="which decision of each rule applies (default worker)")
    ap.add_argument("--pause-flag", help="flag file (pause_ctl.py on): while it exists, deny what the rules' pause section does not allow")
    a = ap.parse_args()
    data = None
    if a.rules:
        try:
            data = load_rules(a.rules)
            if a.pause_flag and "pause" not in data:
                raise RulesError(f"{a.rules}: --pause-flag needs a pause section")
        except RulesError as error:
            print(f"hook_guard: bad rules file: {error}", file=sys.stderr)
            return 1
    elif a.pause_flag:
        print("hook_guard: --pause-flag needs --rules", file=sys.stderr)
        return 1
    try:
        call = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(call, dict):
        return 0
    paused = pause_state(a.pause_flag) if a.pause_flag else None
    if paused and not pause_allows(data, a.profile, call):
        print(f"PAUSED by {paused[0]} at {paused[1]}: {paused[2]}; {data['pause']['reason']}", file=sys.stderr)
        return 2
    tool_input = call.get("tool_input") or {}
    file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if a.protect and call.get("tool_name") in ("Write", "Edit") and isinstance(file_path, str) and file_path:
        cwd = call.get("cwd") if isinstance(call.get("cwd"), str) else None
        why = protected_reason(file_path, cwd, a.protect)
    elif isinstance(command, str):
        why = reason(command, "powershell" if call.get("tool_name") == "PowerShell" else "bash")
    else:
        why = None
    hits = decide(data, a.profile, call, a.rules) if data is not None else []
    deny, ask = first(hits, "deny"), first(hits, "ask")
    if deny:
        print(f"BLOCKED by hook_guard [{deny[1]}]: {deny[2]}", file=sys.stderr)
        return 2
    if why:
        print(f"BLOCKED by hook_guard: {why}", file=sys.stderr)
        return 2
    if ask:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                                 "permissionDecisionReason": f"[{ask[1]}] {ask[2]}"}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
