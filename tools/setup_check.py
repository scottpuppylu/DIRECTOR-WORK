"""Check that setup made the PO page (DIRECTOR-WORK 2.2.0, BOOTSTRAP step 6; run before the first report, step 13),
and since 2.2.1 the PO_PENDING.md entries, the RESUME_STATE.md header and director_work.json beside it.

  setup_check.py [--strict] <WS>/DIRECTOR [...]   each folder's DIRECTOR_STATE.md (a state file may be given instead)

DIRECTOR_STATE.md must say where the PO page is and whether it is pinned. Three states pass:

  PO_PAGE_URL: https://claude.ai/artifact/<id>      (or https://claude.ai/code/artifact/<id>)
  PO_PAGE_PINNED: yes

  PO_PAGE_URL: https://claude.ai/artifact/<id>
  PO_PAGE_PINNED: no reason=<why>                   pinning failed: also prints a note to ask the PO to pin it

  PO_PAGE_URL: NONE reason=<why>                    no page (no Artifact tool, publishing failed, the PO said no);
                                                    PO_PAGE_PINNED may be left out or be `no reason=<why>`

A missing or repeated line, a placeholder (`<...>`), an empty or missing reason, or any other value fails.

2.2.1 checks the three files beside DIRECTOR_STATE.md (in the folder given, or beside a file named
DIRECTOR_STATE.md); a file that is not there yet is only noted (PO_PENDING.md and RESUME_STATE.md come at BOOTSTRAP
step 6, director_work.json at step 7):
  PO_PENDING.md       every entry `ID: OD-xx` / `ID: ACT-xx` has ID, STATUS, QUESTION, OPTIONS, RECOMMENDED, SOURCE
                      and ANSWER once each (CREATED missing is a note); STATUS is open, answered or closed; QUESTION,
                      OPTIONS and RECOMMENDED are filled in; SOURCE is filled in or NONE; answered / closed needs a real
                      ANSWER; an ID is used once
  RESUME_STATE.md     the four header lines PROGRESS / DOING / NEXT_STEP / COMMS first, in this order, filled in, and
                      UPDATED with a date (the same rule as `gate_check.py --resume`)
  director_work.json  a JSON object; schema_version 1 (or left out); window 100000-1000000; mode general / beginner;
                      plugins_off name@marketplace; guard_profile / guard_mode known values; the *_pattern keys valid
                      regular expressions; the other known keys of the right type (an unknown key is a note)
These start in shadow mode: what they find is printed as `  ~ shadow: ...` and the exit code stays what the PO page
check gives. --strict turns them into `  - problem` lines that fail.

Prints `OK   setup <file>` or `FAIL setup <file>` with one `  - problem` line each and `  ~ note` lines; exit 1 when
any file fails. Standard library only, read only.
"""
import argparse
import importlib.util
import json
import pathlib
import re
import sys

ARTIFACT_URL = re.compile(r"https://claude\.ai/(?:code/)?artifact/[A-Za-z0-9_-]+/?")
PLACEHOLDER = re.compile(r"<[^<>@\n]+>")  # same rule as gate_check: <name@host> is an address, not a placeholder
CODE = re.compile(r"`[^`\n]*`")
HERE = pathlib.Path(__file__).resolve().parent
PO_FIELDS = ("ID", "STATUS", "QUESTION", "OPTIONS", "RECOMMENDED", "SOURCE", "ANSWER")
PO_STATUSES = ("open", "answered", "closed")
PO_ID = re.compile(r"^[ \t]*ID[ \t]*:[ \t]*(.*)$")
PO_ITEM = re.compile(r"(?:OD|ACT)-\w+")  # metrics_report.py counts `ID: OD-..` / `ID: ACT-..` the same way
PO_LINE = re.compile(r"^[ \t]*([A-Z][A-Z_]*)[ \t]*:[ \t]?(.*)$")
HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+(.*)$")
CONFIG_MODES = ("general", "beginner")
CONFIG_STRINGS = ("backup_dir", "protect_director", "director_worktree", "session_map", "pause_flag", "audit_log")
CONFIG_LISTS = ("skip_worktrees", "po_pending_files")
CONFIG_BOOLS = ("hooks", "runtime_guard", "guard_review")
CONFIG_PATTERNS = ("trace_id_pattern", "po_item_pattern", "po_open_pattern")
CONFIG_KEYS = (("schema_version", "mode", "window", "plugins_off", "guard_profile", "guard_mode") + CONFIG_STRINGS
               + CONFIG_LISTS + CONFIG_BOOLS + CONFIG_PATTERNS)


def filled(name, value, problems):
    if value.strip() in ("", "...", "…"):
        problems.append(f"{name}: empty")
    elif PLACEHOLDER.search(CODE.sub("", value)):
        problems.append(f"{name}: placeholder left: {PLACEHOLDER.search(CODE.sub('', value)).group(0)}")


def setup_reason(key, value, problems):
    """`<word> reason=<why>`: the why must be written out, not left empty or as a placeholder."""
    m = re.fullmatch(r"(\S+)[ \t]+reason=(.*)", value)
    if not m:
        problems.append(f"{key}: write `{value.split()[0]} reason=<why>`; the reason is missing")
    else:
        filled(f"{key} reason", m.group(2), problems)


def check_setup(text, notes):
    """Problems with the two PO page lines of a DIRECTOR_STATE.md text; notes get the hints."""
    problems, lines = [], {}
    for key in ("PO_PAGE_URL", "PO_PAGE_PINNED"):
        found = re.findall(rf"^{key}[ \t]*:(.*)$", text, re.M)
        if len(found) > 1:
            problems.append(f"{key}: {len(found)} lines; keep one")
        lines[key] = found[0].strip() if found else None
    url, pinned = lines["PO_PAGE_URL"], lines["PO_PAGE_PINNED"]
    none = url is not None and url.split()[:1] == ["NONE"]
    if url is None:
        problems.append("PO_PAGE_URL: line missing; write `PO_PAGE_URL: <claude.ai link>` or "
                        "`PO_PAGE_URL: NONE reason=<why>` (BOOTSTRAP step 6)")
    elif none:
        setup_reason("PO_PAGE_URL", url, problems)
    elif not ARTIFACT_URL.fullmatch(url):
        problems.append("PO_PAGE_URL: not a claude.ai artifact link (https://claude.ai/artifact/<id> or "
                        f"https://claude.ai/code/artifact/<id>) and not `NONE reason=<why>`: {url or 'empty'}")
    if pinned is None:
        if url is not None and not none:
            problems.append("PO_PAGE_PINNED: line missing; write `yes`, or `no reason=<why>` when pinning failed")
    elif pinned.split()[:1] == ["no"]:
        setup_reason("PO_PAGE_PINNED", pinned, problems)
        if not none:
            notes.append("PO_PAGE_PINNED no: ask the PO to pin the page in the sidebar themselves")
    elif pinned != "yes" or none:
        problems.append("PO_PAGE_PINNED: `yes` or `no reason=<why>`" + (" (with PO_PAGE_URL NONE there is no page to "
                        "pin: leave the line out or write `no reason=<why>`)" if none else "") + f", got: {pinned or 'empty'}")
    return problems


def neighbour(name):
    """A sibling tool loaded from this folder, so a rule has one source (gate_check, setup_project_settings)."""
    spec = importlib.util.spec_from_file_location(f"setup_check_{name}", HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def real_answer(value):
    return value.strip() not in ("", "...", "…", "NONE") and not PLACEHOLDER.search(CODE.sub("", value))


def check_po_pending(text, notes):
    """2.2.1: problems with the entries of a PO_PENDING.md text (the fields of templates/PO_PENDING.md)."""
    problems, entries, section, current = [], [], "", None
    for number, line in enumerate(text.splitlines(), 1):
        heading = HEADING.match(line)
        if heading:
            section, current = heading.group(1), None
            continue
        start = PO_ID.match(line)
        if start:
            item = PO_ITEM.match(start.group(1).strip())
            current = None
            if not item:
                notes.append(f"PO_PENDING line {number}: `ID: {start.group(1).strip()[:40]}` is not OD-xx / ACT-xx; "
                             "the tools do not count it")
                continue
            current = {"id": item.group(0), "line": number, "section": section, "fields": {"ID": [item.group(0)]}}
            entries.append(current)
            continue
        field = PO_LINE.match(line)
        if field and current is not None:
            current["fields"].setdefault(field.group(1), []).append(field.group(2).strip())
    if not entries:
        notes.append("PO_PENDING: no entry yet (fine before the first question)")
    seen = {}
    for entry in entries:
        label, fields = f"PO_PENDING {entry['id']} (line {entry['line']})", entry["fields"]
        if entry["id"] in seen:
            problems.append(f"{label}: the ID is used again (first at line {seen[entry['id']]}); give it a new number")
        seen.setdefault(entry["id"], entry["line"])
        for key in PO_FIELDS:
            if key not in fields:
                problems.append(f"{label}: {key}: line missing")
            elif len(fields[key]) > 1:
                problems.append(f"{label}: {key}: {len(fields[key])} lines; keep one")
        if "CREATED" not in fields:
            notes.append(f"{label}: no CREATED line (older entries may lack it)")
        status = (fields.get("STATUS") or [""])[0]
        if "STATUS" in fields and status not in PO_STATUSES:
            problems.append(f"{label}: STATUS: one of {' / '.join(PO_STATUSES)}, got: {status or 'empty'}")
        for key in ("QUESTION", "OPTIONS", "RECOMMENDED"):
            if key in fields:
                filled(f"{label}: {key}", fields[key][0], problems)
        if "SOURCE" in fields and fields["SOURCE"][0] != "NONE":
            filled(f"{label}: SOURCE (or NONE)", fields["SOURCE"][0], problems)
        answer = (fields.get("ANSWER") or [""])[0]
        if status in ("answered", "closed") and not real_answer(answer):
            problems.append(f"{label}: STATUS {status} needs the PO's ANSWER, got: {answer or 'empty'}")
        elif status == "open" and real_answer(answer):
            notes.append(f"{label}: ANSWER is there but STATUS is still open")
        if status == "closed" and "未關閉" in entry["section"]:
            notes.append(f"{label}: closed but still under 未關閉; move it to 已關閉")
        elif status in ("open", "answered") and "已關閉" in entry["section"]:
            notes.append(f"{label}: under 已關閉 but STATUS is {status}")
    return problems


def check_resume_header(text, notes):
    """2.2.1: the RESUME_STATE.md header, by gate_check.check_resume (one rule for both tools)."""
    return [f"RESUME_STATE: {problem}" for problem in neighbour("gate_check").check_resume(text, notes)]


def pattern_problem(key, value):
    if not isinstance(value, str):
        return f"{key}: a string (a regular expression), got {type(value).__name__}"
    try:
        re.compile(value)
    except re.error as error:
        return f"{key}: not a valid regular expression ({error})"
    return None


def check_config(text, notes):
    """2.2.1: problems with a director_work.json text (the keys of director_work.example.json and the tools)."""
    try:
        data = json.loads(text)
    except ValueError as error:
        return [f"director_work.json: not JSON ({error})"]
    if not isinstance(data, dict):
        return [f"director_work.json: a JSON object is needed, got {type(data).__name__}"]
    problems, settings = [], neighbour("setup_project_settings")

    def say(message):
        problems.append(f"director_work.json: {message}")

    version = data.get("schema_version", settings.CONFIG_VERSION)
    if version != settings.CONFIG_VERSION or isinstance(version, bool):
        say(f"schema_version {version!r} is not {settings.CONFIG_VERSION}; the tools refuse it (see CHANGELOG.md)")
    if "mode" in data and data["mode"] not in CONFIG_MODES:
        say(f"mode: {' / '.join(CONFIG_MODES)}, got {data['mode']!r}")
    window = data.get("window")
    if "window" in data and (not isinstance(window, int) or isinstance(window, bool) or not 100000 <= window <= 1000000):
        say(f"window: a whole number 100000-1000000, got {window!r}")
    plugins = data.get("plugins_off", [])
    if not isinstance(plugins, list) or not all(isinstance(p, str) for p in plugins):
        say("plugins_off: a list of name@marketplace strings")
    else:
        for name in plugins:
            if name.startswith("example-plugin@"):
                notes.append(f"director_work.json: plugins_off still holds the example {name}; delete it (BOOTSTRAP)")
            elif "@" not in name:
                say(f"plugins_off: {name!r} is not name@marketplace")
    for key, allowed in (("guard_profile", settings.PROFILES), ("guard_mode", settings.MODES)):
        if data.get(key) is not None and data[key] not in allowed:
            say(f"{key}: one of {' / '.join(allowed)} or null, got {data[key]!r}")
    for key in CONFIG_STRINGS:
        if data.get(key) is not None and not isinstance(data[key], str):
            say(f"{key}: a path string or null, got {type(data[key]).__name__}")
    for key in CONFIG_LISTS:
        if key in data and not (isinstance(data[key], list) and all(isinstance(x, str) for x in data[key])):
            say(f"{key}: a list of strings")
    for key in CONFIG_BOOLS:
        if key in data and not isinstance(data[key], bool):
            say(f"{key}: true or false, got {data[key]!r}")
    for key in CONFIG_PATTERNS:
        if data.get(key) is not None and pattern_problem(key, data[key]):
            say(pattern_problem(key, data[key]))
    unknown = sorted(k for k in data if k not in CONFIG_KEYS and not k.startswith("_"))
    if unknown:
        notes.append(f"director_work.json: keys no tool reads: {', '.join(unknown)} (a typo?)")
    return problems


NEIGHBOURS = (("PO_PENDING.md", check_po_pending), ("RESUME_STATE.md", check_resume_header),
              ("director_work.json", check_config))


def check_neighbours(folder, notes):
    """2.2.1: problems in the three files beside DIRECTOR_STATE.md; a file not there yet is a note."""
    problems, missing = [], []
    for name, check in NEIGHBOURS:
        path = folder / name
        if not path.is_file():
            missing.append(name)
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as error:
            problems.append(f"{name}: cannot read ({error.__class__.__name__})")
            continue
        problems += check(text, notes)
    if missing:
        notes.append(f"not checked, not there yet: {', '.join(missing)}")
    return problems


def state_file(path):
    """A DIRECTOR folder (its DIRECTOR_STATE.md is read) or the state file itself."""
    target = pathlib.Path(path)
    return target / "DIRECTOR_STATE.md" if target.is_dir() else target


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+", metavar="DIR", help="<WS>/DIRECTOR, or a DIRECTOR_STATE.md")
    ap.add_argument("--strict", action="store_true", help="2.2.1 checks (PO_PENDING, RESUME header, director_work.json) "
                    "fail instead of printing shadow notes")
    a = ap.parse_args(argv)
    failed = 0
    for path in a.dirs:
        target, notes = state_file(path), []
        if target.is_file():
            problems = check_setup(target.read_text(encoding="utf-8-sig"), notes)
        else:
            problems = ["file not found"]
        if target.parent.is_dir() and (pathlib.Path(path).is_dir() or target.name == "DIRECTOR_STATE.md"):
            found = check_neighbours(target.parent, notes)
            if a.strict:
                problems += found
            else:
                notes += [f"shadow: {problem}" for problem in found]
        failed += bool(problems)
        print(f"{'FAIL' if problems else 'OK  '} setup {target}")
        for line in [f"  - {p}" for p in problems] + [f"  ~ {n}" for n in notes]:
            print(line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
