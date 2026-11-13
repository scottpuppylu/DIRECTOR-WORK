"""Rebuild an action log from Claude Code transcripts (DIRECTOR-WORK 2.2.1), for a project that ran without the hook.

  python -I -X utf8 transcript_audit.py build --out FILE [--force] --transcript FILE.jsonl [--transcript ...]
  python -I -X utf8 transcript_audit.py build --out FILE [--force] --session ID [--project-dir DIR] [--root DIR]
                                         [--no-subagents]

The output has the format audit_log.py append (the PostToolUse hook) writes, built with the same code (audit_log.py's
summary, output_record, digest and canonical), so `audit_log.py verify` and `report_vs_audit.py` read it as they read a
hook log. One line per tool call that has a result in the transcript:
  session_id / agent_id    the transcript line's sessionId / agentId (agentId only in subagent transcripts)
  tool / tool_use_id       the assistant message's tool_use name / id
  input                    audit_log.summary(tool_use input): masked, at most 500 characters, as the hook writes it
  kind / result.status     the user message's tool_result: is_error -> failure / error (interrupted when it is the
                           user's interrupt message); else result / ok (interrupted when toolUseResult says so)
  result.sha256 / length   audit_log.output_record of toolUseResult (when the line holds one tool_result) or of the
                           tool_result content; NOT comparable with a hook log's hash (the hook sees tool_response)
  duration_ms              null (the transcript does not time the tool)
  ts                       the tool_result line's timestamp, as YYYY-MM-DDTHH:MM:SS.mmm+00:00
Lines are sorted by ts (ties in reading order) and chained from seq 1. Line 1 is kind=rebuild with a `source` field
(by, version, transcripts with name / sha256 / bytes, lines, no_result, duplicates, no_time) so a rebuilt log is never
taken for one the hook wrote while the agent worked. Only `assistant` / `user` lines are read (the api-request copies
of the same blocks are not). A tool_use with no result (still running, cut transcript) is not written and is counted
as no_result; a tool_use_id seen again is counted as duplicates (the first one is kept); a result whose time cannot be
read is counted as no_time. hook_guard decision lines cannot be rebuilt.

--transcript also reads <stem>/subagents/*.jsonl beside each file unless --no-subagents. --session ID reads
<root>/<project-dir>/ID.jsonl, where <project-dir> is --project-dir (default: the current folder) with every character
other than A-Z a-z 0-9 turned into "-" (as usage_report.py) and <root> is ~/.claude/projects.

--out must not exist unless --force; the file is written to a temporary name and moved into place. Prints
`TRANSCRIPT_AUDIT file=... lines=n sessions=n no_result=n duplicates=n no_time=n` and the `AUDIT_HEAD` line of the new
log. Exit 0 written, 1 refused (--out exists) or not written, 2 cannot run (no transcript, no tool call, bad
arguments). Reads the transcripts only; writes only --out. Standard library only.

Limits: the transcript format is Claude Code's own and not documented; when its field names change this finds no tool
call and exits 2. A rebuilt log shows what the transcript holds; it cannot prove nothing else was done (a transcript
can be edited), so a hook log with AUDIT_HEAD anchors stays the stronger evidence.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sys

VERSION = "2.2.1"
INTERRUPT = "[Request interrupted by user"


class CannotRun(Exception):
    pass


def load_audit():
    spec = importlib.util.spec_from_file_location("audit_log", pathlib.Path(__file__).with_name("audit_log.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project_dir_name(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(pathlib.Path(path).resolve()))


def find_transcripts(a):
    """The transcript files to read, main files first, each followed by its subagent files."""
    if a.session:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", a.session):
            raise CannotRun(f"--session {a.session!r}: only letters, digits, _ and -")
        mains = [pathlib.Path(a.root) / project_dir_name(a.project_dir or ".") / f"{a.session}.jsonl"]
    else:
        mains = [pathlib.Path(p) for p in a.transcript]
    files = []
    for main in mains:
        if not main.is_file():
            raise CannotRun(f"no transcript {main}")
        files.append(main)
        if not a.no_subagents:
            files += sorted((main.parent / main.stem / "subagents").glob("*.jsonl"))
    return files


def utc_ms(value):
    """A transcript timestamp as the hook writes ts (UTC, milliseconds, +00:00); None when it cannot be read."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment.astimezone(datetime.timezone.utc).isoformat(timespec="milliseconds")


def blocks(line, kind):
    message = line.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return [b for b in content if isinstance(b, dict) and b.get("type") == kind] if isinstance(content, list) else []


def text_word(line, key):
    return line[key] if isinstance(line.get(key), str) else None


def content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict) and isinstance(b.get("text"), str))
    return ""


def read_calls(files):
    """(calls in reading order, results by tool_use_id, counts, transcript records)."""
    calls, results, counts, sources = {}, {}, {"duplicates": 0, "bad_lines": 0}, []
    order = 0
    for path in files:
        sha, size = hashlib.sha256(), 0
        with open(path, "rb") as fh:  # line by line: a long session's transcript can be hundreds of MB
            for raw in fh:
                sha.update(raw)
                size += len(raw)
                line = parse(raw, counts)
                if line is not None:
                    order = take(line, order, calls, results, counts)
        sources.append({"name": path.name, "sha256": sha.hexdigest(), "bytes": size})
    return calls, results, counts, sources


def parse(raw, counts):
    """The transcript line as a dict, or None (blank, not JSON: counted as bad_lines, or not a dict)."""
    if not raw.strip():
        return None
    try:
        line = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        counts["bad_lines"] += 1
        return None
    return line if isinstance(line, dict) else None


def take(line, order, calls, results, counts):
    """Record the tool_use / tool_result blocks of one assistant / user line (the api-request copies of the same
    blocks are other line types and are skipped); returns the reading order reached."""
    if line.get("type") == "assistant":
        for use in blocks(line, "tool_use"):
            key = use.get("id")
            if not isinstance(key, str) or not isinstance(use.get("name"), str):
                continue
            if key in calls:
                counts["duplicates"] += 1
                continue
            order += 1
            calls[key] = {"order": order, "tool": use["name"], "input": use.get("input"),
                          "session_id": text_word(line, "sessionId"), "agent_id": text_word(line, "agentId")}
    elif line.get("type") == "user":
        found = blocks(line, "tool_result")
        single = len(found) == 1 and "toolUseResult" in line
        for result in found:
            key = result.get("tool_use_id")
            if not isinstance(key, str):
                continue
            if key in results:
                counts["duplicates"] += 1
                continue
            order += 1
            results[key] = {"order": order, "ts": utc_ms(line.get("timestamp")), "is_error": result.get("is_error") is True,
                            "content": result.get("content"), "has_structured": single,
                            "structured": line["toolUseResult"] if single else None}
    return order


def entry_of(audit, call, result):
    if result["is_error"]:
        text = content_text(result["content"])
        record = audit.output_record("interrupted" if text.startswith(INTERRUPT) else "error", text)
        kind = "failure"
    else:
        output = result["structured"] if result["has_structured"] else result["content"]
        interrupted = isinstance(output, dict) and output.get("interrupted") is True
        record = audit.output_record("interrupted" if interrupted else "ok", output)
        kind = "result"
    return {"ts": result["ts"], "session_id": call["session_id"], "agent_id": call["agent_id"], "tool": call["tool"],
            "tool_use_id": None, "input": audit.summary(call["input"]), "kind": kind, "result": record,
            "duration_ms": None}


def build(a):
    audit = load_audit()
    files = find_transcripts(a)
    out = pathlib.Path(a.out)
    if out.exists() and not a.force:
        print(f"REFUSED {out} exists; pick a new --out or add --force")
        return 1
    calls, results, counts, sources = read_calls(files)
    if not calls:
        raise CannotRun(f"no tool call found in {len(files)} transcript file(s) (has the transcript format changed?)")
    rows, no_result, no_time = [], 0, 0
    for key, call in calls.items():
        result = results.get(key)
        if result is None:
            no_result += 1
            continue
        if result["ts"] is None:
            no_time += 1
            continue
        entry = entry_of(audit, call, result)
        entry["tool_use_id"] = key
        rows.append((entry["ts"], result["order"], entry))
    rows.sort(key=lambda row: (row[0], row[1]))
    source = {"by": "transcript_audit.py", "version": VERSION, "transcripts": sources, "lines": len(rows),
              "no_result": no_result, "duplicates": counts["duplicates"], "no_time": no_time,
              "bad_lines": counts["bad_lines"]}
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
    first = {"ts": now, "session_id": None, "agent_id": None, "tool": None, "tool_use_id": None, "input": "",
             "kind": "rebuild", "result": {"status": "rebuilt"}, "duration_ms": None, "source": source}
    prev, lines = audit.GENESIS, []
    for seq, entry in enumerate([first] + [row[2] for row in rows], 1):
        entry = dict(entry, seq=seq, prev=prev)
        entry["hash"] = audit.digest(entry)
        prev = entry["hash"]
        lines.append(audit.canonical(entry) + "\n")
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_name(f"{out.name}.tmp-{os.getpid()}")
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(lines))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary, out)
    except OSError as error:
        if temporary.exists():
            temporary.unlink()
        print(f"NOT_WRITTEN {out}: {error}")
        return 1
    sessions = {row[2]["session_id"] for row in rows}
    shown = out.resolve().as_posix()
    print(f"TRANSCRIPT_AUDIT file={shown} lines={len(rows)} sessions={len(sessions)} no_result={no_result} "
          f"duplicates={counts['duplicates']} no_time={no_time}")
    print(f"AUDIT_HEAD file={shown} seq={len(lines)} sha={prev}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build", help="write a hook-format log from transcripts")
    p.add_argument("--out", required=True, help="the log to write (refused when it exists, unless --force)")
    p.add_argument("--force", action="store_true", help="replace an existing --out")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--transcript", action="append", help="a transcript .jsonl (may be repeated)")
    group.add_argument("--session", help="a session ID, looked up under --root/<project-dir>/")
    p.add_argument("--project-dir", help="with --session: the project's start folder (default: the current folder)")
    p.add_argument("--root", default=str(pathlib.Path.home() / ".claude" / "projects"),
                   help="with --session: the projects root (default ~/.claude/projects)")
    p.add_argument("--no-subagents", action="store_true", help="do not read <stem>/subagents/*.jsonl")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        return build(a)
    except CannotRun as error:
        print(f"NOT_RUN {error}")
        return 2
    except OSError as error:
        print(f"NOT_RUN {error}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
