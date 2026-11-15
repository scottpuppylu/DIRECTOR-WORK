"""Find an agent going round in circles (DIRECTOR-WORK 2.4.0): the same call again and again, the same error again,
two calls in turn, a poll whose answer never changes, calls the tool keeps rejecting, a subagent error nobody handled.

  python -I -X utf8 loop_guard.py scan --audit LOG [--audit LOG ...] [--transcript FILE.jsonl ...] [--no-subagents]
                                  [--config FILE] [--session ID] [--json]

Reads the action log that audit_log.py append writes (and hook_guard.py --audit adds decision lines to; those are
skipped), and / or Claude Code transcripts (read with transcript_audit.py's reader, subagent transcripts beside each
file included unless --no-subagents). Each tool call becomes one event: tool name, a hash of its input (sha256 of the
input summary the log keeps: the JSON text of the tool input, masked in an action log, first 500 characters; first
12 hex), its status (ok / error / interrupted; none while it runs) and a hash of its result. A transcript's input and
output are hashed without masking (faster; the hashes and the text stay inside the tool), so do not compare hashes
of a transcript with hashes of an action log. Calls are compared within one stream (session id + agent id), in order.

Categories (defaults in brackets; all counted within the last `window` [20] calls of the stream):
  repeat                 the same tool with the same input hash `repeat` [3] times or more
  retry_same_error       the same call failing with the same error hash `retry_errors` [2] times or more
  poll_no_progress       the same call `poll` [3] times in a row of its occurrences with an unchanged ok result
  ping_pong              two different calls in turn, A B A B, for `ping_pong` [6] calls or more
  bad_args               `bad_args` [2] or more calls of one tool rejected for their arguments (InputValidationError
                         and the like); needs the error text, which only a transcript holds: with an action log
                         alone it prints `~ NOT_CHECKED bad_args`
  child_error_unhandled  a subagent call (`child_tools` [Agent, Task]) that failed and is the last call of its stream:
                         nothing after it handled the error; with no subagent result in the input it prints
                         `~ NOT_VERIFIED child_error_unhandled` (Claude Code's subagent failure events are not checked)
One key gets one category, the most specific: retry_same_error, then poll_no_progress, then repeat; a key that is part
of a ping_pong finding is not also reported as repeat or poll_no_progress.

--config FILE (JSON, all keys optional): {"schema_version": 1, "window": 20, "repeat": 3, "retry_errors": 2,
"poll": 3, "ping_pong": 6, "bad_args": 2, "child_tools": ["Agent", "Task"], "allow": [{"tool": "Bash",
"input": "<regex on the input JSON text>", "max": 30, "why": "waits for the build"}]}. An allow entry is a legitimate
poll: matching calls are not reported as repeat or poll_no_progress until they reach "max" (default: never); a
retry with the same error is still reported. The regex is matched inside the tool; it is never printed.

Output shows tool names, hashes, counts and seq numbers only, never argument text:
  LOOP repeat tool=Bash args=1a2b3c4d5e6f count=4 seq=10..18 session=abcd1234
  LOOP_GUARD: FOUND n events=n streams=n (repeat=1 ...)   or   LOOP_GUARD: NONE events=n streams=n
Exit 0 none found, 1 found, 2 input error (no such file, bad config, nothing to read: NO_DATA, never a measured 0).

Hook mode: hook_guard.py --loop-guard --audit LOG (setup_project_settings.py --loop-guard) runs hook_check() before
each tool call on the tail of the same action log and the call about to run. It only reminds (or asks, with
--loop-mode ask); it never blocks. It reminds when the count reaches the threshold, then at 2x, 4x, 8x ..., so a long
legitimate wait does not fill the context. It does nothing while the environment has DW_LOOP_GUARD set (hook_guard sets
it for any process it starts), like DW_HOOK_REVIEW.

The detection core (event_of, events_from_entries, detect, coverage, hook_check) is pure: a list of events in, a list
of findings out, no files and no clock, so another host can feed it its own events. Standard library only.
Concepts borrowed (no code): stuck-loop thresholds and circuit breakers from MIT-licensed agent projects (see
CHANGELOG 2.4.0 Credits).
"""
import argparse
import collections
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sys

CATEGORIES = ("repeat", "retry_same_error", "poll_no_progress", "ping_pong", "bad_args", "child_error_unhandled")
DEFAULTS = {"window": 20, "repeat": 3, "retry_errors": 2, "poll": 3, "ping_pong": 6, "bad_args": 2,
            "child_tools": ["Agent", "Task"], "allow": []}
THRESHOLD = {"repeat": "repeat", "retry_same_error": "retry_errors", "poll_no_progress": "poll",
             "ping_pong": "ping_pong", "bad_args": "bad_args", "child_error_unhandled": None}
VALIDATION = re.compile(r"InputValidationError|Invalid tool parameters|invalid_type|required parameter|"
                        r"unexpected (?:parameter|keyword)|is a required property|missing required|"
                        r"Unrecognized key|Expected [a-z]+, received", re.I)
TAIL_BYTES = 256 * 1024
ENV_FLAG = "DW_LOOP_GUARD"


class InputError(Exception):
    """A file or the config cannot be used (exit 2)."""


def short(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:12]


def raw_hash(value):
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def plain_summary(audit, tool_input):
    """The input text as audit_log.summary gives it (JSON, cut at its limit) but not masked: for transcripts, where
    it only stays in memory to be hashed and matched by allow entries (masking 70,000 inputs took about 26 s)."""
    text = audit.text_of({} if tool_input is None else tool_input)
    return text if len(text) <= audit.INPUT_LIMIT else text[:audit.INPUT_LIMIT - 1] + "…"


def load_sibling(name):
    spec = importlib.util.spec_from_file_location(name, pathlib.Path(__file__).with_name(f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------ pure core ------------------------------------

def config(raw=None):
    """The settings: DEFAULTS with raw's keys; raises InputError on a bad key or value."""
    conf = dict(DEFAULTS)
    if raw is None:
        return conf
    if not isinstance(raw, dict):
        raise InputError("config: the top level is not an object")
    if raw.get("schema_version", 1) != 1:
        raise InputError(f"config: schema_version {raw.get('schema_version')!r} is not 1")
    for key, value in raw.items():
        if key in ("schema_version", "why", "note"):
            continue
        if key not in DEFAULTS:
            raise InputError(f"config: unknown key {key!r}")
        if key == "child_tools":
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise InputError("config: child_tools must be a list of tool names")
        elif key == "allow":
            if not isinstance(value, list):
                raise InputError("config: allow must be a list")
            for n, item in enumerate(value):
                if not isinstance(item, dict) or not isinstance(item.get("tool"), str):
                    raise InputError(f"config: allow[{n}] needs a tool name")
                try:
                    re.compile(item.get("input") or "")
                except re.error as error:
                    raise InputError(f"config: allow[{n}].input: {error}") from None
                if "max" in item and (not isinstance(item["max"], int) or isinstance(item["max"], bool) or item["max"] < 1):
                    raise InputError(f"config: allow[{n}].max must be a whole number >= 1")
        elif not isinstance(value, int) or isinstance(value, bool) or value < (2 if key != "window" else 2):
            raise InputError(f"config: {key} must be a whole number >= 2")
        conf[key] = value
    return conf


def event_of(entry, error_text=None, seq=None):
    """One event from an action-log entry (audit_log format); None for decision / rebuild / recovery lines."""
    if not isinstance(entry, dict) or entry.get("kind") not in ("result", "failure", "pending"):
        return None
    result = entry.get("result") if isinstance(entry.get("result"), dict) else {}
    status = result.get("status") if entry.get("kind") != "pending" else None
    text = entry.get("input") if isinstance(entry.get("input"), str) else json.dumps(entry.get("input"), sort_keys=True)
    error_class = None
    if error_text is not None and status == "error":
        error_class = "validation" if VALIDATION.search(error_text) else "other"
    return {"seq": entry.get("seq", seq), "session": entry.get("session_id"), "agent": entry.get("agent_id"),
            "tool": entry.get("tool") or "?", "args": short(text), "input": text, "status": status,
            "result": (result.get("sha256") or "")[:12] or None, "error_class": error_class,
            "error_text_known": error_text is not None}


def events_from_entries(entries):
    """Events from action-log entries, in order; decision and other non-call lines are dropped."""
    out = []
    for n, entry in enumerate(entries, 1):
        event = event_of(entry, seq=n)
        if event is not None:
            out.append(event)
    return out


def streams(events):
    grouped = collections.OrderedDict()
    for event in events:
        grouped.setdefault((event.get("session"), event.get("agent")), []).append(event)
    return grouped


def allowed(event, conf):
    """The allow entry this event matches, or None."""
    for item in conf["allow"]:
        if item["tool"] == event["tool"] and re.search(item.get("input") or "", event.get("input") or ""):
            return item
    return None


def longest_same_result(group):
    """The longest run of consecutive occurrences (of one call) that ended ok with the same result hash."""
    best = run = 0
    last = None
    for event in group:
        if event["status"] == "ok" and event["result"] and event["result"] == last:
            run += 1
        elif event["status"] == "ok" and event["result"]:
            run = 1
        else:
            run = 0
        last = event["result"] if event["status"] == "ok" else None
        best = max(best, run)
    return best


def finding(category, stream, group, **extra):
    first, last = group[0], group[-1]
    out = {"category": category, "session": stream[0], "agent": stream[1], "tools": [first["tool"]],
           "args": [first["args"]], "result": None, "count": len(group), "first": first.get("seq"),
           "last": last.get("seq"), "last_pos": last.get("_pos")}
    out.update(extra)
    return out


def detect_stream(stream, events, conf):
    """Findings for one stream (events in order)."""
    for pos, event in enumerate(events):
        event["_pos"] = pos
    window = conf["window"]
    found, ping_keys = [], set()
    # ping_pong: A B A B ...
    run_start = None
    for i in range(len(events) + 1):
        ok = (i < len(events) and i >= 2 and (events[i]["tool"], events[i]["args"]) == (events[i - 2]["tool"], events[i - 2]["args"])
              and (events[i]["tool"], events[i]["args"]) != (events[i - 1]["tool"], events[i - 1]["args"]))
        if ok and run_start is None:
            run_start = i - 2
        if not ok and run_start is not None:
            group = events[run_start:i]
            if len(group) >= conf["ping_pong"]:
                a, b = group[0], group[1]
                found.append(finding("ping_pong", stream, group, tools=[a["tool"], b["tool"]], args=[a["args"], b["args"]]))
                ping_keys |= {(a["tool"], a["args"]), (b["tool"], b["args"])}
            run_start = None
    # repeat / retry_same_error / poll_no_progress, per key
    positions = collections.OrderedDict()
    for event in events:
        positions.setdefault((event["tool"], event["args"]), []).append(event)
    for key, occurrences in positions.items():
        best = {"retry_same_error": None, "poll_no_progress": None, "repeat": None}
        start = 0
        for end in range(len(occurrences)):
            while occurrences[end]["_pos"] - occurrences[start]["_pos"] >= window:
                start += 1
            group = occurrences[start:end + 1]
            errors = collections.Counter(e["result"] for e in group if e["status"] == "error")
            if errors:
                result, n = errors.most_common(1)[0]
                if n >= conf["retry_errors"] and (best["retry_same_error"] is None or n > best["retry_same_error"][0]):
                    best["retry_same_error"] = (n, [e for e in group if e["status"] == "error" and e["result"] == result], result)
            n = longest_same_result(group)
            if n >= conf["poll"] and (best["poll_no_progress"] is None or n > best["poll_no_progress"][0]):
                best["poll_no_progress"] = (n, group, group[-1]["result"])
            if len(group) >= conf["repeat"] and (best["repeat"] is None or len(group) > best["repeat"][0]):
                best["repeat"] = (len(group), group, None)
        allow = allowed(occurrences[0], conf)
        for category in ("retry_same_error", "poll_no_progress", "repeat"):
            hit = best[category]
            if hit is None:
                continue
            if category != "retry_same_error" and allow is not None and hit[0] < allow.get("max", float("inf")):
                continue
            if category in ("repeat", "poll_no_progress") and key in ping_keys:
                continue
            found.append(finding(category, stream, hit[1], count=hit[0], result=hit[2]))
            break
    # bad_args: one tool's calls rejected for their arguments
    by_tool = collections.OrderedDict()
    for event in events:
        if event.get("error_class") == "validation":
            by_tool.setdefault(event["tool"], []).append(event)
    for tool, rejected in by_tool.items():
        start, best = 0, None
        for end in range(len(rejected)):
            while rejected[end]["_pos"] - rejected[start]["_pos"] >= window:
                start += 1
            group = rejected[start:end + 1]
            if len(group) >= conf["bad_args"] and (best is None or len(group) > len(best)):
                best = group
        if best:
            found.append(finding("bad_args", stream, best, args=sorted({e["args"] for e in best})))
    # child_error_unhandled: a failed subagent call with nothing after it
    if events and events[-1]["tool"] in conf["child_tools"] and events[-1]["status"] == "error":
        found.append(finding("child_error_unhandled", stream, [events[-1]], result=events[-1]["result"]))
    return found


def detect(events, conf=None):
    """All findings over a list of events (pure: the events are copied, nothing is read or written)."""
    conf = conf or config()
    out = []
    for stream, evs in streams([dict(e) for e in events]).items():
        out += detect_stream(stream, evs, conf)
    return out


def coverage(events, conf=None):
    """What the input lets us check: error text (bad_args) and subagent results (child_error_unhandled)."""
    conf = conf or config()
    return {"error_text": any(e.get("error_text_known") for e in events),
            "child_results": any(e["tool"] in conf["child_tools"] and e["status"] is not None for e in events)}


def should_remind(count, threshold):
    """At the threshold, then 2x, 4x, 8x ...: a long legitimate wait does not fill the context."""
    if not threshold or count < threshold or count % threshold:
        return False
    times = count // threshold
    return times & (times - 1) == 0


def hook_check(history, pending, conf=None):
    """The finding to remind of for the call about to run, or None. history: events of the same stream, in order;
    pending: the event of the call (status None)."""
    conf = conf or config()
    events = [dict(e) for e in history if (e.get("session"), e.get("agent")) == (pending.get("session"), pending.get("agent"))]
    events = events[-conf["window"] * 2:] + [dict(pending, status=None, result=None)]
    stream = (pending.get("session"), pending.get("agent"))
    key = (pending["tool"], pending["args"])
    last = len(events) - 1
    for hit in detect_stream(stream, events, conf):
        if hit["category"] == "ping_pong":
            mine = hit["last_pos"] == last
        elif hit["category"] in ("repeat", "retry_same_error", "poll_no_progress"):
            mine = (hit["tools"][0], hit["args"][0]) == key
        else:
            mine = False
        if mine and should_remind(hit["count"], conf[THRESHOLD[hit["category"]]]):
            return hit
    return None


def describe(hit):
    """One line about a finding: names, hashes, counts; never argument text."""
    tools, args = ",".join(hit["tools"]), ",".join(hit["args"])
    seq = f"{hit['first']}..{hit['last']}" if hit["first"] != hit["last"] else f"{hit['first']}"
    extra = f" result={hit['result']}" if hit.get("result") else ""
    session = (hit["session"] or "-")[:8] + (f" agent={hit['agent'][:8]}" if hit.get("agent") else "")
    if hit["category"] == "bad_args":
        args = f"{len(hit['args'])}_distinct"
    return f"LOOP {hit['category']} tool={tools} args={args} count={hit['count']}{extra} seq={seq} session={session}"


def reminder(hit, window):
    what = {"repeat": "the same call {n} times (same input hash {a}) in the last {w} calls",
            "retry_same_error": "the same call failed {n} times with the same error (input hash {a})",
            "poll_no_progress": "the same poll {n} times with an unchanged result (input hash {a})",
            "ping_pong": "two calls in turn for {n} calls ({t})"}[hit["category"]]
    text = what.format(n=hit["count"], a=hit["args"][0], w=window, t=",".join(hit["tools"]))
    return (f"loop_guard reminder [{hit['category']}]: {hit['tools'][0]}: {text}. If it is not making progress, change "
            "the approach, or stop and report what blocks you; if this is a planned wait, carry on (reminder only, "
            "not blocked: the call runs).")


# ------------------------------------------------------------------ reading --------------------------------------

def read_log(path):
    """The entries of an action log; InputError when it is missing. A line that is not JSON is skipped."""
    path = pathlib.Path(path)
    if not path.is_file():
        raise InputError(f"no such log: {path}")
    entries = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
    return entries


def tail_entries(path, limit=TAIL_BYTES):
    """The entries in the last `limit` bytes of an action log (a cut first line is skipped); [] when it is missing."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - limit))
            raw = fh.read()
    except OSError:
        return []
    lines = raw.split(b"\n")
    if size > limit:
        lines = lines[1:]
    out = []
    for line in lines:
        try:
            entry = json.loads(line.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


def transcript_files(paths, subagents=True):
    files = []
    for name in paths:
        main = pathlib.Path(name)
        if not main.is_file():
            raise InputError(f"no transcript {main}")
        files.append(main)
        if subagents:
            files += sorted((main.parent / main.stem / "subagents").glob("*.jsonl"))
    return files


def events_from_transcripts(files):
    """Events from transcripts (via transcript_audit's reader), in the order the calls were made; error text kept
    only as a class (validation / other)."""
    reader, audit = load_sibling("transcript_audit"), load_sibling("audit_log")
    calls, results, _, _ = reader.read_calls(files)
    events = []
    for key, call in sorted(calls.items(), key=lambda kv: kv[1]["order"]):
        result = results.get(key)
        entry = {"kind": "pending", "session_id": call["session_id"], "agent_id": call["agent_id"],
                 "tool": call["tool"], "input": plain_summary(audit, call["input"])}
        error_text = None
        if result is not None:
            # The output is hashed as it is, not masked first like an action-log line: the hash is only compared
            # with other hashes of the same input and never printed, and masking every output made a week of
            # transcripts several times slower (2.4.0 measurement).
            if result["is_error"]:
                error_text = reader.content_text(result["content"])
                status, output = ("interrupted" if error_text.startswith(reader.INTERRUPT) else "error"), error_text
            else:
                output = result["structured"] if result["has_structured"] else result["content"]
                status = "interrupted" if isinstance(output, dict) and output.get("interrupted") is True else "ok"
                error_text = ""
            entry.update(kind="failure" if status != "ok" else "result", result={"status": status, "sha256": raw_hash(output)})
        event = event_of(entry, error_text=error_text, seq=call["order"])
        if event is not None:
            events.append(event)
    return events


def load_config(path):
    if not path:
        return config()
    try:
        raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise InputError(f"config {path}: {error}") from None
    except ValueError as error:
        raise InputError(f"config {path}: not JSON: {error}") from None
    return config(raw)


def pending_event(call):
    """The event of a PreToolUse hook call (the input masked and cut as audit_log keeps it)."""
    audit = load_sibling("audit_log")
    word = lambda k: call.get(k) if isinstance(call.get(k), str) else None  # noqa: E731
    return event_of({"kind": "pending", "session_id": word("session_id"), "agent_id": word("agent_id"),
                     "tool": word("tool_name"), "input": audit.summary(call.get("tool_input"))})


def hook_reminder(call, log, conf):
    """For hook_guard: (category, reminder text) for this PreToolUse call, or None. Never raises."""
    if os.environ.get(ENV_FLAG):
        return None
    try:
        pending = pending_event(call)
        history = events_from_entries(tail_entries(load_sibling("audit_log").expand(log)))
        hit = hook_check(history, pending, conf)
        return (hit["category"], reminder(hit, conf["window"])) if hit else None
    except Exception:  # noqa: BLE001 - a reminder is help, never a reason for the hook to fail
        return None


def summary_line(events, conf=None):
    """`LOOPS ...` for usage_mix / status: counts per category, NOT_CHECKED / NOT_VERIFIED where the input is short."""
    conf = conf or config()
    hits = collections.Counter(h["category"] for h in detect(events, conf))
    cover = coverage(events, conf)
    parts = []
    for category in CATEGORIES:
        if category == "bad_args" and not cover["error_text"]:
            parts.append("bad_args=NOT_CHECKED")
        elif category == "child_error_unhandled" and not cover["child_results"]:
            parts.append("child_error_unhandled=NOT_VERIFIED")
        else:
            parts.append(f"{category}={hits[category]}")
    return f"LOOPS {' '.join(parts)} events={len(events)} (loop_guard.py scan for details)"


def scan(a):
    conf = load_config(a.config)
    events = []
    for log in a.audit:
        events += events_from_entries(read_log(log))
    if a.transcript:
        events += events_from_transcripts(transcript_files(a.transcript, not a.no_subagents))
    if a.session:
        events = [e for e in events if (e["session"] or "").startswith(a.session)]
    if not events:
        print("LOOP_GUARD: NO_DATA events=0 (no tool call read; this is not a measured 0)")
        return 2
    hits = detect(events, conf)
    cover = coverage(events, conf)
    count = collections.Counter(h["category"] for h in hits)
    nstreams = len(streams(events))
    if a.json:
        clean = [{k: v for k, v in h.items() if k != "last_pos"} for h in hits]
        print(json.dumps({"findings": clean, "coverage": cover, "events": len(events), "streams": nstreams},
                         ensure_ascii=False, indent=1))
    else:
        for hit in hits:
            print(describe(hit))
        if not cover["error_text"]:
            print("~ NOT_CHECKED bad_args: an action log keeps no error text; add --transcript")
        if not cover["child_results"]:
            print("~ NOT_VERIFIED child_error_unhandled: no subagent (" + ", ".join(conf["child_tools"]) + ") result in the input")
        detail = " ".join(f"{c}={count[c]}" for c in CATEGORIES if count[c])
        print(f"LOOP_GUARD: FOUND {len(hits)} events={len(events)} streams={nstreams} ({detail})" if hits
              else f"LOOP_GUARD: NONE events={len(events)} streams={nstreams}")
    return 1 if hits else 0


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")  # before parse_args: --help prints during parsing
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="find loops after the fact in action logs and / or transcripts")
    s.add_argument("--audit", action="append", default=[], metavar="LOG", help="action log (audit_log.py), repeatable")
    s.add_argument("--transcript", action="append", default=[], metavar="FILE", help="transcript .jsonl, repeatable")
    s.add_argument("--no-subagents", action="store_true", help="do not read <stem>/subagents/*.jsonl beside a transcript")
    s.add_argument("--config", help="loop_guard config JSON (thresholds, allow list)")
    s.add_argument("--session", help="only streams whose session id starts with this")
    s.add_argument("--json", action="store_true", help="print JSON")
    try:
        a = ap.parse_args(argv)
    except SystemExit as stop:
        return 0 if stop.code in (0, None) else 2
    try:
        if not a.audit and not a.transcript:
            raise InputError("give --audit LOG and / or --transcript FILE")
        return scan(a)
    except InputError as error:
        print(f"LOOP_GUARD: INPUT_ERROR {error}")
        return 2
    except Exception as error:  # noqa: BLE001 - one line, no traceback
        print(f"LOOP_GUARD: INPUT_ERROR {type(error).__name__}: {error}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
