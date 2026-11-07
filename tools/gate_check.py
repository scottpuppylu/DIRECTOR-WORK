"""Check the format of a RESUME_STATE, work order, task report or gate verdict, so a rule fails in a script instead of
relying on the model remembering it.

Prints OK / FAIL per file with one line per problem; exit 1 when anything fails. Only reads, except `--snapshot`,
which writes one snapshot file.
Passing means the file follows the format and the rules below. It does not mean the work is correct: reviewing the
evidence and the product is still the Director's job (docs/02, docs/07).

  --resume   the four header lines come first, in order, filled in; UPDATED holds a date
  --order    required fields filled in; SCOPE / FORBIDDEN are concrete path lists; acceptance rows are concrete;
             an optional `CHECKS:` list holds one `- AC-n: ["program", "arg"]` line (JSON array of strings) per AUTO
             criterion: the check the Director approves, locked by the dispatch hash. A Strict order with an AUTO
             criterion and no check is noted. An optional `REQUIRED_CHANGES:` list (globs the work must change, read
             by scope_check.py) must lie inside SCOPE and outside FORBIDDEN, or the order cannot be done
  --report   required fields filled in; RESULT in the vocabulary; PASS is refused with NOT_RUN tests or a scope violation
  --test-request
             every field of templates/TEST_REQUEST.md filled; BUILD_GB, CACHE_GB and WRITE_GB in GiB, not GB;
             CAPTURE `<sets> x <images> x <MiB> = <GiB>` (or NONE) adds up; WRITE_GB covers BUILD_GB + CAPTURE +
             CACHE_GB (L-030, L-031); DURATION `<sets> x <measured minutes per set, timeouts included> = <minutes>`
             adds up and fits the limit on the TEST REQUEST line (L-033)
  --verdict  verdict and next step in the vocabulary; status split by aspect; stop state written. With --match, the
             verdict's `ORDER: <file> REVISION n` line must name a matched order at its REVISION; with --candidate, its
             `CANDIDATE_HEAD:` must be that commit (exactly for Strict). A missing line fails Strict and is noted otherwise
  --match REPORT ORDER
             the report's ACCEPTANCE table against the order, one row per AC: no AC missing or added; each status
             allowed for its type (a worker cannot write PASS on a REVIEW or PO criterion); PASS needs evidence;
             RESULT PASS with no FAIL / BLOCKED / UNVERIFIED row; ORDER_SHA256 equals the order's hash now.
             Either table fails on a duplicate AC row, a duplicate column name or a row whose cell count differs
             from the header's; a `|` inside backticks or written `\\|` does not split a cell
  --evidence-dir DIR
             with --match: an AUTO row marked PASS must name in 證據 an evidence_record.py file (.json) in DIR whose
             command exited 0, with no artifact missing, recorded at the HEAD the report names. A file without the
             record's fields and types (schema, label, command, cwd, started, finished, exit_code, timed_out, git,
             artifacts) is not evidence; one without `schema` is read as legacy. A legacy record, a record without
             git HEAD, uncommitted changes or a label naming another AC fail a Strict order and are noted otherwise.
             The report's HEAD must be 7 to 40 hex digits: Strict fails, Standard and --report note it. When the order
             has CHECKS, a record's command must be the approved one for its AC: Strict fails, Standard notes it.
             A record's `order` field (`evidence_record.py run --order`) must name this order at its REVISION and
             hash, unless --dispatch-log has the whole line `EVIDENCE_EQUIVALENT <WO-ID> rev=<old> sha=<old hash>
             to rev=<new>` (read like a DISPATCH line). A record without one gets a WARN at REVISION 1; from
             REVISION 2 it fails Strict and is noted otherwise.
             The records are read, not rerun: only `evidence_record.py verify --rerun --order ...` runs a check again
  --dispatch-log LOG
             with --match: the order's hash now must equal the one the Director logged at dispatch, as a line
             `DISPATCH <WO-ID> rev=<n> sha=<64 hex>` in LOG (the last line for an order wins; the ID is the order's
             title or file name), and rev must be the order's REVISION. The line is the whole line, optionally after
             a `<date> |` column and before a `| <basis>` column; a DISPATCH quoted in a note, indented, after `>` or
             inside a ``` / ~~~ fence is not one. No line for the order fails in every governance mode. The title's
             ID and the file name's ID must agree, and the report's ORDER line must name this order.
             Without this flag the hash is only compared with the order as it is now, which a worker can rewrite.
  --candidate SHA
             with --match or --verdict: the commit under review, 40 hex digits, which the Director reads with
             `git rev-parse <worker branch>`. The report's HEAD must be it (a prefix is enough outside Strict) and every
             evidence record must be recorded at it (exactly for Strict).
  Strict binds the review to one commit: a Strict --match fails without --candidate, without --dispatch-log, without
             --evidence-dir when an AUTO row is PASS, or when the report's HEAD is not all 40 hex digits.
             The report's `ORDER: <file> REVISION n` line must name the order's REVISION; without a revision Strict
             fails and Standard notes it.
  --hash FILE  print the SHA-256 that ORDER_SHA256 compares (line endings counted as LF) and the DISPATCH line to log
  --preflight REPORT ORDER
             before moving a review made with an older version to this one: list, one `LACKS` line each, what the
             report, order, evidence and dispatch log lack for a Strict review now (a HEAD that is not 40 hex digits, a
             report ORDER line without REVISION, an order without a DISPATCH line for its REVISION, AUTO criteria
             without CHECKS, evidence records without a supported schema, a full git HEAD or `git.dirty` false).
             With --repo, a short HEAD is resolved there to the full commit (when it is unique). Takes
             --evidence-dir and --dispatch-log; what they would show is NOT_CHECKED without them. Exit 1 when
             anything is lacking. Only reads, like every check here.

2.1 (shadow: these only add `~` notes and never change the exit code; an order without the new fields passes as before):
  --brief BRIEF.md
             alone: print the brief's `BRIEF_REVISION = n` and `BRIEF_FINGERPRINTS_V1 = {"B-2": "<sha256>"}` lines for an
             order to pin. A row's fingerprint is sha256 of UTF-8 `brief-row-v1\n` + the compact JSON array
             [ID, 類別, 內容, 怎麼算做到] of the 編號 table row (cells read by split_cells, ID without ** or backticks).
             With --order / --match / --preflight: `~ BRIEF_STALE <WO> <B> <AC-1,AC-2 | WHOLE_ORDER>` when a pinned row
             changed or is gone (舊條件驗過，新條件待重驗 / 需求已取消), `~ BRIEF_UNCONFIRMED` (依據未確認) for a row listed
             twice or not 4 cells wide, an order without pins that traces brief rows, or a traced row it did not pin. With
             --dispatch-log, the latest whole line `BRIEF_LOCKED rev=<n> sha=<64 hex> snapshot=<path>` (path from the log's
             folder) is the basis: a brief that is not it is compared through the locked snapshot (a draft is not the basis).
  --snapshot DIR
             with --brief (狀態 LOCKED, 版次 a number): write DIR/<版次>-<sha>.md atomically (temp file in DIR, fsync,
             rename; an identical file is kept) and print the BRIEF_LOCKED line to log. With --hash ORDER: keep the order
             as DIR/<WO-ID>-rev<n>-<sha>.md for --order-history.
  --order-history DIR
             with --match: evidence carried over by EVIDENCE_EQUIVALENT is compared with the fingerprints the old order
             (found in DIR by its hash) pinned; a changed condition is `~ BRIEF_STALE`, no old order `~ BRIEF_UNCONFIRMED`.
  --po-acceptance PO_ACCEPTANCE.json
             the PO's acceptance records (schema po-acceptance-v1: candidate_id, commit, entry, entry_sha256,
             manifest_sha256, offered_message_ref, reply_ref, outcome seen / changes / accepted / null, replied_at,
             excerpt); a record missing a binding is `~ UNBOUND_PO_REPLY`. With --candidate the commit must be it.
  A verdict may carry `ORDER_SHA256:` and `REPORT_SHA256:` (gate_check.py --hash of each file); with --match a
             mismatch is `~ VERDICT_RECORD`.

The hash only detects a changed order after the fact; it cannot stop anyone from editing it. An evidence record shows
a command ran and passed, not that it tests the right thing.
Lines starting with `~` are notes for the newer format (v0.10): they never fail a file.

Bringing in a project that already has files in another format:
  --warn          print WARN instead of FAIL and exit 0, so old files do not block work
  --since DATE    SKIP files dated before DATE (YYYY-MM-DD): ISSUED_BY of an order, UPDATED of a RESUME_STATE, the
                  first date in a report or verdict. A file with no such date cannot be placed, so it is also SKIPped,
                  marked UNDATED and counted on its own in the last line; run without --since to check it.
The fixed words come from vocabulary.json next to this file.
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import sys

VOCAB = json.loads((pathlib.Path(__file__).resolve().parent / "vocabulary.json").read_text(encoding="utf-8"))
RESUME_HEADER = tuple(VOCAB["resume_header"])
ORDER_FIELDS = ("ISSUED_BY", "PRIMARY_WORKER", "MODEL / EFFORT", "FALLBACK", "GOVERNANCE", "BASE_REF")
GOVERNANCE = tuple(VOCAB["governance"])
REPORT_FIELDS = ("RESULT", "ENGINEERING", "PRODUCT", "DONE", "TESTS", "SCOPE_CHECK", "EVIDENCE", "UNVERIFIED",
                 "KNOWN_ISSUES", "NEXT")
REPORT_RESULTS = tuple(VOCAB["report_results"])
VERDICTS = tuple(VOCAB["verdicts"])
NEXT_STEPS = tuple(VOCAB["next_steps"])
AC_STATUSES = VOCAB["ac_worker_statuses"]  # type -> the statuses a worker may write in the report
UNFINISHED = ("FAIL", "BLOCKED", "UNVERIFIED")
COLUMNS = {"類型": "type", "type": "type", "要求": "requirement", "req": "requirement", "驗證方法": "how verified",
           "how": "how verified", "預期": "expected", "expected": "expected", "實際": "actual", "actual": "actual",
           "證據": "evidence", "evidence": "evidence", "狀態": "status", "status": "status",
           "追溯": "traces", "traces": "traces"}
LEGACY_COLUMNS = ["requirement", "how verified", "expected", "actual", "evidence", "status"]
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
DATED_BY = {"order": r"^\s*ISSUED_BY\s*=.*?(\d{4}-\d{2}-\d{2})", "resume": r"^UPDATED\s*:.*?(\d{4}-\d{2}-\d{2})"}
VAGUE = re.compile(r"視情況|相關檔案|相關的檔案|等等|之類|適當|盡量|儘量|必要時|(?<![\w./\-])(?:as needed|etc|tbd|todo)(?![\w/\-]|\.\w)", re.I)  # not inside a name like todo.py
PLACEHOLDER = re.compile(r"<[^<>@\n]+>")  # <name@host> is an address, not a placeholder
CODE = re.compile(r"`[^`\n]*`")  # <...> inside a code span is format text, not a placeholder
EVIDENCE_FILE = re.compile(r"[\w.-]+\.json\b")
SHA = re.compile(r"[0-9a-fA-F]{7,40}")
# a DISPATCH event is a whole line: optionally the log's `<date [time] [zone]> |` column first, then the event, then
# optionally `| <basis>`; the same words inside another line (a NOTE, backticks, a `>` quote) are data, not an event
LOG_DATE = r"(?:\d{4}-\d{2}-\d{2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?(?:[ \t]*(?:[+-]\d{2}:?\d{2}|Z))?[ \t]*\|[ \t]*)?"
DISPATCH = re.compile(LOG_DATE + r"DISPATCH[ \t]+([^\s|`]+?)(?:\.md)?[ \t]+rev=(\d+)[ \t]+sha=([0-9a-fA-F]{64})[ \t]*(?:\|[^`]*)?")
# the Director's ruling that evidence recorded for an older revision still holds: a whole line, read like DISPATCH
EQUIVALENT = re.compile(LOG_DATE + r"EVIDENCE_EQUIVALENT[ \t]+([^\s|`]+?)(?:\.md)?[ \t]+rev=(\d+)[ \t]+"
                        r"sha=([0-9a-fA-F]{64})[ \t]+to[ \t]+rev=(\d+)[ \t]*(?:\|[^`]*)?")
FENCE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")
ORDER_ID = re.compile(r"[A-Za-z]+-\d+")
TOO_BROAD = ("*", "**", "**/*", ".", "./", "/")


def blank(value):
    return value.strip() in ("", "...", "…")


def filled(name, value, problems):
    if blank(value):
        problems.append(f"{name}: empty")
    elif PLACEHOLDER.search(CODE.sub("", value)):
        problems.append(f"{name}: placeholder left: {PLACEHOLDER.search(CODE.sub('', value)).group(0)}")
    else:
        return True
    return False


def parse_list(text, key):
    """Items of a `KEY:` line followed by `- item` lines; None when the key is missing. ` #` starts a comment; an item
    written in backticks (`- `a #b.txt``) is taken as it is, so a name holding ` #` round-trips (S02)."""
    lines = text.splitlines()
    for n, line in enumerate(lines):
        if re.fullmatch(rf"\s*{key}\s*[:：]\s*", line):
            items = []
            for item in lines[n + 1:]:
                m = re.match(r"\s*-\s+(.*)", item)
                if not m:
                    break
                quoted = re.fullmatch(r"`([^`]+)`(?:\s+#.*)?\s*", m.group(1))
                items.append(quoted.group(1) if quoted else re.split(r"\s+#", m.group(1))[0].strip())
            return items
    return None


def comment_notes(text, notes):
    """An item cut at ` #` may be a name that holds ` #` (S02): say what was kept, and how to keep the rest. Only when a
    character follows the `#` (`a #1.txt`); `# text`, with a space, is read as an ordinary comment."""
    for key in ("SCOPE", "FORBIDDEN", "REQUIRED_CHANGES", "CHECKS"):
        m = re.search(rf"^[ \t]*{key}[ \t]*[:：][ \t]*\n((?:[ \t]*-[ \t]+.*\n?)*)", text, re.M)
        for line in (m.group(1).splitlines() if m else []):
            item = re.match(r"\s*-\s+(.*)", line).group(1)
            if re.search(r"\s+#\S", item) and not re.fullmatch(r"`([^`]+)`(?:\s+#.*)?\s*", item):
                kept = re.split(r"\s+#", item)[0].strip()
                notes.append(f"{key}: `{item.strip()}` is read as `{kept}` (` #` starts a "
                             "comment); if ` #` is part of the name, write the item in backticks")


def check_paths(key, text, problems):
    items = parse_list(text, key)
    if items is None:
        problems.append(f"{key}: missing (a `{key}:` line followed by `- glob` lines)")
    elif not items:
        problems.append(f"{key}: no entries (write `- NONE` when nothing applies)")
    else:
        for item in items:
            if not filled(key, item, problems):
                continue
            if VAGUE.search(item):
                problems.append(f"{key}: vague entry: {item}")
            elif item in TOO_BROAD:
                problems.append(f"{key}: too broad: {item}")
            elif item.startswith(("/", "..")) or re.match(r"[A-Za-z]:", item):
                problems.append(f"{key}: must be relative to the repo root: {item}")


def split_cells(line):
    r"""The cells of a table row: `|` splits, except inside a backtick code span or escaped as `\|` (which becomes `|`)."""
    cells, cell, fence, i = [], [], 0, 0
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    while i < len(line):
        ch = line[i]
        if ch == "`":
            run = len(line[i:]) - len(line[i:].lstrip("`"))
            fence = 0 if fence == run else (run if fence == 0 else fence)
            cell.append("`" * run)
            i += run
            continue
        if ch == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            cell.append("|")
            i += 2
            continue
        if ch == "|" and not fence:
            cells.append("".join(cell).strip())
            cell = []
        else:
            cell.append(ch)
        i += 1
    cells.append("".join(cell).strip())
    return cells


def ac_table(text, problems=None):
    """{AC id: {column: cell}} from the table rows that start with AC-<n>, columns named by the table's header row.
    A header without known names falls back to the old order: requirement, how verified, expected, ...
    With a problems list, records a duplicate AC row, a duplicate column name and a row whose cell count differs
    from its header's; without one (older callers) it only parses, keeping the first row of a duplicate."""
    header, rows, width = None, {}, None
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = split_cells(line)
        if cells[0] == "ID":
            header = [COLUMNS.get(cell, cell) for cell in cells[1:]]
            width = len(cells)
            seen = set()
            for name in header:
                if name in seen and problems is not None:
                    problems.append(f"acceptance: column {name} appears twice in the header")
                seen.add(name)
        elif re.fullmatch(r"AC-[\w-]+", cells[0]):
            if problems is not None:
                if cells[0] in rows:
                    problems.append(f"{cells[0]}: listed twice; one row per AC")
                if width is not None and len(cells) != width:
                    problems.append(f"{cells[0]}: {len(cells)} cells, the header has {width}")
            if cells[0] in rows:
                continue
            names = header if header and set(header) & set(COLUMNS.values()) else LEGACY_COLUMNS
            rows[cells[0]] = dict(zip(names, cells[1:]))
    return rows


def order_hash(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def order_identity(text, path=None):
    """(names a dispatch line may call this order, problem or None). The names are the first word of its title, its
    file name without .md and that name's leading `WO-n` ID. The problem: the title and the file name give two IDs."""
    title = re.search(r"^#\s+(\S+)", text, re.M)
    title = title.group(1) if title else None
    stem = pathlib.Path(path).stem if path is not None else None
    file_id, title_id = (ORDER_ID.match(name) if name else None for name in (stem, title))
    ids = []
    for name in (title, stem, file_id.group(0) if file_id else None):
        if name and name not in ids:
            ids.append(name)
    problem = None
    if file_id and title_id and file_id.group(0).upper() != title_id.group(0).upper():
        problem = (f"order: the title names {title_id.group(0)}, the file name {pathlib.Path(path).name} names "
                   f"{file_id.group(0)}; one order has one ID")
    return ids, problem


def order_ids(text, path=None):
    """The names a dispatch line may call this order (see order_identity)."""
    return order_identity(text, path)[0]


def order_key(ids):
    """The `WO-n` ID among an order's names (the first one that is only an ID), else its first name, else None."""
    return next((name for name in ids if ORDER_ID.fullmatch(name)), ids[0] if ids else None)


def id_prefixes(names):
    """The leading `WO-n` IDs of names, upper-case."""
    return {m.group(0).upper() for m in (ORDER_ID.match(name) for name in names) if m}


def order_revision(text):
    m = re.search(r"^[ \t]*REVISION[ \t]*=[ \t]*(\d+)", text, re.M)
    return m.group(1) if m else "1"


def order_line(text):
    """(rest of the line, revision or None) of a report's or verdict's `ORDER: WO-file.md REVISION n` line;
    None when there is no ORDER: line. `rev=n` and `REVISION: n` are read too."""
    line = re.search(r"^\s*ORDER\s*:\s*(.+)$", text, re.M)
    if not line:
        return None
    rev = re.search(r"(?:REVISION|\brev)\s*[=:]?\s*(\d+)", line.group(1), re.I)
    return line.group(1), (int(rev.group(1)) if rev else None)


def order_checks(text, problems=None):
    """{AC id: command} from the order's `CHECKS:` list, one `- AC-1: ["program", "arg", ...]` line per AUTO criterion
    (a JSON array of strings, run without a shell); None when the order has no CHECKS. With a problems list, records a
    line that is not in that form and an AC listed twice (the first line wins)."""
    items = parse_list(text, "CHECKS")
    if items is None:
        return None
    checks = {}
    for item in items:
        m = re.fullmatch(r"(AC-[\w-]+)\s*:\s*(.+)", item)
        try:
            command = json.loads(m.group(2)) if m else None
        except ValueError:
            command = None
        if not (isinstance(command, list) and command and all(isinstance(part, str) for part in command)
                and command[0].strip()):
            if problems is not None:
                problems.append(f'CHECKS: `{item}` is not `AC-n: ["program", "arg", ...]` (a JSON array of strings; '
                                "a ` #` starts a comment, so a command cannot hold one)")
            continue
        if m.group(1) in checks:
            if problems is not None:
                problems.append(f"CHECKS: {m.group(1)} listed twice; one approved check per AC")
            continue
        checks[m.group(1)] = command
    return checks


def log_lines(text):
    """The lines of a log that may be events: every line outside a ``` or ~~~ fence, right-stripped. An event must
    then match its pattern as a whole line, so the same words quoted inside another line, after `>` or indented
    are data."""
    fence = None
    for line in text.splitlines():
        mark = FENCE.match(line)
        if mark and fence is None:
            fence = mark.group(1)
            continue
        if fence is not None:
            if mark and mark.group(1)[0] == fence[0] and len(mark.group(1)) >= len(fence) and not mark.group(2).strip():
                fence = None
            continue
        yield line.rstrip()


def dispatch_records(text):
    """{order id: (rev, sha)} from DISPATCH event lines, in log order (a later line for an id moves it to the end, so
    the last item for any of an order's names is its latest dispatch). An event is a whole line,
    `DISPATCH <WO-ID> rev=<n> sha=<64 hex>`, optionally after the log's `<date> |` column and before a `| basis`
    column. The same words quoted inside another line, an indented line and lines inside a ``` or ~~~ fence are data."""
    records = {}
    for line in log_lines(text):
        m = DISPATCH.fullmatch(line)
        if m:
            records.pop(m.group(1), None)
            records[m.group(1)] = (m.group(2), m.group(3).lower())
    return records


def equivalent_records(text):
    """[(order id, old rev, old sha, new rev)] from whole `EVIDENCE_EQUIVALENT <WO-ID> rev=<old> sha=<64 hex> to
    rev=<new>` lines, read by the same rules as DISPATCH lines (log_lines): the Director's ruling that evidence
    recorded for the old revision still answers the new one (G03b)."""
    return [(m.group(1), int(m.group(2)), m.group(3).lower(), int(m.group(4)))
            for m in (EQUIVALENT.fullmatch(line) for line in log_lines(text)) if m]


# 2.1 (題1 P-1/P-4, 題4 P-2): the BRIEF's rows, what an order pinned of them, and the PO's reviews. Shadow: all of it
# only adds notes; a file without the new fields reads as before.
BRIEF_ROW_TAG = "brief-row-v1\n"
UNCONFIRMED = "依據未確認"
BRIEF_LOCKED = re.compile(LOG_DATE + r"BRIEF_LOCKED[ \t]+rev=(\d+)[ \t]+sha=([0-9a-fA-F]{64})(?:[ \t]+snapshot=([^\s|`]+))?"
                          r"[ \t]*(?:\|[^`]*)?")
PO_REVIEW = re.compile(LOG_DATE + r"PO_PRODUCT_REVIEW[ \t]+([A-Za-z]+-\d+)((?:[ \t]+[a-z_]+=[^\s|`]+)+)[ \t]*(?:\|[^`]*)?")
PO_OUTCOMES = {"seen": "seen", "changes": "changes", "accepted": "accepted", "看過": "seen", "要求修改": "changes",
               "接受": "accepted"}
PO_ACCEPTANCE_SCHEMA = "po-acceptance-v1"
HEX64 = re.compile(r"[0-9a-f]{64}")


def id_prefix(name):
    m = re.match(r"[A-Za-z]+", name)
    return m.group(0).upper() if m else ""


def id_sort(name):
    m = re.fullmatch(r"([A-Za-z]+)-(\d+)", name)
    return (m.group(1).upper(), int(m.group(2))) if m else (name, 0)


def brief_table(text):
    """({ID: [ID, 類別, 內容, 怎麼算做到]}, {ambiguous IDs}, problem or None) from the BRIEF's table whose header's first
    cell is 編號 (lines inside a ``` / ~~~ fence are examples, not rows). An ID may be written in ** or backticks. A row
    listed twice, or a row or header that is not 4 cells wide, makes its ID ambiguous: it gets no fingerprint
    (依據未確認). problem: the brief has no such table."""
    rows, ambiguous, width, found = {}, set(), None, False
    for line in log_lines(text):
        if not line.lstrip().startswith("|"):
            width = None
            continue
        cells = split_cells(line)
        if cells[0] == "編號":
            width, found = len(cells), True
            continue
        ident = re.fullmatch(r"\*{0,2}`?([A-Za-z]+-\d+)`?\*{0,2}", cells[0]) if width is not None else None
        if not ident:
            continue
        name = ident.group(1)
        if name in rows or name in ambiguous or width != 4 or len(cells) != 4:
            rows.pop(name, None)
            ambiguous.add(name)
            continue
        rows[name] = [name] + cells[1:]
    return rows, ambiguous, (None if found else "no table whose header starts with 編號")


def brief_fingerprint(row):
    """sha256 of UTF-8 `brief-row-v1\n` + the row as a compact JSON array [ID, 類別, 內容, 怎麼算做到] (ensure_ascii off,
    separators `,` and `:`). Line endings, the spaces around a cell and the 版次 do not change it; a change to any of
    the four cells does."""
    data = BRIEF_ROW_TAG + json.dumps(list(row), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def brief_revision(text):
    m = re.search(r"^\s*[-*]?\s*版次\s*[:：]\s*(\d+)", text, re.M)
    return int(m.group(1)) if m else None


def brief_is_locked(text):
    return bool(re.search(r"^\s*[-*]?\s*狀態\s*[:：]\s*LOCKED\b", text, re.M))


def brief_locks(text):
    """[(rev, sha, snapshot path or None)] from whole `BRIEF_LOCKED rev=<n> sha=<64 hex> [snapshot=<path>]` lines, read
    like DISPATCH lines; the last one is the brief the PO locked."""
    return [(int(m.group(1)), m.group(2).lower(), m.group(3))
            for m in (BRIEF_LOCKED.fullmatch(line) for line in log_lines(text)) if m]


def load_brief(path, log_text=None, log_path=None, notes=None):
    """The brief to compare orders with: {"rows", "ambiguous", "problem", "revision", "label", "sha"}. With a log that
    has BRIEF_LOCKED lines, a brief that is not the latest locked one is replaced by that lock's snapshot (a draft is
    not the basis) when the snapshot is there with the logged hash; otherwise the brief is read and noted as
    依據待確認."""
    notes = notes if notes is not None else []
    data = pathlib.Path(path).read_bytes()
    text, label, sha = data.decode("utf-8-sig", errors="replace"), str(path), order_hash(data)
    locks = brief_locks(log_text) if log_text else []
    if locks and locks[-1][1] != sha:
        rev, locked, snap = locks[-1]
        snap_path = pathlib.Path(log_path).parent / snap if snap and log_path else None
        if snap_path and snap_path.is_file() and order_hash(snap_path.read_bytes()) == locked:
            notes.append(f"BRIEF: {path} is not the latest BRIEF_LOCKED (rev={rev} sha={locked[:12]}); a draft is not the "
                         f"basis: compared with the locked snapshot {snap}")
            text, label, sha = snap_path.read_bytes().decode("utf-8-sig", errors="replace"), snap, locked
        else:
            notes.append(f"BRIEF_UNCONFIRMED: {path} is not the latest BRIEF_LOCKED (rev={rev} sha={locked[:12]}) and its "
                         f"snapshot {snap or '(none named)'} is missing or changed: 依據待確認")
    elif log_text is not None and not locks:
        notes.append("BRIEF: the log has no BRIEF_LOCKED line, so which brief the PO locked is 依據待確認 "
                     "(`gate_check.py --brief BRIEF.md --snapshot DIRECTOR/brief-history` prints it)")
    if not brief_is_locked(text):
        notes.append(f"BRIEF: {label} does not say 狀態：LOCKED; a draft is 依據待確認")
    rows, ambiguous, problem = brief_table(text)
    return {"rows": rows, "ambiguous": ambiguous, "problem": problem, "revision": brief_revision(text), "label": label,
            "sha": sha}


def order_brief(text, notes=None):
    """(BRIEF_REVISION or None, {B: fingerprint} or None) of an order. A value in another form is noted and read as
    absent (shadow: never a problem). The fingerprints are a JSON object on the `BRIEF_FINGERPRINTS_V1 =` line; a
    trailing ` # comment` is allowed."""
    revision = pins = None
    rev = re.search(r"^[ \t]*BRIEF_REVISION[ \t]*=[ \t]*(\S*)", text, re.M)
    if rev and rev.group(1).isdigit():
        revision = int(rev.group(1))
    elif rev and notes is not None:
        notes.append(f"BRIEF_REVISION: not a number ({rev.group(1) or 'empty'}); read as absent")
    line = re.search(r"^[ \t]*BRIEF_FINGERPRINTS_V1[ \t]*=[ \t]*(.*)$", text, re.M)
    if line:
        m = re.search(r"\{.*\}", line.group(1))
        try:
            value = json.loads(m.group(0)) if m else None
        except ValueError:
            value = None
        if isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str) and HEX64.fullmatch(v)
                                           for k, v in value.items()):
            pins = value
        elif notes is not None:
            notes.append('BRIEF_FINGERPRINTS_V1: not a JSON object {"B-2": "<64 lower-case hex>"}; read as absent')
    return revision, pins


def order_traces(text):
    """(IDs on the TRACES_TO line, {AC: IDs of its 追溯 cell} or None when the AC table has no 追溯 column)."""
    line = re.search(r"^[ \t]*TRACES_TO[ \t]*=[ \t]*(.*)$", text, re.M)
    traced = ORDER_ID.findall(re.split(r"\s+#", line.group(1))[0]) if line else []
    rows = ac_table(text)
    per_ac = ({ac: ORDER_ID.findall(row.get("traces", "")) for ac, row in rows.items()}
              if any("traces" in row for row in rows.values()) else None)
    return traced, per_ac


def brief_domain(brief, extra=()):
    """The ID prefixes that are brief rows: those of the brief's rows, else of extra (an order's pins), else B."""
    names = (set(brief["rows"]) | brief["ambiguous"]) if brief else set()
    return {id_prefix(n) for n in names} or {id_prefix(n) for n in extra} or {"B"}


def brief_acs(b, per_ac):
    acs = [ac for ac, ids in (per_ac or {}).items() if b in ids]
    return ",".join(acs) if acs else "WHOLE_ORDER"


def brief_notes(order_text, order_path, brief, notes):
    """Shadow notes for one order against the brief: BRIEF_STALE for a pinned row that changed or is gone,
    BRIEF_UNCONFIRMED (依據未確認) for an ambiguous row, an order with no pins that traces brief rows, and a traced
    row without a pin. A raised 版次 with the rows unchanged is no note."""
    key = order_key(order_ids(order_text, order_path)) or "<WO-ID>"
    revision, pins = order_brief(order_text, notes)
    traced, per_ac = order_traces(order_text)
    rows, ambiguous, domain = brief["rows"], brief["ambiguous"], brief_domain(brief, pins or ())
    wanted = [b for b in dict.fromkeys(traced + [i for ids in (per_ac or {}).values() for i in ids])
              if id_prefix(b) in domain]
    if pins is None:
        if wanted:
            notes.append(f"BRIEF_UNCONFIRMED {key} {','.join(sorted(wanted, key=id_sort))}: {UNCONFIRMED}: the order has "
                         "no BRIEF_FINGERPRINTS_V1, so a changed brief row is not detected (`gate_check.py --brief "
                         "BRIEF.md` prints the lines to add)")
        return
    for b in sorted(set(wanted) | set(pins), key=id_sort):
        acs = brief_acs(b, per_ac)
        if b in ambiguous:
            notes.append(f"BRIEF_UNCONFIRMED {key} {b}: {UNCONFIRMED}: {brief['label']} lists {b} twice or not as 4 cells")
        elif b not in pins:
            notes.append(f"BRIEF_UNCONFIRMED {key} {b}: {UNCONFIRMED}: the order traces {b} but BRIEF_FINGERPRINTS_V1 "
                         "has no fingerprint for it")
        elif b not in rows:
            notes.append(f"BRIEF_STALE {key} {b} {acs}: {b} is no longer in {brief['label']}: 需求已取消，待調整範圍")
        elif brief_fingerprint(rows[b]) != pins[b]:
            same = revision is not None and revision == brief["revision"]
            notes.append(f"BRIEF_STALE {key} {b} {acs}: the brief row changed since the order pinned it (BRIEF_REVISION "
                         f"{revision if revision is not None else '?'}, brief 版次 "
                         f"{brief['revision'] if brief['revision'] is not None else '?'})"
                         + ("; 同版內容有變: the 版次 was not raised" if same else "") + ": 舊條件驗過，新條件待重驗")


def find_order_snapshot(folder, sha):
    """The file in folder whose order_hash is sha, or None."""
    for path in sorted(pathlib.Path(folder).iterdir()) if folder and pathlib.Path(folder).is_dir() else []:
        if path.is_file() and order_hash(path.read_bytes()) == sha:
            return path
    return None


def carried_notes(ac, name, bound, binding, notes):
    """Evidence carried over by EVIDENCE_EQUIVALENT (F-4): the brief rows this AC traced in the old order (found by its
    hash in --order-history) against the brief now (or the new order's pins without --brief)."""
    key = order_key(binding["ids"]) or "<WO-ID>"
    brief, history = binding.get("brief"), binding.get("history")
    old = find_order_snapshot(history, bound["sha"])
    if old is None:
        notes.append(f"BRIEF_UNCONFIRMED {key} {ac}: {name} is carried over from REVISION {bound['rev']} by "
                     f"EVIDENCE_EQUIVALENT, but the order it was recorded for (sha {bound['sha'][:12]}) is not in "
                     + (f"--order-history {history}" if history else "an --order-history folder")
                     + ", so its brief condition is not compared: 沿用依據未確認")
        return
    old_text = old.read_bytes().decode("utf-8-sig", errors="replace")
    _, old_pins = order_brief(old_text)
    traced, per_ac = order_traces(old_text)
    pinned = binding.get("pinned") or {}
    domain = brief_domain(brief, set(old_pins or ()) | set(pinned))
    for b in [b for b in (per_ac.get(ac, []) if per_ac is not None else traced) if id_prefix(b) in domain]:
        was = (old_pins or {}).get(b)
        now = (brief_fingerprint(brief["rows"][b]) if b in brief["rows"] else None) if brief else pinned.get(b)
        if was is None:
            notes.append(f"BRIEF_UNCONFIRMED {key} {b} {ac}: {name} is carried over from REVISION {bound['rev']}, whose "
                         f"order ({old.name}) pinned no fingerprint for {b}: 沿用依據未確認")
        elif now != was:
            notes.append(f"BRIEF_STALE {key} {b} {ac}: {name} was recorded for REVISION {bound['rev']} under the old "
                         f"condition of {b} and carried over by EVIDENCE_EQUIVALENT: 舊條件驗過，新條件待重驗")


def write_snapshot(data, folder, name):
    """(path, written) of folder/name holding data, written atomically: a temp file in the same folder, fsync, then a
    rename over the name. A file already there with the same hash is kept, so a retry writes nothing."""
    import tempfile
    folder = pathlib.Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    if target.is_file() and order_hash(target.read_bytes()) == order_hash(data):
        return target, False
    fd, tmp = tempfile.mkstemp(prefix=".snapshot-", suffix=".part", dir=str(folder))
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, str(target))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return target, True


def print_brief(path, folder=None):
    """Print the brief's BRIEF_REVISION and BRIEF_FINGERPRINTS_V1 lines; with folder, write its snapshot and print the
    BRIEF_LOCKED line. True when the brief has no 編號 table."""
    data = pathlib.Path(path).read_bytes()
    text, sha = data.decode("utf-8-sig", errors="replace"), order_hash(data)
    rows, ambiguous, problem = brief_table(text)
    if problem:
        print(f"FAIL brief {path}\n  - {problem}")
        return True
    revision = brief_revision(text)
    print(f"BRIEF {path}: 版次 {revision if revision is not None else '?'}, {len(rows)} row(s), sha {sha}")
    print(f"  BRIEF_REVISION = {revision if revision is not None else '<版次>'}")
    print("  BRIEF_FINGERPRINTS_V1 = " + json.dumps({b: brief_fingerprint(rows[b]) for b in sorted(rows, key=id_sort)},
                                                  ensure_ascii=False))
    for b in sorted(ambiguous, key=id_sort):
        print(f"  ~ BRIEF_UNCONFIRMED {b}: {UNCONFIRMED}: listed twice or not as 4 cells; no fingerprint")
    if folder:
        target, written = write_snapshot(data, folder, f"{revision}-{sha}.md")
        print(f"  SNAPSHOT {target} ({'written' if written else 'already there, kept'})")
        print(f"  BRIEF_LOCKED rev={revision} sha={sha} snapshot={pathlib.Path(folder).name}/{target.name}")
    return False


def po_reviews(text):
    """The PO's product reviews in the Director's log, whole lines read like DISPATCH: `PO_PRODUCT_REVIEW <WO-ID>
    candidate=<7-40 hex> outcome=seen|changes|accepted [ref=<message>] [manifest=<64 hex>] [brief=B-2:<64 hex>,...]`
    (看過 / 要求修改 / 接受 read as the three outcomes). [{"order", "candidate", "outcome", "ref", "manifest", "brief",
    "problem", "line"}]; problem names what does not bind, or is None."""
    found = []
    for line in log_lines(text):
        m = PO_REVIEW.fullmatch(line)
        if not m:
            continue
        tokens = dict(token.split("=", 1) for token in m.group(2).split())
        brief, problem = {}, []
        for part in filter(None, tokens.get("brief", "").split(",")):
            b, _, fp = part.partition(":")
            if ORDER_ID.fullmatch(b) and HEX64.fullmatch(fp.lower()):
                brief[b] = fp.lower()
            else:
                problem.append(f"brief={part} is not B-n:<64 hex>")
        candidate = tokens.get("candidate", "").lower()
        if not re.fullmatch(r"[0-9a-f]{7,40}", candidate):
            problem.append("candidate= is not a commit (7 to 40 hex digits)")
        outcome = PO_OUTCOMES.get(tokens.get("outcome", ""))
        if outcome is None:
            problem.append("outcome= is not seen / changes / accepted")
        manifest = tokens.get("manifest", "").lower() or None
        if manifest is not None and not HEX64.fullmatch(manifest):
            problem.append("manifest= is not 64 hex digits")
        found.append({"order": m.group(1), "candidate": candidate, "outcome": outcome, "ref": tokens.get("ref"),
                      "manifest": manifest, "brief": brief, "problem": "; ".join(problem) or None, "line": line.strip()})
    return found


def acceptance_records(text):
    """(records, problem) of a PO_ACCEPTANCE.json: one object, a list of them, or {"records": [...]}."""
    try:
        data = json.loads(text)
    except ValueError as error:
        return [], f"not JSON ({error})"
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        data = data["records"]
    if isinstance(data, dict):
        data = [data]
    return (data, None) if isinstance(data, list) else ([], "not a JSON object or list")


def acceptance_problems(record, candidate=None):
    """What keeps one PO_ACCEPTANCE record from binding the PO's reply to one product: candidate ID, commit (40 hex),
    entry file, manifest SHA-256 and the message it was offered in; an outcome needs the reply's message too."""
    if not isinstance(record, dict):
        return ["not a JSON object"]
    out = []
    if record.get("schema") != PO_ACCEPTANCE_SCHEMA:
        out.append(f"schema is {json.dumps(record.get('schema'), ensure_ascii=False)}, not {PO_ACCEPTANCE_SCHEMA}")
    for key in ("candidate_id", "entry", "offered_message_ref"):
        if not (isinstance(record.get(key), str) and record[key].strip()):
            out.append(f"{key} missing")
    commit = record.get("commit")
    if not (isinstance(commit, str) and re.fullmatch(r"[0-9a-fA-F]{40}", commit)):
        out.append("commit is not 40 hex digits")
    elif candidate and commit.lower() != candidate:
        out.append(f"commit {commit[:12]} is not the --candidate {candidate[:12]}")
    for key, needed in (("manifest_sha256", True), ("entry_sha256", False)):
        value = record.get(key)
        if (value is not None or needed) and not (isinstance(value, str) and HEX64.fullmatch(value.lower())):
            out.append(f"{key} is not 64 hex digits")
    outcome = record.get("outcome")
    if outcome is not None and not (isinstance(outcome, str) and outcome in PO_OUTCOMES):
        out.append("outcome is not seen / changes / accepted / null")
    elif outcome is not None and not (isinstance(record.get("reply_ref"), str) and record["reply_ref"].strip()):
        out.append("an outcome without reply_ref: the PO's reply is not bound to a message")
    return out


def check_po_acceptance(text, notes, candidate=None):
    """PO_ACCEPTANCE.json (題4 P-2), notes only: each record bound, or UNBOUND_PO_REPLY with what it lacks."""
    records, problem = acceptance_records(text)
    if problem:
        notes.append(f"UNBOUND_PO_REPLY file: {problem}; no record read")
        return []
    if not records:
        notes.append("PO_ACCEPTANCE: no record")
    for n, record in enumerate(records, 1):
        tag = record.get("candidate_id") if isinstance(record, dict) and isinstance(record.get("candidate_id"), str) \
            and record["candidate_id"].strip() else f"#{n}"
        bad = acceptance_problems(record, candidate)
        if bad:
            notes.append(f"UNBOUND_PO_REPLY {tag}: {'; '.join(bad)}")
        else:
            state = {"seen": "看過", "changes": "看過，要求再改", "accepted": "已驗收"}.get(
                PO_OUTCOMES.get(record.get("outcome") or ""), "已送出，還沒回覆")
            notes.append(f"PO_ACCEPTANCE {tag}: {record['commit'][:12]} {record['entry']}: {state} "
                         f"({record.get('reply_ref') or record['offered_message_ref']})")
    return []


def verdict_record_notes(text, order_path, report_path, notes):
    """A verdict's optional `ORDER_SHA256:` / `REPORT_SHA256:` lines against the --match order and report now."""
    for key, path, what in (("ORDER_SHA256", order_path, "order"), ("REPORT_SHA256", report_path, "report")):
        m = re.search(rf"^\s*{key}\s*[:=]\s*(\S*)", text, re.M)
        if not m:
            continue
        value = m.group(1).strip("`").lower()
        if path is None or not pathlib.Path(path).is_file():
            notes.append(f"VERDICT_RECORD: {key} given, but no --match {what} to compare it with")
            continue
        now = order_hash(pathlib.Path(path).read_bytes())
        if not HEX64.fullmatch(value):
            notes.append(f"VERDICT_RECORD: {key} is not 64 hex digits: {value or 'empty'}")
        elif value != now:
            notes.append(f"VERDICT_RECORD: {key} {value[:12]} is not the {what}'s hash now ({now[:12]}); the verdict "
                         f"judged another {what}")


def order_binding(data, path=None):
    """(binding, problem): what `evidence_record.py run --order` writes into a record's `order` field, {"id", "rev",
    "sha", "path"}. sha is order_hash of the file's bytes, the hash `--hash` prints for the DISPATCH line, so a record
    and a dispatch name an order the same way (G03b). problem: the order has no ID, or its title and file name differ."""
    text = data.decode("utf-8-sig", errors="replace")
    ids, problem = order_identity(text, path)
    if problem or not ids:
        return None, problem or "order: no title or file name to take its ID from"
    return {"id": order_key(ids), "rev": int(order_revision(text)), "sha": order_hash(data),
            "path": str(pathlib.Path(path).resolve()) if path is not None else None}, None


def dispatch_for(dispatch, ids):
    """(name, (rev, sha)) of the latest DISPATCH line for any of an order's names, or None."""
    hits = [(name, value) for name, value in dispatch.items() if name in ids]
    return hits[-1] if hits else None


def check_dispatch(order_text, order_path, now, dispatch, log_name, problems, notes):
    """The order's hash now against the hash the Director logged when dispatching it. Given a log, an order with no
    DISPATCH line fails in every governance: GOVERNANCE, REVISION and the ID are the order's own claim until its hash
    equals a dispatched one, so a worker cannot lower the mode or rename the order to skip the check."""
    ids = order_ids(order_text, order_path)
    hit = dispatch_for(dispatch, ids)
    if hit is None:
        line = f"DISPATCH {order_key(ids) or '<WO-ID>'} rev={order_revision(order_text)} sha={now}"
        problems.append(f"DISPATCH: no line for {' / '.join(ids) or order_path} in {log_name}; an order the log does not "
                        f"show as dispatched is not reviewed against it (the Director logs `{line}` when dispatching)")
        return
    name, (rev, sha) = hit
    if rev != order_revision(order_text):
        problems.append(f"DISPATCH: the latest line for {name} logs rev={rev}, the order is at REVISION "
                        f"{order_revision(order_text)}; log a DISPATCH line for this revision when dispatching it")
    if sha != now:
        problems.append(f"DISPATCH: the order's hash now ({now[:12]}) is not the one logged at dispatch "
                        f"({sha[:12]}, {name} rev={rev}); the order changed after dispatch: compare its 變更紀錄, "
                        "and treat the report's ORDER_SHA256 as matching a changed order")


def check_resume(text, notes):
    problems = []
    head = [line for line in text.splitlines() if line.strip()][:4]
    for n, key in enumerate(RESUME_HEADER):
        m = re.fullmatch(rf"{key}\s*:\s*(.*)", head[n]) if n < len(head) else None
        if not m:
            problems.append(f"line {n + 1} of the header must be `{key}: ...`")
        else:
            filled(key, m.group(1), problems)
    updated = re.search(r"^UPDATED\s*:\s*(.*)$", text, re.M)
    if not updated or not re.search(r"\d{4}-\d{2}-\d{2}", updated.group(1)):
        problems.append("UPDATED: missing or without a date (read it from `date`)")
    return problems


def check_order(text, notes):
    problems = []
    for key in ORDER_FIELDS:
        m = re.search(rf"^\s*{re.escape(key)}\s*=\s*(.*)$", text, re.M)
        if not m:
            problems.append(f"{key}: missing")
        elif filled(key, m.group(1), problems) and key == "GOVERNANCE" and m.group(1).strip() not in GOVERNANCE:
            problems.append(f"GOVERNANCE: must be one of {', '.join(GOVERNANCE)}")
    check_paths("SCOPE", text, problems)
    check_paths("FORBIDDEN", text, problems)
    comment_notes(text, notes)
    required_changes(text, problems)
    rows = ac_table(text, problems)
    if not rows:
        problems.append("acceptance: no AC-<n> row")
    for ac, row in rows.items():
        for name in ("requirement", "how verified", "expected"):
            cell = row.get(name, "")
            if filled(f"{ac} {name}", cell, problems) and VAGUE.search(cell):
                problems.append(f"{ac} {name}: vague: {cell.strip()}")
        if "type" in row and row["type"] not in AC_STATUSES:
            problems.append(f"{ac} 類型: must be one of {', '.join(AC_STATUSES)}, got: {row['type'] or 'empty'}")
    sample = next(iter(rows.values()), {})
    if rows and "type" not in sample:
        notes.append(f"acceptance: no 類型 column; give each AC one of {' / '.join(AC_STATUSES)}")
    if {"actual", "evidence", "status"} & sample.keys():
        notes.append("acceptance: 實際 / 證據 / 狀態 belong in the TASK REPORT's ACCEPTANCE table, not in the order")
    checks = order_checks(text, problems)
    for ac in sorted(checks or {}):
        kind = rows.get(ac, {}).get("type") or "AUTO"
        if ac not in rows:
            problems.append(f"CHECKS: {ac} is not an acceptance criterion of this order")
        elif kind != "AUTO" and kind in AC_STATUSES:  # a type outside the vocabulary is reported above
            problems.append(f"CHECKS: {ac} is {kind}; only an AUTO criterion has a check to rerun")
    if re.search(r"^\s*GOVERNANCE\s*=\s*Strict\b", text, re.M):
        unchecked = [ac for ac, row in rows.items() if (row.get("type") or "AUTO") == "AUTO" and ac not in (checks or {})]
        if unchecked:
            notes.append(f"CHECKS: Strict order without an approved check for AUTO {', '.join(unchecked)}; add "
                         '`CHECKS:` with `- AC-n: ["program", "arg"]` so `evidence_record.py verify --rerun --order` '
                         "runs the check the Director approved")
    revision = re.search(r"^[ \t]*REVISION[ \t]*=[ \t]*(\S*)", text, re.M)
    if not revision:
        notes.append("REVISION: missing; start at 1 and log every later change under 變更紀錄")
    elif not revision.group(1).isdigit():
        problems.append(f"REVISION: must be a number, got: {revision.group(1) or 'empty'}")
    else:
        for n in range(2, int(revision.group(1)) + 1):
            if not re.search(rf"^\|\s*{n}\s*\|", text, re.M):
                problems.append(f"REVISION {revision.group(1)}: 變更紀錄 has no row for revision {n}")
    if not re.search(r"^\s*TRACES_TO\s*=", text, re.M):
        notes.append("TRACES_TO: missing; name the requirement or decision IDs this order serves, or NONE")
    for key in ("DELIVERABLES", "STOP_RULES"):
        m = re.search(rf"{key}\s*[:：=]\s*(.*)", text)
        if not m:
            problems.append(f"{key}: missing")
        else:
            filled(key, m.group(1), problems)
    return problems


def report_fields(text):
    fields, key = {}, None
    for line in text.splitlines():
        m = re.match(r"\s*([A-Z][A-Z_]+)(?:（[^）]*）)?\s*:\s*(.*)$", line)
        if m:
            key = m.group(1)
            fields[key] = m.group(2)
        elif key and not line.startswith(("```", "#")):
            fields[key] += " " + line.strip()
    return fields


def check_report(text, notes):
    problems = []
    fields = report_fields(text)
    if "TASK_ID" not in text or "HEAD" not in text:
        problems.append("TASK_ID / HEAD: missing")
    for key in REPORT_FIELDS:
        if key not in fields:
            problems.append(f"{key}: missing")
        else:
            filled(key, fields[key], problems)
    result = fields.get("RESULT", "").strip()
    if result and result not in REPORT_RESULTS:
        problems.append(f"RESULT: must be exactly one of {', '.join(REPORT_RESULTS)}, got: {result}")
    scope = re.sub(r"^SCOPE_CHECK:\s*", "", fields.get("SCOPE_CHECK", "").strip())  # the pasted last line keeps its prefix
    if scope and not scope.startswith(("PASS", "VIOLATION", "NOT_RUN")) and not blank(scope):
        problems.append("SCOPE_CHECK: must start with PASS, VIOLATION or NOT_RUN (the last line of scope_check.py)")
    if fields.get("EVIDENCE", "").strip() == "NONE":
        problems.append("EVIDENCE: a bare NONE needs a reason: `NONE: why`")
    if result == "PASS":
        if "NOT_RUN" in fields.get("TESTS", ""):
            problems.append("RESULT PASS with NOT_RUN in TESTS: a skipped test is not a pass")
        if scope.startswith("VIOLATION"):
            problems.append("RESULT PASS with a scope violation")
        if scope.startswith("NOT_RUN"):
            problems.append("RESULT PASS with SCOPE_CHECK NOT_RUN: the scope was not checked")
    check_head(text, problems, notes)
    check_header_once(text, problems)
    if not ac_table(text, problems):
        notes.append("ACCEPTANCE: no table; give each AC of the order its own row and check it with --match")
    return problems


def report_head_values(text):
    """Every value a report writes as HEAD, in order: the value after `HEAD:`, or its place in
    `TASK_ID / ... / HEAD / WORKTREE_CLEAN: ... / <value> / yes` (counted from the right, so a branch name with slashes
    does not shift it)."""
    found = []
    for line in text.splitlines():
        keys, sep, values = line.partition(":")
        names = [key.strip() for key in keys.split("/")]
        if sep and "HEAD" in names:
            parts = [value.strip() for value in values.split("/")]
            back = len(names) - names.index("HEAD")
            if len(parts) >= back:
                found.append(parts[-back])
    return found


def report_head_value(text):
    """The first value a report writes as HEAD; None when no line names HEAD."""
    values = report_head_values(text)
    return values[0] if values else None


HEADER_ONCE = ("ORDER", "ORDER_SHA256", "RESULT")


def check_header_once(text, problems):
    """A report names its commit, order, order hash and result once (G02b): a second line could say something else."""
    heads = report_head_values(text)
    if len(heads) > 1:
        problems.append(f"HEAD: the report names HEAD {len(heads)} times ({', '.join(v[:12] or 'empty' for v in heads)}); "
                        "write it once")
    for key in HEADER_ONCE:
        lines = re.findall(rf"^[ \t]*{key}[ \t]*:", text, re.M)
        if len(lines) > 1:
            problems.append(f"{key}: the report has {len(lines)} {key}: lines; write it once")


def report_head(text):
    """The commit a report names, lower-case, or None when the HEAD value is not 7 to 40 hex digits."""
    value = report_head_value(text)
    return value.lower() if value and SHA.fullmatch(value) else None


def check_head(text, problems, notes, strict=False):
    """HEAD must be a commit hash (7 to 40 hex digits): a problem for a Strict order, otherwise a note."""
    value = report_head_value(text)
    if value is not None and not SHA.fullmatch(value):
        (problems if strict else notes).append(f"HEAD: {value or 'empty'} is not a commit hash (7 to 40 hex digits)")
    return value


def required_changes(text, problems):
    """An optional REQUIRED_CHANGES list must be concrete and lie inside SCOPE and outside FORBIDDEN."""
    required = parse_list(text, "REQUIRED_CHANGES")
    if required is None:
        return
    check_paths("REQUIRED_CHANGES", text, problems)
    import importlib.util
    spec = importlib.util.spec_from_file_location("scope_check", pathlib.Path(__file__).resolve().parent / "scope_check.py")
    scope_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scope_check)
    scope = [scope_check.glob_regex(g) for g in parse_list(text, "SCOPE") or [] if g != "NONE"]
    forbidden = [(g, scope_check.glob_regex(g)) for g in parse_list(text, "FORBIDDEN") or [] if g != "NONE"]
    for item in required:
        path = item.replace("\\", "/").lstrip("/")
        rule = next((g for g, rx in forbidden if rx.fullmatch(path)), None)
        if rule:
            problems.append(f"REQUIRED_CHANGES: {item} is FORBIDDEN ({rule}); the order cannot be done")
        elif item != "NONE" and not any(rx.fullmatch(path) for rx in scope):
            problems.append(f"REQUIRED_CHANGES: {item} is outside SCOPE; the order cannot be done")


def evidence_module():
    """evidence_record.py next to this file, for its record checks."""
    import importlib.util
    path = pathlib.Path(__file__).resolve().parent / "evidence_record.py"
    spec = importlib.util.spec_from_file_location("evidence_record", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_binding(ac, name, record, binding, problems, notes, strict):
    """The record's `order` field (evidence_record.py run --order) against the order now (G03b). binding: {"ids", "rev",
    "sha", "path", "equivalent"} of the order and the log's EVIDENCE_EQUIVALENT lines. A bound record must be for this
    order at this revision and hash, or an EVIDENCE_EQUIVALENT line must carry it over. An unbound record is accepted
    with a warning at REVISION 1; from REVISION 2 it may answer an earlier revision, which fails Strict."""
    bound, rev, now, ids = record.get("order"), binding["rev"], binding["sha"], binding["ids"]
    key, fix = order_key(ids) or "<WO-ID>", f"evidence_record.py run --order {binding['path'] or '<order>'}"
    out = problems if strict else notes
    if bound is None:
        if rev == 1:
            notes.append(f"{ac}: {name}: WARN evidence not bound to the order (recorded without --order); "
                         "from the next MAJOR version `evidence_record.py run --order` is required")
        else:
            out.append(f"{ac}: {name}: not bound to an order revision and the order is at REVISION {rev}, so it may "
                       f"answer an earlier one; " + ("Strict: " if strict else "") + f"record again with `{fix}`")
        return
    same_order = bound["id"] in ids or bool(id_prefixes([bound["id"]]) & id_prefixes(ids))
    if not same_order:
        out.append(f"{ac}: {name}: recorded for order {bound['id']}, this order is {key}; record again with `{fix}`")
        return
    if (bound["rev"], bound["sha"]) == (rev, now):
        return
    carried = any((eid in ids or id_prefixes([eid]) & id_prefixes(ids)) and (old_rev, old_sha, new_rev) == (bound["rev"], bound["sha"], rev)
                  for eid, old_rev, old_sha, new_rev in binding["equivalent"])
    if not carried:
        out.append(f"{ac}: {name}: recorded for {bound['id']} REVISION {bound['rev']} (sha {bound['sha'][:12]}), the order "
                   f"is REVISION {rev} (sha {now[:12]}); record again with `{fix}`, or the Director logs the whole line "
                   f"`EVIDENCE_EQUIVALENT {key} rev={bound['rev']} sha={bound['sha']} to rev={rev}`")
    elif binding.get("history") or binding.get("brief"):  # 2.1: the keys evidence_record.py's binding does not have
        carried_notes(ac, name, bound, binding, notes)


def check_evidence(ac, evidence, folder, head, problems, notes, strict=False, candidate=None, approved=None, binding=None):
    """An AUTO row marked PASS against the evidence_record.py files its 證據 cell names.
    strict: uncommitted changes, a label naming another AC, a legacy record, a record without git HEAD and a command
    other than the approved one fail instead of being noted. candidate: the commit under review; the record's HEAD is
    compared with it instead of the report's (exactly for a Strict order, as a prefix otherwise). approved: the order's
    CHECKS command for this AC, or None. binding: the order's identity for check_binding, or None."""
    names = EVIDENCE_FILE.findall(evidence)
    if not names:
        problems.append(f"{ac}: PASS names no evidence_record file (.json) in 證據")
        return
    ev = evidence_module()
    for name in names:
        try:
            record = json.loads((pathlib.Path(folder) / name).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            problems.append(f"{ac}: {name} is not an evidence_record file in {folder}")
            continue
        bad = ev.record_problems(record)
        if bad:
            more = f" (+{len(bad) - 1} more)" if len(bad) > 1 else ""
            problems.append(f"{ac}: {name} is not an evidence_record file: {bad[0]}{more}")
            continue
        if "schema" not in record:
            (problems if strict else notes).append(
                f"{ac}: {name}: legacy record without `schema`; "
                + ("Strict: record again with evidence_record.py run" if strict else "only command, exit_code and artifacts checked"))
        elif record["schema"] not in ev.SCHEMAS:
            (problems if strict else notes).append(
                f"{ac}: {name}: schema {record['schema']} is not one this tool reads ({', '.join(map(str, ev.SCHEMAS))})"
                + ("; Strict: record again with this evidence_record.py" if strict else ""))
        code, git = record["exit_code"], record.get("git") or {}
        if code != 0 or record.get("timed_out"):
            problems.append(f"{ac}: {name}: the command exited {code}{' (timed out)' if record.get('timed_out') else ''}")
        lost = [item.get("path") for item in record.get("artifacts", []) if item.get("sha256") is None]
        if lost:
            problems.append(f"{ac}: {name}: artifact missing when recorded: {lost[0]}")
        recorded = (git.get("head") or "").lower()
        if candidate and recorded:
            if not (recorded == candidate if strict else candidate.startswith(recorded)):
                problems.append(f"{ac}: {name}: recorded at HEAD {recorded[:12]}, the candidate is {candidate[:12]}; "
                                "record again at the candidate commit")
        elif head and recorded and not (recorded.startswith(head) or head.startswith(recorded)):
            problems.append(f"{ac}: {name}: recorded at HEAD {recorded[:12]}, the report says {head[:12]}; "
                            "record again after the last commit")
        elif not recorded and (strict or head or candidate):
            (problems if strict else notes).append(
                f"{ac}: {name}: recorded with no git HEAD; " + ("Strict: record again inside the worktree" if strict
                                                                 else "not compared with the report's"))
        if git.get("dirty"):
            (problems if strict else notes).append(
                f"{ac}: {name}: recorded with uncommitted changes" + ("; Strict: commit, then record again" if strict else ""))
        elif strict and "schema" in record and git.get("dirty") is not False:
            problems.append(f"{ac}: {name}: git.dirty is {json.dumps(git.get('dirty'))}, not false: the record does not say "
                            "the worktree was clean; Strict: record again inside the worktree")
        for item in record.get("artifacts", []):
            if item.get("sha256") is None:
                continue
            path = pathlib.Path(item["path"])
            if not path.is_absolute() and not record.get("cwd"):
                notes.append(f"{ac}: {name}: artifact {item['path']} not hashed again: the record has no cwd to find it from")
                continue
            now_hash = ev.hash_artifact(path if path.is_absolute() else pathlib.Path(record["cwd"], path))["sha256"]
            if now_hash != item["sha256"]:
                (problems if strict else notes).append(
                    f"{ac}: {name}: artifact {'gone' if now_hash is None else 'changed'} since it was recorded: {item['path']}"
                    + ("; Strict: the record's hash is not what is on disk" if strict else ""))
        if approved is not None and record["command"] != approved:
            (problems if strict else notes).append(
                f"{ac}: {name}: its command is not the order's approved check (CHECKS {ac}); "
                + ("Strict: record again with exactly that command" if strict else "record again with that command"))
        label = record.get("label")
        if label is not None and ac not in re.split(r"[\s,;/+]+", str(label)):
            (problems if strict else notes).append(
                f"{ac}: {name}: its label is {label}, not {ac}" + ("; Strict: record once per AC, or label both" if strict else ""))
        if binding is not None:
            check_binding(ac, name, record, binding, problems, notes, strict)


def check_match(report, order, notes, evidence_dir=None, dispatch=None, order_path=None, log_name=None, candidate=None,
                equivalent=None, brief=None, history=None):
    """The report's ACCEPTANCE rows against the order's acceptance criteria and its hash.
    dispatch: the records of --dispatch-log (None when the flag is absent), order_path: the order file's path,
    candidate: the commit under review (40 hex digits, lower-case) from --candidate, or None, equivalent: the
    EVIDENCE_EQUIVALENT lines of --dispatch-log, brief: load_brief of --brief, history: the --order-history folder
    (both only add notes on carried-over evidence)."""
    problems = []
    order_text = order.decode("utf-8-sig")
    binding = {"ids": order_ids(order_text, order_path), "rev": int(order_revision(order_text)), "sha": order_hash(order),
               "path": str(order_path) if order_path is not None else None, "equivalent": equivalent or [],
               "brief": brief, "history": history, "pinned": order_brief(order_text)[1]}
    order_problems = []
    wanted, got = ac_table(order_text, order_problems), ac_table(report, problems)
    checks = order_checks(order_text, order_problems) or {}
    problems.extend(f"order: {p}" for p in order_problems)
    strict = bool(re.search(r"^\s*GOVERNANCE\s*=\s*Strict\b", order_text, re.M))
    head_value = check_head(report, problems, notes, strict)
    check_header_once(report, problems)
    hashlike = head_value.lower() if head_value and SHA.fullmatch(head_value) else None
    if strict and (head_value is None or hashlike) and not (hashlike and len(hashlike) == 40):
        problems.append(f"HEAD: a Strict report names the full commit (40 hex digits), got {hashlike or 'none'}")
    if strict and not candidate:
        problems.append("CANDIDATE: a Strict match needs --candidate <40 hex digits> (`git rev-parse <worker branch>`)")
    if candidate and hashlike and not candidate.startswith(hashlike):
        problems.append(f"HEAD: the report names {hashlike[:12]}, the candidate is {candidate[:12]}; "
                        "the report was not written for the commit under review")
    head = report_head(report) if evidence_dir else None
    if evidence_dir and not head and not candidate:
        notes.append("HEAD: the report names no commit hash" + ("" if head_value is None else " (see above)")
                     + "; evidence HEAD not compared")
    if not wanted:
        problems.append("order: no AC-<n> row")
    for ac, spec in wanted.items():
        kind = spec.get("type", "")
        if not kind:
            notes.append(f"{ac}: the order gives no 類型; checked as AUTO")
            kind = "AUTO"
        row = got.get(ac)
        if row is None:
            problems.append(f"{ac}: in the order but not in the report's ACCEPTANCE table")
            continue
        if kind not in AC_STATUSES:
            problems.append(f"{ac}: the order's 類型 {kind} is not one of {', '.join(AC_STATUSES)}")
            continue
        status, evidence = row.get("status", ""), row.get("evidence", "")
        if status not in AC_STATUSES[kind]:
            hint = {"REVIEW": "; a reviewer, then the Director, judges it", "PO": "; only the PO judges it"}.get(kind, "")
            problems.append(f"{ac} ({kind}): status must be one of {' / '.join(AC_STATUSES[kind])}, got: {status or 'empty'}{hint}")
        if status == "PASS" and (blank(evidence) or evidence.upper().startswith("NONE")):
            problems.append(f"{ac}: PASS without evidence")
        elif status == "PASS" and kind == "AUTO" and evidence_dir:
            check_evidence(ac, evidence, evidence_dir, head, problems, notes, strict, candidate, checks.get(ac), binding)
        if status in ("PASS", "FAIL") and blank(row.get("actual", "")):
            problems.append(f"{ac}: {status} with 實際 empty")
    for ac in sorted(got.keys() - wanted.keys()):
        problems.append(f"{ac}: in the report but not in the order")
    auto_pass = [ac for ac, spec in wanted.items() if spec.get("type", "AUTO") in ("AUTO", "")
                 and got.get(ac, {}).get("status", "") == "PASS"]
    if strict and auto_pass and not evidence_dir:
        problems.append(f"EVIDENCE: Strict order checked without --evidence-dir; the records of AUTO PASS rows "
                        f"{', '.join(auto_pass)} were not read")
    if report_fields(report).get("RESULT", "").strip() == "PASS":
        open_rows = sorted(ac for ac, row in got.items() if row.get("status", "") in UNFINISHED)
        if open_rows:
            problems.append(f"RESULT PASS with {' / '.join(UNFINISHED)} rows: {', '.join(open_rows)}")
    named, wanted_rev = order_line(report), int(order_revision(order_text))
    if named is None or named[1] is None:
        (problems if strict else notes).append(
            f"ORDER: the report names no order revision; write `ORDER: {pathlib.Path(order_path).name if order_path else 'WO-file.md'} "
            f"REVISION {wanted_rev}`")
    elif named[1] != wanted_rev:
        problems.append(f"ORDER: the report is for REVISION {named[1]}, the order is at REVISION {wanted_rev}; "
                        "the report answers an older or newer order")
    ids, identity = order_identity(order_text, order_path)
    if identity:
        problems.append(identity)
    named_ids, order_id_set = id_prefixes([named[0].strip()] if named else []), id_prefixes(ids)
    if named_ids and order_id_set and not named_ids & order_id_set:
        problems.append(f"ORDER: the report names {named[0].split()[0]}, the order is {order_key(ids)}; "
                        "the report answers another order")
    claimed = re.search(r"^\s*ORDER_SHA256\s*[:=]\s*([0-9a-fA-F]{64})\b", report, re.M)
    now = order_hash(order)
    if not claimed:
        problems.append("ORDER_SHA256: missing (64 hex digits from `gate_check.py --hash ORDER`)")
    elif claimed.group(1).lower() != now:
        problems.append(f"ORDER_SHA256: the order is not the one the worker hashed ({claimed.group(1)[:12]} != {now[:12]}); "
                        "compare it with its 變更紀錄 and the hash logged at dispatch")
    if dispatch is not None:
        check_dispatch(order_text, order_path, now, dispatch, log_name, problems, notes)
    elif strict:
        problems.append("DISPATCH: Strict order checked without --dispatch-log; the hash was only compared with the order as it is now")
    return problems


def resolve_commit(repo, short):
    """The full commit a short hash names in repo, or None when it is unknown or ambiguous."""
    import subprocess
    try:
        done = subprocess.run(["git", "-C", str(repo), "-c", "core.useReplaceRefs=false", "rev-parse", "--verify",
                               "--quiet", f"{short}^{{commit}}"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    full = done.stdout.strip().lower()
    return full if done.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", full) else None


def preflight(report, order, order_path, evidence_dir=None, dispatch=None, log_name=None, repo=None):
    """(lacks, not checked): what an older report, order, evidence and dispatch log lack for a Strict review now (M01-M03),
    each with the step that supplies it. Only reads."""
    lacks, unchecked = [], []
    order_text = order.decode("utf-8-sig")
    wanted, got = ac_table(order_text) or {}, ac_table(report) or {}
    rev = order_revision(order_text)
    heads = report_head_values(report)
    value = heads[0] if heads else None
    if value is None:
        lacks.append("HEAD: the report names no commit; the worker writes `HEAD: <40 hex digits>` (git rev-parse HEAD)")
    elif not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        full = resolve_commit(repo, value) if repo and SHA.fullmatch(value) else None
        if full:
            lacks.append(f"HEAD: the report names {value}; in {repo} that is {full}: write the full commit in the report "
                         "(keep the old report for the record)")
        else:
            lacks.append(f"HEAD: the report names {value or 'empty'}, not 40 hex digits; "
                         + ("it does not name one commit in " + str(repo) + ": the worker resubmits" if repo else
                            "resolve it with `git rev-parse <short>` in a trusted checkout (--repo), or the worker resubmits"))
    named = order_line(report)
    if named is None or named[1] is None:
        lacks.append(f"ORDER: the report names no revision; write `ORDER: {pathlib.Path(order_path).name} REVISION {rev}`")
    elif str(named[1]) != rev:
        lacks.append(f"ORDER: the report is for REVISION {named[1]}, the order is at REVISION {rev}; the worker reports "
                     "on this revision")
    if dispatch is None:
        unchecked.append("DISPATCH: no --dispatch-log")
    else:
        hit = dispatch_for(dispatch, order_ids(order_text, order_path))
        now = order_hash(order)
        if hit is None or hit[1] != (rev, now):
            ids = order_ids(order_text, order_path)
            lacks.append(f"DISPATCH: {log_name} has no `DISPATCH {order_key(ids) or '<WO-ID>'} rev={rev} sha={now[:12]}...` "
                         "line for the order as it is; the Director logs it (gate_check.py --hash) when dispatching "
                         "this revision" + (f" (latest is rev={hit[1][0]} sha={hit[1][1][:12]})" if hit else ""))
    auto = [ac for ac, spec in wanted.items() if spec.get("type", "AUTO") in ("AUTO", "")]
    checks = order_checks(order_text) or {}
    without = [ac for ac in auto if ac not in checks]
    if without:
        lacks.append(f"CHECKS: no approved check for AUTO {', '.join(without)}; for `evidence_record.py verify --rerun` "
                     "the Director writes CHECKS, raises REVISION, logs a new DISPATCH and the worker records again "
                     "(--match without CHECKS still works)")
    files = sorted({name for ac in auto if got.get(ac, {}).get("status") == "PASS"
                    for name in EVIDENCE_FILE.findall(got[ac].get("evidence", ""))})
    if not evidence_dir:
        unchecked.append(f"EVIDENCE: no --evidence-dir ({len(files)} record(s) named by AUTO PASS rows)")
        return lacks, unchecked
    ev = evidence_module()
    for name in files:
        try:
            record = json.loads((pathlib.Path(evidence_dir) / name).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            lacks.append(f"EVIDENCE {name}: not readable in {evidence_dir}; record again at the candidate")
            continue
        bad = ev.record_problems(record)
        git = record.get("git") if isinstance(record, dict) and isinstance(record.get("git"), dict) else {}
        missing = []
        if bad:
            missing.append(f"not an evidence record ({bad[0]})")
        elif "schema" not in record:
            missing.append("no `schema` (legacy record)")
        elif record["schema"] not in ev.SCHEMAS:
            missing.append(f"schema {record['schema']} is not one this version reads")
        head = str(git.get("head") or "")
        if not bad and not re.fullmatch(r"[0-9a-fA-F]{40}", head):
            missing.append(f"git.head is {head or 'missing'}, not 40 hex digits")
        if not bad and git.get("dirty") is not False:
            missing.append(f"git.dirty is {json.dumps(git.get('dirty'))}, not false")
        if not bad and rev != "1" and record.get("order") is None:
            missing.append(f"no `order` binding and the order is at REVISION {rev} (run --order)")
        if missing:
            lacks.append(f"EVIDENCE {name}: {'; '.join(missing)}; record again with this evidence_record.py run (or verify "
                         "--rerun) at the candidate; keep the old file with a closed review as it was")
    return lacks, unchecked


def check_verdict(text, notes):
    problems = []
    section = re.search(r"^##\s*A\b.*?$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    lines = [line.strip() for line in section.group(1).splitlines() if line.strip()] if section else []
    if not lines or lines[0] not in VERDICTS:
        problems.append(f"verdict: the first line of section A must be exactly one of {', '.join(VERDICTS)}")
    aspects = next((line for line in lines if "工程" in line), "")
    if not all(word in aspects for word in ("工程", "成品", "PO 驗收")):
        problems.append("status by aspect: one line must cover 工程, 成品 and PO 驗收")
    step = next((line for line in lines if line.startswith("下一步")), None)
    value = re.split(r"[:：]", step, maxsplit=1)[-1].strip() if step else ""
    if value not in NEXT_STEPS:
        problems.append(f"下一步: must be exactly one of {', '.join(NEXT_STEPS)}")
    stop = re.search(r"^##\s*F\b.*?$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    if not stop or blank(stop.group(1)):
        problems.append("section F (stop state): missing or empty")
    return problems


def verdict_binding(text, orders, candidate, notes, reports=None):
    """With --match or --candidate: the verdict must answer a --match order at its REVISION and judge the candidate.
    orders: [(order text, order path)] of the --match pairs; candidate: 40 hex digits, lower-case, or None; reports:
    {str(order path): report path} of the pairs, for the verdict's optional REPORT_SHA256 (notes only)."""
    problems, named = [], order_line(text)
    named_ids = id_prefixes([named[0].strip()]) if named else set()
    hits = [(t, p) for t, p in orders if named_ids & id_prefixes(order_ids(t, p))]
    if not hits and not named_ids and len(orders) == 1:
        hits = orders
    strict = any(re.search(r"^\s*GOVERNANCE\s*=\s*Strict\b", t, re.M) for t, _ in (hits or orders))
    if orders and not named_ids:
        (problems if strict else notes).append(
            "ORDER: the verdict names no order; write `ORDER: <order file> REVISION n` at the top")
    elif orders and not hits:
        problems.append(f"ORDER: the verdict names {named[0].split()[0]}, which is none of the --match orders; "
                        "the verdict judges another order")
    for order_text, order_path in hits[:1]:
        wanted = int(order_revision(order_text))
        if named is None or named[1] is None:
            (problems if strict else notes).append(f"ORDER: the verdict names no REVISION; the order is at REVISION {wanted}")
        elif named[1] != wanted:
            problems.append(f"ORDER: the verdict is for REVISION {named[1]}, the order is at REVISION {wanted}; "
                            "the verdict judges an older or newer order")
        verdict_record_notes(text, order_path, (reports or {}).get(str(order_path)), notes)
    if candidate:
        head = re.search(r"^\s*CANDIDATE_HEAD\s*[:=]\s*(\S*)", text, re.M)
        value = head.group(1).strip("`").lower() if head else ""
        if not value:
            (problems if strict else notes).append(
                f"CANDIDATE_HEAD: the verdict names no commit; write `CANDIDATE_HEAD: {candidate}`")
        elif not re.fullmatch(r"[0-9a-f]{7,40}", value):
            problems.append(f"CANDIDATE_HEAD: not a commit hash (7 to 40 hex digits): {value}")
        elif not (value == candidate if strict else candidate.startswith(value)):
            problems.append(f"CANDIDATE_HEAD: the verdict is for {value[:12]}, the candidate is {candidate[:12]}; "
                            "the verdict judged another commit")
    return problems


TR_FIELDS = ("TEST REQUEST", "FROM", "PURPOSE", "MIN_SCOPE", "TIER", "CHANGES", "SWITCHES", "EXCLUSIVE_MIN", "NORMAL_MIN",
             "BUILD_GB", "CAPTURE", "CACHE_GB", "WRITE_GB", "DURATION", "TIER0_DONE")
NUMBER = r"(\d+(?:\.\d+)?)"
TIMES = r"\s*[x×*]\s*"


def tr_fields(text):
    fields = {}
    for line in text.splitlines():
        m = re.match(r"\s*([A-Z][A-Z0-9_ ]*[A-Z0-9_])\s*:\s*(.*)$", line)
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return fields


def check_test_request(text, notes):
    """The TEST REQUEST fields (templates/TEST_REQUEST.md): all filled, the disk estimate in GiB covering build,
    capture and cache (L-030, L-031), the duration counted as sets x measured minutes with timeouts (L-033)."""
    problems, fields = [], tr_fields(text)
    for key in TR_FIELDS:
        if key not in fields:
            problems.append(f"{key}: missing")
        else:
            filled(key, fields[key], problems)
    gib = {}
    for key in ("BUILD_GB", "CACHE_GB", "WRITE_GB"):
        value = fields.get(key, "")
        if re.search(r"\bGB\b", value):
            problems.append(f"{key}: write GiB (2^30 bytes), not decimal GB (L-031)")
        m = re.match(NUMBER, value)
        if m:
            gib[key] = float(m.group(1))
        elif value and not PLACEHOLDER.search(value):
            problems.append(f"{key}: a number of GiB, got: {value}")
    capture = fields.get("CAPTURE", "")
    m = re.match(NUMBER + TIMES + NUMBER + TIMES + NUMBER + r"\s*(?:MiB|MB)?\s*=\s*" + NUMBER, capture)
    if capture.upper().startswith("NONE"):
        gib["CAPTURE"] = 0.0
    elif m:
        sets, images, mib, total = (float(x) for x in m.groups())
        if abs(sets * images * mib / 1024 - total) > max(0.05, 0.05 * total):
            problems.append(f"CAPTURE: {sets:g} x {images:g} x {mib:g} MiB is {sets * images * mib / 1024:.2f} GiB, "
                            f"not {total:g}")
        gib["CAPTURE"] = total
    elif capture and not PLACEHOLDER.search(capture):
        problems.append("CAPTURE: `<sets> x <images per set> x <MiB per image> = <GiB>`, or NONE")
    if len(gib) == 4 and gib["WRITE_GB"] + 0.05 < gib["BUILD_GB"] + gib["CAPTURE"] + gib["CACHE_GB"]:
        problems.append(f"WRITE_GB: {gib['WRITE_GB']:g} GiB is less than BUILD_GB + CAPTURE + CACHE_GB = "
                        f"{gib['BUILD_GB'] + gib['CAPTURE'] + gib['CACHE_GB']:g} GiB (L-030)")
    duration = fields.get("DURATION", "")
    m = re.match(NUMBER + TIMES + NUMBER + r"\s*(?:min|分鐘)?\s*=\s*" + NUMBER, duration)
    if m:
        sets, each, total = (float(x) for x in m.groups())
        if abs(sets * each - total) > 1:
            problems.append(f"DURATION: {sets:g} x {each:g} is {sets * each:g} minutes, not {total:g}")
        cap = re.findall(r"\d+", fields.get("TEST REQUEST", ""))
        if cap and float(cap[-1]) < total:
            problems.append(f"TEST REQUEST: the limit {cap[-1]} minutes is below DURATION {total:g}")
    elif duration and not PLACEHOLDER.search(duration):
        problems.append("DURATION: `<sets> x <measured minutes per set, timeouts included> = <minutes>` (L-033)")
    return problems


CHECKS = {"resume": check_resume, "order": check_order, "report": check_report, "verdict": check_verdict,
          "test-request": check_test_request, "po-acceptance": check_po_acceptance}


def dated(kind, text):
    """The date a file says it was written, or None."""
    m = re.search(DATED_BY[kind], text, re.M) if kind in DATED_BY else DATE.search(text)
    return m.group(m.lastindex or 0) if m else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for kind in CHECKS:
        ap.add_argument(f"--{kind}", nargs="+", default=[], metavar="FILE")
    ap.add_argument("--match", nargs=2, action="append", default=[], metavar=("REPORT", "ORDER"))
    ap.add_argument("--evidence-dir", metavar="DIR", help="with --match: AUTO PASS rows need a passing evidence record here")
    ap.add_argument("--dispatch-log", metavar="LOG", help="with --match: the order's hash must equal its DISPATCH line here")
    ap.add_argument("--candidate", metavar="SHA", help="with --match: the commit under review, 40 hex digits (git rev-parse <branch>)")
    ap.add_argument("--hash", nargs="+", default=[], metavar="FILE", help="print the hash ORDER_SHA256 compares and the DISPATCH line")
    ap.add_argument("--preflight", nargs=2, action="append", default=[], metavar=("REPORT", "ORDER"),
                    help="list what an older review lacks for a Strict review now (LACKS lines)")
    ap.add_argument("--repo", metavar="DIR", help="with --preflight: a trusted checkout to resolve a short HEAD in")
    ap.add_argument("--brief", metavar="BRIEF", help="the brief's fingerprints; with --order / --match / --preflight: "
                    "BRIEF_STALE notes (shadow)")
    ap.add_argument("--snapshot", metavar="DIR", help="with --brief or --hash: keep a snapshot in DIR (atomic write)")
    ap.add_argument("--order-history", metavar="DIR", help="with --match: old orders, found by hash, for carried-over evidence")
    ap.add_argument("--warn", action="store_true", help="report problems as WARN and exit 0")
    ap.add_argument("--since", metavar="YYYY-MM-DD", help="skip files dated before this day")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    jobs = [(kind, path) for kind in CHECKS for path in getattr(a, kind.replace("-", "_"))] + [("match", pair) for pair in a.match]
    if a.snapshot and not (a.brief or a.hash):
        ap.error("--snapshot works with --brief or --hash")
    if a.brief and not pathlib.Path(a.brief).is_file():
        ap.error(f"--brief: file not found: {a.brief}")
    if a.brief and a.snapshot:
        brief_text = pathlib.Path(a.brief).read_text(encoding="utf-8-sig")
        if not brief_is_locked(brief_text) or brief_revision(brief_text) is None:
            ap.error("--brief with --snapshot: the brief must say 狀態：LOCKED and 版次：<number>; a draft is not snapshotted")
    if a.order_history and not a.match:
        ap.error("--order-history works with --match")
    if a.order_history and not pathlib.Path(a.order_history).is_dir():
        ap.error(f"--order-history: folder not found: {a.order_history}")
    missing = [path for path in a.hash if not pathlib.Path(path).is_file()]
    for path in a.hash:
        if path in missing:
            print(f"FAIL hash {path}\n  - file not found")
            continue
        data = pathlib.Path(path).read_bytes()
        text, digest = data.decode("utf-8-sig", errors="replace"), order_hash(data)
        ids, identity = order_identity(text, path)
        print(f"{digest}  {path}\n  DISPATCH {order_key(ids) or pathlib.Path(path).stem} rev={order_revision(text)} sha={digest}")
        if identity:
            print(f"  - {identity}")
        if a.snapshot:
            name = f"{order_key(ids) or pathlib.Path(path).stem}-rev{order_revision(text)}-{digest}.md"
            target, written = write_snapshot(data, a.snapshot, name)
            print(f"  SNAPSHOT {target} ({'written' if written else 'already there, kept'})")
    brief_failed = print_brief(a.brief, a.snapshot) if a.brief and (a.snapshot or not (jobs or a.preflight)) else False
    if not jobs and (a.hash or a.brief) and not a.preflight:
        return 1 if missing or brief_failed else 0
    if not jobs and not a.preflight:
        ap.error("give at least one of --resume / --order / --report / --verdict / --test-request / --po-acceptance / "
                 "--match / --preflight / --hash / --brief")
    if a.repo and not a.preflight:
        ap.error("--repo works with --preflight")
    if a.since and not DATE.fullmatch(a.since):
        ap.error("--since takes a date: YYYY-MM-DD")
    if a.evidence_dir and not (a.match or a.preflight):
        ap.error("--evidence-dir works with --match or --preflight")
    if a.evidence_dir and not pathlib.Path(a.evidence_dir).is_dir():
        ap.error(f"--evidence-dir: folder not found: {a.evidence_dir}")
    if a.dispatch_log and not (a.match or a.preflight or a.brief):
        ap.error("--dispatch-log works with --match, --preflight or --brief")
    if a.dispatch_log and not pathlib.Path(a.dispatch_log).is_file():
        ap.error(f"--dispatch-log: file not found: {a.dispatch_log}")
    if a.candidate and not (a.match or a.verdict or a.po_acceptance):
        ap.error("--candidate works with --match, --verdict or --po-acceptance")
    if a.candidate and not re.fullmatch(r"[0-9a-fA-F]{40}", a.candidate):
        ap.error(f"--candidate takes the full commit, 40 hex digits (git rev-parse <branch>), got: {a.candidate}")
    candidate = a.candidate.lower() if a.candidate else None
    log_text = pathlib.Path(a.dispatch_log).read_text(encoding="utf-8-sig") if a.dispatch_log else None
    dispatch = dispatch_records(log_text) if log_text is not None else None
    equivalent = equivalent_records(log_text) if log_text is not None else []
    matched = [(pathlib.Path(o).read_text(encoding="utf-8-sig"), pathlib.Path(o)) for _, o in a.match if pathlib.Path(o).is_file()]
    pairs = {str(pathlib.Path(o)): pathlib.Path(r) for r, o in a.match}
    brief = None
    if a.brief and (jobs or a.preflight):
        brief_lines = []
        brief = load_brief(a.brief, log_text, a.dispatch_log, brief_lines)
        print(f"BRIEF {brief['label']}: 版次 {brief['revision'] if brief['revision'] is not None else '?'}, "
              f"{len(brief['rows'])} row(s); notes only, never fails")
        for line in ([brief["problem"]] if brief["problem"] else []) + brief_lines:
            print(f"  ~ {line}")

    failed = skipped = undated = 0
    for report_path, order_path in a.preflight:
        files = [pathlib.Path(report_path), pathlib.Path(order_path)]
        if not all(f.is_file() for f in files):
            failed += 1
            print(f"FAIL preflight {report_path} against {order_path}\n  - file not found")
            continue
        order = files[1].read_bytes()
        mode = re.search(r"^\s*GOVERNANCE\s*=\s*(\w+)", order.decode("utf-8-sig"), re.M)
        lacks, unchecked = preflight(files[0].read_text(encoding="utf-8-sig"), order, files[1], a.evidence_dir, dispatch,
                                     a.dispatch_log, a.repo)
        failed += bool(lacks)
        print(f"PREFLIGHT {report_path} against {order_path} (GOVERNANCE {mode.group(1) if mode else 'not set'}): "
              + (f"{len(lacks)} item(s) to migrate" if lacks else "nothing lacking") + "; only read")
        for line in [f"  LACKS {item}" for item in lacks] + [f"  NOT_CHECKED {item}" for item in unchecked]:
            print(line)
        if brief:
            extra = []
            brief_notes(order.decode("utf-8-sig"), files[1], brief, extra)
            for line in extra:
                print(f"  ~ {line}")
    for kind, path in jobs:
        files = [pathlib.Path(p) for p in (path if kind == "match" else [path])]
        text = files[0].read_text(encoding="utf-8-sig") if all(f.is_file() for f in files) else None
        name = " against ".join(path) if kind == "match" else path
        day = dated(kind, text) if text is not None and a.since else None
        if day and day < a.since:
            skipped += 1
            print(f"SKIP {kind} {name} (dated {day}, before --since)")
            continue
        if a.since and text is not None and not day:
            undated += 1
            print(f"SKIP {kind} {name} (UNDATED: no date for --since to compare; run without --since to check it)")
            continue
        notes = []
        if text is None:
            problems = ["file not found"]
        elif kind == "match":
            problems = check_match(text, files[1].read_bytes(), notes, a.evidence_dir, dispatch, files[1], a.dispatch_log,
                                   candidate, equivalent, brief, a.order_history)
        elif kind == "po-acceptance":
            problems = check_po_acceptance(text, notes, candidate)
        else:
            problems = CHECKS[kind](text, notes)
            if kind == "verdict" and (a.match or candidate):
                problems += verdict_binding(text, matched, candidate, notes, pairs)
        if brief and text is not None and kind in ("order", "match"):
            brief_notes(text if kind == "order" else files[1].read_text(encoding="utf-8-sig"), files[-1], brief, notes)
        failed += bool(problems)
        print(f"{('WARN' if a.warn else 'FAIL') if problems else 'OK  '} {kind} {name}")
        for line in [f"  - {p}" for p in problems] + [f"  ~ {n}" for n in notes]:
            print(line)
    if a.warn or a.since:
        print(f"checked {len(jobs) - skipped - undated}, {'warned' if a.warn else 'failed'} {failed}, skipped {skipped}"
              + (f", UNDATED {undated} (not checked)" if undated else ""))
    return 1 if failed and not a.warn else 0


if __name__ == "__main__":
    sys.exit(main())
