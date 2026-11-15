"""Run-script closing template: ACK first, DONE always, GO re-notified once (DIRECTOR-WORK 2.3.0, N5).

Copy this file next to a project's test scripts and wrap every scheduled run with it. Lessons behind it: a worker that
got GO never started and nobody saw it for 47 minutes; runs that ended (or crashed) without a DONE kept the GPU / device
window booked; an idle check reported NO_ACK for a run that had already finished and written its result.

  run_closing.py run   --board DIR --id ID [--result PATH] -- COMMAND [ARGS...]
  run_closing.py go    --board DIR --id ID [--notify COMMAND] [--wait 300] [--poll 5] [--result PATH]
  run_closing.py check --board DIR --id ID [--grace 300] [--result PATH]

  run    the worker side. Its first action writes `ACK <id> <time>` (before anything that could fail), then runs
         COMMAND, then - in a finally block, also after a crash or Ctrl+C - writes `DONE <id> <minutes> exit=<code>`.
         The run never ends without a DONE; the exit code is COMMAND's.
  go     the scheduler side. Writes `GO <id> <time>`, runs --notify (the command that tells the worker), and waits up
         to --wait seconds (default 300 = 5 minutes) for the ACK. No ACK: it first looks for a DONE or --result file
         (a short run can finish before anyone looks); none either: it re-notifies once and waits --wait again; still
         nothing prints `NO_ACK <id>` and exits 1, so the scheduler asks the worker directly instead of waiting.
  check  the idle check. GO without ACK after --grace seconds is NO_ACK, unless a DONE or --result file exists
         (then `DONE_WITHOUT_ACK`, not an alarm). Prints one state line: NONE / WAIT_ACK / NO_ACK / RUNNING / DONE /
         DONE_WITHOUT_ACK, and exits 1 only on NO_ACK.

Signals are one-line files in --board: <id>.GO, <id>.ACK, <id>.DONE (written whole, then renamed). Wiring: if the
project has a board tool or a message channel, change only `signal()` (write) and `seen()` (read) below to call it;
keep the order ACK -> COMMAND -> DONE-in-finally and the check for DONE / RESULT before NO_ACK. Python stdlib only;
works on Windows and Linux.
"""
import argparse
import datetime
import os
import pathlib
import subprocess
import sys
import time


def now():
    return datetime.datetime.now(datetime.timezone.utc).astimezone()


def signal(board, ident, kind, text=""):
    """Write <id>.<KIND> as one line (temp file, then rename, so a reader never sees half a line)."""
    folder = pathlib.Path(board)
    folder.mkdir(parents=True, exist_ok=True)
    line = f"{kind} {ident} {now().isoformat(timespec='seconds')}" + (f" {text}" if text else "") + "\n"
    temp = folder / f".{ident}.{kind}.tmp"
    temp.write_text(line, encoding="utf-8")
    os.replace(temp, folder / f"{ident}.{kind}")
    print(line.rstrip(), flush=True)


def seen(board, ident, kind):
    """The time the <id>.<KIND> signal was written, or None."""
    path = pathlib.Path(board) / f"{ident}.{kind}"
    return path.stat().st_mtime if path.is_file() else None


def finished(board, ident, result):
    return seen(board, ident, "DONE") is not None or bool(result and pathlib.Path(result).exists())


def cmd_run(a):
    signal(a.board, a.id, "ACK")  # first, before anything that could fail
    start, code = time.monotonic(), 2
    try:
        if not a.command:
            raise ValueError("run needs a COMMAND after --")
        code = subprocess.run(a.command).returncode
    finally:
        minutes = (time.monotonic() - start) / 60
        signal(a.board, a.id, "DONE", f"{minutes:.1f}min exit={code}")
    return code


def wait_ack(a, seconds):
    end = time.monotonic() + seconds
    while True:
        if seen(a.board, a.id, "ACK") is not None:
            return True
        if time.monotonic() >= end:
            return False
        time.sleep(max(0.05, min(a.poll, end - time.monotonic())))


def notify(a):
    if a.notify:
        subprocess.run(a.notify, shell=True)


def cmd_go(a):
    signal(a.board, a.id, "GO")
    notify(a)
    for attempt in (1, 2):
        if wait_ack(a, a.wait):
            print(f"ACK_SEEN {a.id}")
            return 0
        if finished(a.board, a.id, a.result):
            print(f"DONE_WITHOUT_ACK {a.id}: the run finished before an ACK was seen (not an alarm)")
            return 0
        if attempt == 1:
            print(f"RENOTIFY {a.id}: no ACK after {a.wait:g}s; notifying once more")
            notify(a)
    print(f"NO_ACK {a.id}: no ACK after two notices; ask the worker directly (do not wait)")
    return 1


def cmd_check(a):
    go, ack = seen(a.board, a.id, "GO"), seen(a.board, a.id, "ACK")
    if seen(a.board, a.id, "DONE") is not None:
        state = "DONE" if ack is not None else "DONE_WITHOUT_ACK"
    elif ack is not None:
        state = "RUNNING"
    elif go is None:
        state = "DONE_WITHOUT_ACK" if finished(a.board, a.id, a.result) else "NONE"
    elif finished(a.board, a.id, a.result):
        state = "DONE_WITHOUT_ACK"  # a result file exists: look before raising NO_ACK
    elif time.time() - go > a.grace:
        state = "NO_ACK"
    else:
        state = "WAIT_ACK"
    print(f"{state} {a.id}")
    return 1 if state == "NO_ACK" else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("run", "go", "check"))
    ap.add_argument("--board", required=True, help="folder of the GO / ACK / DONE signal files")
    ap.add_argument("--id", required=True, help="the test request ID")
    ap.add_argument("--result", help="the run's RESULT file; its presence counts as finished")
    ap.add_argument("--notify", help="go: shell command that tells the worker")
    ap.add_argument("--wait", type=float, default=300.0, help="go: seconds to wait for ACK (default 300)")
    ap.add_argument("--poll", type=float, default=5.0, help="go: seconds between looks")
    ap.add_argument("--grace", type=float, default=300.0, help="check: seconds after GO before NO_ACK")
    argv = sys.argv[1:] if argv is None else list(argv)
    command = argv[argv.index("--") + 1:] if "--" in argv else []  # run: everything after -- is COMMAND
    a = ap.parse_args(argv[:argv.index("--")] if "--" in argv else argv)
    a.command = command
    sys.stdout.reconfigure(encoding="utf-8")
    return {"run": cmd_run, "go": cmd_go, "check": cmd_check}[a.action](a)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:  # one line, never a Traceback
        print(f"RUN_CLOSING: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        sys.exit(2)
