"""Keep a small, re-checkable record of a verification: command, exit code, end of the output, git HEAD and the SHA-256 of
what it produced. The full output stays out of the record and out of the conversation.

  run     run a command and write <out-dir>/<time>-<label>.json; never overwrites a record
  verify  check the record's fields, hash the artifacts again and compare; --rerun also runs the recorded command
          again first. The last line reports three things apart: integrity (artifacts unchanged), test (passed only
          when a rerun exits 0; not-rerun otherwise) and artifacts (a missing one is never OK)

A record proves what ran and which files came out, not that the result is right.
Do not put secrets in the command: it is stored as written, and so is the end of its output.

Exit codes of run: the command's own; 124 timed out; 127 command not found; 3 the command passed but an artifact is missing.
Exit codes of verify: 0 OK; 1 something differs, failed or is missing; 2 could not read the record, or it is not one.
"""
import argparse
import collections
import datetime
import hashlib
import json
import locale
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time

MAX_LINE = 400
SHA = re.compile(r"[0-9a-fA-F]{7,40}")
# field: type a record written by `run` has; a record missing one, or with another type, is not evidence
RECORD_FIELDS = {"schema": int, "label": str, "command": (list, str), "cwd": str, "started": str, "finished": str,
                 "exit_code": int, "timed_out": bool, "git": dict, "artifacts": list}
CORE_FIELDS = ("command", "exit_code", "artifacts")  # a record without `schema` (legacy) must still have these


def record_problems(record):
    """Why a parsed JSON value is not a complete evidence record; empty when it is one.
    Without `schema` only CORE_FIELDS are required (the caller reports it as legacy)."""
    if not isinstance(record, dict):
        return ["not a JSON object"]
    out = []
    for key in (CORE_FIELDS if "schema" not in record else RECORD_FIELDS):
        kind = RECORD_FIELDS[key]
        names = " or ".join(k.__name__ for k in (kind if isinstance(kind, tuple) else (kind,)))
        if key not in record:
            out.append(f"missing field {key}")
        elif not isinstance(record[key], kind) or (kind is int and isinstance(record[key], bool)):
            out.append(f"field {key} is not {names}")
    if isinstance(record.get("command"), (list, str)) and not record["command"]:
        out.append("command is empty")
    git = record.get("git")
    if isinstance(git, dict) and git.get("head") is not None and not (isinstance(git["head"], str) and SHA.fullmatch(git["head"])):
        out.append(f"git.head is not a commit hash: {git['head']}")
    for n, item in enumerate(record.get("artifacts") or [], 1):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or "sha256" not in item:
            out.append(f"artifact {n} has no path or sha256")
        elif item["sha256"] is not None and not (isinstance(item["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", item["sha256"])):
            out.append(f"artifact {n}: sha256 is not 64 hex digits")
    return out


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def hash_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_artifact(path):
    """A file's SHA-256, or for a folder the SHA-256 of its sorted `relative path + file hash` lines."""
    p = pathlib.Path(path).resolve()
    if p.is_file():
        return {"path": str(p), "kind": "file", "size": p.stat().st_size, "sha256": hash_file(p)}
    if p.is_dir():
        files = sorted((f for f in p.rglob("*") if f.is_file()), key=lambda f: f.relative_to(p).as_posix())
        digest = hashlib.sha256()
        for f in files:
            digest.update(f"{f.relative_to(p).as_posix()}\0{hash_file(f)}\n".encode("utf-8"))
        return {"path": str(p), "kind": "folder", "size": sum(f.stat().st_size for f in files),
                "files": len(files), "sha256": digest.hexdigest()}
    return {"path": str(p), "kind": "missing", "sha256": None}


def decode(raw):
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(locale.getpreferredencoding(False), "replace")


def execute(command, cwd, tail_lines, timeout, log_path):
    """Run a command; returns (exit code, timed out, total lines, last lines). Keeps only the tail in memory."""
    tail, count = collections.deque(maxlen=tail_lines), [0]
    program = shutil.which(command[0], path=None) or command[0]
    try:
        proc = subprocess.Popen([program, *command[1:]], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as error:
        return 127, False, 0, [f"could not start: {error}"]

    def read():
        log = open(log_path, "wb") if log_path else None
        try:
            for raw in proc.stdout:
                count[0] += 1
                tail.append(decode(raw).rstrip()[:MAX_LINE])
                if log:
                    log.write(raw)
        finally:
            if log:
                log.close()

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    timed_out = False
    try:
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        proc.wait()
        code = 124
    reader.join(5)
    return code, timed_out, count[0], list(tail)


def git_state(cwd):
    def ask(*args):
        done = subprocess.run(["git", "-C", cwd, *args], capture_output=True)
        return done.stdout.decode("utf-8", "replace") if done.returncode == 0 else None

    head = ask("rev-parse", "HEAD")
    status = ask("status", "--porcelain")
    return {"head": head.strip() if head else None, "dirty": bool(status.strip()) if status is not None else None}


def cmd_run(a):
    command = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    if not command:
        print("EVIDENCE: NOT_RUN no command after --")
        return 2
    cwd = str(pathlib.Path(a.cwd).resolve())
    started, clock = now(), time.monotonic()
    code, timed_out, lines, tail = execute(command, cwd, a.tail, a.timeout, a.log)
    artifacts = [hash_artifact(pathlib.Path(cwd, path)) for path in a.artifact]
    missing = sum(1 for item in artifacts if item["sha256"] is None)
    record = {"schema": 1, "label": a.label, "command": command, "cwd": cwd, "started": started, "finished": now(),
              "seconds": round(time.monotonic() - clock, 1), "exit_code": code, "timed_out": timed_out,
              "git": git_state(cwd), "output_lines": lines, "output_tail": tail, "log": a.log, "artifacts": artifacts}

    out_dir = pathlib.Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.datetime.now():%Y%m%dT%H%M%S}-{re.sub(r'[^A-Za-z0-9_.-]', '_', a.label)}"
    for n in range(1000):
        path = out_dir / f"{stem}{f'-{n}' if n else ''}.json"
        try:
            with open(path, "x", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=1)
            break
        except FileExistsError:
            continue
    if a.verbose:
        print("\n".join(tail))
    print(f"EVIDENCE: exit={code} lines={lines} artifacts={len(artifacts)} missing={missing} file={path}")
    return 3 if code == 0 and missing else code


def cmd_verify(a):
    try:
        record = json.loads(pathlib.Path(a.record).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        print(f"EVIDENCE_VERIFY: NOT_RUN {error}")
        return 2
    bad = record_problems(record)
    if bad:
        for line in bad:
            print(f"  - {line}")
        print(f"EVIDENCE_VERIFY: NOT_RUN not an evidence record ({len(bad)} problem{'s' if len(bad) > 1 else ''})")
        return 2
    if "schema" not in record:
        print("  ~ legacy record without `schema`: only command, exit_code and artifacts checked")
    artifacts, command, cwd, expected = record["artifacts"], record["command"], record.get("cwd", "."), record["exit_code"]
    lines, changed, missing = [], 0, 0
    test = "not-rerun" if expected == 0 else f"failed(recorded exit {expected})"
    if a.rerun:
        print(f"rerun in {cwd}: {command}")
        code = execute(command, cwd, 1, a.timeout, None)[0]
        if code != expected:
            lines.append(f"exit code {expected} -> {code}")
        test = "passed" if code == 0 else f"failed(rerun exit {code})"
    for item in artifacts:
        if item["sha256"] is None:
            missing += 1
            lines.append(f"artifact missing when recorded: {item['path']}")
            continue
        now_hash = hash_artifact(item["path"])["sha256"]
        if now_hash is None:
            missing += 1
            lines.append(f"artifact gone: {item['path']}")
        elif now_hash != item["sha256"]:
            changed += 1
            lines.append(f"artifact changed: {item['path']}")
    for line in lines:
        print(f"  - {line}")
    ok = not lines and not test.startswith("failed")
    print(f"EVIDENCE_VERIFY: {'OK' if ok else 'MISMATCH'} integrity={'changed' if changed else 'same'} test={test} "
          f"artifacts={len(artifacts)} missing={missing} rerun={'yes' if a.rerun else 'no'}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="action", required=True)
    run = sub.add_parser("run", help="run a command and write a record")
    run.add_argument("--out-dir", required=True, help="folder for the records (outside the repo)")
    run.add_argument("--label", required=True, help="what this verifies, for example AC-1")
    run.add_argument("--artifact", action="append", default=[], help="file or folder to hash; repeatable")
    run.add_argument("--cwd", default=".", help="folder to run in (default: current folder)")
    run.add_argument("--tail", type=int, default=40, help="last output lines to keep (default 40)")
    run.add_argument("--timeout", type=float, help="seconds before the command is killed")
    run.add_argument("--log", help="also write the full output to this file")
    run.add_argument("--verbose", action="store_true", help="also print the kept lines")
    run.add_argument("cmd", nargs=argparse.REMAINDER, help="-- command and arguments")
    verify = sub.add_parser("verify", help="compare artifacts with a record")
    verify.add_argument("record")
    verify.add_argument("--rerun", action="store_true", help="run the recorded command again first")
    verify.add_argument("--timeout", type=float, help="seconds before the rerun is killed")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    return cmd_run(a) if a.action == "run" else cmd_verify(a)


if __name__ == "__main__":
    sys.exit(main())
