"""Check that a file read on every call stays small: a memory index (for example MEMORY.md), or since 2.2.2 the
RESUME_STATE.md files every resume reads in full.

  memory_size_check.py [--file F]                         one memory index (default limit 6144 bytes)
  memory_size_check.py --kind resume --file F [--file G]  one line per file, then `SIZE: PASS|OVER files=n over=n`
  memory_size_check.py --kind resume --glob "D:/X/**/RESUME_STATE*.md"
  memory_size_check.py --kind resume --workstreams <DIRECTOR>/ACTIVE_WORKSTREAMS.md

Prints size in bytes, a rough token estimate (bytes / 2, mixed Chinese / English text) and the longest line.
--kind memory (default): limit 6144 bytes (about 3k tokens), no line limit unless --max-line-bytes is given.
--kind resume (2.2.2): limit 20480 bytes, any line over 4096 bytes is OVER too (docs/06); --config director_work.json
  reads `resume.max_bytes` / `resume.max_line_bytes`. --max-bytes / --max-line-bytes win over both.
One --file without --kind, --glob or --workstreams prints the 2.2.1 report for that file. Otherwise each file gets one
line `OK  ` / `OVER` and the last line is `SIZE: PASS|OVER|MISSING files=n over=n [missing=n]`; a glob that matches
nothing or a registered path that is not there counts as missing. --workstreams reads the RESUME_STATE column of the
ACTIVE_WORKSTREAMS.md table (templates/DIRECTOR_FILES.md), or any `...RESUME_STATE*.md` path in it; a relative path is
read from that file's folder. Exit 1 when a file is over or missing, 0 otherwise.
Without --file, --glob or --workstreams it looks at ~/.claude/projects/<current-folder-as-project-dir>/memory/MEMORY.md.
Only reads; tidy by hand: the memory index per docs/09_memory.md, a RESUME_STATE per docs/06_resume_lossless.md (move
closed sections to RESUME_HISTORY_<YYYYMMDD>.md beside it, never delete them).
"""
import argparse
import glob
import json
import pathlib
import re
import sys

LIMITS = {"memory": (6144, None), "resume": (20480, 4096)}
RESUME_PATH = re.compile(r"[^\s`|()<>\"']*RESUME_STATE[^\s`|()<>\"'/\\]*\.md", re.I)


def measure(raw):
    """Size facts of a file's bytes: size, ~tokens, lines, and the longest line (number, bytes)."""
    lines = raw.split(b"\n")
    longest = max(range(len(lines)), key=lambda n: len(lines[n].rstrip(b"\r")))
    return {"bytes": len(raw), "tokens": len(raw) // 2, "lines": len(raw.decode("utf-8", "replace").splitlines()),
            "longest_line": longest + 1, "longest_bytes": len(lines[longest].rstrip(b"\r"))}


def over_limits(facts, max_bytes, max_line_bytes):
    """What is over: a list of short words (`size`, `line`), empty when the file fits."""
    over = ["size"] if facts["bytes"] > max_bytes else []
    if max_line_bytes is not None and facts["longest_bytes"] > max_line_bytes:
        over.append("line")
    return over


def positive(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def resume_limits(data, notes):
    """2.2.2: (max_bytes, max_line_bytes) from a director_work.json object's `resume` key, defaults for what is
    missing; a value of the wrong type is a note and the default is used."""
    max_bytes, max_line_bytes = LIMITS["resume"]
    section = data.get("resume") if isinstance(data, dict) else None
    if section is None:
        return max_bytes, max_line_bytes
    if not isinstance(section, dict):
        notes.append(f"director_work.json resume: an object is needed, got {type(section).__name__}; defaults used")
        return max_bytes, max_line_bytes
    found = []
    for key, default in (("max_bytes", max_bytes), ("max_line_bytes", max_line_bytes)):
        value = section.get(key, default)
        if not positive(value):
            notes.append(f"director_work.json resume.{key}: a whole number above 0, got {value!r}; {default} used")
            value = default
        found.append(value)
    return tuple(found)


KEEP_DEFAULTS = {"keep_recent": 10,
                 "protect_headings": ["現況", "未結", "OPEN", "BLOCKED", "TODO", "待辦", "IN_FLIGHT", "DO_NOT_REPEAT"]}


def resume_settings(data, notes):
    """2.2.2: every `resume` setting of a director_work.json object: max_bytes, max_line_bytes, keep_recent (the
    newest sections and Before: entries resume_archive.py never moves; by count, never by age) and
    protect_headings (words that keep a section). A wrong type is a note and the default is used."""
    max_bytes, max_line_bytes = resume_limits(data, notes)
    found = {"max_bytes": max_bytes, "max_line_bytes": max_line_bytes, **KEEP_DEFAULTS}
    section = data.get("resume") if isinstance(data, dict) else None
    if not isinstance(section, dict):
        return found
    for key, ok, want in (("keep_recent", positive, "a whole number above 0"),
                          ("protect_headings", lambda v: isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v),
                           "a list of non-empty strings")):
        if key in section:
            if ok(section[key]):
                found[key] = section[key]
            else:
                notes.append(f"director_work.json resume.{key}: {want}, got {section[key]!r}; {KEEP_DEFAULTS[key]!r} used")
    return found


def read_config(path, notes):
    """A director_work.json object; an unreadable file is a note and gives {} (the defaults)."""
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        notes.append(f"director_work.json {path}: cannot read ({error.__class__.__name__}); defaults used")
        data = {}
    return data


def config_limits(path, notes):
    """resume_limits from a director_work.json file; an unreadable file is a note and gives the defaults."""
    return resume_limits(read_config(path, notes), notes)


def archive_tool():
    """resume_archive.py from this folder (2.2.2: the movable bytes of a RESUME_STATE)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("memory_size_resume_archive",
                                                  pathlib.Path(__file__).resolve().parent / "resume_archive.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def workstream_paths(path):
    """The RESUME_STATE paths an ACTIVE_WORKSTREAMS.md registers: the table column whose header names RESUME_STATE,
    else any `...RESUME_STATE*.md` path in the text. Relative paths are read from the file's folder."""
    text = pathlib.Path(path).read_text(encoding="utf-8-sig")
    found, column, in_table = [], None, False
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            column, in_table = None, False
            continue
        cells = [c.strip().strip("`").strip() for c in line.strip().strip("|").split("|")]
        if not in_table:  # the first row of a table is its header
            in_table = True
            hits = [n for n, c in enumerate(cells) if "RESUME" in c.upper()]
            column = hits[0] if hits else None
            continue
        if column is not None and column < len(cells) and not re.fullmatch(r":?-+:?", cells[column]) and cells[column]:
            value = cells[column]
            if value.upper() not in ("NONE", "N/A", "-") and not re.fullmatch(r"<[^<>]*>", value):
                found.append(value)
    if not found:
        found = RESUME_PATH.findall(text)
    base = pathlib.Path(path).resolve().parent
    return [str(p if pathlib.Path(p).is_absolute() else base / p) for p in dict.fromkeys(found)]


def legacy(path, max_bytes, top):
    """The 2.2.1 report for one memory index."""
    if not path.is_file():
        print(f"NOT_FOUND {path}")
        return 1
    raw = path.read_bytes()
    lines = raw.decode("utf-8", "replace").splitlines()
    size = len(raw)
    links = [m for line in lines for m in re.findall(r"\]\(([^)]+)\)", line)]
    dup = sorted({x for x in links if links.count(x) > 1})
    ok = size <= max_bytes
    print(f"{'OK  ' if ok else 'OVER'} {path.name}: {size} bytes (limit {max_bytes}), ~{size // 2} tokens, "
          f"{len(lines)} lines, {len(links)} links")
    if dup:
        print(f"duplicate links: {', '.join(dup)}")
    if not ok:
        print("longest lines (line: bytes):")
        for n, line in sorted(enumerate(lines, 1), key=lambda t: -len(t[1].encode("utf-8")))[:top]:
            print(f"  {n}: {len(line.encode('utf-8'))}")
        print("tidy per docs/09_memory.md: back up first, move closed / history entries to ARCHIVE_INDEX.md, "
              "keep rule entries and open work.")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", action="append", default=[], help="a file to check (may be given more than once)")
    ap.add_argument("--glob", action="append", default=[], help="a glob pattern, ** reaches into subfolders (quote it)")
    ap.add_argument("--workstreams", action="append", default=[], metavar="ACTIVE_WORKSTREAMS.md",
                    help="check the RESUME_STATE paths this file registers")
    ap.add_argument("--kind", choices=sorted(LIMITS), help="memory (default limits 6144 bytes, no line limit) or "
                    "resume (20480 bytes, lines 4096 bytes)")
    ap.add_argument("--config", help="director_work.json: with --kind resume, read resume.max_bytes / max_line_bytes")
    ap.add_argument("--max-bytes", type=int, help="limit in bytes (default by --kind)")
    ap.add_argument("--max-line-bytes", type=int, help="limit for one line in bytes (default by --kind)")
    ap.add_argument("--top", type=int, default=5, help="single memory index: how many longest lines to show (default 5)")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    kind, notes = a.kind or "memory", []
    if a.config and kind != "resume":
        ap.error("--config works with --kind resume")
    for name in ("max_bytes", "max_line_bytes"):
        if getattr(a, name) is not None and getattr(a, name) <= 0:
            ap.error(f"--{name.replace('_', '-')} takes a whole number above 0")
    settings = resume_settings(read_config(a.config, notes) if a.config else {}, notes)
    max_bytes, max_line_bytes = (settings["max_bytes"], settings["max_line_bytes"]) if kind == "resume" else LIMITS[kind]
    max_bytes = a.max_bytes if a.max_bytes is not None else max_bytes
    max_line_bytes = a.max_line_bytes if a.max_line_bytes is not None else max_line_bytes
    archive = archive_tool() if kind == "resume" else None

    if not (a.glob or a.workstreams or a.kind or len(a.file) > 1):
        if a.file:
            path = pathlib.Path(a.file[0])
        else:
            name = re.sub(r"[^A-Za-z0-9]", "-", str(pathlib.Path.cwd().resolve()))
            path = pathlib.Path.home() / ".claude" / "projects" / name / "memory" / "MEMORY.md"
        return legacy(path, max_bytes, a.top)

    targets, missing = list(a.file), []
    for pattern in a.glob:
        hits = sorted(p for p in glob.glob(pattern, recursive=True) if pathlib.Path(p).is_file())
        if not hits:
            missing.append(f"NO_MATCH {pattern}")
        targets += hits
    for registry in a.workstreams:
        if not pathlib.Path(registry).is_file():
            missing.append(f"NOT_FOUND {registry} (the workstreams file)")
            continue
        paths = workstream_paths(registry)
        if not paths:
            notes.append(f"{registry}: no RESUME_STATE path registered")
        targets += paths
    if not targets and not missing:
        ap.error("give --file, --glob or --workstreams")
    seen, over, checked = set(), 0, 0
    for target in targets:
        path = pathlib.Path(target)
        key = str(path.resolve()).lower() if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        if not path.is_file():
            missing.append(f"NOT_FOUND {path}")
            continue
        raw = path.read_bytes()
        facts, checked = measure(raw), checked + 1
        bad = over_limits(facts, max_bytes, max_line_bytes)
        over += bool(bad)
        line_limit = f" (limit {max_line_bytes})" if max_line_bytes is not None else ""
        movable = ""
        if archive is not None:
            try:
                movable = f", movable {archive.plan(raw, settings)['moved_bytes']} bytes"
            except UnicodeDecodeError:
                movable = ", movable ? (not UTF-8)"
        print(f"{'OVER' if bad else 'OK  '} {path}: {facts['bytes']} bytes (limit {max_bytes}), ~{facts['tokens']} tokens, "
              f"longest line {facts['longest_line']}: {facts['longest_bytes']} bytes{line_limit}{movable}"
              + (f"; over: {', '.join(bad)}" if bad else ""))
    for line in missing:
        print(line)
    for note in notes:
        print(f"  ~ {note}")
    if over:
        how = ("the work line moves old sections word for word to RESUME_HISTORY_<YYYYMMDD>.md beside the file with "
               "resume_archive.py (dry-run first, then --execute); the header, the current state, open items and recent "
               "sections stay (docs/06)") if kind == "resume" else "tidy per docs/09_memory.md"
        print(f"  ~ {how}")
    status = "OVER" if over else "MISSING" if missing else "PASS"
    print(f"SIZE: {status} files={checked} over={over}" + (f" missing={len(missing)}" if missing else ""))
    return 1 if over or missing else 0


if __name__ == "__main__":
    sys.exit(main())
