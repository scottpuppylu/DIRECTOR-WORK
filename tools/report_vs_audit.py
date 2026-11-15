"""Check the commands a TASK REPORT says were run against the action log (audit_log.py) of the same session: was each
one run, did it end the way the report says, and at the time it says. Only reads. For the Director's gate review.

  report_vs_audit.py --report REPORT.md --log AUDIT.jsonl [--log ...] [--session ID] [--tolerance-min 10]
  report_vs_audit.py --lead GATE_VERDICT.md --lead DIRECTOR_LOG.md --log AUDIT.jsonl [--repo DIR] [--session ID]

Claims come from two places in the report:
  RAN: lines, one claim each (also as a list under a RAN: field):
      RAN: `python -I -X utf8 tools/selftest.py` exit=0 at=2026-11-07T19:40+08:00
      - `mcp__UnityMCP__run_tests` exit=0
    exit= and at= are optional; at= takes an ISO time with an offset, or HH:MM (that day in the report's own offset
    is not known, so HH:MM is compared on the clock of the log's UTC time plus --utc-offset, default the local one).
  inline `code` in the TESTS:, EVIDENCE: and DONE: fields that looks like a run of a selftest, Unity, Blender or a hash
    check (selftest.py, Unity.exe / -batchmode / mcp__UnityMCP__*, blender / mcp__blender__*, sha256sum, Get-FileHash,
    certutil -hashfile, gate_check.py --hash, evidence_record.py). The same line's "exit=N" / "exit N" sets the exit;
    PASS / OK / 通過 there means exit 0.

The session is --session, else the report's SESSION_ID: line, else the only session_id in the logs (else exit 2).
A shell claim matches a Bash / PowerShell line of that session whose command holds the claimed command (spaces, quotes,
case and slash direction aside; a line cut at 500 characters matches on its first part); an mcp__ claim matches the
tool name. Since 2.2.1 the command of a cut line is decoded like the JSON string it is (escaped quotes and
backslashes put back, so a long Windows command still matches), a leading & / cmd /c and a python / node / pwsh launcher
with its startup flags (-I -X utf8 ...) are dropped from both sides, and the claim's words may also be found in order
on a run of the log's words: "..." or "<name>" skips any number of words and a file name or path matches a longer path
that ends with it; this word match needs at least 2 claim words that are not "..." / "<name>". The log does not hold
exit codes: exit 0 must meet a "result" line with status ok, another exit a "failure" line. When at= is given the
matching line must lie within --tolerance-min minutes of it. A log rebuilt from a transcript (transcript_audit.py,
first line kind=rebuild) is read the same way; a note says so.

2.2.3: a new line, ;, && and || split a command into statements on both sides (the launcher is dropped in each), so a
claim of several statements matches a multi-line script (heredoc, multi-line python -c, PowerShell here-string) that
holds them in that order; at= ends at the time (at=13:17 followed by a note is 13:17); a full-width （note） in the
claim is left out; a claim that names several IDs in one word (AC-1/AC-2/AC-4, AC-1/2/4, AC-1..AC-5) needs one run per
ID. A claim that leaves parts out ("...", "x...", a CJK-only word such as 同上) may also skip the log's options (-x /
--x and one value), "x..." matches a word that starts with x, and a bare name matches a file name that starts with it
and goes on with - _ or . ; a cut log line also matches when at least 3 claim words reach its end. Of the matching
runs the one nearest at= (else the last) is shown; when no run ended as claimed and that run goes on with other
statements after the claimed one, its status is theirs, so the exit is "not checkable" (OK with a note). Shadow WARN
lines (the exit code is not changed): a RAN list line with no `command`, and a report that says SCOPE_CHECK PASS while
the agent that ran its commands made its last commit after its last scope_check.py run.

2.2.4: variables are put back before the match: an assignment earlier in the same call or in an earlier call of the same
agent in the session (X=v / export X=v, $x = 'v' / "v" / @'...'@ here-string, $env:X = v, set X=v) gives $X, ${X},
$env:X and %X% their value; a variable with no value found (and a cut last word that starts with $) stands for any
text inside its word. "git -C DIR x" is read as "cd DIR ; git x"; ； also ends a statement. Inside a word, "..." / "…"
stands for any text (.../repo matches d:/w/repo, D:/.../x.py a longer path), a short hex word (7+) matches a longer
hex word that starts with it, an absolute claimed path matches a relative logged one it ends with, and a word between
two CJK-only words is left out with them. at= takes HH:MM:SS and a span HH:MM–HH:MM (the span is added to the
tolerance). A ``` fence opened before RAN: and closed after it is not a RAN block. A claim of several statements that
no single call holds may be found statement by statement in calls in time order (OK with a note). A claim not found
in any call is UNVERIFIED (in log cut part) when a call cut at the log's input limit lies within at= (any time when
at= is not given) and another command of the same report matched that cut call: the claim may sit in its cut part, so
the log can neither show it ran nor show it did not. UNVERIFIED is its own status, not OK: it is counted apart
(unverified=n) and does not change the exit code. A claim found in the part of a cut call that the log kept is OK. A
call of a harness tool the log maps (tool_raw) whose status in this session is never error does not carry the exit
code, so a claimed exit other than 0 is "not checkable" there.

2.2.5: at= also takes a span with a full-width ～ / 〜 (at=00:30～00:31). --tolerance-min defaults to 10. Before the
match a statement that only sets TEMP / TMP / TMPDIR / PYTHONIOENCODING / PYTHONUTF8 (TEMP=x, export / set TEMP=x,
$env:TEMP = 'x') is left out on both sides, and so are those assignments in front of a command (TEMP=x python ...,
env TEMP=x ...). A log call's relative paths are also read against its folder: the input's "workdir" / "cwd" field and
a cd / Set-Location / pushd earlier in the same call (tools/x.py run in D:/w/DIRECTOR is D:/w/DIRECTOR/tools/x.py, so
the claim DIRECTOR/tools/x.py matches); a word counts as a path when it holds a /, ends with a file extension, or is
the value of an option named ...dir / path / file / repo / cwd / out / root / folder / log / report / order. A claim
of one statement may leave out options the log statement has (OK with a note naming them), unless a left-out option
can weaken the run (-f -n -k --force --warn --dry-run --no-... --skip... --allow... --ignore... --quick --only and the
like). A log line rebuilt with "input_cut": true (transcript_audit.py build --input-limit) is a cut line. Each FAIL
names its class (類別：沒跑 / 時間不符 / 結束碼不符 / 格式); a claim not run whose at= has a call starting with the same
two words gets that call as a hint. --lead FILE (repeatable) checks files the lead writes itself (GATE_VERDICT,
DIRECTOR_LOG): their RAN lines as claims, and every line that starts with a stamp YYYY-MM-DD HH:MM against the earliest
logged call whose input holds that line (the time it was written): a stamp more than 1 minute after that call, or more
than --tolerance-min before it, is a FAIL (時間不符); with --repo a stamped line that names a commit (a word with COMMIT
and a 7+ hex word) is also compared with that commit's time. Lines found in no call are counted (stamps_unfound=n).

Prints OK / UNVERIFIED / FAIL per claim, WARN lines, and a last line
  REPORT_VS_AUDIT: PASS|FAIL|NONE claims=n ok=n failed=n session=ID logs=n unverified=n time_mismatch=n not_run=n
  (2.2.5: --lead adds stamps=n stamps_unfound=n)
exit 1 on any FAIL or a broken hash chain, 0 on PASS or NONE (no claims found), 2 when it cannot run. UNVERIFIED
claims never fail the run.
"""
import argparse
import collections
import datetime
import functools
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

SHELL_TOOLS = frozenset(("bash", "powershell", "pwsh"))  # compared lower-case
LAUNCHER = re.compile(r"(?:^|/)(?:python(?:\d+(?:\.\d+)*)?|py|node|pwsh|powershell)(?:\.exe)?$", re.I)
STARTUP = frozenset(("-i", "-x", "-u", "-b", "-e", "-s", "-o", "-oo", "-v", "-q", "utf8", "-utf8", "-noprofile",
                     "-noninteractive", "-nologo", "-noexit", "-command", "-commandwithargs", "-inputformat",
                     "-outputformat", "-windowstyle", "-version"))
WILDCARD = re.compile(r"^(?:\.{2,}|…|<[^<>]+>)$")
MIN_WORDS = 2  # a word match needs this many claim words that are not wildcards
CUT_WORDS = 3  # 2.2.3: a cut log line matches when this many claim words reach its end
PLACEHOLDER = re.compile(r"^[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f]+$")  # a CJK-only word (同上) stands for words left out
ELLIPSIS_END = re.compile(r"^(.{2,}?)(?:\.{3,}|…)$")  # 427fcef... : a word given by its start
SEPARATOR = re.compile(r"\r?\n|\r|;|&&|\|\|")  # 2.2.3: these end a statement (2.2.4: norm() reads ； as ;)
ANNOTATION = re.compile(r"（[^（）]*）")  # a full-width note inside a claimed command
ID_LIST = re.compile(r"^([A-Z][A-Z0-9]*-)(\d+)((?:/(?:[A-Z][A-Z0-9]*-)?\d+)+)$")  # AC-1/AC-2/AC-4, AC-1/2/4
ID_RANGE = re.compile(r"^([A-Z][A-Z0-9]*-)(\d+)\.\.(?:[A-Z][A-Z0-9]*-)?(\d+)$")  # AC-1..AC-5
MAX_IDS = 30
COMMIT = re.compile(r"\bgit\b(?:\s+-[Cc]\s+\S+)*\s+commit\b")
SCOPE_RUN = re.compile(r"scope_check\.py", re.I)
SCOPE_PASS = re.compile(r"^[ \t]*SCOPE_CHECK[ \t]*:.*\bPASS\b", re.M)
FENCE = re.compile(r"^[ \t]*(?:-[ \t]+)?```")
JSON_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
CLAIM_FIELDS = ("TESTS", "EVIDENCE", "DONE")
KINDS = [
    ("selftest", re.compile(r"selftest\.py", re.I)),
    ("unity", re.compile(r"unity(?:\.exe)?\b.*-batchmode|-batchmode|\bunity\.exe\b|mcp__unitymcp__", re.I)),
    ("blender", re.compile(r"\bblender(?:\.exe)?\b|mcp__blender__", re.I)),
    ("hash", re.compile(r"sha256sum|get-filehash|certutil\s+-hashfile|gate_check\.py\s+--hash|evidence_record\.py", re.I)),
]
EXIT = re.compile(r"\bexit(?:\s*code)?\s*[=:]?\s*(-?\d+)\b", re.I)
AT = re.compile(r"\bat=([^\s（(，,；;]+)")  # 2.2.3: stops before a full-width note, e.g. at=13:28（重跑）
PASS_WORD = re.compile(r"\b(?:[Pp][Aa][Ss][Ss](?:[Ee][Dd])?|OK)\b|通過")
FIELD = re.compile(r"^[ \t]*([A-Z][A-Z_]+)[ \t]*:[ \t]?(.*)$")
MARK = "\x00"  # 2.2.4: a variable with no value found, inside a word: any text
VAR_REF = re.compile(r"\$\{(\w+)\}|\$env:(\w+)|\$(\w+)|%(\w+)%", re.I)
HERE_STRING = re.compile(r"\$(\w+)[ \t]*=[ \t]*@(['\"])[ \t]*\r?\n(.*?)\r?\n[ \t]*\2@", re.S)
STATEMENT_END = re.compile(r"(\r?\n|\r|;|&&|\|\|)")
# 2.2.5: a shell function, name(){ body; } or function name { body; } (the } after ; or a new line)
FUNCTION_DEF = re.compile(r"(?:^|(?<=[\n;&|]))[ \t]*(?:function[ \t]+([A-Za-z_][\w-]*)(?:[ \t]*\(\))?|([A-Za-z_][\w-]*)[ \t]*\(\))[ \t]*\{(.*?)(?:;|\n)[ \t]*\}", re.S)
CALL_LEAD = re.compile(r"^([ \t]*(?:(?:do|then|else|\{|\()[ \t]+)?)([A-Za-z_][\w-]*)(?=[ \t]|$)(.*)$", re.S)
POSITIONAL = re.compile(r"\"\$[@*]\"|\$[@*]|\$\{(\d+)\}|\$(\d)|\$#")
SHELL_WORD = re.compile(r"\"[^\"]*\"|'[^']*'|\S+")
FUNCTION_KEY = "()"  # 2.2.5: env key prefix of a shell function (never a variable name)
BASH_SET = re.compile(r"^(?:export\s+)?([A-Za-z_]\w*)=(\"[^\"]*\"|'[^']*'|\S*)$")
PS_SET = re.compile(r"^\$(?:env:)?(\w+)\s*=(?!=)\s*(.+)$", re.I | re.S)
CMD_SET = re.compile(r'^set\s+"?(\w+)=(.*?)"?$', re.I)
GIT_C = re.compile(r"\bgit\s+-C\s+(\"[^\"]*\"|'[^']*'|\S+)\s+")
HEX = re.compile(r"[0-9a-f]{7,64}")
INNER_GAP = re.compile(r"\.{3,}|…|\x00")  # 2.2.4: inside a word, any text
ID_SPACED = re.compile(r"\b([A-Z][A-Z0-9]*-\d+)[ \t]+\.\.[ \t]+((?:[A-Z][A-Z0-9]*-)?\d+)\b")  # AC-1 .. AC-6
CLOCK = r"\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
AT_SPAN = re.compile(rf"({CLOCK})\s*[–—~～〜-]\s*({CLOCK})")  # 2.2.5: full-width ～ / 〜
NEUTRAL_ENV = frozenset(("temp", "tmp", "tmpdir", "pythonioencoding", "pythonutf8"))  # 2.2.5: left out before the match
ENV_WORD = re.compile(r"^([a-z_]\w*)=\S*$")
MSYS_DRIVE = re.compile(r"(^|=)/([a-z])/")  # 2.2.5: Git Bash /d/x is d:/x (after norm(): lower case)
PS_ENV = re.compile(r"^\$env:(\w+)\s*=")
PATH_OPTION = re.compile(r"^--?[\w-]*(?:dir|path|file|repo|cwd|out|root|folder|log|report|order)$")
CD_WORDS = frozenset(("cd", "chdir", "pushd", "set-location", "sl"))
RISKY_OPTION = re.compile(r"^--?(?:f|n|k|force|warn|dry-run|no-[\w-]+|skip[\w-]*|allow[\w-]*|ignore[\w-]*|unsafe|lenient|"
                          r"lax|loose|shadow|bypass[\w-]*|override[\w-]*|keep-going|continue[\w-]*|only|select|exclude|"
                          r"filter|quick|fast|partial|sample|limit|max[\w-]*|tolerance[\w-]*)$")
STAMP = re.compile(r"^[ \t]*(?:[-*][ \t]+)?(\d{4}-\d{2}-\d{2})[ T](\d{1,2}:\d{2})(?::\d{2})?(?![\d:])")
STAMP_AHEAD_MIN = 1  # 2.2.5: a stamp may be this many minutes after the call that wrote it (minute rounding)
STAMP_COMMIT = re.compile(r"[A-Z_]*COMMIT")
STAMP_HEX = re.compile(r"\b[0-9a-f]{7,40}\b")


def load_audit():
    spec = importlib.util.spec_from_file_location("audit_log", pathlib.Path(__file__).with_name("audit_log.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def kind_of(command):
    return next((name for name, pattern in KINDS if pattern.search(command)), None)


def claim_from(line, command, explicit):
    exit_found = EXIT.search(line.replace(command, " ")) if command in line else EXIT.search(line)
    if exit_found:
        code = int(exit_found.group(1))
    elif PASS_WORD.search(line.replace(command, " ")):
        code = 0
    else:
        code = None
    at = AT.search(line)
    return {"command": command.strip(), "kind": kind_of(command) or "command", "exit": code,
            "at": at.group(1) if at else None, "explicit": explicit, "line": line.strip()}


def claims(text):
    """[claim] from RAN: lines and the inline code of the TESTS / EVIDENCE / DONE fields."""
    return parse(text)[0]


def parse(text):
    """([claim], [RAN list line with no `command`]). 2.2.3: a ``` block opened under RAN: is one claim of several lines;
    its exit= / at= go after the closing ```."""
    out, loose, field, block, outer = [], [], None, None, False
    for line in text.splitlines():
        if block is None and FENCE.match(line) and not FIELD.match(line) and (outer or field != "RAN"):
            outer = not outer  # 2.2.4: a fence opened outside RAN: (even one that holds RAN:) is not a RAN block
            if not outer:
                field = None
            continue
        if block is not None:
            closing = re.match(r"^[ \t]*```(.*)$", line)
            if closing:
                command = "\n".join(part.strip() for part in block if part.strip())
                if command:
                    out.append(claim_from(closing.group(1), command, True))
                block = None
            else:
                block.append(line)
            continue
        if field == "RAN" and FENCE.match(line) and not FIELD.match(line):
            block = []
            continue
        found = FIELD.match(line)
        if found:
            field, rest = found.group(1), found.group(2)
        else:
            rest = line
        if field == "RAN":
            commands = re.findall(r"`([^`]+)`", rest)
            for command in commands:
                out.append(claim_from(rest, command, True))
            if not commands and re.match(r"^[ \t]*-[ \t]+\S", rest):
                loose.append(rest.strip())
        elif field in CLAIM_FIELDS:
            for command in re.findall(r"`([^`]+)`", rest):
                if kind_of(command):
                    out.append(claim_from(rest, command, False))
    seen, unique = set(), []
    for c in out:
        key = (c["command"], c["exit"], c["at"])
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique, loose


def norm(text):
    """Slashes one way, quotes out, spaces collapsed, lower case; 2.2.3: a statement end (new line, ;, &&, ||) is the
    word ";" (never two in a row, none at the start or end)."""
    text = text.replace("；", ";").replace("\\\\", "/").replace("\\", "/").replace('"', "").replace("'", "")
    out = []
    for word in re.sub(r"\s+", " ", SEPARATOR.sub(" ; ", text)).strip().lower().split(" "):
        if word and not (word == ";" and (not out or out[-1] == ";")):
            out.append(word)
    while out and out[-1] == ";":
        out.pop()
    return " ".join(out)


def json_string_prefix(text):
    """(decoded value, closed) of a JSON string body that may be cut; text starts after the opening quote. Escapes are
    put back (quote, backslash, slash, b f n r t, u and 4 hex digits), an escape cut at the end is dropped, and closed
    is True when the closing quote is there (what follows it is ignored)."""
    out, i = [], 0
    while i < len(text):
        char = text[i]
        if char == '"':
            return "".join(out), True
        if char != "\\":
            out.append(char)
            i += 1
            continue
        if i + 1 >= len(text):
            break  # cut in the middle of an escape
        code = text[i + 1]
        if code in JSON_ESCAPES:
            out.append(JSON_ESCAPES[code])
            i += 2
        elif code == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", text[i + 2:i + 6]):
            value = int(text[i + 2:i + 6], 16)
            low = re.fullmatch(r"\\u([dD][c-fC-F][0-9a-fA-F]{2})", text[i + 6:i + 12])
            if 0xD800 <= value < 0xDC00 and low:
                value = 0x10000 + ((value - 0xD800) << 10) + (int(low.group(1), 16) - 0xDC00)
                i += 6
            out.append(chr(value))
            i += 6
        elif code == "u":
            break  # \u cut short
        else:
            out.append(code)  # not valid JSON; keep the character
            i += 2
    return "".join(out), False


def shell_command(entry):
    """(command, cut) of a Bash / PowerShell log line (its input is the masked tool input as JSON, maybe cut at 500
    characters). 2.2.1: a cut line's command is decoded as the JSON string it is, so escaped quotes and backslashes are put back."""
    raw = entry.get("input") or ""
    try:
        value = json.loads(raw)
        return str(value.get("command", "")) if isinstance(value, dict) else raw, entry.get("input_cut") is True
    except ValueError:
        body = raw[:-1] if raw.endswith("…") else raw
        found = re.match(r'\{"command":\s*"', body)
        if not found:
            return body, raw.endswith("…")
        text, closed = json_string_prefix(body[found.end():])
        return text, not closed and raw.endswith("…")


def lookup(env, name):
    if name in env:
        return env[name]
    low = name.lower()
    return next((value for key, value in env.items() if key.lower() == low), None)


def unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def ps_value(expression, refs):
    """2.2.4: the value of a PowerShell right side made of quoted strings, variables and plain words joined by +; an
    expression it cannot read (a call, a pipe) is MARK."""
    pieces = re.findall(r"\"[^\"]*\"|'[^']*'|[^+\s]+|\+", expression.strip())
    out = []
    for piece in pieces:
        if piece == "+":
            continue
        if piece[0] == '"':
            out.append(refs(piece[1:-1]))
        elif piece[0] == "'":
            out.append(piece[1:-1])
        elif piece.startswith("$"):
            out.append(refs(piece))
        elif re.fullmatch(r"[\w.:/\\-]+", piece) and not piece.startswith("-"):
            out.append(piece)
        else:
            return MARK
    return "".join(out) if out else MARK


def functions(command, env):
    """2.2.5: the command with its shell function definitions taken out (kept in env under FUNCTION_KEY + name) and
    each call of a known function (a statement starting with its name, also after do / then / else) replaced by the
    function body with $1.., ${N}, $@, $* and $# filled in from the call's words (shift drops the first); one level,
    the words after a | or > of the call stay after the body."""
    def keep(found):
        env[FUNCTION_KEY + (found.group(1) or found.group(2))] = found.group(3)
        return ""

    command = FUNCTION_DEF.sub(keep, command)
    if not any(key.startswith(FUNCTION_KEY) for key in env):
        return command
    out = []
    for part in STATEMENT_END.split(command):
        found = CALL_LEAD.match(part) if part and not STATEMENT_END.fullmatch(part) else None
        body = found and env.get(FUNCTION_KEY + found.group(2))
        if body is None or found is None:
            out.append(part)
            continue
        words = SHELL_WORD.findall(found.group(3))
        cut = next((k for k, word in enumerate(words) if word[0] in "|><" or word[:2] in ("1>", "2>", "&>")),
                   len(words))
        args, rest = [unquote(word) for word in words[:cut]], words[cut:]
        lines = []
        for statement in STATEMENT_END.split(body):
            if not statement.strip() or STATEMENT_END.fullmatch(statement):
                continue
            shift = re.fullmatch(r"\s*shift(?:\s+(\d+))?\s*", statement)
            if shift:
                args = args[int(shift.group(1) or 1):]
                continue

            def fill(ref):
                if ref.group(0) == "$#":
                    return str(len(args))
                number = ref.group(1) or ref.group(2)
                if number is None:
                    return " ".join(args)
                return args[int(number) - 1] if 0 < int(number) <= len(args) else ""
            lines.append(POSITIONAL.sub(fill, statement).strip())
        out.append(found.group(1) + " ; ".join(lines) + (" " + " ".join(rest) if rest else ""))
    return "".join(out)


def expand(command, env=None):
    """2.2.4: (command with its variables put back, the variables after it). env holds earlier assignments; the
    command's own assignments (X=v, export X=v, $x = ..., $env:X = ..., set X=v, a here-string $x = @'...'@) count
    from the statement after them. $X, ${X}, $env:X and %X% with no value found become MARK (any text in the word)."""
    env = dict(env or {})
    command = functions(command, env)  # 2.2.5

    def refs(text):
        def one(found):
            value = lookup(env, next(group for group in found.groups() if group is not None))
            return MARK if value is None else value
        return VAR_REF.sub(one, text)

    out, pos, pieces = [], 0, []
    for found in HERE_STRING.finditer(command):
        pieces.append((command[pos:found.start()], None))
        pieces.append((found.group(0), (found.group(1), found.group(3))))
        pos = found.end()
    pieces.append((command[pos:], None))
    for text, here in pieces:
        if here:
            env[here[0]] = here[1]
            out.append(text)
            continue
        for part in STATEMENT_END.split(text):
            if not part or STATEMENT_END.fullmatch(part):
                out.append(part)
                continue
            statement = part.strip()
            name = next((found.group(1) for found in (BASH_SET.match(statement), CMD_SET.match(statement),
                                                      PS_SET.match(statement)) if found), None)
            if name and name.lower() in NEUTRAL_ENV:
                out.append(part)  # 2.2.5: kept as written, to be left out before the match
            else:
                out.append(refs(part))
            found = BASH_SET.match(statement)
            if found:
                env[found.group(1)] = unquote(refs(found.group(2)))
                continue
            found = CMD_SET.match(statement)
            if found:
                env[found.group(1)] = refs(found.group(2))
                continue
            found = PS_SET.match(statement)
            if found:
                env[found.group(1)] = ps_value(found.group(2), refs)
    return "".join(out), env


def expand_line(command, cut, env=None):
    """(expanded command, variables after it) of a log line; 2.2.4: a cut line whose last word starts with $ (its name
    may be cut short) ends with MARK there."""
    tail = ""
    if cut:
        last = re.search(r"\$[\w:{]*$", command)
        if last:
            command, tail = command[:last.start()], MARK
    expanded, env = expand(command, env)
    return expanded + tail, env


def command_of(entry):
    """(command, cut) of a shell log line with its variables put back (prepare() gives it the session's earlier
    assignments; without it only the call's own count)."""
    if "_command" in entry:
        return entry["_command"]
    command, cut = shell_command(entry)
    return expand_line(command, cut)[0], cut


def prepare(mine):
    """2.2.4: put back the variables of every shell line of the session, carrying assignments from call to call of
    the same agent (in seq order)."""
    envs = {}
    for entry in sorted(mine, key=lambda e: (e.get("seq") is None, e.get("seq") or 0)):
        if str(entry.get("tool") or "").lower() in SHELL_TOOLS:
            command, cut = shell_command(entry)
            agent = entry.get("agent_id")
            expanded, envs[agent] = expand_line(command, cut, envs.get(agent))
            entry["_command"] = (expanded, cut)


def canonical_command(command):
    """norm() with a leading & / ; / cmd /c and a python / node / pwsh launcher with its startup flags dropped; 2.2.3: in
    each statement, joined again by " ; ". 2.2.4: "git -C DIR x" is "cd DIR ; git x". 2.2.5: TEMP=x in front left out (drop_env), a
    Git Bash drive path /d/x read as d:/x."""
    statements = []
    for statement in norm(GIT_C.sub(lambda found: f"cd {found.group(1)} ; git ", command)).split(" ; "):
        parts = [part for part in statement.split(" ") if part]
        while parts and parts[0] in ("&", ";", "&&", "||"):
            parts.pop(0)
        parts = drop_env(parts)
        parts = [MSYS_DRIVE.sub(r"\1\2:/", part) for part in parts]
        if parts and (parts[0] == "cmd" or parts[0].endswith("/cmd.exe")):
            parts.pop(0)
            while parts and parts[0] in ("/c", "/k"):
                parts.pop(0)
        if parts and LAUNCHER.search(parts[0]):
            parts.pop(0)
            while parts and (parts[0] in STARTUP or re.fullmatch(r"-x\w+", parts[0])):
                parts.pop(0)
        if parts:
            statements.append(" ".join(parts))
    return " ; ".join(statements)


def drop_env(parts):
    """2.2.5: the words of one statement without TEMP=x / env TEMP=x in front; [] for a statement that only sets
    TEMP / TMP / TMPDIR / PYTHONIOENCODING / PYTHONUTF8 (TEMP=x, export TEMP=x, set TEMP=x, $env:TEMP = x)."""
    found = PS_ENV.match(" ".join(parts))
    if found and found.group(1) in NEUTRAL_ENV:
        return []
    start = 1 if parts and parts[0] in ("export", "set", "env") else 0
    end = start
    while end < len(parts) and ENV_WORD.match(parts[end]) and ENV_WORD.match(parts[end]).group(1) in NEUTRAL_ENV:
        end += 1
    if end == start:
        return parts
    if end == len(parts):
        return []
    return parts if parts[0] in ("export", "set") else parts[end:]


def cwd_of(entry):
    """2.2.5: the folder a log call ran in when its input names one ("workdir" / "cwd"), else None."""
    raw = entry.get("input") or ""
    try:
        value = json.loads(raw)
    except ValueError:
        found = re.search(r'"(?:workdir|cwd)":\s*"', raw)
        if not found:
            return None
        text, closed = json_string_prefix(raw[found.end():])
        return text if closed and text.strip() else None
    if isinstance(value, dict):
        return next((value[key] for key in ("workdir", "cwd") if isinstance(value.get(key), str)
                     and value[key].strip()), None)
    return None


def absolute(word):
    return word.startswith(("/", "~")) or re.match(r"^[a-z]:/", word) is not None


def join_path(base, word):
    """2.2.5: base/word with . and .. read (both already norm()ed)."""
    out = []
    for i, piece in enumerate((base.rstrip("/") + "/" + word).split("/")):
        if piece == "." or (piece == "" and i):
            continue
        if piece == ".." and out and out[-1] not in ("..", "") and not out[-1].endswith(":"):
            out.pop()
            continue
        out.append(piece)
    return "/".join(out)


def path_like(word, previous):
    """2.2.5: True for a relative word that names a path: it holds a /, ends with a file extension, or is the value of
    a path option (--repo bills, --evidence-dir evidence)."""
    if (not word or word == ";" or word.startswith(("-", "$", MARK)) or "://" in word or "=" in word
            or INNER_GAP.search(word) or skips(word) or absolute(word)):
        return False
    if "/" in word or word in (".", ".."):
        return True
    if re.search(r"[^./]\.[a-z0-9]{1,5}$", word) and not re.fullmatch(r"[\d.]+", word):
        return True
    return bool(previous and PATH_OPTION.match(previous))


def resolve(have, cwd):
    """2.2.5: a canonical log command with its relative paths read against the call's folder (cwd, norm()ed or None)
    and the cd / Set-Location / pushd statements before them; the same text when nothing changes."""
    base, out = cwd, []
    for statement in have.split(" ; "):
        words = statement.split(" ")
        if words[0] in CD_WORDS and len(words) > 1 and not words[1].startswith("-"):
            base = words[1] if absolute(words[1]) else (join_path(base, words[1]) if base else None)
            out.append(statement)
            continue
        if base:
            words = [join_path(base, word) if path_like(word, words[k - 1] if k else None) else word
                     for k, word in enumerate(words)]
        out.append(" ".join(words))
    return " ; ".join(out)


def log_forms(entry, command, have=None):
    """2.2.5: the canonical log command (have), then (when it differs) the same with its relative paths resolved."""
    have = canonical_command(command) if have is None else have
    cwd = cwd_of(entry)
    resolved = resolve(have, norm(cwd) if cwd else None)
    return [have] if resolved == have else [have, resolved]


@functools.lru_cache(maxsize=4096)
def word_pattern(word):
    """2.2.4: a word holding "..." / "…" / MARK as a regex (those parts any text; a leading part may also be a longer
    path), else None."""
    parts = INNER_GAP.split(word)
    if len(parts) == 1 or (len(parts) == 2 and not parts[1] and MARK not in word):
        return None  # none, or only at the end: x... is short_word()'s (2.2.3)
    return re.compile("(?:.*/)?" + ".*".join(re.escape(part) for part in parts), re.S)


def same_word(claim_word, log_word):
    """Equal, or the log word is a longer path that ends with the claim word (tools/x.py matches d:/w/tools/x.py).
    2.2.4: "..." / "…" / MARK inside either word is any text; a hex word of 7+ matches a longer hex word that starts
    with it; an absolute claimed path matches a relative logged path it ends with."""
    if loose_word(claim_word, log_word):
        return True
    return claim_word == log_word or log_word.endswith("/" + claim_word.lstrip("/"))


def loose_word(claim_word, log_word):
    """2.2.4 part of same_word()."""
    pattern = word_pattern(claim_word)
    if pattern is not None and pattern.fullmatch(log_word):
        return True
    pattern = word_pattern(log_word)
    if pattern is not None and pattern.fullmatch(claim_word):
        return True
    if HEX.fullmatch(claim_word) and HEX.fullmatch(log_word) and log_word.startswith(claim_word):
        return True
    return ("/" in log_word and not log_word.startswith(("/", ".", "-")) and re.match(r"^(?:[a-z]:)?/", claim_word)
            is not None and claim_word.endswith("/" + log_word))


def short_word(claim_word, log_word):
    """2.2.3, only for a claim that leaves parts out: "427fcef..." matches a word (or a file name) that starts with
    427fcef; a bare name of 3+ characters (wo-003) matches a file whose name starts with it and goes on with - _ or .
    (d:/w/orders/wo-003-expression.md)."""
    base = log_word.rsplit("/", 1)[-1]
    found = ELLIPSIS_END.match(claim_word)
    if found:
        return log_word.startswith(found.group(1)) or base.startswith(found.group(1))
    if len(claim_word) < 3 or "/" in claim_word or claim_word.startswith("-"):
        return False
    return base.startswith(claim_word) and len(base) > len(claim_word) and base[len(claim_word)] in "-_."


def skips(word):
    """A claim word that stands for any number of log words: "...", "…", "<name>", 2.2.3 a CJK-only word (同上)."""
    return bool(WILDCARD.match(word) or PLACEHOLDER.match(word))


def leaves_out(claim):
    """2.2.3 / 2.2.4: True when the claim leaves parts out ("...", <name>, 同上, x..., or "..." inside a word)."""
    return any(skips(word) or ELLIPSIS_END.match(word) or "..." in word or "…" in word for word in claim)


def fold(claim):
    """2.2.4: a word between two CJK-only words (複製 w3 三檔後) is left out with them."""
    return [word for i, word in enumerate(claim)
            if not (0 < i < len(claim) - 1 and PLACEHOLDER.match(claim[i - 1]) and PLACEHOLDER.match(claim[i + 1])
                    and not skips(word) and word != ";")]


def word_match(claim, log, cut=False, short=None, least=MIN_WORDS):
    """True when the claim words sit, in order, on a run of the log words; "..." / "<name>" skip any number of words.
    Needs MIN_WORDS claim words that are not wildcards, so a claim made mostly of wildcards proves nothing.
    2.2.3: a claim ";" skips to the end of a log statement; a claim that leaves parts out may skip log options and
    match short words (short_word); a cut log line (cut=True) matches when CUT_WORDS claim words reach its end (its
    last word may be cut short). 2.2.4: short=True / False says whether the claim leaves parts out (default: from
    its words); least is the number of claim words needed (MIN_WORDS)."""
    if sum(1 for word in claim if not skips(word) and word != ";") < least or not log:
        return False
    short = leaves_out(claim) if short is None else short
    long_enough = len(" ".join(log)) >= 40
    cache = {}

    def walk(ci, li, n):
        if ci == len(claim):
            return True
        key = (ci, li, n)
        if key in cache:
            return cache[key]
        word = claim[ci]
        if skips(word):
            found = any(walk(ci + 1, skip, n) for skip in range(li, len(log) + 1))
        elif li >= len(log):
            found = cut and long_enough and n >= CUT_WORDS  # the line was cut before the rest of the claim
        elif word == ";":
            found = (any(walk(ci + 1, k + 1, n) for k in range(li, len(log)) if log[k] == ";")
                     or (cut and walk(ci + 1, len(log), n)))
        else:
            up = min(n + 1, CUT_WORDS)
            found = (same_word(word, log[li]) or (short and short_word(word, log[li]))) and walk(ci + 1, li + 1, up)
            if not found and cut and long_enough and n >= CUT_WORDS and li == len(log) - 1 and word.startswith(log[li]):
                found = walk(ci + 1, li + 1, up)  # the last word of a cut line, cut short (does not count as a word)
            if not found and short and log[li].startswith("-"):
                found = walk(ci, li + 1, n) or (li + 1 < len(log) and log[li + 1] != ";" and walk(ci, li + 2, n))
        cache[key] = found
        return found

    return any(walk(0, start, 0) for start in range(len(log)))


def matches(claim, entry, short=None, subset=True):
    """2.2.5: also against the log command with its relative paths resolved (log_forms), and (subset=True) a claim
    that leaves out options the log statement has that cannot weaken the run (left_out)."""
    if claim["command"].startswith("mcp__"):
        return entry.get("tool") == claim["command"].split()[0]
    if str(entry.get("tool") or "").lower() not in SHELL_TOOLS:
        return False
    command, cut = command_of(entry)
    want, have = canonical_command(claim["command"]), canonical_command(command)
    if not want:
        return False
    if any(matches_form(claim, want, form, command, cut, short) for form in log_forms(entry, command, have)):
        return True
    return subset and left_out(claim, entry, short) is not None


def matches_form(claim, want, have, command, cut, short):
    """The 2.2.4 match of the canonical claim (want) against one form of the canonical log command (have)."""
    if want in have or (cut and len(have) >= 40 and want.startswith(have)):
        return True
    words = fold(want.split(" "))
    if sum(1 for word in words if not skips(word) and word != ";") < MIN_WORDS:
        # 2.2.4: too short without its launcher (python -c "..."): compare with the launcher kept
        launched = norm(GIT_C.sub(lambda found: f"cd {found.group(1)} ; git ", claim["command"])).split(" ")
        return word_match(fold(launched), norm(command).split(" "), cut, short)
    return (word_match(words, have.split(" "), cut, short)
            or any_order(words, have.split(" "), leaves_out(words) if short is None else short))


def left_out(claim, entry, short=None):
    """2.2.5: [options of the log statement the claim leaves out] when that is the only difference and none of them
    can weaken the run, else None (shell calls only). Only for a whole claim (one that leaves parts out with "..."
    already skips log options, 2.2.3) whose options are in the log's order (a claim in another order names every
    option, 2.2.4)."""
    if claim["command"].startswith("mcp__") or str(entry.get("tool") or "").lower() not in SHELL_TOOLS:
        return None
    command = command_of(entry)[0]
    words = fold(canonical_command(claim["command"]).split(" "))
    if leaves_out(words) if short is None else short:
        return None
    short = False
    for have in log_forms(entry, command):
        found = omitted_options(words, have.split(" "), short)
        if found:
            return found
    return None


def omitted_options(claim, log, short):
    """2.2.5: [left-out option names] when a one-statement claim's head, tail (after --) and options sit on one log
    statement (options in any order) and the log statement has more options, none of them RISKY_OPTION; else None."""
    if ";" in claim or sum(1 for word in claim if not skips(word)) < MIN_WORDS:
        return None
    head, options, tail = groups(claim)
    statement = []
    for word in log + [";"]:
        if word != ";":
            statement.append(word)
            continue
        log_head, log_options, log_tail = groups(statement)
        statement = []
        if not head or not same_run(head, log_head, short) or not same_run(tail, log_tail, short):
            continue
        used = []
        for option in options:
            hit = next((k for k, other in enumerate(log_options) if k not in used and same_run(option, other, short)),
                       None)
            if hit is None:
                break
            used.append(hit)
        else:
            if used != sorted(used):
                continue
            left = [log_options[k][0] for k in range(len(log_options)) if k not in used]
            if left and not any(RISKY_OPTION.match(name) for name in left):
                return left
    return None


def groups(words):
    """2.2.4: (head words, [option with its values], words after --) of one statement."""
    main, tail = (words[:words.index("--")], words[words.index("--") + 1:]) if "--" in words else (words, [])
    head, options = [], []
    for word in main:
        if word.startswith("-") and len(word) > 1:
            options.append([word])
        elif options:
            options[-1].append(word)
        else:
            head.append(word)
    return head, options, tail


def same_run(claim, log, short):
    """2.2.4: the claim words are the log words (word by word), or, for a claim that leaves parts out, sit on them."""
    if not claim:
        return not log or short
    if len(claim) == len(log) and all(same_word(a, b) or (short and short_word(a, b)) for a, b in zip(claim, log)):
        return True
    return bool(short) and word_match(claim, log, short=True, least=1)


def any_order(claim, log, short):
    """2.2.4: a one-statement claim whose options (each with its values) are those of one log statement in another
    order: the same words before the first option and after --, every claimed option in the statement; a claim that
    does not leave parts out must name all of the statement's options. Only for options in another order."""
    if ";" in claim or sum(1 for word in claim if not skips(word)) < MIN_WORDS:
        return False
    head, options, tail = groups(claim)
    if not options:
        return False
    statement = []
    for word in log + [";"]:
        if word != ";":
            statement.append(word)
            continue
        log_head, log_options, log_tail = groups(statement)
        statement = []
        if not same_run(head, log_head, short) or not same_run(tail, log_tail, short):
            continue
        used = []
        for option in options:
            hit = next((k for k, other in enumerate(log_options) if k not in used and same_run(option, other, short)),
                       None)
            if hit is None:
                break
            used.append(hit)
        else:
            if used != sorted(used) and (short or len(used) == len(log_options)):
                return True  # options in log order are word_match()'s (2.2.3)
    return False


def runs_more(claimed, entry):
    """2.2.3: True when the log call goes on with another statement after the claimed one; the call's status is then
    that statement's, so the claimed exit cannot be checked against it."""
    if str(entry.get("tool") or "").lower() not in SHELL_TOOLS:  # runs_more: shell calls only
        return False
    have = canonical_command(command_of(entry)[0]).split(" ")
    if ";" not in have:
        return False
    want = [word for word in canonical_command(claimed).split(" ") if word != ";" and not skips(word)]
    if not want:
        return True
    last = want[-1]
    hits = [i for i, word in enumerate(have) if same_word(last, word) or last in word or short_word(last, word)]
    return not hits or ";" in have[hits[-1] + 1:]


def variants(command):
    """2.2.3: the claimed command once per ID when one word names several (AC-1/AC-2/AC-4, AC-1/2/4, AC-1..AC-5); a
    full-width （note） is left out. The spaces and new lines between the words are kept (they end statements).
    2.2.4: also AC-1 .. AC-6 with spaces."""
    command = ID_SPACED.sub(r"\1..\2", command)
    words = re.split(r"(\s+)", ANNOTATION.sub(" ", command).strip())
    for i, word in enumerate(words):
        ids = None
        found = ID_LIST.match(word)
        if found:
            ids = [found.group(1) + found.group(2)] + [part if "-" in part else found.group(1) + part
                                                       for part in found.group(3).split("/")[1:]]
        found = ID_RANGE.match(word)
        if found and int(found.group(2)) < int(found.group(3)) <= int(found.group(2)) + MAX_IDS:
            ids = [f"{found.group(1)}{n}" for n in range(int(found.group(2)), int(found.group(3)) + 1)]
        if ids:
            return ["".join(words[:i] + [one] + words[i + 1:]) for one in ids]
    return ["".join(words)]


def parse_time(value, offset):
    """An aware datetime from at= (ISO with offset, ISO without = local offset, or HH:MM = a clock time, date None).
    2.2.4: also HH:MM:SS (compared by the minute)."""
    clock = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2}(?:\.\d+)?)?", value)
    if clock:
        return None, (int(clock.group(1)), int(clock.group(2)))
    try:
        when = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"at={value} is not an ISO time, HH:MM or HH:MM:SS")
    return (when if when.tzinfo else when.replace(tzinfo=offset)), None


def parse_at(value, offset):
    """2.2.4: (at, extra minutes) of at=; a span HH:MM–HH:MM is its start plus its length as extra tolerance."""
    span = AT_SPAN.fullmatch(value)
    if not span:
        return parse_time(value, offset), 0
    start, end = parse_time(span.group(1), offset)[1], parse_time(span.group(2), offset)[1]
    return (None, start), (end[0] * 60 + end[1] - start[0] * 60 - start[1]) % 1440


def gap(entry_ts, at, offset, fine=False):
    """Minutes between a log time and at= (for HH:MM on the clock, whole minutes, across midnight; fine=True: from the
    seconds to that minute, to pick the nearest run)."""
    stamp = datetime.datetime.fromisoformat(entry_ts.replace("Z", "+00:00"))
    full, clock = at
    if full is not None:
        return abs((stamp - full).total_seconds()) / 60
    local = stamp.astimezone(offset)
    minutes = local.hour * 60 + local.minute - (clock[0] * 60 + clock[1])
    if fine:
        seconds = (minutes * 60 + local.second + local.microsecond / 1e6) % 86400
        seconds = min(seconds, 86400 - seconds + 60)
        return max(0.0, seconds - 60) / 60 if seconds >= 60 else 0.0
    return min(abs(minutes), 1440 - abs(minutes))


def near(entry_ts, at, offset, tolerance):
    return gap(entry_ts, at, offset) <= tolerance


def split_runs(claim, mine, offset, tolerance):
    """2.2.4: [run per statement] when a claim of several statements is found statement by statement in calls in
    time order (each within at= when given), else None. Statements with fewer than MIN_WORDS words are not looked
    for; at least 2 must be."""
    whole = canonical_command(claim["command"])
    statements = [part for part in whole.split(" ; ")
                  if sum(1 for word in fold(part.split(" ")) if not skips(word)) >= MIN_WORDS]
    if len(statements) < 2:
        return None
    short = leaves_out(whole.split(" "))
    at, extra = None, 0
    if claim["at"]:
        try:
            at, extra = parse_at(claim["at"], offset)
        except ValueError:
            return None
    pool = sorted((e for e in mine if e.get("kind") in ("result", "failure") and when(e) is not None
                   and (at is None or near(str(e.get("ts")), at, offset, tolerance + extra))), key=when)
    found, start = [], 0
    for statement in statements:
        part = dict(claim, command=statement)
        hit = next((i for i in range(start, len(pool)) if matches(part, pool[i], short)), None)
        if hit is None:
            return None
        found.append(pool[hit])
        start = hit
    return found


def check(claim, mine, offset, tolerance, session):
    """(problems, the run shown or None, note) for one claimed command."""
    runs = [e for e in mine if e.get("kind") in ("result", "failure") and matches(claim, e)]
    if not runs:
        parts = split_runs(claim, mine, offset, tolerance)
        if parts:
            return [], parts[-1], ("its statements were run in separate calls, seq "
                                   + ", ".join(str(e.get("seq")) for e in parts))
        denied = [e for e in mine if e.get("kind") == "decision" and matches(claim, e)]
        hint = similar(claim, mine, offset, tolerance)
        return [f"not run in session {session}"
                + (f" (the hook denied it, seq {denied[-1].get('seq')})" if denied else "")
                + (f"; near at= a call starts the same: seq {hint.get('seq')} at {hint.get('ts')} "
                   f"`{shorten(command_of(hint)[0])}`" if hint is not None else "")], None, None
    problems, note = [], None
    if claim["at"]:
        try:
            at, extra = parse_at(claim["at"], offset)
        except ValueError as error:
            problems.append(str(error))
            at = None
        if at is not None:
            timed = [e for e in runs if near(str(e.get("ts")), at, offset, tolerance + extra)]
            if not timed:
                problems.append(f"at={claim['at']}, but the runs were at {', '.join(str(e.get('ts')) for e in runs[-3:])}")
            runs = sorted(timed or runs, key=lambda e: gap(str(e.get("ts")), at, offset, True), reverse=True)  # nearest last
    if claim["exit"] is not None:
        want = "ok" if claim["exit"] == 0 else "error"
        ended = [e for e in runs if (e.get("result") or {}).get("status") == want]
        raw = runs[-1].get("tool_raw")
        if ended:
            runs = ended
        elif runs_more(claim["command"], runs[-1]):
            got = (runs[-1].get("result") or {}).get("status")
            note = (f"exit={claim['exit']} not checkable: seq {runs[-1].get('seq')} goes on with other statements, so "
                    f"its status ({got}) is theirs")
        elif (raw and claim["exit"] != 0 and (runs[-1].get("result") or {}).get("status") == "ok"
              and not any(e.get("tool_raw") == raw and (e.get("result") or {}).get("status") == "error" for e in mine)):
            note = (f"exit={claim['exit']} not checkable: seq {runs[-1].get('seq')} is a {raw} call and no {raw} call of "
                    f"this session has status error, so its status does not carry the exit code")
        else:
            got = ", ".join(sorted({str((e.get("result") or {}).get("status")) for e in runs}))
            problems.append(f"exit={claim['exit']}, but the log says {got} (seq {runs[-1].get('seq')})")
    if not problems and not matches(claim, runs[-1], subset=False):
        left = left_out(claim, runs[-1])
        if left:
            extra = f"seq {runs[-1].get('seq')} also has {', '.join(left)}, which the claim leaves out"
            note = f"{note}; {extra}" if note else extra
    return problems, runs[-1], note


def shorten(text, size=160):
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= size else text[:size - 1] + "…"


def similar(claim, mine, offset, tolerance):
    """2.2.5: for a claim not run: the call nearest at= whose statement starts with the claim's first word and holds
    its second (git commit -m x vs git -c a=b commit -m y), or None. Only when at= is given."""
    if not claim["at"] or claim["command"].startswith("mcp__"):
        return None
    words = [word for word in canonical_command(claim["command"]).split(" ") if not skips(word)]
    if len(words) < 2 or ";" in words[:2]:
        return None
    try:
        at, extra = parse_at(claim["at"], offset)
    except ValueError:
        return None
    pool = []
    for e in mine:
        if (str(e.get("tool") or "").lower() not in SHELL_TOOLS or e.get("kind") not in ("result", "failure")
                or not near(str(e.get("ts")), at, offset, tolerance + extra)):
            continue
        for statement in canonical_command(command_of(e)[0]).split(" ; "):
            have = statement.split(" ")
            if have[0] == words[0] and words[1] in have[1:]:
                pool.append(e)
                break
    pool.sort(key=lambda e: gap(str(e.get("ts")), at, offset, True), reverse=True)
    return pool[-1] if pool else None


def cut_cover(claim, mine, offset, tolerance, anchors):
    """2.2.4: the cut call that may hold a claim found nowhere: a call cut at the log's input limit that another
    command of the same report matched (anchors: seq numbers), within at= when given. The call or None."""
    at, extra = None, 0
    if claim["at"]:
        try:
            at, extra = parse_at(claim["at"], offset)
        except ValueError:
            return None
    pool = [e for e in mine if e.get("seq") in anchors and str(e.get("tool") or "").lower() in SHELL_TOOLS
            and command_of(e)[1] and (at is None or near(str(e.get("ts")), at, offset, tolerance + extra))]
    if at is not None:
        pool.sort(key=lambda e: gap(str(e.get("ts")), at, offset, True), reverse=True)
    return pool[-1] if pool else None


def when(entry):
    try:
        return datetime.datetime.fromisoformat(str(entry.get("ts")).replace("Z", "+00:00"))
    except ValueError:
        return None


def scope_warning(text, mine, backing):
    """2.2.3 shadow check: when the report says SCOPE_CHECK PASS, the agent that ran most of the report's commands (the
    whole session when none matched) must have run scope_check.py after its last commit. A WARN text or None."""
    if not SCOPE_PASS.search(text):
        return None
    pool, who = mine, "the session"
    agents = collections.Counter(e.get("agent_id") for e in backing)
    if agents:
        agent = agents.most_common(1)[0][0]
        pool = [e for e in mine if e.get("agent_id") == agent]
        who = f"agent {agent}" if agent else "the main agent"
    shell = [(e, command_of(e)[0]) for e in pool if str(e.get("tool") or "").lower() in SHELL_TOOLS
             and e.get("kind") in ("result", "failure") and when(e) is not None]
    commits = sorted((e for e, command in shell
                      if COMMIT.search(command) and (e.get("result") or {}).get("status") == "ok"), key=when)
    if not commits:
        return None
    last = commits[-1]
    command = command_of(last)[0]
    tail = command[COMMIT.search(command).end():]
    checks = sorted((e for e, body in shell if SCOPE_RUN.search(body) and "--help" not in body), key=when)
    later = [e for e in checks if (when(e) > when(last) or (e is last and SCOPE_RUN.search(tail)))
             and (e.get("result") or {}).get("status") == "ok"]
    if later:
        return None
    before = (f"; its last scope_check.py run is seq {checks[-1].get('seq')} at {checks[-1].get('ts')}" if checks
              else "; it ran no scope_check.py at all")
    return (f"the report says SCOPE_CHECK PASS, but {who} committed last at seq {last.get('seq')} ({last.get('ts')}) "
            f"and ran no scope_check.py after it{before} (shadow, exit code unchanged)")


def fail_classes(problems):
    """2.2.5: the classes of a claim's problems, in order: 沒跑 / 時間不符 / 結束碼不符 / 格式."""
    out = []
    for problem in problems:
        if "not run in session" in problem:
            name = "沒跑"
        elif ", but the runs were at " in problem:
            name = "時間不符"
        elif "but the log says" in problem:
            name = "結束碼不符"
        else:
            name = "格式"
        if name not in out:
            out.append(name)
    return out


def squash(text):
    return re.sub(r"\s+", " ", text).strip()


def input_text(entry):
    """2.2.5: every string of a log call's input, joined and with spaces collapsed (a cut input: its raw text with
    the common JSON escapes put back)."""
    if "_text" not in entry:
        raw = entry.get("input") or ""
        try:
            value = json.loads(raw)
        except ValueError:
            text = raw.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
        else:
            parts, stack = [], [value]
            while stack:
                item = stack.pop()
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    stack.extend(reversed(list(item.values())))
                elif isinstance(item, list):
                    stack.extend(reversed(item))
            text = "\n".join(parts)
        entry["_text"] = squash(text)
    return entry["_text"]


def commit_time(repo, word):
    """2.2.5: the committer time of a commit in repo, or None (not found, git missing)."""
    try:
        done = subprocess.run(["git", "-C", str(repo), "show", "-s", "--format=%cI", word + "^{commit}"],
                              capture_output=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        # git writes a UTC time as ...Z; fromisoformat takes Z only from Python 3.11 on
        return (datetime.datetime.fromisoformat(re.sub(r"Z$", "+00:00", done.stdout.strip()))
                if done.returncode == 0 else None)
    except ValueError:
        return None


def stamp_checks(text, pool, offset, tolerance, repo):
    """2.2.5: [(line number, stamp, [problem], written)] for each line of a lead file that starts with a stamp
    YYYY-MM-DD HH:MM. The line was written by the earliest call of pool (time order) whose input holds it; the stamp
    may not be more than STAMP_AHEAD_MIN minutes after that call nor more than tolerance minutes before it. With repo
    a line that names a commit (COMMIT word and a hex word) is also compared with that commit's time: the stamp may not
    be before the commit's minute nor more than tolerance minutes after it."""
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        found = STAMP.match(line)
        if not found:
            continue
        hour, minute = found.group(2).split(":")
        try:
            stamp = datetime.datetime.fromisoformat(f"{found.group(1)}T{int(hour):02d}:{minute}").replace(tzinfo=offset)
        except ValueError:
            out.append((number, found.group(0).strip(), [f"{found.group(0).strip()} is not a date and time"], False))
            continue
        body = squash(line)
        writer = next((e for e in pool if body in input_text(e)), None)
        problems = []
        if writer is not None:
            written = when(writer)
            ahead = (stamp - written).total_seconds() / 60
            late = (written - stamp).total_seconds() / 60 - 1  # the stamp names a whole minute
            if ahead > STAMP_AHEAD_MIN:
                problems.append(f"seq {writer.get('seq')} wrote it at {writer.get('ts')}, {ahead:.0f} min before the "
                                f"time it states")
            elif late > tolerance:
                problems.append(f"seq {writer.get('seq')} wrote it at {writer.get('ts')}, {late + 1:.0f} min after the "
                                f"time it states (tolerance {tolerance})")
        if repo and STAMP_COMMIT.search(line[found.end():]):
            for word in STAMP_HEX.findall(line[found.end():]):
                committed = commit_time(repo, word)
                if committed is None:
                    continue
                after = (stamp - committed.replace(second=0, microsecond=0)).total_seconds() / 60
                if after < 0:
                    problems.append(f"commit {word} is at {committed.isoformat()}, after the time it states (a commit "
                                    f"is logged once it is made)")
                elif after > tolerance:
                    problems.append(f"commit {word} is at {committed.isoformat()}, {after:.0f} min before the time it "
                                    f"states (tolerance {tolerance})")
                break
        out.append((number, found.group(0).strip(), problems, writer is not None))
    return out


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")  # before parse_args: --help prints during parsing
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", help="the worker's TASK REPORT")
    ap.add_argument("--lead", action="append", default=[],
                    help="2.2.5: a file the lead writes (GATE_VERDICT, DIRECTOR_LOG): RAN lines and stamps (repeatable)")
    ap.add_argument("--log", action="append", required=True, help="action log (repeatable)")
    ap.add_argument("--session", help="session_id (default: the report's SESSION_ID: line, else the logs' only one)")
    ap.add_argument("--tolerance-min", type=int, default=10, help="at= may differ this many minutes (default 10)")
    ap.add_argument("--utc-offset", help="offset for at= without one and for HH:MM, e.g. +08:00 (default: local)")
    ap.add_argument("--repo", help="2.2.5, with --lead: the repo whose commit times a stamped COMMIT line is compared with")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if not a.report and not a.lead:
        print("report_vs_audit: give --report and / or --lead", file=sys.stderr)
        return 2
    if a.tolerance_min < 0:
        print("report_vs_audit: --tolerance-min must be 0 or more", file=sys.stderr)
        return 2
    audit = load_audit()
    if a.utc_offset:
        found = re.fullmatch(r"([+-])(\d{2}):?(\d{2})", a.utc_offset)
        if not found:
            print(f"report_vs_audit: --utc-offset {a.utc_offset} is not +HH:MM", file=sys.stderr)
            return 2
        sign = 1 if found.group(1) == "+" else -1
        offset = datetime.timezone(sign * datetime.timedelta(hours=int(found.group(2)), minutes=int(found.group(3))))
    else:
        offset = datetime.datetime.now().astimezone().tzinfo
    texts = []
    for path, lead in [(a.report, False)] * bool(a.report) + [(path, True) for path in a.lead]:
        try:
            texts.append((path, pathlib.Path(path).read_text(encoding="utf-8-sig"), lead))
        except (OSError, UnicodeDecodeError) as error:
            print(f"report_vs_audit: {path}: {type(error).__name__}: {getattr(error, 'strerror', None) or error}",
                  file=sys.stderr)
            return 2
    text = "\n".join(body for _, body, _ in texts)
    entries, broken = [], []
    for log in a.log:
        try:
            lines, problem = audit.load(log)
        except audit.CannotRun as error:
            print(f"report_vs_audit: {error}", file=sys.stderr)
            return 2
        problem = problem or audit.chain_problem(lines)
        if problem:
            broken.append(f"{log}: {problem}")
        entries += [e for _, e in lines]
    found_claims, loose = parse(text)
    session = a.session
    if not session:
        found = re.search(r"^[ \t]*SESSION_ID[ \t]*:[ \t]*(\S+)", text, re.M)
        session = found.group(1) if found else None
    if not session:
        ids = sorted({e.get("session_id") for e in entries if e.get("session_id")})
        if len(ids) == 1:
            session = ids[0]
        elif a.report or found_claims:
            print(f"report_vs_audit: the logs hold {len(ids)} sessions; pass --session or write SESSION_ID: in the report",
                  file=sys.stderr)
            return 2
    mine = [e for e in entries if session and e.get("session_id") == session]
    if any(e.get("kind") == "rebuild" for e in entries):
        print("  ~ note: a log was rebuilt from a transcript after the fact (transcript_audit.py), not written by the hook "
              "while the agent worked; it shows what the transcript holds, not that nothing else was done")
    failed, backing, classes = 0, [], collections.Counter()
    for problem in broken:
        print(f"FAIL log: hash chain {problem} (audit_log.py verify)")
    prepare(mine)
    results = []
    for claim in found_claims:
        forms = variants(claim["command"]) if mine else []
        results.append([[form, *check(dict(claim, command=form), mine, offset, a.tolerance_min, session)]
                        for form in forms])
    anchors = {last.get("seq") for rows in results for _, wrong, last, _ in rows if last is not None and not wrong}
    in_cut = set()
    for index, (rows, claim) in enumerate(zip(results, found_claims)):
        for row in rows:
            if row[2] is None:
                cover = cut_cover(dict(claim, command=row[0]), mine, offset, a.tolerance_min, anchors)
                if cover is not None:
                    row[1:] = [[], cover, (f"no call shows it, but seq {cover.get('seq')} was cut at the log's input "
                                           f"limit and another command of this report matched it, so it may be in the "
                                           f"cut part; not verified")]
                    in_cut.add(index)
    unverified = 0
    for index, (rows, claim) in enumerate(zip(results, found_claims)):
        label = f"{claim['kind']}: `{claim['command']}`".replace("\n", "; ")
        if not mine:
            failed += 1
            classes["沒跑"] += 1
            print(f"FAIL {label}: the logs hold no line of session {session} (類別：沒跑)")
            continue
        problems, shown, notes = [], [], []
        for form, wrong, last, note in rows:
            prefix = f"`{form}`: " if len(rows) > 1 else ""
            problems += [prefix + problem for problem in wrong]
            if last is not None:
                shown.append(last)
            if note:
                notes.append(prefix + note)
        if problems:
            failed += 1
            names = fail_classes(problems)
            classes.update(names)
            print(f"FAIL {label}: " + "; ".join(problems) + f" (類別：{'、'.join(names)})")
            continue
        if index in in_cut:
            unverified += 1
            print(f"UNVERIFIED {label}: in log cut part: " + "; ".join(notes) + " (exit code unchanged)")
            continue
        backing += shown
        last = shown[-1]
        print(f"OK   {label}: seq {', '.join(str(e.get('seq')) for e in shown)} at {last.get('ts')} "
              f"status={(last.get('result') or {}).get('status')}"
              + ("" if claim["exit"] is not None else " (exit not claimed)")
              + "".join(f" (~ {note})" for note in notes))
    for line in loose:
        print(f"WARN ran: a RAN line with no `command`, so nothing to check: {line} (shadow, exit code unchanged)")
    report_text = texts[0][1] if a.report else ""
    warning = scope_warning(report_text, mine, backing) if mine and a.report else None
    if warning:
        print(f"WARN scope_check: {warning}")
    stamps = unfound = stamp_failed = 0
    if a.lead:
        pool = sorted((e for e in (mine if a.session else entries) if e.get("kind") in ("result", "failure")
                       and when(e) is not None), key=when)
        for path, body, lead in texts:
            if not lead:
                continue
            name = pathlib.Path(path).name
            rows = stamp_checks(body, pool, offset, a.tolerance_min, a.repo)
            missing = [str(number) for number, _, _, written in rows if not written]
            stamps += len(rows)
            unfound += len(missing)
            for number, stamp, problems, _ in rows:
                if problems:
                    stamp_failed += 1
                    classes["時間不符"] += 1
                    print(f"FAIL stamp: {name}:{number} `{stamp}`: " + "; ".join(problems) + " (類別：時間不符)")
            print(f"  ~ stamps: {name}: {len(rows)} stamped lines, {len(rows) - len(missing)} found in a logged call"
                  + (f"; not found (written by a program, or the log is cut): lines {', '.join(missing[:12])}"
                     + (" ..." if len(missing) > 12 else "") if missing else ""))
    ok = len(found_claims) - failed - unverified
    bad = failed or broken or stamp_failed
    result = "FAIL" if bad else ("NONE" if not found_claims and not stamps else "PASS")
    print(f"REPORT_VS_AUDIT: {result} claims={len(found_claims)} ok={ok} failed={failed} session={session} logs={len(a.log)} "
          f"unverified={unverified} time_mismatch={classes['時間不符']} not_run={classes['沒跑']}"
          + (f" stamps={stamps} stamps_unfound={unfound}" if a.lead else ""))
    return 1 if result == "FAIL" else 0


def entry_point(argv=None):
    """2.2.5: main() with every unexpected error turned into one line and exit 2 (no Traceback)."""
    try:
        return main(argv)
    except KeyboardInterrupt:
        print("report_vs_audit: interrupted", file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001 - the top level reports, never a Traceback
        print(f"report_vs_audit: cannot run: {type(error).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(entry_point())
