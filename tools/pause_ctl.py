"""Pause switch for every session's tool calls, and a CPU report of a process tree after a stop.

  python -I -X utf8 pause_ctl.py on --director DIR --reason TEXT [--by NAME]   write DIR/PAUSE, log "PAUSE on" in DIR/DIRECTOR_LOG.md
  python -I -X utf8 pause_ctl.py off --director DIR [--by NAME]                remove DIR/PAUSE, log "PAUSE off"
  python -I -X utf8 pause_ctl.py status --director DIR                         print "PAUSE: on|off ..."; exit 0
  python -I -X utf8 pause_ctl.py procs (--root PID ... | --pids-file F) [--sample 3] [--busy 0.05]

--flag FILE uses FILE instead of DIR/PAUSE (on / off / status then log only when --director is given too).

While the flag file exists, hook_guard.py --pause-flag FILE denies every tool call but those the rules file's "pause"
section lets through: reading, reporting, progress files, the pause status. The flag stops new actions only: a program
already running keeps running. Stop it by PID, the whole tree (docs/02), then run procs to see what is left.

procs lists the given PIDs and all their descendants, reads CPU time twice at least --sample seconds apart, and prints
  STOPPED    the given PIDs that no longer exist
  REMAINING  the tree's live processes, most CPU in the sample first: PID, PPID, CPU seconds, name, command line
  PROCS: stopped=n remaining=m busy=k    (busy: CPU over BUSY of one core in the sample)
and exits 1 when any process remains. It never ends a process. Windows reads Win32_Process through PowerShell; Linux
reads /proc. A PID the system reused for a new program after the stop shows as remaining: check its command line.
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys
import time

LINE = re.compile(r"^PAUSE by (?P<by>.+?) at (?P<at>\S+): (?P<reason>.*)$")


def flag_paths(a):
    """(flag file, log file or None) from --flag / --director."""
    director = pathlib.Path(a.director) if a.director else None
    if a.flag:
        flag = pathlib.Path(a.flag)
    elif director:
        flag = director / "PAUSE"
    else:
        sys.exit("pause_ctl: give --director DIR or --flag FILE")
    return flag, (director / "DIRECTOR_LOG.md" if director else None)


def clean(text):
    """One line with no <...> (a hook message never shows a placeholder)."""
    return re.sub(r"\s+", " ", text).replace("<", "(").replace(">", ")").strip()


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def read_flag(flag):
    """(by, at, reason) of a flag file; fields it cannot read are "unknown"."""
    try:
        first = flag.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except (OSError, IndexError):
        first = ""
    found = LINE.match(first)
    return (found["by"], found["at"], found["reason"]) if found else ("unknown", "unknown", clean(first) or "unknown")


def log(path, text):
    if path is None:
        return
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(text + "\n")


def snapshot():
    """{pid: (ppid, cpu seconds, name, command line)} of every process now."""
    if os.name == "nt":
        script = ("Get-CimInstance Win32_Process | ForEach-Object { [pscustomobject]@{p=[int]$_.ProcessId;"
                  "q=[int]$_.ParentProcessId;t=[double]($_.KernelModeTime+$_.UserModeTime)/1e7;n=$_.Name;c=$_.CommandLine} }"
                  " | ConvertTo-Json -Compress")
        done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                              capture_output=True, encoding="utf-8", errors="replace", timeout=120)
        rows = json.loads(done.stdout or "[]")
        rows = rows if isinstance(rows, list) else [rows]
        return {r["p"]: (r["q"], r["t"], r["n"] or "", r["c"] or "") for r in rows}
    out, tick = {}, os.sysconf("SC_CLK_TCK")
    for entry in pathlib.Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
        except OSError:
            continue
        name, fields = stat[stat.index("(") + 1:stat.rindex(")")], stat[stat.rindex(")") + 2:].split()
        out[int(entry.name)] = (int(fields[1]), (int(fields[11]) + int(fields[12])) / tick, name, command)
    return out


def tree(roots, procs):
    """The roots and all their descendants that are in procs."""
    found, todo = set(), [p for p in roots if p in procs]
    while todo:
        pid = todo.pop()
        if pid in found:
            continue
        found.add(pid)
        todo += [c for c, row in procs.items() if row[0] == pid and c != pid]
    return found


def cmd_procs(a):
    roots = list(a.root)
    if a.pids_file:
        for line in pathlib.Path(a.pids_file).read_text(encoding="utf-8").splitlines():
            word = line.split("#", 1)[0].strip()
            if word:
                if not word.isdigit():
                    sys.exit(f"pause_ctl: {a.pids_file}: not a PID: {word!r}")
                roots.append(int(word))
    if not roots:
        sys.exit("pause_ctl procs: give --root PID or --pids-file F")
    before, start = snapshot(), time.monotonic()
    time.sleep(a.sample)
    after = snapshot()
    elapsed = time.monotonic() - start  # reading the table takes time too (about a second through PowerShell)
    # a child started during the sample counts too; a PID whose parent changed is still in the tree it was in
    live = tree(roots, after) | {p for p in tree(roots, before) if p in after}
    stopped = sorted(p for p in set(roots) if p not in after)
    delta = {p: max(0.0, after[p][1] - before[p][1]) if p in before else after[p][1] for p in live}
    remaining = sorted(live, key=lambda p: (-delta[p], p))
    busy = [p for p in remaining if delta[p] > a.busy * elapsed]
    print("STOPPED")
    for pid in stopped:
        print(f"  {pid}")
    print(f"REMAINING (CPU seconds over {elapsed:.1f} s, most first)")
    for pid in remaining:
        ppid, _, name, command = after[pid]
        print(f"  {pid:>7} {ppid:>7} {delta[pid]:8.2f}  {name}  {clean(command)[:80]}")
    print(f"PROCS: stopped={len(stopped)} remaining={len(remaining)} busy={len(busy)}")
    return 1 if remaining else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="action", required=True)
    for name in ("on", "off", "status"):
        p = sub.add_parser(name)
        p.add_argument("--director", help="DIRECTOR folder: the flag is DIR/PAUSE, the log DIR/DIRECTOR_LOG.md")
        p.add_argument("--flag", help="flag file instead of DIR/PAUSE")
        if name != "status":
            p.add_argument("--by", default="Director", help="who switches it (default Director)")
        if name == "on":
            p.add_argument("--reason", required=True, help="why; shown in every blocked tool call")
    p = sub.add_parser("procs")
    p.add_argument("--root", type=int, action="append", default=[], help="a PID to check with all its descendants")
    p.add_argument("--pids-file", help="a file of PIDs, one per line (# starts a comment)")
    p.add_argument("--sample", type=float, default=3.0, help="seconds between the two CPU readings (default 3)")
    p.add_argument("--busy", type=float, default=0.05, help="share of one core that counts as busy (default 0.05)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.action == "procs":
        return cmd_procs(a)
    flag, log_path = flag_paths(a)
    if a.action == "status":
        if flag.exists():
            by, at, why = read_flag(flag)
            print(f"PAUSE: on by {by} at {at}: {why}")
        else:
            print("PAUSE: off")
        return 0
    by, stamp = clean(a.by) or "Director", now()
    if a.action == "on":
        why = clean(a.reason)
        if not why:
            sys.exit("pause_ctl on: --reason is empty")
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text(f"PAUSE by {by} at {stamp}: {why}\n", encoding="utf-8", newline="\n")
        log(log_path, f"PAUSE on by={by} at={stamp} reason={why}")
        print(f"PAUSE: on by {by} at {stamp}: {why}")
        return 0
    if flag.exists():
        flag.unlink()
        log(log_path, f"PAUSE off by={by} at={stamp}")
        print(f"PAUSE: off by {by} at {stamp}")
    else:
        print("PAUSE: off (it was not on)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
