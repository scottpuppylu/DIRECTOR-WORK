"""Write RAN lines and time stamps from the system clock, never by hand (DIRECTOR-WORK 2.2.5, B1).

A model that types `at=02:43` from memory gets it wrong (WO-DS-008 r2: reports an hour off, verdicts stamped 15
minutes after they were written). This tool takes the time from the clock and the exit code from the command itself.

  ran_line.py --to REPORT.md -- COMMAND [ARG ...]
      run COMMAND (no shell; its output goes to the terminal as usual), then add its RAN line to REPORT.md:
      - `COMMAND ARG ...` exit=N at=HH:MM          (at=HH:MM-HH:MM when it ran across a minute)
      The exit code of ran_line.py is the command's.
  ran_line.py --to REPORT.md --exit N --cmd "COMMAND TEXT"
      record a command that already ran (in another shell, a tool call): at= is now, so run this right after it.
  ran_line.py --stamp [--to FILE] [--text "| EVENT | ..."]
      print `YYYY-MM-DD HH:MM` (the GATE_VERDICT header, a DIRECTOR_LOG line); with --to, add the line
      `YYYY-MM-DD HH:MM <text>` to the end of FILE.

The RAN line goes right after the last line of the report's `RAN:` block (the `RAN:` line and the `- `...`` lines
under it); a report without a RAN: line gets `RAN:` and the line at the end. --print writes nothing, it only prints the line.
--utc-offset +08:00 uses that offset instead of the computer's (the report's HH:MM is local time).
Only writes the file named by --to. Not a per-turn read: open it when you write a report, a verdict or the log.
Exit: the command's code (run), 0 written, 2 could not run or write (one line, never a Traceback).
"""
import argparse
import datetime
import os
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile

VERSION = "2.2.5"
RAN_FIELD = re.compile(r"^[ \t]*RAN[ \t]*:")
RAN_ITEM = re.compile(r"^[ \t]*-[ \t]+`")
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def use_work_temp():
    """2.2.5 (B9): with WORK_DIR set, temp files go to WORK_DIR/tmp. Git Bash exports TMPDIR (the system temp folder)
    and Python's tempfile reads TMPDIR before TEMP / TMP, so `export TEMP=...` alone never reached Windows Python."""
    work = os.environ.get("WORK_DIR", "").strip()
    if not work:
        return None
    folder = os.path.join(work, "tmp")
    os.makedirs(folder, exist_ok=True)
    tempfile.tempdir = folder
    for name in ("TMPDIR", "TEMP", "TMP"):
        os.environ[name] = folder
    return folder


def clean(text):
    """One line: control characters out, newlines to `; `."""
    return CONTROL.sub("", re.sub(r"\r?\n", "; ", text)).strip()


def command_text(argv):
    text = subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)
    return clean(text)


def offset_of(value):
    if not value:
        return datetime.datetime.now().astimezone().tzinfo
    found = re.fullmatch(r"([+-])(\d{2}):?(\d{2})", value)
    if not found:
        raise ValueError(f"--utc-offset {value} is not +HH:MM")
    sign = 1 if found.group(1) == "+" else -1
    return datetime.timezone(sign * datetime.timedelta(hours=int(found.group(2)), minutes=int(found.group(3))))


def now(offset):
    return datetime.datetime.now(datetime.timezone.utc).astimezone(offset)


def ran_line(command, code, start, end=None):
    """`- `command` exit=N at=HH:MM` (at=HH:MM-HH:MM when start and end are in different minutes)."""
    if "`" in command:
        command = command.replace("`", "'")
    at = start.strftime("%H:%M")
    if end is not None and end.strftime("%H:%M") != at:
        at += "-" + end.strftime("%H:%M")
    return f"- `{command}` exit={code} at={at}"


def insert_ran(text, line):
    """text with line put after the report's RAN: block, else a new RAN: block at the end."""
    lines = text.splitlines()
    field = max((n for n, row in enumerate(lines) if RAN_FIELD.match(row)), default=None)
    if field is None:
        return text + ("" if not text or text.endswith("\n") else "\n") + "RAN:\n" + line + "\n"
    end = field
    while end + 1 < len(lines) and RAN_ITEM.match(lines[end + 1]):
        end += 1
    indent = re.match(r"[ \t]*", lines[end] if end > field else "").group(0)
    lines.insert(end + 1, indent + line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def write(path, line, ran):
    target = pathlib.Path(path)
    old = target.read_text(encoding="utf-8-sig") if target.is_file() else ""
    new = insert_ran(old, line) if ran else old + ("" if not old or old.endswith("\n") else "\n") + line + "\n"
    target.write_text(new, encoding="utf-8")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    command = None
    if "--" in argv:
        cut = argv.index("--")
        argv, command = argv[:cut], argv[cut + 1:]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--to", help="the report (RAN line) or log (--stamp) to add the line to")
    ap.add_argument("--exit", type=int, help="record mode: the exit code of a command that already ran")
    ap.add_argument("--cmd", help="record mode: the command text")
    ap.add_argument("--stamp", action="store_true", help="print YYYY-MM-DD HH:MM from the clock")
    ap.add_argument("--text", default="", help="with --stamp --to: the rest of the log line")
    ap.add_argument("--print", action="store_true", help="only print the line, write nothing")
    ap.add_argument("--utc-offset", help="offset for HH:MM, e.g. +08:00 (default: the computer's)")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    use_work_temp()
    offset = offset_of(a.utc_offset)
    modes = sum((bool(command), a.exit is not None or a.cmd is not None, a.stamp))
    if modes != 1:
        print("ran_line: give one of `-- COMMAND ...`, `--exit N --cmd TEXT` or `--stamp`", file=sys.stderr)
        return 2
    if a.stamp:
        stamp = now(offset).strftime("%Y-%m-%d %H:%M")
        line = f"{stamp} {clean(a.text)}".rstrip() if a.text else stamp
        if a.to and not a.print:
            write(a.to, line, False)
        print(line)
        return 0
    if not a.to and not a.print:
        print("ran_line: give --to REPORT (or --print)", file=sys.stderr)
        return 2
    if command is not None:
        if not command:
            print("ran_line: nothing after --", file=sys.stderr)
            return 2
        start = now(offset)
        sys.stdout.flush()
        try:
            code = subprocess.run(command).returncode
        except OSError as error:
            print(f"ran_line: cannot start {clean(command[0])}: {error.strerror or type(error).__name__}; nothing "
                  "written", file=sys.stderr)
            return 2
        line = ran_line(command_text(command), code, start, now(offset))
    else:
        if a.exit is None or not (a.cmd or "").strip():
            print("ran_line: record mode needs both --exit N and --cmd TEXT", file=sys.stderr)
            return 2
        code = a.exit
        line = ran_line(clean(a.cmd), code, now(offset))
    if not a.print:
        write(a.to, line, True)
    print(line)
    return code


def entry_point():
    try:
        return main()
    except KeyboardInterrupt:
        print("ran_line: interrupted", file=sys.stderr)
        return 2
    except (OSError, UnicodeError, ValueError) as error:
        print(f"ran_line: {type(error).__name__}: {clean(str(getattr(error, 'strerror', None) or error))[:200]}",
              file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001 - the top level reports one line, never a Traceback
        print(f"ran_line: cannot run: {type(error).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(entry_point())
