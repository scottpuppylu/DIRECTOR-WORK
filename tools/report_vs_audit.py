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

Prints OK / FAIL per claim, WARN lines, and a last line
  REPORT_VS_AUDIT: PASS|FAIL|NONE claims=n ok=n failed=n session=ID logs=n
exit 1 on any FAIL or a broken hash chain, 0 on PASS or NONE (no claims found), 2 when it cannot run.
"""
import argparse
import collections
import datetime
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
SEPARATOR = re.compile(r"\r?\n|\r|;|&&|\|\|")  # 2.2.3: these end a statement
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
    out, loose, field, block = [], [], None, None
    for line in text.splitlines():
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
    text = text.replace("\\\\", "/").replace("\\", "/").replace('"', "").replace("'", "")
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


def canonical_command(command):
    """norm() with a leading & / ; / cmd /c and a python / node / pwsh launcher with its startup flags dropped; 2.2.3: in
    each statement, joined again by " ; "."""
    statements = []
    for statement in norm(command).split(" ; "):
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


def same_word(claim_word, log_word):
    """Equal, or the log word is a longer path that ends with the claim word (tools/x.py matches d:/w/tools/x.py)."""
    return claim_word == log_word or log_word.endswith("/" + claim_word.lstrip("/"))


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


def word_match(claim, log, cut=False):
    """True when the claim words sit, in order, on a run of the log words; "..." / "<name>" skip any number of words.
    Needs MIN_WORDS claim words that are not wildcards, so a claim made mostly of wildcards proves nothing.
    2.2.3: a claim ";" skips to the end of a log statement; a claim that leaves parts out may skip log options and
    match short words (short_word); a cut log line (cut=True) matches when CUT_WORDS claim words reach its end (its
    last word may be cut short)."""
    if sum(1 for word in claim if not skips(word) and word != ";") < MIN_WORDS or not log:
        return False
    short = any(skips(word) or ELLIPSIS_END.match(word) for word in claim)
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


def matches(claim, entry):
    if claim["command"].startswith("mcp__"):
        return entry.get("tool") == claim["command"].split()[0]
    if str(entry.get("tool") or "").lower() not in SHELL_TOOLS:
        return False
    command, cut = shell_command(entry)
    want, have = canonical_command(claim["command"]), canonical_command(command)
    if not want:
        return False
    if want in have or (cut and len(have) >= 40 and want.startswith(have)):
        return True
    return word_match(want.split(" "), have.split(" "), cut)


def runs_more(claimed, entry):
    """2.2.3: True when the log call goes on with another statement after the claimed one; the call's status is then
    that statement's, so the claimed exit cannot be checked against it."""
    if str(entry.get("tool") or "").lower() not in SHELL_TOOLS:  # runs_more: shell calls only
        return False
    have = canonical_command(shell_command(entry)[0]).split(" ")
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
    full-width （note） is left out. The spaces and new lines between the words are kept (they end statements)."""
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
    """An aware datetime from at= (ISO with offset, ISO without = local offset, or HH:MM = a clock time, date None)."""
    clock = re.fullmatch(r"(\d{1,2}):(\d{2})", value)
    if clock:
        return None, (int(clock.group(1)), int(clock.group(2)))
    try:
        when = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"at={value} is not an ISO time or HH:MM")
    return (when if when.tzinfo else when.replace(tzinfo=offset)), None


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


def check(claim, mine, offset, tolerance, session):
    """(problems, the run shown or None, note) for one claimed command."""
    runs = [e for e in mine if e.get("kind") in ("result", "failure") and matches(claim, e)]
    if not runs:
        denied = [e for e in mine if e.get("kind") == "decision" and matches(claim, e)]
        return [f"not run in session {session}"
                + (f" (the hook denied it, seq {denied[-1].get('seq')})" if denied else "")], None, None
    problems, note = [], None
    if claim["at"]:
        try:
            at = parse_time(claim["at"], offset)
        except ValueError as error:
            problems.append(str(error))
            at = None
        if at is not None:
            timed = [e for e in runs if near(str(e.get("ts")), at, offset, tolerance)]
            if not timed:
                problems.append(f"at={claim['at']}, but the runs were at {', '.join(str(e.get('ts')) for e in runs[-3:])}")
            runs = sorted(timed or runs, key=lambda e: gap(str(e.get("ts")), at, offset, True), reverse=True)  # nearest last
    if claim["exit"] is not None:
        want = "ok" if claim["exit"] == 0 else "error"
        ended = [e for e in runs if (e.get("result") or {}).get("status") == want]
        if ended:
            runs = ended
        elif runs_more(claim["command"], runs[-1]):
            got = (runs[-1].get("result") or {}).get("status")
            note = (f"exit={claim['exit']} not checkable: seq {runs[-1].get('seq')} goes on with other statements, so "
                    f"its status ({got}) is theirs")
        else:
            got = ", ".join(sorted({str((e.get("result") or {}).get("status")) for e in runs}))
            problems.append(f"exit={claim['exit']}, but the log says {got} (seq {runs[-1].get('seq')})")
    return problems, runs[-1], note


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
    shell = [(e, shell_command(e)[0]) for e in pool if str(e.get("tool") or "").lower() in SHELL_TOOLS
             and e.get("kind") in ("result", "failure") and when(e) is not None]
    commits = sorted((e for e, command in shell
                      if COMMIT.search(command) and (e.get("result") or {}).get("status") == "ok"), key=when)
    if not commits:
        return None
    last = commits[-1]
    command = shell_command(last)[0]
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
    for claim in found_claims:
        label = f"{claim['kind']}: `{claim['command']}`".replace("\n", "; ")
        if not mine:
            failed += 1
            print(f"FAIL {label}: the logs hold no line of session {session}")
            continue
        forms = variants(claim["command"])
        problems, shown, notes = [], [], []
        for form in forms:
            wrong, last, note = check(dict(claim, command=form), mine, offset, a.tolerance_min, session)
            prefix = f"`{form}`: " if len(forms) > 1 else ""
            problems += [prefix + problem for problem in wrong]
            if last is not None:
                shown.append(last)
            if note:
                notes.append(prefix + note)
        if problems:
            failed += 1
            print(f"FAIL {label}: " + "; ".join(problems))
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
    ok = len(found_claims) - failed
    result = "FAIL" if failed or broken else ("NONE" if not found_claims else "PASS")
    print(f"REPORT_VS_AUDIT: {result} claims={len(found_claims)} ok={ok} failed={failed} session={session} logs={len(a.log)}")
    return 1 if result == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
