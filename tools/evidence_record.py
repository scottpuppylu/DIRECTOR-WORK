"""Keep a small, re-checkable record of a verification: command, exit code, end of the output, git HEAD and the SHA-256 of
what it produced. The full output stays out of the record and out of the conversation.

  run     run a command and write <out-dir>/<time>-<label>.json; never overwrites a record
  verify  check the record's fields, hash the artifacts again and compare. The last line reports three things apart:
          integrity (artifacts unchanged), test (passed only when the approved check reruns with exit 0; not-rerun
          otherwise) and artifacts (a missing one is never OK)

verify --rerun --order ORDER --dispatch-log LOG --repo REPO --candidate SHA
          runs the check the Director approved, not the command written in the record:
          1. the order's hash and REVISION must equal its latest DISPATCH line in LOG (exit 2 otherwise);
          2. the record's label names the AC; the order's `CHECKS:` line for that AC is the command (exit 2 if none);
          3. REPO's HEAD must be the candidate (40 hex digits); REPO must have no changed or untracked file, no file
             marked assume-unchanged or skip-worktree and no `refs/replace/` ref (exit 2). Git runs with replace
             objects off, so a replace ref cannot pass another tree off as the candidate's;
          4. the program is an absolute path, a path inside the candidate (`./tools/check`) or python / python3 (this
             Python); a bare name the PATH would resolve is refused (exit 2);
          5. the candidate's tree is written from git's objects into a new temporary folder, each blob's hash checked,
             and the check runs there without a shell: never in REPO's working files. A record made at another
             commit, or whose command is not the approved one, is a MISMATCH (exit 1); the record's command is only
             compared, never run. Artifacts are hashed again in that folder, at their path relative to the record's
             cwd; one that comes out different is a MISMATCH;
          6. after the check REPO is read again: a HEAD, tree, status or flag that changed is a MISMATCH (exit 1).
          The last line adds `check=AC-n source=order candidate=<12 digits>`.
          The folder holds the committed files only: no .git, no untracked or ignored files. This proves the approved
          check ran on the candidate's tree; it still runs the candidate's own test code, so it is not a sandbox.
verify --rerun-recorded
          runs the command written in the record, in its cwd: the old --rerun. Anyone who can edit the record chooses
          what runs, so it reports test=recorded-command-passed source=record, never test=passed.

A record proves what ran and which files came out, not that the result is right.
Do not put secrets in the command: it is stored as written, and so is the end of its output.

Exit codes of run: the command's own; 124 timed out; 127 command not found; 3 the command passed but an artifact is missing.
Exit codes of verify: 0 OK; 1 something differs, failed or is missing; 2 could not read the record, it is not one, or
the rerun was refused before anything ran (NOT_RUN).
"""
import argparse
import importlib.util
import collections
import datetime
import hashlib
import json
import locale
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
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
    required = CORE_FIELDS if "schema" not in record else RECORD_FIELDS
    for key, kind in RECORD_FIELDS.items():  # a field a legacy record does have must still have the right type
        names = " or ".join(k.__name__ for k in (kind if isinstance(kind, tuple) else (kind,)))
        if key not in record or (record[key] is None and key not in required):
            if key in required:
                out.append(f"missing field {key}")
        elif not isinstance(record[key], kind) or (kind is int and isinstance(record[key], bool)):
            out.append(f"field {key} is not {names}")
    if isinstance(record.get("command"), (list, str)) and not record["command"]:
        out.append("command is empty")
    elif isinstance(record.get("command"), list) and not all(isinstance(part, str) for part in record["command"]):
        out.append("command: every part must be a string")
    git = record.get("git")
    if isinstance(git, dict) and git.get("head") is not None and not (isinstance(git["head"], str) and SHA.fullmatch(git["head"])):
        out.append(f"git.head is not a commit hash: {git['head']}")
    artifacts = record.get("artifacts")
    for n, item in enumerate(artifacts if isinstance(artifacts, list) else [], 1):  # another type is reported above
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


def execute(command, cwd, tail_lines, timeout, log_path, program=None):
    """Run a command; returns (exit code, timed out, total lines, last lines). Keeps only the tail in memory.
    program: the file to start instead of looking command[0] up in PATH."""
    tail, count = collections.deque(maxlen=tail_lines), [0]
    program = program or shutil.which(command[0], path=None) or command[0]
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


def gate_module():
    """gate_check.py next to this file, for the order's hash, DISPATCH lines and CHECKS."""
    spec = importlib.util.spec_from_file_location("gate_check", pathlib.Path(__file__).resolve().parent / "gate_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Refused(Exception):
    """The trusted rerun cannot start; the message says why. Nothing has run."""


PYTHON_NAMES = {"python", "python3", "python.exe", "python3.exe"}
# git for the trusted rerun: replace objects off, no variables that point git at another repository or index
GIT_ENV = {key: value for key, value in os.environ.items()
           if key not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                          "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_REPLACE_REF_BASE")}
GIT_ENV["GIT_NO_REPLACE_OBJECTS"] = "1"


def git_trusted(repo, *args, raw=False):
    done = subprocess.run(["git", "-c", "core.useReplaceRefs=false", "-C", str(repo), *args], capture_output=True, env=GIT_ENV)
    if done.returncode:
        raise Refused(f"git {' '.join(args)} failed in {repo}: {decode(done.stderr).strip()[:200]}")
    return done.stdout if raw else decode(done.stdout).strip()


def repo_state(repo, commit):
    """What the trusted rerun requires of REPO, as a list of reasons it is not met (empty when it is)."""
    out = []
    head = git_trusted(repo, "rev-parse", "HEAD").lower()
    if head != commit:
        out.append(f"{repo} is at {head[:12]}, not the candidate {commit[:12]}; "
                   f"check it out: git worktree add --detach <dir> {commit}")
    if git_trusted(repo, "for-each-ref", "--format=%(refname)", "refs/replace/"):
        out.append(f"{repo} has refs/replace/ refs, which can show another tree under the candidate's name; "
                   "rerun in a fresh clone without them")
    if git_trusted(repo, "status", "--porcelain", "--untracked-files=all"):
        out.append(f"{repo} has changed or untracked files; rerun in a clean checkout of the candidate")
    flagged = [line[2:] for line in git_trusted(repo, "ls-files", "-v").splitlines() if line[:1] != "H"]
    if flagged:
        out.append(f"{repo} marks {len(flagged)} file(s) assume-unchanged or skip-worktree (first: {flagged[0]}), "
                   "so git status cannot see their changes; clear the flags or rerun in a fresh checkout")
    return out


def check_program(command):
    """Refuse a program the PATH would choose (R04): it must be absolute, a path inside the candidate or python."""
    first = command[0]
    if not (os.path.isabs(first) or "/" in first or "\\" in first or first.lower() in PYTHON_NAMES):
        raise Refused(f"the approved check starts {first!r}, a bare name the PATH would resolve to some program; write "
                      "an absolute path, a path inside the candidate such as ./tools/check, or python")


def program_in(command, root):
    """The file the trusted rerun starts for command[0], inside the materialized folder when it is a relative path."""
    first = command[0]
    if os.path.isabs(first):
        return first
    if first.lower() in PYTHON_NAMES:
        return sys.executable
    path = (root / first).resolve()
    if root not in path.parents or not path.is_file():
        raise Refused(f"the approved check starts {first!r}, which is not a file inside the candidate")
    return str(path)


def safe_part(part):
    if part in ("", ".", "..") or part.lower() == ".git":
        return False
    return os.name != "nt" or not (set(part) & set('\\:*?"<>|') or part != part.rstrip(" ."))


def materialize(repo, commit, dest):
    """Write the commit's tree from git's objects into dest, checking each blob's hash; returns the file count.
    A symbolic link is written as a file holding its target, a submodule as an empty folder (as git does without them)."""
    algorithm = "sha1"
    try:
        algorithm = git_trusted(repo, "rev-parse", "--show-object-format") or "sha1"
    except Refused:
        pass
    entries = []
    for raw in git_trusted(repo, "ls-tree", "-r", "-z", "--full-tree", commit, raw=True).split(b"\0"):
        if not raw:
            continue
        meta, _, name = raw.partition(b"\t")
        mode, kind, sha = meta.decode("ascii").split()
        try:
            path = name.decode("utf-8")
        except UnicodeDecodeError:
            raise Refused(f"the candidate has a path that is not UTF-8: {name[:80]!r}")
        if not all(safe_part(part) for part in path.split("/")):
            raise Refused(f"the candidate has a path that cannot be written safely here: {path}")
        entries.append((mode, kind, sha, path))
    blobs = [entry for entry in entries if entry[1] == "blob"]
    for mode, kind, sha, path in entries:
        if kind == "commit":
            (dest / path).mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(["git", "-c", "core.useReplaceRefs=false", "-C", str(repo), "cat-file", "--batch"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=GIT_ENV)

    def feed():
        try:
            proc.stdin.write("".join(f"{sha}\n" for _, _, sha, _ in blobs).encode("ascii"))
        finally:
            proc.stdin.close()

    writer = threading.Thread(target=feed, daemon=True)
    writer.start()
    try:
        for mode, _, sha, path in blobs:
            header = proc.stdout.readline().decode("ascii", "replace").split()
            if len(header) != 3 or header[0] != sha or header[1] != "blob":
                raise Refused(f"git cat-file could not read {path} ({sha[:12]}): {' '.join(header)}")
            size = int(header[2])
            data = proc.stdout.read(size)
            proc.stdout.read(1)
            if len(data) != size or hashlib.new(algorithm, b"blob %d\0" % size + data).hexdigest() != sha:
                raise Refused(f"the object for {path} does not hash to {sha[:12]}")
            target = dest / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            if mode == "100755" and os.name != "nt":
                target.chmod(0o755)
    finally:
        proc.stdout.close()
        proc.wait()
        writer.join(5)
    return len(blobs)


def approved_check(a, record):
    """(AC, command, folder to run in) for a trusted rerun, after checking the order against its DISPATCH line and the
    repo against the candidate. Raises Refused."""
    gate = gate_module()
    try:
        data = pathlib.Path(a.order).read_bytes()
        log = pathlib.Path(a.dispatch_log).read_text(encoding="utf-8-sig")
    except OSError as error:
        raise Refused(f"cannot read: {error}")
    text, now = data.decode("utf-8-sig", errors="replace"), gate.order_hash(data)
    (ids, identity), dispatch = gate.order_identity(text, a.order), gate.dispatch_records(log)
    if identity:
        raise Refused(identity)
    hit = gate.dispatch_for(dispatch, ids)
    if hit is None:
        raise Refused(f"no DISPATCH line for {' / '.join(ids)} in {a.dispatch_log}")
    rev, sha = hit[1]
    if rev != gate.order_revision(text):
        raise Refused(f"the latest DISPATCH line logs rev={rev}, the order is at REVISION {gate.order_revision(text)}")
    if sha != now:
        raise Refused(f"the order's hash now ({now[:12]}) is not the one logged at dispatch ({sha[:12]}); "
                      "its CHECKS may have changed after dispatch")
    problems = []
    checks = gate.order_checks(text, problems)
    if problems:
        raise Refused("; ".join(problems))
    if not checks:
        raise Refused(f"{a.order} has no `CHECKS:` list; the Director approves a check per AUTO AC there")
    names = [part for part in re.split(r"[\s,;/+]+", str(record.get("label", ""))) if part in checks]
    if not names:
        raise Refused(f"the record's label {record.get('label')!r} names no AC with an approved check in {a.order}")
    if len({json.dumps(checks[name]) for name in names}) > 1:
        raise Refused(f"the record's label names {', '.join(names)}, whose approved checks differ; record once per AC")

    approved = checks[names[0]]
    check_program(approved)
    wanted = git_trusted(a.repo, "rev-parse", "--verify", f"{a.candidate}^{{commit}}").lower()
    problems = repo_state(a.repo, wanted)
    if problems:
        raise Refused(problems[0])
    return names[0], approved, wanted, git_trusted(a.repo, "rev-parse", f"{wanted}^{{tree}}")


def cmd_verify(a):
    try:
        record = json.loads(pathlib.Path(a.record).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        print(f"EVIDENCE_VERIFY: NOT_RUN {error}")
        return 2
    trusted = (a.order, a.dispatch_log, a.repo, a.candidate)
    if a.rerun and not all(trusted):
        absent = [flag for flag, value in zip(("--order", "--dispatch-log", "--repo", "--candidate"), trusted) if not value]
        print(f"EVIDENCE_VERIFY: NOT_RUN --rerun runs the order's approved check and needs {' '.join(absent)}: "
              "verify RECORD --rerun --order ORDER --dispatch-log LOG --repo REPO --candidate SHA "
              "(--rerun-recorded runs the command written in the record instead, and never reports test=passed)")
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
    lines, extra = [], ""
    test = "not-rerun" if expected == 0 else f"failed(recorded exit {expected})"
    if a.rerun:
        root = None
        try:
            ac, approved, candidate, tree = approved_check(a, record)
            root = pathlib.Path(tempfile.mkdtemp(prefix="dw-rerun-")).resolve()
            count = materialize(a.repo, candidate, root)
            program = program_in(approved, root)
        except Refused as why:
            if root:
                shutil.rmtree(root, ignore_errors=True)
            print(f"EVIDENCE_VERIFY: NOT_RUN {why}")
            return 2
        try:
            return finish_rerun(a, record, ac, approved, candidate, tree, root, count, program)
        finally:
            shutil.rmtree(root, ignore_errors=True)
    elif a.rerun_recorded:
        print(f"rerun the recorded command in {cwd}: {command}")
        code = execute(command, cwd, 1, a.timeout, None)[0]
        if code != expected:
            lines.append(f"exit code {expected} -> {code}")
        test = "recorded-command-passed" if code == 0 else f"failed(rerun exit {code})"
        extra = " source=record"
    return report(a, artifacts, lines, test, extra)


def finish_rerun(a, record, ac, approved, candidate, tree, root, count, program):
    """Run the approved check in the materialized folder root, then read REPO again and hash the artifacts in root."""
    lines, expected, command = [], record["exit_code"], record["command"]
    recorded = ((record.get("git") or {}).get("head") or "").lower()
    if recorded != candidate:
        lines.append(f"recorded at HEAD {recorded[:12] or 'none'}, the candidate is {candidate[:12]}")
    if command != approved:
        lines.append(f"record command differs from the approved check: {json.dumps(command, ensure_ascii=False)} "
                     f"!= {json.dumps(approved, ensure_ascii=False)}")
    print(f"rerun {ac} in a new folder holding the {count} committed files of {candidate[:12]} (not {a.repo}): {approved}")
    code = execute(approved, str(root), 1, a.timeout, None, program)[0]
    if code != expected:
        lines.append(f"exit code {expected} -> {code}")
    try:
        after = repo_state(a.repo, candidate)
        if not after and git_trusted(a.repo, "rev-parse", f"{candidate}^{{tree}}") != tree:
            after = [f"the candidate's tree is no longer {tree[:12]}"]
    except Refused as why:
        after = [str(why)]
    lines += [f"the repo changed while the check ran: {why}" for why in after]
    test = "passed" if code == 0 else f"failed(rerun exit {code})"
    return report(a, record["artifacts"], lines, test, f" check={ac} source=order candidate={candidate[:12]}",
                  root, pathlib.Path(record.get("cwd") or "."))


def report(a, artifacts, lines, test, extra, root=None, base=None):
    """Hash the artifacts again (in root, at their path relative to base, after a trusted rerun) and print the result."""
    changed = missing = 0
    for item in artifacts:
        if item["sha256"] is None:
            missing += 1
            lines.append(f"artifact missing when recorded: {item['path']}")
            continue
        path = pathlib.Path(item["path"])
        if root is not None:
            try:
                path = (root / (path.relative_to(base) if path.is_absolute() else path)).resolve()
            except ValueError:
                path = None
            if path is None or (path != root and root not in path.parents):
                changed += 1
                lines.append(f"artifact outside the record's cwd, so the rerun cannot make it: {item['path']}")
                continue
        now_hash = hash_artifact(path)["sha256"]
        where = f" (in the rerun folder: {path.relative_to(root).as_posix()})" if root is not None else ""
        if now_hash is None:
            missing += 1
            lines.append(f"artifact gone: {item['path']}{where}")
        elif now_hash != item["sha256"]:
            changed += 1
            lines.append(f"artifact changed: {item['path']}{where}")
    for line in lines:
        print(f"  - {line}")
    ok = not lines and not test.startswith("failed")
    print(f"EVIDENCE_VERIFY: {'OK' if ok else 'MISMATCH'} integrity={'changed' if changed else 'same'} test={test} "
          f"artifacts={len(artifacts)} missing={missing} rerun={'yes' if a.rerun or a.rerun_recorded else 'no'}{extra}")
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
    how = verify.add_mutually_exclusive_group()
    how.add_argument("--rerun", action="store_true", help="run the order's approved check first; needs the four flags below")
    how.add_argument("--rerun-recorded", action="store_true", help="run the command written in the record (never test=passed)")
    verify.add_argument("--order", help="with --rerun: the work order whose CHECKS hold the approved command")
    verify.add_argument("--dispatch-log", help="with --rerun: the log with the order's DISPATCH line")
    verify.add_argument("--repo", help="with --rerun: a clean checkout of the candidate; the check runs in a copy of its tree")
    verify.add_argument("--candidate", help="with --rerun: the commit under review, 40 hex digits (git rev-parse <branch>)")
    verify.add_argument("--timeout", type=float, help="seconds before the rerun is killed")
    a = ap.parse_args()
    if a.action == "verify" and not a.rerun and any((a.order, a.dispatch_log, a.repo, a.candidate)):
        ap.error("--order, --dispatch-log, --repo and --candidate work with --rerun")
    if a.action == "verify" and a.candidate and not re.fullmatch(r"[0-9a-fA-F]{40}", a.candidate):
        ap.error(f"--candidate takes the full commit, 40 hex digits (git rev-parse <branch>), got: {a.candidate}")
    sys.stdout.reconfigure(encoding="utf-8")
    return cmd_run(a) if a.action == "run" else cmd_verify(a)


if __name__ == "__main__":
    sys.exit(main())
