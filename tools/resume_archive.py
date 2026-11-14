"""Move old parts of a RESUME_STATE.md word for word into RESUME_HISTORY_<YYYYMMDD>.md beside it (2.2.2, docs/06).

  resume_archive.py RESUME_STATE.md              dry-run (default): what would move, what stays and why; writes nothing
  resume_archive.py RESUME_STATE.md --execute    back up, move, verify; any failed check restores the files, exit 1

"Compress" means a verbatim move, never a summary. What moves goes into the history file unchanged and leaves an index
in its place naming the date, the history file and the sha256 of the moved text. When in doubt, nothing moves.
Recent means by count only (PO 2026-11-14 10:13): the newest resume.keep_recent entries (default 10) stay; the
age in days is never used. When the count or the order cannot be read, nothing moves and a shadow note says why.
Body sections (a block between blank lines or headings; a block of list items is one section per item, from its
`- ` / `* ` / `1. ` line to the next): a moved section leaves one line
`> RESUME_ARCHIVED: <first words> | <date> | RESUME_HISTORY_<YYYYMMDD>.md | sha256=<16>`. Never moved:
  - the block holding `UPDATED:` (the current state), headings, blank lines and earlier index lines;
  - a section whose heading, first line, or any line's leading word holds a word of resume.protect_headings
    (default 現況 未結 OPEN BLOCKED TODO 待辦 IN_FLIGHT DO_NOT_REPEAT; case does not matter);
  - a section with no full date (YYYY-MM-DD, YYYY/MM/DD or YYYYMMDD) in it: its place in the order is unclear, so it
    stays (`~ shadow: RESUME_ORDER ...` counts them);
  - the newest resume.keep_recent dated sections. The date only puts the sections in order (a section's date is the
    latest full date written in it); a section dated the same day as the last one kept stays too (same day = order
    unclear).
The four header lines (the first block) stay four lines. A header line that carries a `Before:` chain (each checkpoint
put the old text after `Before:`, so the chain is newest first) keeps its current text and the first keep_recent
`Before:` entries; only the older tail moves, and the line ends with
`[RESUME_ARCHIVED: n older entries | <date of the newest moved entry or ?> | RESUME_HISTORY_<YYYYMMDD>.md | sha256=<16>]`.
The order comes from the chain itself. When a leading `(YYYY-MM-DD HH:MM)` / `(MM-DD HH:MM)` shows an entry newer than
one before it in the chain, or an entry is empty, the order or the count is unclear: the whole line stays and
`~ shadow: RESUME_HEADER ...` is printed.
--execute: writes `<file>.<YYYYMMDD-HHMMSS>.bak` first (never deleted, an existing one is refused), appends the moved
text to the history file, writes the new file, then checks (a) the history file holds every moved text word for word,
in order, and its old content is unchanged, (b) every kept part is unchanged (sha256), in order, and the header still
has the same four lines, (c) putting the moved texts back in place of their indexes gives the original file byte for
byte. Any failure restores the file from the .bak and the history file to what it was, exit 1. No other file is touched.
If the file is still over resume.max_bytes / max_line_bytes after the move, it prints
`~ shadow: RESUME_SIZE protected part over limit`: protected parts are never moved; the Director decides by hand.
Settings: --config director_work.json (else the one beside the file, if any) `resume` key; --keep-recent wins. Exit 0 dry-run or done, 1 a check failed (restored), 2 cannot run (not found, not UTF-8, backup name taken).
"""
import argparse
import datetime
import hashlib
import importlib.util
import pathlib
import re
import sys

INDEX = "> RESUME_ARCHIVED:"
CHAIN_INDEX = "[RESUME_ARCHIVED:"
HEADING = re.compile(r"#{1,6}\s")
ITEM = re.compile(r"(?:[-*+]|\d{1,3}[.)])\s")
DATE = re.compile(r"(?<!\d)(20\d\d)([-/.])(\d{1,2})\2(\d{1,2})(?!\d)|(?<!\d)(20\d\d)(\d\d)(\d\d)(?!\d)")
LEAD = re.compile(r"^[\s>*_`#+-]*(?:\d{1,3}[.)]\s*)?")
HEADER_KEY = re.compile(r"([A-Z][A-Z_]*):")
CHAIN = re.compile(r"(?<=\s)Before:")
ENTRY_DATE = re.compile(r"\s*\(?\s*(?:(20\d\d)-)?(\d{1,2})-(\d{1,2})[ T]\d{1,2}:\d")


def size_tool():
    """memory_size_check.py from this folder: the settings reader and the size facts."""
    spec = importlib.util.spec_from_file_location("resume_archive_size",
                                                  pathlib.Path(__file__).resolve().parent / "memory_size_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_lines(text):
    """Lines with their own endings; joining them gives the text back exactly."""
    return re.findall(r"[^\n]*\n|[^\n]+\Z", text)


def latest_date(text):
    """The latest real calendar date written in full in the text, or None."""
    best = None
    for m in DATE.finditer(text):
        year, month, day = (m.group(1), m.group(3), m.group(4)) if m.group(1) else (m.group(5), m.group(6), m.group(7))
        try:
            found = datetime.date(int(year), int(month), int(day))
        except ValueError:
            continue
        best = found if best is None or found > best else best
    return best


def protect_word(text, words):
    """The protect word on the text's first line or leading any of its lines, else None (case does not matter)."""
    lines = text.splitlines() or [""]
    first = lines[0].casefold()
    for word in words:
        w = word.casefold()
        if w in first or any(LEAD.sub("", line, count=1).casefold().startswith(w) for line in lines):
            return word
    return None


def entry_date(entry):
    """(year or None, month, day) of a chain entry's leading `(YYYY-MM-DD HH:MM)` / `(MM-DD HH:MM)`, else None."""
    m = ENTRY_DATE.match(entry)
    if not m:
        return None
    year, month, day = m.groups()
    if not (1 <= int(month) <= 12 and 1 <= int(day) <= 31):
        return None
    return int(year) if year else None, int(month), int(day)


def chain_pieces(line, line_no, settings, history_name, notes):
    """Pieces of one header line: kept text, and the moved older tail of its `Before:` chain (or nothing moves)."""
    content = line.rstrip("\r\n")
    ending = line[len(content):]
    key = HEADER_KEY.match(content).group(1)
    starts = [m.start() for m in CHAIN.finditer(content)]
    whole = [{"start": line_no, "end": line_no, "text": line, "kind": "keep", "reason": "header line"}]
    keep_recent = settings["keep_recent"]
    if len(starts) <= keep_recent:
        return whole
    entries = [content[len(key) + 1:starts[0]]] + [content[s + len("Before:"):e] for s, e in
                                                    zip(starts, starts[1:] + [len(content)])]
    why = None
    empty = [n for n, entry in enumerate(entries) if n and not entry.strip()]
    if empty:
        why = f"Before: entry {empty[0]} is empty, the count is unclear"
    dated = [(n, entry_date(entry)) for n, entry in enumerate(entries) if entry_date(entry)]
    for (n1, d1), (n2, d2) in zip(dated, dated[1:]):
        earlier, later = (d1, d2) if d1[0] and d2[0] else (d1[1:], d2[1:])
        if why is None and later > earlier:
            why = f"Before: entry {n2} is dated after entry {n1}, the order is unclear"
    if why:
        notes.append(f"shadow: RESUME_HEADER line {line_no} {key}: {why}; the whole line stays "
                     f"({len(starts)} Before: entries, {len(line.encode('utf-8'))} bytes)")
        return whole
    cut = starts[keep_recent]  # Before: entry keep_recent + 1 begins here: it and every older entry move
    moved = content[cut:]
    newest = entry_date(entries[keep_recent + 1])
    date = "?" if newest is None else (f"{newest[0]}-" if newest[0] else "") + f"{newest[1]:02d}-{newest[2]:02d}"
    index = (f"{CHAIN_INDEX} {len(starts) - keep_recent} older entries | {date} | {history_name} | "
             f"sha256={sha(moved)[:16]}]")
    return [{"start": line_no, "end": line_no, "text": content[:cut], "kind": "keep",
             "reason": f"header {key}: current text + Before: entries 1-{keep_recent} (newest {keep_recent})"},
            {"start": line_no, "end": line_no, "text": moved, "kind": "move", "index": index, "date": date,
             "what": f"header {key} Before: entries {keep_recent + 1}-{len(starts)}",
             "reason": f"older than the newest {keep_recent} entries"},
            {"start": line_no, "end": line_no, "text": ending, "kind": "structure", "reason": "line ending"}]


def sections(text, words):
    """Split into units: dicts with start / end line (1-based), text, kind (structure, index, header, keep,
    candidate), reason and date."""
    units, block, heading, line_no, seen_block = [], [], "", 0, False

    def close_block():
        nonlocal block, seen_block
        if not block:
            return
        start, lines = block[0][0], [line for _, line in block]
        body = "".join(lines)
        first_block, seen_block = not seen_block, True
        if first_block:
            units.append({"start": start, "end": start + len(lines) - 1, "text": body, "kind": "header",
                          "reason": "header", "lines": block})
            block = []
            return
        if any(line.lstrip().startswith("UPDATED:") for line in lines):
            reason = "current state (UPDATED block)"
        elif protect_word(heading, words):
            reason = f"protected heading ({protect_word(heading, words)})"
        else:
            reason = None
        if reason:
            units.append({"start": start, "end": start + len(lines) - 1, "text": body, "kind": "keep", "reason": reason})
            block = []
            return
        parts, current = [], []
        for n, line in block:
            if ITEM.match(line) and current:
                parts.append(current)
                current = []
            current.append((n, line))
        parts.append(current)
        for part in parts:
            part_text = "".join(line for _, line in part)
            unit = {"start": part[0][0], "end": part[-1][0], "text": part_text}
            word, date = protect_word(part_text, words), latest_date(part_text)
            if word:
                unit.update(kind="keep", reason=f"protected word ({word})")
            elif date is None:
                unit.update(kind="keep", reason="no full date (order unclear, stays)")
            else:
                unit.update(kind="candidate", reason=None, date=date)
            units.append(unit)
        block = []

    for line in split_lines(text):
        line_no += 1
        bare = line.strip()
        if not bare or HEADING.match(line) or line.startswith(INDEX):
            close_block()
            kind = "index" if line.startswith(INDEX) else "structure"
            if HEADING.match(line):
                heading = bare
                seen_block = True  # a heading before any block: there is no four-line header to keep
            units.append({"start": line_no, "end": line_no, "text": line, "kind": kind, "reason": kind})
        else:
            block.append((line_no, line))
    close_block()
    return units


def index_line(unit, history_name):
    first = unit["text"].splitlines()[0] if unit["text"].strip() else ""
    title = re.sub(r"\s+", " ", LEAD.sub("", first, count=1)).replace("|", "/").strip()[:60] or "section"
    ending = "\r\n" if unit["text"].endswith("\r\n") else "\n" if unit["text"].endswith("\n") else ""
    return f"{INDEX} {title} | {unit['date']} | {history_name} | sha256={sha(unit['text'])[:16]}{ending}"


def plan(raw, settings, today=None, notes=None):
    """What a move would do. raw: the file's bytes (strict UTF-8). settings: memory_size_check.resume_settings.
    Returns units (kind keep / move / structure / index, in file order), the new text, the history name and sizes."""
    text = raw.decode("utf-8")
    notes = [] if notes is None else notes
    today = today or datetime.date.today()
    history_name = f"RESUME_HISTORY_{today:%Y%m%d}.md"
    units = []
    for unit in sections(text, settings["protect_headings"]):
        if unit["kind"] != "header":
            units.append(unit)
            continue
        for n, line in unit["lines"]:
            if HEADER_KEY.match(line) and CHAIN.search(line):
                units += chain_pieces(line, n, settings, history_name, notes)
            else:
                units.append({"start": n, "end": n, "text": line, "kind": "keep", "reason": "header line"})
    candidates = [u for u in units if u["kind"] == "candidate"]
    newest = sorted(candidates, key=lambda u: u["date"], reverse=True)
    keep_recent = settings["keep_recent"]
    cut = newest[keep_recent - 1]["date"] if len(newest) > keep_recent else None
    for unit in candidates:
        if cut is None or unit["date"] >= cut:
            unit.update(kind="keep", reason=f"recent (newest {keep_recent} dated)")
        else:
            unit.update(kind="move", reason=f"older than the newest {keep_recent} dated",
                        index=index_line(unit, history_name), what=f"lines {unit['start']}-{unit['end']}")
    undated = sum(u.get("reason") == "no full date (order unclear, stays)" for u in units)
    if undated:
        notes.append(f"shadow: RESUME_ORDER {undated} part(s) have no full date: their place in the order cannot be "
                     "read, they stay")
    new_text = "".join(u["index"] if u["kind"] == "move" else u["text"] for u in units)
    moved = [u for u in units if u["kind"] == "move"]
    return {"units": units, "moved": moved, "history_name": history_name, "new_text": new_text, "notes": notes,
            "before_bytes": len(raw), "after_bytes": len(new_text.encode("utf-8")),
            "moved_bytes": sum(len(u["text"].encode("utf-8")) for u in moved)}


def history_entries(result, source_name, at, ending):
    parts = []
    for u in result["moved"]:
        body = u["text"] if u["text"].endswith("\n") else u["text"] + ending
        parts.append(f"<!-- RESUME_ARCHIVE from={source_name} {u['what'].replace(' ', '_')} date={u['date']} at={at} "
                     f"sha256={sha(u['text'])} bytes={len(u['text'].encode('utf-8'))} -->{ending}{body}"
                     f"<!-- /RESUME_ARCHIVE -->{ending}")
    return "".join(parts)


def header_keys(text):
    lines = text.splitlines()[:4]
    return [HEADER_KEY.match(line).group(1) if HEADER_KEY.match(line) else line for line in lines]


def verify(raw, new_raw, old_history, history_raw, result):
    """The three checks; returns (problems, kept) where kept lists (unit, sha16) of every kept part found unchanged."""
    problems, kept = [], []
    # (a) the history file: old part unchanged, every moved text word for word, in order, in the new part
    if not history_raw.startswith(old_history):
        problems.append("(a) the history file's earlier content changed")
    added, pos = history_raw[len(old_history):].decode("utf-8", "replace"), 0
    for u in result["moved"]:
        at = added.find(u["text"], pos)
        if at < 0:
            problems.append(f"(a) moved {u['what']} is not in the history file word for word")
            break
        pos = at + len(u["text"])
    # (b) every kept part unchanged and in order in the new file; the header keeps its four lines
    try:
        new_text = new_raw.decode("utf-8")
    except UnicodeDecodeError:
        return problems + ["(b) the new file is not UTF-8"], kept
    pos = 0
    for u in result["units"]:
        if u["kind"] in ("move", "structure") or not u["text"]:
            continue
        at = new_text.find(u["text"], pos)
        if at < 0 or sha(new_text[at:at + len(u["text"])]) != sha(u["text"]):
            problems.append(f"(b) kept lines {u['start']}-{u['end']} ({u['reason']}) changed or missing")
            break
        kept.append((u, sha(u["text"])[:16]))
        pos = at + len(u["text"])
    if header_keys(new_text) != header_keys(raw.decode("utf-8")):
        problems.append("(b) the header is no longer the same four lines")
    # (c) moved + kept = the original: put each moved text back in place of its index, in order
    rebuilt, pos = [], 0
    for u in result["moved"]:
        at = new_text.find(u["index"], pos)
        if at < 0:
            problems.append(f"(c) the index of {u['what']} is missing")
            return problems, kept
        rebuilt += [new_text[pos:at], u["text"]]
        pos = at + len(u["index"])
    rebuilt.append(new_text[pos:])
    if "".join(rebuilt).encode("utf-8") != raw:
        problems.append("(c) moved + kept does not give the original file byte for byte")
    return problems, kept


def report(result, settings, size):
    facts = size.measure(result["raw"])
    print(f"before: {facts['bytes']} bytes, ~{facts['tokens']} tokens, longest line {facts['longest_line']}: "
          f"{facts['longest_bytes']} bytes")
    for u in result["units"]:
        if u["kind"] in ("structure", "index"):
            continue
        size_bytes = len(u["text"].encode("utf-8"))
        date = f", {u['date']}" if u.get("date") else ""
        if u["kind"] == "move":
            print(f"MOVE {u['what']}: {size_bytes} bytes{date}")
        else:
            print(f"KEEP lines {u['start']}-{u['end']}: {size_bytes} bytes{date} - {u['reason']}")
    for note in result["notes"]:
        print(f"  ~ {note}")
    after = size.measure(result["new_text"].encode("utf-8"))
    print(f"after: {after['bytes']} bytes, ~{after['tokens']} tokens, longest line {after['longest_line']}: "
          f"{after['longest_bytes']} bytes; {len(result['moved'])} parts, {result['moved_bytes']} bytes to "
          f"{result['history_name']}")
    if size.over_limits(after, settings["max_bytes"], settings["max_line_bytes"]):
        print(f"~ shadow: RESUME_SIZE protected part over limit: {after['bytes']} bytes (limit {settings['max_bytes']}), "
              f"longest line {after['longest_line']}: {after['longest_bytes']} bytes (limit {settings['max_line_bytes']}) "
              f"after every movable part moves; protected parts are never moved, the Director decides by hand")
    return after


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="a RESUME_STATE.md")
    ap.add_argument("--execute", action="store_true", help="really move (default: dry-run, writes nothing)")
    ap.add_argument("--config", help="director_work.json (default: the one beside the file, if any)")
    ap.add_argument("--keep-recent", type=int, help="newest sections / chain entries never moved (default 10)")
    ap.add_argument("--today", help="YYYY-MM-DD: the history file's date (tests; default today)")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    path, notes, size = pathlib.Path(a.file), [], size_tool()
    if not path.is_file():
        print(f"NOT_FOUND {path}")
        return 2
    config = pathlib.Path(a.config) if a.config else path.resolve().parent / "director_work.json"
    if a.config and not config.is_file():
        print(f"NOT_FOUND {config} (--config)")
        return 2
    settings = size.resume_settings(size.read_config(config, notes) if config.is_file() else {}, notes)
    if a.keep_recent is not None:
        if a.keep_recent < 1:
            ap.error("--keep-recent takes a whole number above 0")
        settings["keep_recent"] = a.keep_recent
    try:
        today = datetime.date.fromisoformat(a.today) if a.today else datetime.date.today()
    except ValueError:
        ap.error("--today takes YYYY-MM-DD")
    raw = path.read_bytes()
    try:
        result = plan(raw, settings, today, notes)
    except UnicodeDecodeError:
        print(f"NOT_UTF8 {path}: not read, nothing moved")
        return 2
    result["raw"] = raw
    print(f"RESUME_ARCHIVE {path} ({'execute' if a.execute else 'dry-run, nothing written'}; keep_recent="
          f"{settings['keep_recent']} today={today})")
    after = report(result, settings, size)
    if not a.execute:
        print(f"ARCHIVE: DRY_RUN movable={len(result['moved'])} bytes={result['moved_bytes']}")
        return 0
    if not result["moved"]:
        print("ARCHIVE: NOTHING_TO_MOVE (file not touched)")
        return 0
    now = datetime.datetime.now()
    backup = path.with_name(f"{path.name}.{now:%Y%m%d-%H%M%S}.bak")
    if backup.exists():
        print(f"BACKUP_EXISTS {backup}: nothing moved, run again in a second")
        return 2
    backup.write_bytes(raw)
    if backup.read_bytes() != raw:
        print(f"BACKUP_FAILED {backup}: nothing moved")
        return 1
    history = path.with_name(result["history_name"])
    had_history = history.exists()
    old_history = history.read_bytes() if had_history else b""
    ending = "\r\n" if "\r\n" in result["new_text"] else "\n"
    added = history_entries(result, path.name, now.strftime("%Y-%m-%d %H:%M"), ending)
    if not had_history:
        added = (f"# RESUME_HISTORY {today} - parts moved word for word from {path.name} by resume_archive.py; "
                 f"never edit, read on demand{ending}{ending}") + added
    new_raw = result["new_text"].encode("utf-8")
    try:
        with open(history, "ab") as out:
            out.write(added.encode("utf-8"))
        path.write_bytes(new_raw)
        problems, kept = verify(raw, path.read_bytes(), old_history, history.read_bytes(), result)
    except OSError as error:
        problems, kept = [f"write failed: {error}"], []
    if problems:
        for problem in problems:
            print(f"VERIFY FAIL {problem}")
        path.write_bytes(backup.read_bytes())
        if had_history:
            history.write_bytes(old_history)
        elif history.exists():
            history.unlink()
        restored = path.read_bytes() == raw and (history.read_bytes() == old_history if had_history else not history.exists())
        print(f"RESTORED from {backup.name}: {'file and history back as they were' if restored else 'RESTORE FAILED, copy the .bak back by hand'}")
        print(f"ARCHIVE: FAIL restored={'yes' if restored else 'NO'} backup={backup}")
        return 1
    print(f"VERIFY (a) OK: {history.name} holds the {len(result['moved'])} moved parts word for word; earlier content unchanged")
    print(f"VERIFY (b) OK: {len(kept)} kept parts unchanged (sha256 before = after); the header is still the same four lines")
    for unit, digest in kept:
        if unit["kind"] == "keep":
            print(f"  SHA lines {unit['start']}-{unit['end']} sha256={digest} unchanged - {unit['reason']}")
    print("VERIFY (c) OK: moved + kept = the original file byte for byte")
    print(f"ARCHIVE: DONE moved={len(result['moved'])} bytes {result['before_bytes']} -> {after['bytes']} "
          f"(~{result['before_bytes'] // 2} -> ~{after['tokens']} tokens) history={history} backup={backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
