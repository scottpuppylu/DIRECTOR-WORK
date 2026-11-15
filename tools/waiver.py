"""Waivers that say what lifts them, and branches that block integration (DIRECTOR-WORK 2.3.0, N4).

A lane that waits on something (a license renewal, another line's build, an owner decision) was woken again and again
by the idle check although nothing it waited for had changed; and one branch held up integration for 10-16 hours while
everyone waited for it. Here a waiver names its `until` (the event that lifts it) and, best, a `watch` file whose
change is that event; a watcher or status.py wakes the lane only when the watch file changed or a snooze ran out.
The waivers live in one JSON file, so a watcher that restarts reads them back instead of dropping them.

  waiver.py add   --file WAIVERS.json --lane LANE --until "TEXT" [--watch PATH] [--reason TEXT]
  waiver.py snooze --file WAIVERS.json --lane LANE --until "TEXT" --minutes N
  waiver.py lift  --file WAIVERS.json --lane LANE
  waiver.py block --file WAIVERS.json --branch NAME [--note TEXT]        (the branch blocks integration from now)
  waiver.py unblock --file WAIVERS.json --branch NAME
  waiver.py check --file WAIVERS.json [--block-hours 8] [--wake-only]

  add      the lane is waived until TEXT; --watch records the SHA-256 of PATH now (relative to the file's folder),
           so a later change of that file is what wakes the lane. One waiver per lane: a new one replaces the old.
  snooze   a waiver that also ends by time: after N minutes the lane is woken whatever else happened.
  check    per lane: `WAIVED <lane> until: <TEXT> (unchanged; do not wake)`, `SNOOZED <lane> ... till HH:MM`,
           `WAKE <lane>: <why>` (the watch file changed or is gone, the snooze ran out), `~ WARN NO_UNTIL <lane>` (a
           waiver that does not say what lifts it: write --until). Per blocking branch: `BLOCK <branch> <h>h`, or after
           --block-hours (default 8) `~ INTEGRATION_BLOCKED <branch> <h>h > <n>h: merge it behind a default-off flag
           instead of waiting`. Last line `WAIVERS: lanes=n wake=n blocked_long=n`. --wake-only prints only the WAKE
           lines and the last line (for a watcher: wake exactly those lanes).

The file is written whole and atomically (a temp file in its folder, then a rename). Wiring: an idle watcher calls
`waiver.py check --wake-only` on start and before each wake-up and wakes only the lanes listed; a status script can
print `waiver.py check`. Exit 0; 2 when the file cannot be read or written (one line, never a Traceback). Not a
per-turn read: run it when a lane goes idle or a watcher starts.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import sys
import tempfile

SCHEMA = "waivers-v1"


def file_digest(path):
    """SHA-256 of a file, or "missing"."""
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return "missing"


def evaluate(data, base, now, block_hours):
    """(lines, wake count, long block count) for a waivers-v1 object; base is the file's folder; now is aware."""
    lines, wake, long_blocks = [], 0, 0

    def moment(text):
        try:
            value = datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
        except ValueError:
            return None
        return value if value.tzinfo else value.replace(tzinfo=now.tzinfo)

    for item in data.get("waivers") or []:
        lane, until = str(item.get("lane") or "?"), str(item.get("until") or "").strip()
        if not until:
            lines.append(f"~ WARN NO_UNTIL {lane}: the waiver does not say what lifts it (waiver.py add --until ...)")
        snooze = moment(item["snooze_until"]) if item.get("snooze_until") else None
        watch = item.get("watch")
        if snooze is not None and now >= snooze:
            lines.append(f"WAKE {lane}: the snooze ran out at {snooze.astimezone(now.tzinfo):%H:%M} (until: {until})")
            wake += 1
            continue
        if watch:
            path = watch if os.path.isabs(watch) else os.path.join(base, watch)
            now_digest = file_digest(path)
            if now_digest != item.get("watch_sha256"):
                why = "is gone" if now_digest == "missing" else "changed"
                lines.append(f"WAKE {lane}: {watch} {why} since the waiver (until: {until})")
                wake += 1
                continue
        if snooze is not None:
            lines.append(f"SNOOZED {lane} until: {until} till {snooze.astimezone(now.tzinfo):%H:%M} (do not wake)")
        elif watch:
            lines.append(f"WAIVED {lane} until: {until} ({watch} unchanged; do not wake)")
        else:
            lines.append(f"WAIVED {lane} until: {until} (no watch file: lift it by hand when that happens; do not wake)")
    for item in data.get("blocks") or []:
        branch, since = str(item.get("branch") or "?"), moment(item.get("since"))
        if since is None:
            lines.append(f"~ WARN BLOCK {branch}: no readable since time")
            continue
        hours = (now - since).total_seconds() / 3600
        if hours > block_hours:
            long_blocks += 1
            lines.append(f"~ INTEGRATION_BLOCKED {branch} {hours:.1f}h > {block_hours:g}h: merge it behind a default-off "
                         "flag instead of waiting" + (f" ({item['note']})" if item.get("note") else ""))
        else:
            lines.append(f"BLOCK {branch} {hours:.1f}h (limit {block_hours:g}h)")
    return lines, wake, long_blocks


def read(path):
    target = pathlib.Path(path)
    if not target.is_file():
        return {"schema": SCHEMA, "waivers": [], "blocks": []}
    data = json.loads(target.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError(f"{path} is not a {SCHEMA} file")
    data.setdefault("waivers", [])
    data.setdefault("blocks", [])
    return data


def write(path, data):
    target = pathlib.Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=str(target.parent), prefix=".waivers_", suffix=".tmp")
    with os.fdopen(handle, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temp, target)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("add", "snooze", "lift", "block", "unblock", "check"))
    ap.add_argument("--file", required=True, help="the waivers JSON file (created on the first add / block)")
    ap.add_argument("--lane")
    ap.add_argument("--until", help="the event that lifts the waiver")
    ap.add_argument("--watch", help="add: a file whose change is that event (relative to the file's folder)")
    ap.add_argument("--reason", default="")
    ap.add_argument("--minutes", type=float, help="snooze: wake the lane after this many minutes")
    ap.add_argument("--branch")
    ap.add_argument("--note", default="")
    ap.add_argument("--block-hours", type=float, default=8.0, help="check: a block longer than this is flagged")
    ap.add_argument("--wake-only", action="store_true", help="check: print only the lanes to wake")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    def refuse(text):  # on stdout too, so a watcher's log shows why nothing was written
        print(f"WAIVERS: NOT_RUN {text}")
        ap.error(text)

    data = read(a.file)
    base = str(pathlib.Path(a.file).resolve().parent)
    now = datetime.datetime.now(datetime.timezone.utc).astimezone()
    stamp = now.isoformat(timespec="seconds")
    if a.action in ("add", "snooze", "lift") and not a.lane:
        refuse(f"{a.action} needs --lane")
    if a.action in ("block", "unblock") and not a.branch:
        refuse(f"{a.action} needs --branch")
    if a.action in ("add", "snooze"):
        if not (a.until or "").strip():
            refuse(f"{a.action} needs --until: what lifts the waiver")
        if a.action == "snooze" and (a.minutes is None or a.minutes <= 0):
            refuse("snooze needs --minutes N (more than 0)")
        item = {"lane": a.lane, "until": a.until.strip(), "since": stamp, "reason": a.reason}
        if a.watch:
            path = a.watch if os.path.isabs(a.watch) else os.path.join(base, a.watch)
            item.update(watch=a.watch, watch_sha256=file_digest(path))
        if a.action == "snooze":
            item["snooze_until"] = (now + datetime.timedelta(minutes=a.minutes)).isoformat(timespec="seconds")
        data["waivers"] = [w for w in data["waivers"] if w.get("lane") != a.lane] + [item]
        write(a.file, data)
        print(f"{a.action.upper()} {a.lane} until: {item['until']}" + (f" watch={a.watch}" if a.watch else "")
              + (f" till {item['snooze_until']}" if a.action == "snooze" else ""))
        return 0
    if a.action == "lift":
        kept = [w for w in data["waivers"] if w.get("lane") != a.lane]
        print(f"LIFT {a.lane}: " + ("removed" if len(kept) < len(data["waivers"]) else "no waiver for this lane"))
        data["waivers"] = kept
        write(a.file, data)
        return 0
    if a.action == "block":
        data["blocks"] = [b for b in data["blocks"] if b.get("branch") != a.branch] + [
            {"branch": a.branch, "since": stamp, "note": a.note}]
        write(a.file, data)
        print(f"BLOCK {a.branch} since {stamp}")
        return 0
    if a.action == "unblock":
        kept = [b for b in data["blocks"] if b.get("branch") != a.branch]
        print(f"UNBLOCK {a.branch}: " + ("removed" if len(kept) < len(data["blocks"]) else "not blocking"))
        data["blocks"] = kept
        write(a.file, data)
        return 0
    lines, wake, long_blocks = evaluate(data, base, now, a.block_hours)
    for line in lines:
        if not a.wake_only or line.startswith("WAKE "):
            print(line)
    print(f"WAIVERS: lanes={len(data['waivers'])} wake={wake} blocked_long={long_blocks}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, UnicodeError, ValueError) as error:  # one line, never a Traceback
        print(f"WAIVERS: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        sys.exit(2)
