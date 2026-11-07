"""Hash-chained action log (JSONL) that Claude Code hooks write, and the checks that read it.

  python -I -X utf8 audit_log.py append --log FILE      PostToolUse / PostToolUseFailure hook (stdin: the hook JSON)
  python -I -X utf8 audit_log.py verify --log FILE [--from N] [--to M] [--anchor-log LOG]
                                 [--anchor-rev REV --anchor-path PATH [--repo DIR]] [--cite "AUDIT_RANGE ..."]
  python -I -X utf8 audit_log.py head --log FILE        print AUDIT_HEAD file=... seq=n sha=... (the Director's anchor)
  python -I -X utf8 audit_log.py cite --log FILE --from A --to B   print AUDIT_RANGE ... for a TASK REPORT
  python -I -X utf8 audit_log.py recover --log FILE     after a break: keep a copy, close the gap with a recovery line

One JSON object per line: seq, ts, session_id, agent_id, tool, tool_use_id, kind (result / failure / decision /
recovery), input
(the tool input masked by secret_mask.py, at most 500 characters; since 2.2.0 each string is masked before the input
is serialized, and a secret-named field is replaced whole), result (status ok / error / interrupted, or the
decision deny / ask / remind / pause; with the sha256 and length of the masked output, never the output itself), duration_ms,
rule (decision lines), prev (the hash of the line before; 64 zeros for seq 1) and hash (sha256 of the line's other
fields as sorted compact JSON). hook_guard.py --audit FILE adds the decision lines, so a blocked call is on the chain.
Lines are added under a lock file (FILE.lock, os.open O_CREAT|O_EXCL; busy for 5 s -> exit 1; a lock older than 30 s
is taken over). append also masks the Bash tool's output: when stdout or stderr holds a secret it prints
updatedToolOutput with the same fields, masked (a PostToolUse field; the PowerShell tool's output is NOT_VERIFIED and
left as it is). Masking the output and writing the line are two results: when the line cannot be written append exits
1, except that a masked output is still returned (exit 0) and then additionalContext and stderr say the line is missing.

recover (2.2.0) is for a log that verify calls broken (a line cut off by a crash, a line that is not JSON, a line off
the chain). Under the lock it copies the whole file, untouched, to FILE.damaged-<UTC time>, keeps every line up to the
first bad one (so the last good hash and every AUDIT_HEAD anchor before it stay valid) and adds one kind=recovery line
on the chain: damage = first_line, lines, bytes and sha256 of the part taken out, the copy's name and its sha256. Then
append goes on as usual. verify prints `GAP seq=n: ...` for each recovery line (not a break), counts gaps=n, and is
BROKEN when the copy next to the log no longer has that sha256, or is missing while an anchor is checked (2.2.0; without
an anchor a missing copy prints a `~ warning` line). Lines after the first bad one stay in the copy
only. A log with nothing broken is left as it is (exit 0); a missing log gives exit 2.

verify recomputes the chain and prints the first break (BROKEN seq=n / BROKEN line=n) with exit 1; a missing log,
anchor commit or file gives exit 2. A chain that was rewritten whole, every hash recomputed, passes on its own: only an
anchor catches it. --anchor-log reads AUDIT_HEAD lines from a file; --anchor-rev reads them from DIRECTOR_LOG as
committed (git show REV:PATH), so an edited working copy of the LOG does not help. Every AUDIT_HEAD line for this log
(same absolute path) must still be on the chain with the same hash; none at all is a failure too. Lines added after
the last anchor are covered only by the chain itself, so cutting them off is caught only by a later anchor.

FILE may hold two placeholders, filled in when the command runs (append, verify, head, cite and hook_guard --audit):
  {worktree}   DW_WORKER_NAME, else the name of CLAUDE_PROJECT_DIR, else of the current folder
  {container}  the first 12 characters of the container ID (from /proc/self/mountinfo, else the host name when
               /.dockerenv exists), else "host"
so workers that share a worktree name in different containers write separate files, each its own chain. Characters
other than letters, digits, ".", "_" and "-" become "_". Any other {word} is an error (append exit 1, others exit 2).
"""
import argparse
import contextlib
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import time

GENESIS = "0" * 64
INPUT_LIMIT = 500
LOCK_WAIT_S = 5.0
STALE_LOCK_S = 30.0
KINDS = {"PostToolUse": "result", "PostToolUseFailure": "failure"}
HEAD_LINE = re.compile(r"AUDIT_HEAD file=(.+?) seq=(\d+) sha=([0-9a-f]{64})[ \t]*$", re.M)
RANGE_LINE = re.compile(r"AUDIT_RANGE file=(.+?) seq=(\d+)\.\.(\d+) first=([0-9a-f]{64}) last=([0-9a-f]{64})\s*$")


def _load_mask():
    spec = importlib.util.spec_from_file_location("secret_mask", pathlib.Path(__file__).with_name("secret_mask.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MASKER = _load_mask()
MASK, MASK_TREE = _MASKER.mask, _MASKER.mask_tree


class AuditError(Exception):
    """The log cannot be written (lock busy, last line broken)."""


class CannotRun(Exception):
    """verify / head / cite cannot run: exit 2."""


MOUNTINFO = "/proc/self/mountinfo"
DOCKERENV = "/.dockerenv"
PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
CONTAINER_ID = re.compile(r"/containers/([0-9a-f]{64})/")


def safe_name(text):
    return re.sub(r"[^A-Za-z0-9._-]", "_", text) or "_"


def worker_name(folder=None):
    """DW_WORKER_NAME, else the name of FOLDER, CLAUDE_PROJECT_DIR or the current folder."""
    name = os.environ.get("DW_WORKER_NAME")
    if not name:
        name = pathlib.Path(folder or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve().name
    return safe_name(name)


def container_id(mountinfo=None, dockerenv=None):
    """12 characters of the container ID, or "host" outside a container."""
    try:
        with open(mountinfo or MOUNTINFO, encoding="utf-8", errors="replace") as fh:
            found = CONTAINER_ID.search(fh.read())
        if found:
            return found.group(1)[:12]
    except OSError:
        pass
    if os.path.exists(dockerenv or DOCKERENV):
        import socket
        return safe_name(socket.gethostname())[:64]
    return "host"


def expand(path, folder=None, only=None, mountinfo=None, dockerenv=None):
    """PATH with {worktree} and {container} filled in (only those in ONLY when given); other {word} -> ValueError."""
    path = str(path)
    for word in PLACEHOLDER.findall(path):
        if word not in ("worktree", "container"):
            raise ValueError(f"unknown placeholder {{{word}}} in {path} (only {{worktree}} and {{container}})")
    if (only is None or "worktree" in only) and "{worktree}" in path:
        path = path.replace("{worktree}", worker_name(folder))
    if (only is None or "container" in only) and "{container}" in path:
        path = path.replace("{container}", container_id(mountinfo, dockerenv))
    return path


def canonical(fields):
    return json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(entry):
    return hashlib.sha256(canonical({k: v for k, v in entry.items() if k != "hash"}).encode("utf-8")).hexdigest()


def text_of(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)


def summary(tool_input):
    # mask each string first, then serialize (F12): masking the JSON text missed a quoted secret whose quotes JSON
    # escapes. No second pass over the JSON: it would turn `"secret_mode": false` into text that is not JSON
    text = text_of(MASK_TREE({} if tool_input is None else tool_input))
    return text if len(text) <= INPUT_LIMIT else text[:INPUT_LIMIT - 1] + "…"


def output_record(status, output):
    text, _ = MASK(text_of("" if output is None else output))
    return {"status": status, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "length": len(text)}


def common(call):
    def word(key):
        return call.get(key) if isinstance(call.get(key), str) else None
    return {"session_id": word("session_id"), "agent_id": word("agent_id"), "tool": word("tool_name"),
            "tool_use_id": word("tool_use_id"), "input": summary(call.get("tool_input"))}


def hook_entry(call):
    """The fields of one PostToolUse / PostToolUseFailure call (failure also when the event is unnamed and has error)."""
    kind = KINDS.get(call.get("hook_event_name"), "failure" if "error" in call else "result")
    if kind == "failure":
        result = output_record("interrupted" if call.get("is_interrupt") is True else "error", call.get("error"))
    else:
        response = call.get("tool_response")
        interrupted = isinstance(response, dict) and response.get("interrupted") is True
        result = output_record("interrupted" if interrupted else "ok", response)
    duration = call.get("duration_ms")
    duration = duration if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None
    return dict(common(call), kind=kind, result=result, duration_ms=duration)


def decision_entry(call, decision, rule):
    """The fields of a hook_guard decision (deny / ask / remind / pause) and the rule that gave it."""
    return dict(common(call), kind="decision", result={"status": decision}, rule=rule, duration_ms=None)


@contextlib.contextmanager
def locked(path):
    lock = f"{path}.lock"
    end = time.monotonic() + LOCK_WAIT_S
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except (FileExistsError, PermissionError):  # Windows: PermissionError while the holder deletes it
            try:
                if time.time() - os.path.getmtime(lock) > STALE_LOCK_S:
                    os.remove(lock)
                    continue
            except OSError:
                pass
            if time.monotonic() > end:
                raise AuditError(f"lock {lock} still held after {LOCK_WAIT_S:g} s")
            time.sleep(0.01)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            os.remove(lock)


def last_entry(path):
    """The last line of the log, checked; None for a missing or empty log."""
    try:
        size = os.path.getsize(path)
    except FileNotFoundError:
        return None
    with open(path, "rb") as fh:
        fh.seek(max(0, size - 65536))
        tail = fh.read()
    if not tail.strip():
        return None
    if not tail.endswith(b"\n"):
        raise AuditError("the last line is cut off; run verify, then recover")
    try:
        entry = json.loads(tail.rstrip(b"\n").rsplit(b"\n", 1)[-1].decode("utf-8"))
    except ValueError:
        raise AuditError("the last line is not JSON; run verify, then recover") from None
    if not isinstance(entry, dict) or type(entry.get("seq")) is not int or entry.get("hash") != digest(entry):
        raise AuditError("the last line does not check out; run verify, then recover")
    return entry


def append_entry(path, fields):
    """Add one line after the last; returns the entry written."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path):
        last = last_entry(path)
        entry = {k: v for k, v in fields.items() if k != "hash"}
        entry.update(seq=last["seq"] + 1 if last else 1, prev=last["hash"] if last else GENESIS,
                     ts=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds"))
        entry["hash"] = digest(entry)
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(canonical(entry) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    return entry


def good_prefix(raw):
    """(bytes of the lines before the first break, the last good entry or None, how many good lines)."""
    pos, last, count = 0, None, 0
    while True:
        end = raw.find(b"\n", pos)
        if end < 0:
            return pos, last, count
        try:
            entry = json.loads(raw[pos:end].decode("utf-8"))
        except ValueError:
            return pos, last, count
        if (not isinstance(entry, dict) or type(entry.get("seq")) is not int or entry["seq"] != (last["seq"] if last else 0) + 1
                or entry.get("prev") != (last["hash"] if last else GENESIS) or entry.get("hash") != digest(entry)):
            return pos, last, count
        pos, last, count = end + 1, entry, count + 1


def recover(path):
    """Keep a copy of a broken log and close the gap with a recovery line; None when nothing is broken."""
    path = pathlib.Path(path)
    with locked(path):
        raw = path.read_bytes()
        keep, last, good = good_prefix(raw)
        if keep == len(raw):
            return None
        copy = path.with_name(f"{path.name}.damaged-{datetime.datetime.now(datetime.timezone.utc):%Y%m%dT%H%M%S%fZ}")
        with open(copy, "xb") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        cut = raw[keep:]
        entry = {"session_id": None, "agent_id": None, "tool": None, "tool_use_id": None, "input": "", "kind": "recovery",
                 "result": {"status": "recovered"}, "duration_ms": None,
                 "damage": {"first_line": good + 1, "lines": cut.count(b"\n") + (not cut.endswith(b"\n")),
                            "bytes": len(cut), "sha256": hashlib.sha256(cut).hexdigest(), "copy": copy.name,
                            "copy_sha256": hashlib.sha256(raw).hexdigest()},
                 "seq": last["seq"] + 1 if last else 1, "prev": last["hash"] if last else GENESIS,
                 "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")}
        entry["hash"] = digest(entry)
        temp = path.with_name(f"{path.name}.recover-tmp")
        with open(temp, "wb") as fh:
            fh.write(raw[:keep] + (canonical(entry) + "\n").encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, path)
    return entry


def gaps(entries, log):
    """[(GAP line, problem or None)] for each recovery line; a problem when the copy beside the log was changed."""
    out = []
    for _, entry in entries:
        damage = entry.get("damage")
        if entry.get("kind") != "recovery" or not isinstance(damage, dict):
            continue
        name = str(damage.get("copy"))
        copy = pathlib.Path(log).with_name(pathlib.Path(name).name)
        state, problem = "copy not found", None
        if copy.is_file():
            state = "copy checked"
            if hashlib.sha256(copy.read_bytes()).hexdigest() != damage.get("copy_sha256"):
                state, problem = "copy changed", f"seq={entry.get('seq')}: the copy {name} is not the one recovered"
        out.append((f"GAP seq={entry.get('seq')}: from line {damage.get('first_line')} ({damage.get('lines')} lines, "
                    f"{damage.get('bytes')} bytes, sha256={str(damage.get('sha256'))[:16]}) kept in {name}, {state}", problem))
    return out


def masked_output(call):
    """The Bash tool output with secrets masked, same fields; None when there is nothing to mask."""
    response = call.get("tool_response")
    if call.get("tool_name") != "Bash" or call.get("hook_event_name", "PostToolUse") != "PostToolUse" or not isinstance(response, dict):
        return None
    out = dict(response)
    for key in ("stdout", "stderr"):
        if isinstance(response.get(key), str):
            out[key] = MASK(response[key])[0]
    return out if out != response else None


def load(path):
    """[(line number, entry)]; a line that is not a JSON object is a break."""
    if not os.path.isfile(path):
        raise CannotRun(f"{path}: no such log")
    entries = []
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        for no, line in enumerate(fh, 1):
            try:
                entry = json.loads(line)
            except ValueError:
                return entries, f"line={no}: not JSON"
            if not isinstance(entry, dict):
                return entries, f"line={no}: not a JSON object"
            entries.append((no, entry))
    return entries, None


def chain_problem(entries, low=None, high=None):
    """The first break among the entries whose seq is in low..high (all when None), checked against the line before."""
    prev_hash, prev_seq = GENESIS, 0
    for no, entry in entries:
        seq = entry.get("seq")
        if type(seq) is not int:
            return f"line={no}: no seq"
        if (low is None or seq >= low) and (high is None or seq <= high):
            if seq != prev_seq + 1:
                return f"seq={seq}: comes after seq={prev_seq}"
            if entry.get("prev") != prev_hash:
                return f"seq={seq}: prev is not the hash of the line before"
            if entry.get("hash") != digest(entry):
                return f"seq={seq}: hash does not match the line"
        prev_hash, prev_seq = entry.get("hash"), seq
    return None


def same_file(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def anchor_problems(entries, text, log):
    hashes = {e.get("seq"): e.get("hash") for _, e in entries}
    heads = [(int(seq), sha) for name, seq, sha in HEAD_LINE.findall(text) if same_file(name, log)]
    if not heads:
        return ["anchor: no AUDIT_HEAD line for this log"], 0
    out = []
    for seq, sha in heads:
        if seq and seq not in hashes:
            out.append(f"anchor seq={seq}: not in the log (cut off?)")
        elif (hashes.get(seq) if seq else GENESIS) != sha:
            out.append(f"anchor seq={seq}: hash differs (rewritten?)")
    return out, len(heads)


def committed_text(repo, rev, path):
    if rev.startswith("-"):
        raise CannotRun(f"anchor commit {rev} not found")
    found = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"],
                           capture_output=True, text=True)
    if found.returncode != 0:
        raise CannotRun(f"anchor commit {rev} not found")
    shown = subprocess.run(["git", "-C", repo, "show", f"{found.stdout.strip()}:{path}"], capture_output=True,
                           encoding="utf-8", errors="replace")
    if shown.returncode != 0:
        raise CannotRun(f"{path} is not in commit {rev}")
    return shown.stdout


def checked(log):
    """(entries, the first break of the whole chain or None)."""
    entries, bad = load(log)
    return entries, bad or chain_problem(entries)


def show(log):
    return pathlib.Path(log).resolve().as_posix()


def cmd_verify(a):
    cite = None
    if a.cite is not None:
        cite = RANGE_LINE.match(a.cite.strip())
        if not cite:
            raise CannotRun("--cite is not an AUDIT_RANGE line")
        if a.log and not same_file(a.log, cite.group(1)):
            raise CannotRun("--cite names another log than --log")
    log = a.log or (cite.group(1) if cite else None)
    if not log:
        raise CannotRun("verify needs --log or --cite")
    if bool(a.anchor_rev) != bool(a.anchor_path):
        raise CannotRun("--anchor-rev and --anchor-path go together")
    entries, bad = load(log)
    problems = [bad or chain_problem(entries, a.from_seq, a.to_seq)]
    texts = []
    if a.anchor_log:
        if not os.path.isfile(a.anchor_log):
            raise CannotRun(f"{a.anchor_log}: no such anchor file")
        texts.append(pathlib.Path(a.anchor_log).read_text(encoding="utf-8", errors="replace"))
    if a.anchor_rev:
        texts.append(committed_text(a.repo, a.anchor_rev, a.anchor_path))
    found_gaps = gaps(entries, log)
    for line, problem in found_gaps:
        print(line)
        problems.append(problem)
        if line.endswith(", copy not found"):
            seq = line.split(":", 1)[0].split()[1]
            if texts:
                problems.append(f"{seq}: the copy is missing, so the cut lines of an anchored log cannot be checked")
            else:
                print(f"  ~ warning {seq}: the copy is not beside the log; keep it with the log, without it the cut lines"
                      " cannot be checked")
    anchors = 0
    for text in texts:
        found, count = anchor_problems(entries, text, log)
        problems += found
        anchors += count
    if cite:
        first, last = int(cite.group(2)), int(cite.group(3))
        hashes = {e.get("seq"): e.get("hash") for _, e in entries}
        problems.append(bad or chain_problem(entries))
        if (hashes.get(first), hashes.get(last)) != (cite.group(4), cite.group(5)):
            problems.append(f"cite seq={first}..{last}: the lines are not the ones cited")
    problems = list(dict.fromkeys(p for p in problems if p))
    for problem in problems:
        print(f"BROKEN {problem}")
    head = entries[-1][1] if entries else {}
    print(f"AUDIT_VERIFY file={show(log)} entries={len(entries)} head_seq={head.get('seq', 0)}"
          f"{f' anchors={anchors}' if texts else ''}{f' gaps={len(found_gaps)}' if found_gaps else ''}"
          f"{' cite=checked' if cite else ''} {'BROKEN' if problems else 'OK'}")
    if bad or chain_problem(entries):
        print(f"  ~ to go on writing: audit_log.py recover --log {log} (keeps a copy, adds a recovery line)")
    return 1 if problems else 0


def cmd_head(a):
    entries, problem = checked(a.log)
    if problem:
        print(f"BROKEN {problem}")
        return 1
    last = entries[-1][1] if entries else {"seq": 0, "hash": GENESIS}
    print(f"AUDIT_HEAD file={show(a.log)} seq={last['seq']} sha={last['hash']}")
    return 0


def cmd_cite(a):
    if a.from_seq < 1 or a.to_seq < a.from_seq:
        raise CannotRun("--from must be 1 or more and --to not below it")
    entries, problem = checked(a.log)
    if problem:
        print(f"BROKEN {problem}")
        return 1
    hashes = {e.get("seq"): e.get("hash") for _, e in entries}
    if a.to_seq not in hashes or a.from_seq not in hashes:
        raise CannotRun(f"seq {a.from_seq}..{a.to_seq} is not in the log")
    print(f"AUDIT_RANGE file={show(a.log)} seq={a.from_seq}..{a.to_seq} first={hashes[a.from_seq]} last={hashes[a.to_seq]}")
    return 0


def cmd_recover(a):
    if not os.path.isfile(a.log):
        raise CannotRun(f"{a.log}: no such log")
    entry = recover(a.log)
    if entry is None:
        print(f"AUDIT_RECOVER file={show(a.log)} nothing broken; left as it is")
        return 0
    damage = entry["damage"]
    print(f"AUDIT_RECOVER file={show(a.log)} kept={damage['first_line'] - 1} lines; took out {damage['lines']} lines "
          f"({damage['bytes']} bytes) from line {damage['first_line']}; copy={damage['copy']} recovery seq={entry['seq']}")
    print(f"AUDIT_HEAD file={show(a.log)} seq={entry['seq']} sha={entry['hash']}")
    return 0


def cmd_append(a):
    try:
        call = json.loads(sys.stdin.read())
    except ValueError:
        call = None
    if not isinstance(call, dict):
        print("audit_log: hook input is not a JSON object; nothing written", file=sys.stderr)
        return 1
    updated = masked_output(call)
    try:
        append_entry(expand(a.log), hook_entry(call))
        failed = None
    except (AuditError, OSError, ValueError) as error:
        failed = error
    if updated is not None:
        out = {"hookEventName": "PostToolUse", "updatedToolOutput": updated}
        if failed:
            out["additionalContext"] = f"audit_log: output masked, but the audit line was NOT written: {failed}"
        print(json.dumps({"hookSpecificOutput": out}, ensure_ascii=False))
    if failed:
        print(f"audit_log: masked={'yes' if updated is not None else 'no'} written=no: {failed}", file=sys.stderr)
        return 0 if updated is not None else 1
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("append", help="hook: add one line for the call on stdin")
    p.add_argument("--log", required=True)
    p = sub.add_parser("verify", help="recompute the chain; check anchors and a cited range")
    p.add_argument("--log")
    p.add_argument("--from", dest="from_seq", type=int)
    p.add_argument("--to", dest="to_seq", type=int)
    p.add_argument("--anchor-log", help="file with AUDIT_HEAD lines (DIRECTOR_LOG.md)")
    p.add_argument("--anchor-rev", help="commit whose --anchor-path holds the AUDIT_HEAD lines")
    p.add_argument("--anchor-path", help="path of DIRECTOR_LOG inside the repo, for --anchor-rev")
    p.add_argument("--repo", default=".", help="repo for --anchor-rev (default: current folder)")
    p.add_argument("--cite", help="an AUDIT_RANGE line to check")
    p = sub.add_parser("head", help="print the AUDIT_HEAD line")
    p.add_argument("--log", required=True)
    p = sub.add_parser("cite", help="print the AUDIT_RANGE line for seq A..B")
    p.add_argument("--log", required=True)
    p.add_argument("--from", dest="from_seq", type=int, required=True)
    p.add_argument("--to", dest="to_seq", type=int, required=True)
    p = sub.add_parser("recover", help="keep a copy of a broken log and go on with a recovery line")
    p.add_argument("--log", required=True)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        if a.log and a.cmd != "append":  # append expands it itself, so a masked output still goes back
            a.log = expand(a.log)
    except ValueError as error:
        print(f"NOT_RUN {error}")
        return 2
    try:
        return {"append": cmd_append, "verify": cmd_verify, "head": cmd_head, "cite": cmd_cite,
                "recover": cmd_recover}[a.cmd](a)
    except CannotRun as error:
        print(f"NOT_RUN {error}")
        return 2
    except (AuditError, OSError) as error:
        print(f"NOT_RUN {error}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
