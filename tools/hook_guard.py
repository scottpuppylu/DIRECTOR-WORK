"""PreToolUse hook: flag the shell commands that docs/08 reserves for the PO or forbids outright.

Claude Code runs it before every Bash / PowerShell tool call and passes the call as JSON on stdin. A call nothing
flags exits 0 silently, so it costs no context. What a flagged call gets depends on --mode:
  remind (default)  exit 0, the call runs; one JSON line on stdout: "systemMessage" (shown to the user) and
                    hookSpecificOutput.additionalContext (shown to the model), both "hook_guard reminder [ID]: reason",
                    the second with a note that this is only a reminder. A call the user approved in the conversation
                    is simply run, with no second question and no settings change.
  ask               exit 0 and a PreToolUse permissionDecision "ask" JSON on stdout: the user decides there and then.
  block             the explicit opt-in strict mode: exit 2 and "BLOCKED by hook_guard ..." on stderr, which Claude Code
                    shows to the model instead of running the command (the behaviour of 1.3.0 and before).
Do not install block on worker lines by default: a guard that stops approved work teaches the agent to do nothing.
A seat belt, not a brake. The pause flag (--pause-flag) is an explicit stop set by a person and denies in every mode;
auto-pause and --review act in block mode only.

Flagged: git push (any form, also `git -C <dir> push` and C:\\...\\git.exe push), git reset --hard,
git clean (except -n / --dry-run), bare git stash / stash pop / drop / clear (`git stash push -m <mark>`, list, show,
apply stay allowed), deleting a worktree, branch or tag, and ending processes by name (taskkill /IM or /FI, pkill,
killall, Stop-Process without -Id, which also covers `Get-Process x | Stop-Process`).
The line is split only outside quotes, and a quoted string is checked as a command only when a wrapper runs it
(bash / sh -c, cmd /c, powershell -Command, eval, Invoke-Expression) or it holds $(...) / `...`.
In Bash the body of a here-document (cat <<'EOF' ... EOF, also <<- and an unquoted EOF) is data, not commands, and is
not checked; with an unquoted EOF its $(...) and `...` still run and are checked. A here-document without its closing
line is checked as it is. A quoted string is never split into commands, so echo "git push" or a commit message that
names one passes.
Not covered: deleting files (rm -rf, Remove-Item -Recurse), a command hidden in a script file or built at run time.
This is a seat belt, not a security boundary. Install with setup_project_settings.py --hooks (remind mode unless
--guard-mode ask or block). Below, "blocked", "denied" and "exit 2" describe block mode; in remind and ask mode the
same calls get the reminder or the ask instead.

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
Auto-pause: when the rules file's "auto_pause" gives the profile {"denies": N, "window_s": S} (worker 5 in 600 s;
director null, off), every deny while not paused adds "TIME RULE" to FILE.denies beside the flag; the N-th deny within
S seconds writes the flag itself ("PAUSE by hook_guard at TIME: auto: N denies in Ss (G02 G50 ...)"), clears
FILE.denies and says so in the deny message. pause_ctl.py off lifts it as usual. A FILE.denies that cannot be read or
written never changes the decision: the deny stays a deny and no pause is written.
With --audit FILE every deny, ask, remind and pause is also added to the action log FILE (audit_log.py) as a kind=decision
line with the rule ID (G.., builtin for the checks above, PAUSE), so a blocked call is on the chain too. A log that
cannot be written (lock busy for 5 s, broken last line) never changes the decision.
With --review (needs --rules with a "review" section; off unless given) an ask whose rule category is in
review.categories is first shown to a second model: CLAUDE_CODE_EXECPATH (the claude executable of this session; a
.py path runs with this Python, for tests), else claude on PATH, run as
  claude -p --model M --settings {"disableAllHooks":true} --tools "" --no-session-persistence --output-format json PROMPT
with no tools and no hooks. The prompt holds the tool name, the tool input masked by secret_mask.py (at most 1000
characters), the rule ID and its reason; no file contents. Only a reply whose result is exactly the JSON
{"verdict": "block" | "no_objection", "reason": "..."} counts: block turns the ask into a deny (exit 2, "BLOCKED by
hook_guard [ID]: second-model review: REASON"); no_objection keeps the ask (a person still decides); a timeout
(review.timeout_s), a non-zero exit or anything else keeps the ask as review=unavailable. So the review can only
tighten: a deny or a silent pass is never sent to it. --audit lines say "ID review=VERDICT via=SOURCE". Each review
is one claude -p call on the logged-in account: no money, but it uses the subscription's quota.
With --sessions FILE (needs --rules; setup_project_settings.py --session-map) the profile is chosen per call from the
hook input's session_id, because Claude Code reads settings only from the folder a session was started in: several
sessions (Director, workers, cleaner) that start in one folder share one settings file, whatever worktree each later
works in. FILE (templates/guard_sessions.json):
  {"schema_version": 1, "default": "worker",
   "sessions": {"SESSION_ID": "director", "SESSION_ID2": {"profile": "cleaner", "name": "cleaner"}},
   "protected": ["D:/work/DIRECTOR/**", "~/keep/**", "**/RESUME_STATE.md"]}
A session_id the file does not name gets "default" (else --profile). cleaner is the worker profile with the rules of
category "delete" off (it may delete files); for every profile a delete or move command (the delete rules' commands,
mv, Move-Item, ren, Rename-Item) on a path that a protected glob matches, or on a folder above a protected glob's
fixed part (also a wildcard word such as D:/work/* that matches such a folder), is denied (exit 2, rule "protected"
in the action log). A **/ glob only matches the named file, so deleting a folder that happens to hold one is not
seen. The worktree, branch and tag checks above hold for the cleaner too. With --sessions the Director's session is
never held by --pause-flag and never auto-pauses. A sessions file that cannot be read or is malformed gives exit 1.
Without --rules, --mode block gives the output of 1.3.0 and before, byte for byte.
"""
import argparse
import datetime
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
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


HEREDOC = re.compile(r"""<<(-?)[ \t]*(?:'([^'\n]*)'|"([^"\n]*)"|\\([^\s;&|<>()'"]+)|([^\s;&|<>()'"]+))""")


def heredoc_end(command, start, delim, tabs):
    """(start of the closing line, index just past it) of a here-document whose body starts at start; None when the
    closing line is missing."""
    i = start
    while i <= len(command):
        nl = command.find("\n", i)
        line = command[i:len(command) if nl < 0 else nl].rstrip("\r")
        if (line.lstrip("\t") if tabs else line) == delim:
            return i, len(command) if nl < 0 else nl + 1
        if nl < 0:
            return None
        i = nl + 1
    return None


def substitutions(body):
    """The $(...) and `...` of a here-document body, one per line: an unquoted EOF still runs them."""
    found, i = [], 0
    while i < len(body):
        if body[i] == "\\":
            i += 2
            continue
        if body[i] == "`" or body.startswith("$(", i):
            end = matching_end(body, i + (body[i] == "$"))
            found.append(body[i + 2 - (body[i] == "`"):end - 1])
            i = end
            continue
        i += 1
    return found


def strip_heredocs(command):
    """Bash: the line without the body of each here-document and without its <<WORD; the body is data. With an
    unquoted WORD its $(...) and `...` are kept, each on a line of its own. A here-document whose closing line is
    missing is left as it is, so nothing that runs can be hidden."""
    if "<<" not in command:
        return command
    out, pending, quote, i = [], [], None, 0
    while i < len(command):
        c = command[i]
        if quote == "'":
            quote = None if c == "'" else quote
        elif quote:
            if c == "\\":
                out.append(command[i:i + 2])
                i += 2
                continue
            quote = None if c == '"' else quote
        elif c == "\\":
            out.append(command[i:i + 2])
            i += 2
            continue
        elif c in "'\"":
            quote = c
        elif command.startswith("<<", i) and not command.startswith("<<<", i) and not command[i - 1:i] == "<":
            m = HEREDOC.match(command, i)
            if m:
                delim = next(g for g in m.groups()[1:] if g is not None)
                pending.append((len(out), m.group(0), delim, m.group(1) == "-", m.group(5) is not None))
                out.append(m.group(0))
                i = m.end()
                continue
        elif c == "\n" and pending:
            out.append(c)
            at, extra = i + 1, []
            for _, _, delim, tabs, open_body in pending:
                found = heredoc_end(command, at, delim, tabs)
                if found is None:
                    return command
                extra += substitutions(command[at:found[0]]) if open_body else []
                at = found[1]
            for slot, _, _, _, _ in pending:
                out[slot] = ""
            out += [x + "\n" for x in extra]
            pending, i = [], at
            continue
        out.append(c)
        i += 1
    if pending:  # body after the last line: nothing closes it
        return command
    return "".join(out)


def parse(command, shell="bash"):
    """Simple commands of a shell line as word lists; also the commands inside $(...) / `...` in double quotes.
    In Bash a here-document body is not a command (strip_heredocs)."""
    quotes, esc = SHELLS[shell]
    if shell == "bash":
        command = strip_heredocs(command)
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
MODES = ("remind", "ask", "block")
REMIND_NOTE = (" (reminder only, not blocked: the call runs. Approved by the user in this conversation: go ahead and do"
               " not ask again. Not approved: tell the user what ran.)")
# cleaner: a worker whose "delete" rules do not apply; the sessions file's protected list still holds (--sessions)
SESSION_PROFILES = PROFILES + ("cleaner",)
CLEANER_OPEN = ("delete",)
DECISIONS = ("deny", "ask", "none")
KINDS = {"shell": ("cmd",), "path": ("tools", "globs"), "mcp": ("words",)}
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
SHELL_TOOLS = ("Bash", "PowerShell", "Monitor")  # Monitor runs a shell command; checked as Bash
PATH_FIELDS = ("file_path", "notebook_path", "path")
PATTERN_FIELDS = {"Grep": "glob", "Glob": "pattern"}  # a file pattern under the search path, checked like a path
OPTS_WITH_VALUE = {"git": GIT_OPTS_WITH_VALUE, "gh": {"-R", "--repo"}, "aws": {"--profile", "--region", "--output", "--endpoint-url"},
                   "az": {"--subscription", "--output", "-o", "--query"}, "gcloud": {"--project", "--account", "--configuration"}}
SELF_RULE = {"id": "G00", "decision": {"worker": "deny", "director": "ask"},
             "reason": "the guard rules and hook_guard.py are changed by the PO or the Director, not by a guarded session; report the change you need"}


class RulesError(Exception):
    pass


def base_profile(profile):
    """The profile of the rules file whose pause and auto-pause settings a session profile uses."""
    return "worker" if profile == "cleaner" else profile


def rule_decision(rule, profile):
    if profile == "cleaner":
        return "none" if rule.get("category") in CLEANER_OPEN else rule["decision"]["worker"]
    return rule["decision"][profile]


SESSION_KEYS = {"schema_version", "about", "default", "sessions", "protected"}


def load_sessions(path):
    """The sessions file (--sessions): {"schema_version": 1, "default": PROFILE, "sessions": {SESSION_ID: PROFILE or
    {"profile": PROFILE, "name": TEXT}}, "protected": [GLOB, ...]}; raises RulesError when it is bad."""
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise RulesError(f"cannot read {path}: {error}")
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise RulesError(f"{path}: needs schema_version 1")
    problems = [f"unknown key {k}" for k in sorted(set(data) - SESSION_KEYS)]
    if data.get("default", "worker") not in SESSION_PROFILES:
        problems.append(f"default must be one of {', '.join(SESSION_PROFILES)}")
    sessions = data.get("sessions", {})
    if not isinstance(sessions, dict):
        problems.append("sessions must be an object of session_id: profile")
        sessions = {}
    for sid, entry in sessions.items():
        profile = entry.get("profile") if isinstance(entry, dict) else entry
        if not sid.strip() or profile not in SESSION_PROFILES or (isinstance(entry, dict) and set(entry) - {"profile", "name", "about"}):
            problems.append(f"sessions.{sid}: a profile ({', '.join(SESSION_PROFILES)}) or {{profile, name}}")
    protected = data.get("protected", [])
    if not string_list(protected, empty=True) or not all(
            g.startswith(("~/", "**/", "/")) or re.match(r"[A-Za-z]:[\\/]", g) for g in protected):
        problems.append("protected must be a list of absolute, ~/ or **/ globs")
    if problems:
        raise RulesError(f"{path}: " + "; ".join(problems))
    return data


def session_profile(sessions, call, fallback):
    entry = sessions.get("sessions", {}).get(str(call.get("session_id") or ""))
    if entry is not None:
        return entry["profile"] if isinstance(entry, dict) else entry
    return sessions.get("default", fallback)


MOVERS = ("mv", "move", "move-item", "mi", "ren", "rename-item", "rni")


def protected_delete(data, commands, cwd, globs):
    """The reason a shell line deletes or moves a protected path (or a folder above one), else None."""
    if not globs:
        return None
    home = rule_path(str(pathlib.Path.home()), None)
    norm = (lambda s: s.lower()) if os.name == "nt" else (lambda s: s)
    deleters = [m for r in data["rules"] if r.get("category") in CLEANER_OPEN for m in as_list(r["match"]) if m["kind"] == "shell"]
    for name, rest in commands:
        if name not in MOVERS and not any(shell_match(m, name, rest, cwd, home) for m in deleters):
            continue
        for word in rest:
            if word.startswith("-") or not word.strip():
                continue
            target = arg_path(word, cwd)
            wild = glob_regex(target, home) if re.search(r"[*?]", target) else None
            for g in globs:
                if glob_regex(g, home).fullmatch(target):
                    return f"{word} is on the protected list ({g}); report it to the Director instead of deleting it"
                literal = re.split(r"[*?]", (home.rstrip("/") + g[1:]) if g.startswith("~/") else g.replace("\\", "/"))[0]
                folder = norm(literal.rstrip("/"))
                parts = folder.split("/")
                above = ["/".join(parts[:k]) for k in range(len(parts), 0, -1)]  # down to the drive or /
                if folder and (any(norm(target).rstrip("/") == p for p in above) or wild and any(wild.fullmatch(p) for p in above)):
                    return f"{word} holds protected paths ({g}); report it to the Director instead of deleting it"
    return None


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
        for key in ("bare", "shell_write"):
            if key in m and not isinstance(m[key], bool):
                out.append(f"{rid}: {key} must be true or false")
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


def auto_pause_problems(auto):
    """What is wrong with the rules file's "auto_pause" section."""
    if not isinstance(auto, dict) or not set(PROFILES) <= set(auto):
        return ["auto_pause must give worker and director each null or {denies, window_s}"]
    out = []
    for profile in PROFILES:
        conf = auto[profile]
        if conf is None:
            continue
        if not (isinstance(conf, dict) and set(conf) == {"denies", "window_s"}
                and all(isinstance(conf[k], int) and not isinstance(conf[k], bool) and conf[k] >= 1 for k in conf)):
            out.append(f"auto_pause.{profile} must be null or {{denies, window_s}} with whole numbers of at least 1")
    return out


def auto_pause(flag, conf, rule):
    """Count this deny in FLAG.denies; at conf["denies"] within conf["window_s"] seconds write the flag. Returns the
    pause reason when it paused, else None. Any OSError: None, nothing paused (the deny itself stands)."""
    if not conf:
        return None
    state = pathlib.Path(str(flag) + ".denies")
    now = datetime.datetime.now().astimezone()
    try:
        with open(state, "a", encoding="utf-8", newline="\n") as out:
            out.write(f"{now.timestamp():.3f} {rule}\n")
        recent = []
        for line in state.read_text(encoding="utf-8", errors="replace").splitlines():
            stamp, _, rid = line.partition(" ")
            try:
                if now.timestamp() - float(stamp) <= conf["window_s"]:
                    recent.append(re.sub(r"[^\w.-]", "", rid) or "unknown")
            except ValueError:
                continue
        if len(recent) < conf["denies"]:
            if len(recent) * 4 < len(state.read_text(encoding="utf-8", errors="replace").splitlines()):
                with open(state, "w", encoding="utf-8", newline="\n") as out:  # Path.write_text(newline=) needs 3.10
                    out.write("".join(f"{now.timestamp():.3f} {r}\n" for r in recent))
            return None
        why = f"auto: {len(recent)} denies in {conf['window_s']}s ({' '.join(recent)})"
        with open(flag, "w", encoding="utf-8", newline="\n") as out:
            out.write(f"PAUSE by hook_guard at {now.isoformat(timespec='seconds')}: {why}\n")
        state.write_text("", encoding="utf-8")
        return why
    except OSError:
        return None


def review_problems(review):
    """What is wrong with the rules file's "review" section."""
    if not isinstance(review, dict):
        return ["review must be an object"]
    out = []
    if not (isinstance(review.get("model"), str) and re.fullmatch(r"[\w.:-]+", review["model"])):
        out.append("review: model must be a model name")
    timeout = review.get("timeout_s")
    if not (isinstance(timeout, int) and not isinstance(timeout, bool) and 1 <= timeout <= 600):
        out.append("review: timeout_s must be a whole number from 1 to 600")
    if not string_list(review.get("categories"), empty=False):
        out.append("review: categories must be a non-empty list of rule categories")
    return out


REVIEW_PROMPT = """You review one action that an AI coding agent wants to take. A rule already sent it to a person for
approval. Answer only with one JSON object and nothing else:
{{"verdict": "block" or "no_objection", "reason": "one short sentence"}}
Say block when the action looks destructive, outward-facing beyond what the rule describes, or like a way around the
rule. Say no_objection otherwise; the person still decides.
Tool: {tool}
Input (secrets masked): {action}
Rule {rule}: {reason}"""


def review_command(model, prompt):
    """(argv, source): the claude to run and where it came from; argv None when there is none."""
    path = os.environ.get("CLAUDE_CODE_EXECPATH")
    source = "CLAUDE_CODE_EXECPATH"
    if not path:
        path, source = shutil.which("claude"), "PATH"
    if not path:
        return None, "none"
    base = [sys.executable, "-I", path] if path.lower().endswith(".py") else [path]
    return base + ["-p", "--model", model, "--settings", '{"disableAllHooks":true}', "--tools", "",
                   "--no-session-persistence", "--output-format", "json", prompt], source


def review(conf, call, rule, reason):
    """(verdict, reason, source); verdict block / no_objection / unavailable. Never raises."""
    try:
        spec = importlib.util.spec_from_file_location("secret_mask", pathlib.Path(__file__).with_name("secret_mask.py"))
        mask = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mask)
        action = mask.mask(json.dumps(call.get("tool_input"), ensure_ascii=False))[0][:1000]
    except Exception:
        return "unavailable", "secret_mask.py could not be loaded", "none"
    prompt = REVIEW_PROMPT.format(tool=call.get("tool_name"), action=action, rule=rule, reason=reason)
    argv, source = review_command(conf["model"], prompt)
    if argv is None:
        return "unavailable", "no claude executable", source
    env = dict(os.environ, DW_HOOK_REVIEW="1")
    try:
        done = subprocess.run(argv, capture_output=True, encoding="utf-8", errors="replace", timeout=conf["timeout_s"],
                              env=env, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return "unavailable", "timed out", source
    except OSError as error:
        return "unavailable", type(error).__name__, source
    if done.returncode != 0:
        return "unavailable", f"exit {done.returncode}", source
    try:
        outer = json.loads(done.stdout)
        answer = json.loads(outer["result"]) if isinstance(outer, dict) and isinstance(outer.get("result"), str) else None
    except ValueError:
        answer = None
    if not (isinstance(answer, dict) and set(answer) == {"verdict", "reason"} and answer["verdict"] in ("block", "no_objection")
            and isinstance(answer["reason"], str)):
        return "unavailable", "reply is not the agreed JSON", source
    said = re.sub(r"\s+", " ", answer["reason"]).replace("<", "(").replace(">", ")").strip()[:300] or "no reason given"
    return answer["verdict"], said, source


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


def redirect_targets(command, shell="bash"):
    """The file words of the line's output redirects (> >> &> >| *>), quotes removed, also inside $(...) or `...` in
    double quotes; "" for a > with no file word, such as >(...). Read from the raw line, so { } ( ) next to the >
    cannot hide it (echo {}>file). Stream joins such as 2>&1 are not redirects. A here-document body is skipped."""
    quotes, esc = SHELLS[shell]
    if shell == "bash":
        command = strip_heredocs(command)
    out, quote, i = [], None, 0
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
                out += redirect_targets(command[i + 2 - (c == "`"):end - 1], shell)
                i = end
                continue
        elif c in quotes:
            quote = c
        elif c == esc:
            i += 1
        elif c == ">":
            dup = FD_DUP.match(command, i - 1 if i and command[i - 1] in "0123456789*" else i)
            if dup and dup.end() > i:
                i = dup.end()
                continue
            i += 1
            while i < len(command) and command[i] in ">|&":  # >> >| >&file
                i += 1
            word, i = target_word(command, i, shell)
            out.append(word)
            continue
        i += 1
    return out


def target_word(command, i, shell):
    """(word, end) of the redirect target that starts at i, after blanks, quotes removed; ("", i) when a separator
    or ( comes first."""
    quotes, esc = SHELLS[shell]
    while i < len(command) and command[i] in " \t":
        i += 1
    word, quote = "", None
    while i < len(command):
        c, nxt = command[i], command[i + 1:i + 2]
        if quote:
            if c == quote:
                quote = None
            elif c == esc and quote == '"' and nxt in ('"', esc):
                word, i = word + nxt, i + 1
            else:
                word += c
        elif c in quotes:
            quote = c
        elif c == esc and nxt and (shell != "bash" or nxt in " \t'\"\\;|&<>()"):
            word, i = word + nxt, i + 1
        elif c in " \t\r\n;|&<>()":
            break
        else:
            word += c
        i += 1
    return word, i


def has_redirect(command, shell="bash"):
    """True when the line sends output to a file: an unquoted > / >> / &> / >| / >(...), also inside $(...) or `...`
    in double quotes. Stream joins such as 2>&1 do not count."""
    return bool(redirect_targets(command, shell))


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


def self_write(commands, names, targets=()):
    """True when a command writes a guarded file (named by file name in any word): a write verb that names it, a >
    whose target names it, or a .NET write call ([IO.File]::WriteAllText) on a line that names it. A > with no target
    in its command (>| splits there) counts when the line names the file. targets: redirect_targets of the raw line,
    which still sees the > of echo {}>file after { } split the parsed words."""
    named = lambda words: any(n in w.lower() for n in names for w in words)
    line_named = any(named([n] + list(r)) for n, r in commands)
    if line_named and any(DOTNET_WRITE.search(n) for n, _ in commands):
        return True  # the ( of the call splits it from its path
    if any(named([t]) if t else line_named for t in targets):
        return True
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


COPY_VERBS = {"cp", "copy", "copy-item", "cpi", "install", "ln", "scp", "xcopy", "robocopy", "rsync"}  # write only the destination


def written_words(name, rest, cwd):
    """The words a write verb writes to: for a copy, its destination (joined with each source's name when it is a
    folder); for the others, every non-option word."""
    words = [a for a in rest if not a.startswith("-")]
    if name not in COPY_VERBS:
        return words
    lower = [a.lower() for a in rest]
    flag = next((k for k, a in enumerate(lower) if a in ("-destination", "-t", "--target-directory")), None)
    if flag is not None and flag + 1 < len(rest):
        dest = rest[flag + 1]
        sources = [w for w in words if w != dest]
    elif words:
        dest, sources = words[-1], words[:-1]
    else:
        return []
    if dest.endswith(("/", "\\")) or os.path.isdir(arg_path(dest, cwd)):
        base = dest.rstrip("/\\")
        return [dest] + [base + "/" + re.split(r"[/\\]", s.rstrip("/\\"))[-1] for s in sources]
    return [dest]


LINE_WORD = re.compile(r"""'([^']*)'|"([^"]*)"|([^\s'"(),;|&<>]+)""")


def shell_write_match(m, commands, targets, cwd, home, line=""):
    """A path rule's globs read as files a shell line writes: a write verb's destination, a > target, or a .NET write
    call on a line that names a matching path (read from the raw line: the ( of the call splits the path off)."""
    def hit(word):
        return bool(word) and globs_match(m["globs"], m.get("except", []), arg_path(word, cwd), home)
    if any(hit(t) for t in targets):
        return True
    if DOTNET_WRITE.search(line) and any(hit("".join(w)) for w in LINE_WORD.findall(line)):
        return True
    return any(writes_file(n, r) and any(hit(w) for w in written_words(n, r, cwd)) for n, r in commands)


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
    allowed = pause["allow_shell"][base_profile(profile)]
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
    if "auto_pause" in data:
        problems += auto_pause_problems(data["auto_pause"])
    if "review" in data:
        problems += review_problems(data["review"])
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
    # Monitor's command goes through PreToolUse hooks since Claude Code 2.1.314 (input field NOT_VERIFIED: command)
    shell_call = tool in SHELL_TOOLS and isinstance(command, str)
    shell = "powershell" if tool == "PowerShell" else "bash"
    # 2>&1 is dropped first: its & would otherwise split the line and leave "2>" looking like a redirect
    commands = list(simple_commands(FD_DUP.sub(" ", command), shell)) if shell_call else []
    line_targets = redirect_targets(command, shell) if shell_call else []
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
    if tool in WRITE_TOOLS and target in guarded or self_write(commands, names, line_targets):
        hits.append((SELF_RULE["decision"][base_profile(profile)], "G00", SELF_RULE["reason"]))
    for rule in data["rules"]:
        decision = rule_decision(rule, profile)
        if decision == "none":
            continue
        for m in as_list(rule["match"]):
            if (m["kind"] == "shell" and any(shell_match(m, n, r, cwd, home) for n, r in commands)
                    or m["kind"] == "path" and path_match(m, tool, targets, home)
                    or m["kind"] == "path" and m.get("shell_write") and shell_write_match(m, commands, line_targets, cwd, home, command if shell_call else "")
                    or m["kind"] == "mcp" and mcp_match(m, action, read_only)):
                hits.append((decision, rule["id"], rule["reason"]))
                break
    return hits


def first(hits, decision):
    """The hit with the lowest id among those with this decision, or None."""
    found = sorted((h for h in hits if h[0] == decision), key=lambda h: int(h[1][1:]))
    return found[0] if found else None


def audit(log, call, decision, rule):
    """Add a decision line to the action log; any failure is ignored so the decision stays the same."""
    if not log:
        return
    try:
        spec = importlib.util.spec_from_file_location("audit_log", pathlib.Path(__file__).with_name("audit_log.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.append_entry(module.expand(log), module.decision_entry(call, decision, rule))
    except Exception:  # noqa: BLE001 - the log is a record, never a reason to block or allow
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--protect", action="append", default=[], help="DIRECTOR folder whose orders/ and DIRECTOR_LOG.md Write / Edit may not touch")
    ap.add_argument("--rules", help="rules file (tools/guard_rules.json): check every tool call against it")
    ap.add_argument("--profile", choices=SESSION_PROFILES, default="worker", help="which decision of each rule applies (default worker)")
    ap.add_argument("--pause-flag", help="flag file (pause_ctl.py on): while it exists, deny what the rules' pause section does not allow")
    ap.add_argument("--review", action="store_true", help="show asks of the rules' review categories to a second model "
                    "first; it can only turn an ask into a deny (uses claude -p quota)")
    ap.add_argument("--audit", help="action log (audit_log.py): add a decision line for every deny, ask, remind and pause")
    ap.add_argument("--sessions", help="sessions file: the profile per session_id (director / worker / cleaner) and "
                    "the protected list; --profile is the fallback for a session it does not name (needs --rules)")
    ap.add_argument("--mode", choices=MODES, default="remind", help="what a flagged call gets: remind (default; it "
                    "runs, with a one-line reminder), ask (the user decides) or block (exit 2; explicit opt-in)")
    a = ap.parse_args()
    data = sessions = None
    if a.sessions and not a.rules:
        print("hook_guard: --sessions needs --rules", file=sys.stderr)
        return 1
    if a.rules:
        try:
            data = load_rules(a.rules)
            if a.pause_flag and "pause" not in data:
                raise RulesError(f"{a.rules}: --pause-flag needs a pause section")
            sessions = load_sessions(a.sessions) if a.sessions else None
        except RulesError as error:
            print(f"hook_guard: bad {'sessions' if a.sessions and data else 'rules'} file: {error}", file=sys.stderr)
            return 1
    elif a.pause_flag:
        print("hook_guard: --pause-flag needs --rules", file=sys.stderr)
        return 1
    if a.review and (data is None or "review" not in data):
        print("hook_guard: --review needs --rules with a review section", file=sys.stderr)
        return 1
    try:
        call = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(call, dict):
        return 0
    original = call
    if (call.get("tool_name") in ("Bash", "Monitor") and isinstance(call.get("tool_input"), dict)
            and isinstance(call["tool_input"].get("command"), str)):
        # a here-document body is data: every check below sees the line without it; the log keeps the call as sent
        call = dict(call, tool_input=dict(call["tool_input"], command=strip_heredocs(call["tool_input"]["command"])))
    if sessions is not None:
        a.profile = session_profile(sessions, call, a.profile)
    # one settings file serves every session of a launch folder: the Director is never held by the workers' pause
    paused = pause_state(a.pause_flag) if a.pause_flag and not (sessions is not None and a.profile == "director") else None
    if paused and not pause_allows(data, a.profile, call):
        print(f"PAUSED by {paused[0]} at {paused[1]}: {paused[2]}; {data['pause']['reason']}", file=sys.stderr)
        audit(a.audit, original, "pause", "PAUSE")
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
    label = "builtin"
    if not why and sessions is not None and isinstance(command, str) and call.get("tool_name") in SHELL_TOOLS:
        shell = "powershell" if call.get("tool_name") == "PowerShell" else "bash"
        cwd = call.get("cwd") if isinstance(call.get("cwd"), str) else None
        why = protected_delete(data, list(simple_commands(FD_DUP.sub(" ", command), shell)), cwd, sessions.get("protected", []))
        label = "protected" if why else label
    hits = decide(data, a.profile, call, a.rules) if data is not None else []
    deny, ask = first(hits, "deny"), first(hits, "ask")
    reviewed = None
    if a.mode != "block" and (deny or why or ask):
        rule, text = (deny[1], deny[2]) if deny else (label, why) if why else (ask[1], ask[2])
        if a.mode == "ask":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                                     "permissionDecisionReason": f"[{rule}] {text}"}}))
        else:
            line = f"hook_guard reminder [{rule}]: {text}"
            print(json.dumps({"systemMessage": line, "hookSpecificOutput": {
                "hookEventName": "PreToolUse", "additionalContext": line + REMIND_NOTE}}))
        audit(a.audit, original, a.mode, rule)
        return 0
    if ask and not deny and not why and a.review and not os.environ.get("DW_HOOK_REVIEW"):
        category = next((r.get("category") for r in data["rules"] if r.get("id") == ask[1]), None)
        if category in data["review"]["categories"]:
            reviewed = review(data["review"], original, ask[1], ask[2])
            if reviewed[0] == "block":
                deny = ("deny", ask[1], f"second-model review: {reviewed[1]}")
    if deny or why:
        rule = deny[1] if deny else label
        print(f"BLOCKED by hook_guard [{deny[1]}]: {deny[2]}" if deny else f"BLOCKED by hook_guard: {why}", file=sys.stderr)
        audit(a.audit, original, "deny", rule + (f" review={reviewed[0]} via={reviewed[2]}" if reviewed else ""))
        conf = ((data.get("auto_pause") or {}).get(base_profile(a.profile)) if a.pause_flag and data is not None and not paused
                and not (sessions is not None and a.profile == "director") else None)
        paused_now = auto_pause(a.pause_flag, conf, rule)
        if paused_now:
            print(f"AUTO-PAUSED by hook_guard: {paused_now}; stop here, report where you stopped and wait for the Director"
                  " (pause_ctl.py off lifts it)", file=sys.stderr)
            audit(a.audit, original, "pause", "AUTO")
        return 2
    if ask:
        note = "" if not reviewed else (f" (second-model review: no objection: {reviewed[1]})" if reviewed[0] == "no_objection"
                                        else f" (second-model review unavailable: {reviewed[1]})")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                                 "permissionDecisionReason": f"[{ask[1]}] {ask[2]}{note}"}}))
        audit(a.audit, original, "ask", ask[1] + (f" review={reviewed[0]} via={reviewed[2]}" if reviewed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
