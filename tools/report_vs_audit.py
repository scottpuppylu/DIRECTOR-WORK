"""Check the commands a TASK REPORT says were run against the action log (audit_log.py) of the same session: was each
one run, did it end the way the report says, and at the time it says. Only reads. For the Director's gate review.

  report_vs_audit.py --report REPORT.md --log AUDIT.jsonl [--log ...] [--session ID] [--tolerance-min 15]

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

Prints OK / UNVERIFIED / FAIL per claim, WARN lines, and a last line
  REPORT_VS_AUDIT: PASS|FAIL|NONE claims=n ok=n failed=n session=ID logs=n unverified=n
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
BASH_SET = re.compile(r"^(?:export\s+)?([A-Za-z_]\w*)=(\"[^\"]*\"|'[^']*'|\S*)$")
PS_SET = re.compile(r"^\$(?:env:)?(\w+)\s*=(?!=)\s*(.+)$", re.I | re.S)
CMD_SET = re.compile(r'^set\s+"?(\w+)=(.*?)"?$', re.I)
GIT_C = re.compile(r"\bgit\s+-C\s+(\"[^\"]*\"|'[^']*'|\S+)\s+")
HEX = re.compile(r"[0-9a-f]{7,64}")
INNER_GAP = re.compile(r"\.{3,}|…|\x00")  # 2.2.4: inside a word, any text
ID_SPACED = re.compile(r"\b([A-Z][A-Z0-9]*-\d+)[ \t]+\.\.[ \t]+((?:[A-Z][A-Z0-9]*-)?\d+)\b")  # AC-1 .. AC-6
CLOCK = r"\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
AT_SPAN = re.compile(rf"({CLOCK})\s*[–—~-]\s*({CLOCK})")


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
        return str(value.get("command", "")) if isinstance(value, dict) else raw, False
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


def expand(command, env=None):
    """2.2.4: (command with its variables put back, the variables after it). env holds earlier assignments; the
    command's own assignments (X=v, export X=v, $x = ..., $env:X = ..., set X=v, a here-string $x = @'...'@) count
    from the statement after them. $X, ${X}, $env:X and %X% with no value found become MARK (any text in the word)."""
    env = dict(env or {})

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
    each statement, joined again by " ; ". 2.2.4: "git -C DIR x" is "cd DIR ; git x"."""
    statements = []
    for statement in norm(GIT_C.sub(lambda found: f"cd {found.group(1)} ; git ", command)).split(" ; "):
        parts = [part for part in statement.split(" ") if part]
        while parts and parts[0] in ("&", ";", "&&", "||"):
            parts.pop(0)
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


def matches(claim, entry, short=None):
    if claim["command"].startswith("mcp__"):
        return entry.get("tool") == claim["command"].split()[0]
    if str(entry.get("tool") or "").lower() not in SHELL_TOOLS:
        return False
    command, cut = command_of(entry)
    want, have = canonical_command(claim["command"]), canonical_command(command)
    if not want:
        return False
    if want in have or (cut and len(have) >= 40 and want.startswith(have)):
        return True
    words = fold(want.split(" "))
    if sum(1 for word in words if not skips(word) and word != ";") < MIN_WORDS:
        # 2.2.4: too short without its launcher (python -c "..."): compare with the launcher kept
        launched = norm(GIT_C.sub(lambda found: f"cd {found.group(1)} ; git ", claim["command"])).split(" ")
        return word_match(fold(launched), norm(command).split(" "), cut, short)
    return (word_match(words, have.split(" "), cut, short)
            or any_order(words, have.split(" "), leaves_out(words) if short is None else short))


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
        return [f"not run in session {session}"
                + (f" (the hook denied it, seq {denied[-1].get('seq')})" if denied else "")], None, None
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
    return problems, runs[-1], note


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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", required=True)
    ap.add_argument("--log", action="append", required=True, help="action log (repeatable)")
    ap.add_argument("--session", help="session_id (default: the report's SESSION_ID: line, else the logs' only one)")
    ap.add_argument("--tolerance-min", type=int, default=15, help="at= may differ this many minutes (default 15)")
    ap.add_argument("--utc-offset", help="offset for at= without one and for HH:MM, e.g. +08:00 (default: local)")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
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
    try:
        text = pathlib.Path(a.report).read_text(encoding="utf-8-sig")
    except OSError as error:
        print(f"report_vs_audit: {error}", file=sys.stderr)
        return 2
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
    session = a.session
    if not session:
        found = re.search(r"^[ \t]*SESSION_ID[ \t]*:[ \t]*(\S+)", text, re.M)
        session = found.group(1) if found else None
    if not session:
        ids = sorted({e.get("session_id") for e in entries if e.get("session_id")})
        if len(ids) != 1:
            print(f"report_vs_audit: the logs hold {len(ids)} sessions; pass --session or write SESSION_ID: in the report",
                  file=sys.stderr)
            return 2
        session = ids[0]
    mine = [e for e in entries if e.get("session_id") == session]
    if any(e.get("kind") == "rebuild" for e in entries):
        print("  ~ note: a log was rebuilt from a transcript after the fact (transcript_audit.py), not written by the hook "
              "while the agent worked; it shows what the transcript holds, not that nothing else was done")
    found_claims, loose = parse(text)
    failed, backing = 0, []
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
            print(f"FAIL {label}: the logs hold no line of session {session}")
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
            print(f"FAIL {label}: " + "; ".join(problems))
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
    warning = scope_warning(text, mine, backing) if mine else None
    if warning:
        print(f"WARN scope_check: {warning}")
    ok = len(found_claims) - failed - unverified
    result = "FAIL" if failed or broken else ("NONE" if not found_claims else "PASS")
    print(f"REPORT_VS_AUDIT: {result} claims={len(found_claims)} ok={ok} failed={failed} session={session} logs={len(a.log)} "
          f"unverified={unverified}")
    return 1 if result == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
