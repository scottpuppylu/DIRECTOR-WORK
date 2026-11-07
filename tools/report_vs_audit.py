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
A shell claim matches a Bash / PowerShell line of that session whose command holds the claimed command (spaces, quotes
and slash direction aside; a line cut at 500 characters matches on its first part); an mcp__ claim matches the tool
name. The log does not hold exit codes: exit 0 must meet a "result" line with status ok, another exit a "failure"
line. When at= is given the matching line must lie within --tolerance-min minutes of it.

Prints OK / FAIL per claim and a last line
  REPORT_VS_AUDIT: PASS|FAIL|NONE claims=n ok=n failed=n session=ID logs=n
exit 1 on any FAIL or a broken hash chain, 0 on PASS or NONE (no claims found), 2 when it cannot run.
"""
import argparse
import datetime
import importlib.util
import json
import pathlib
import re
import sys

SHELL_TOOLS = ("Bash", "PowerShell")
CLAIM_FIELDS = ("TESTS", "EVIDENCE", "DONE")
KINDS = [
    ("selftest", re.compile(r"selftest\.py", re.I)),
    ("unity", re.compile(r"unity(?:\.exe)?\b.*-batchmode|-batchmode|\bunity\.exe\b|mcp__unitymcp__", re.I)),
    ("blender", re.compile(r"\bblender(?:\.exe)?\b|mcp__blender__", re.I)),
    ("hash", re.compile(r"sha256sum|get-filehash|certutil\s+-hashfile|gate_check\.py\s+--hash|evidence_record\.py", re.I)),
]
EXIT = re.compile(r"\bexit(?:\s*code)?\s*[=:]?\s*(-?\d+)\b", re.I)
AT = re.compile(r"\bat=(\S+)")
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
    out, field = [], None
    for line in text.splitlines():
        found = FIELD.match(line)
        if found:
            field, rest = found.group(1), found.group(2)
        else:
            rest = line
        if field == "RAN":
            for command in re.findall(r"`([^`]+)`", rest):
                out.append(claim_from(rest, command, True))
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
    return unique


def norm(text):
    text = text.replace("\\\\", "/").replace("\\", "/").replace('"', "").replace("'", "")
    return re.sub(r"\s+", " ", text).strip().lower()


def shell_command(entry):
    """The command of a Bash / PowerShell log line (its input is the masked tool input as JSON, maybe cut)."""
    raw = entry.get("input") or ""
    try:
        value = json.loads(raw)
        return str(value.get("command", "")) if isinstance(value, dict) else raw, False
    except ValueError:
        found = re.match(r'\{"command":\s*"(.*)', raw, re.S)
        return (found.group(1) if found else raw).rstrip("…"), raw.endswith("…")


def matches(claim, entry):
    if claim["command"].startswith("mcp__"):
        return entry.get("tool") == claim["command"].split()[0]
    if entry.get("tool") not in SHELL_TOOLS:
        return False
    command, cut = shell_command(entry)
    want, have = norm(claim["command"]), norm(command)
    return want in have or (cut and len(have) >= 40 and want.startswith(have))


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


def near(entry_ts, at, offset, tolerance):
    when = datetime.datetime.fromisoformat(entry_ts.replace("Z", "+00:00"))
    full, clock = at
    if full is not None:
        return abs((when - full).total_seconds()) <= tolerance * 60
    local = when.astimezone(offset)
    minutes = local.hour * 60 + local.minute - (clock[0] * 60 + clock[1])
    return min(abs(minutes), 1440 - abs(minutes)) <= tolerance


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
    found_claims = claims(text)
    failed = 0
    for problem in broken:
        print(f"FAIL log: hash chain {problem} (audit_log.py verify)")
    for claim in found_claims:
        label = f"{claim['kind']}: `{claim['command']}`"
        if not mine:
            failed += 1
            print(f"FAIL {label}: the logs hold no line of session {session}")
            continue
        runs = [e for e in mine if e.get("kind") in ("result", "failure") and matches(claim, e)]
        if not runs:
            denied = [e for e in mine if e.get("kind") == "decision" and matches(claim, e)]
            failed += 1
            print(f"FAIL {label}: not run in session {session}" + (f" (the hook denied it, seq {denied[-1].get('seq')})" if denied else ""))
            continue
        problems = []
        if claim["at"]:
            try:
                at = parse_time(claim["at"], offset)
            except ValueError as error:
                problems.append(str(error))
                at = None
            if at is not None:
                timed = [e for e in runs if near(str(e.get("ts")), at, offset, a.tolerance_min)]
                if not timed:
                    problems.append(f"at={claim['at']}, but the runs were at {', '.join(str(e.get('ts')) for e in runs[-3:])}")
                runs = timed or runs
        if claim["exit"] is not None:
            want = "ok" if claim["exit"] == 0 else "error"
            ended = [e for e in runs if (e.get("result") or {}).get("status") == want]
            if not ended:
                got = ", ".join(sorted({str((e.get("result") or {}).get("status")) for e in runs}))
                problems.append(f"exit={claim['exit']}, but the log says {got} (seq {runs[-1].get('seq')})")
            runs = ended or runs
        last = runs[-1]
        if problems:
            failed += 1
            print(f"FAIL {label}: " + "; ".join(problems))
        else:
            print(f"OK   {label}: seq {last.get('seq')} at {last.get('ts')} status={(last.get('result') or {}).get('status')}"
                  + ("" if claim["exit"] is not None else " (exit not claimed)"))
    ok = len(found_claims) - failed
    result = "FAIL" if failed or broken else ("NONE" if not found_claims else "PASS")
    print(f"REPORT_VS_AUDIT: {result} claims={len(found_claims)} ok={ok} failed={failed} session={session} logs={len(a.log)}")
    return 1 if result == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
