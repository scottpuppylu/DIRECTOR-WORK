"""Check the format of a RESUME_STATE, work order, task report or gate verdict, so a rule fails in a script instead of
relying on the model remembering it.

Prints OK / FAIL per file with one line per problem; exit 1 when anything fails. Only reads.
Passing means the file follows the format and the rules below. It does not mean the work is correct: reviewing the
evidence and the product is still the Director's job (docs/02, docs/07).

  --resume   the four header lines come first, in order, filled in; UPDATED holds a date
  --order    required fields filled in; SCOPE / FORBIDDEN are concrete path lists; acceptance rows are concrete
  --report   required fields filled in; RESULT in the vocabulary; PASS is refused with NOT_RUN tests or a scope violation
  --verdict  verdict and next step in the vocabulary; status split by aspect; stop state written
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
             artifacts) is not evidence; one without `schema` is read as legacy and noted. Uncommitted changes or a
             label naming another AC fail a Strict order and are noted otherwise. The report's HEAD must be 7 to 40
             hex digits: Strict fails, Standard and --report note it. The records are read, not rerun: only
             `evidence_record.py verify --rerun` runs a command again
  --dispatch-log LOG
             with --match: the order's hash now must equal the one the Director logged at dispatch, as a line
             `DISPATCH <WO-ID> rev=<n> sha=<64 hex>` in LOG (the last line for an order wins; the ID is the order's
             title or file name). No line for the order: Strict fails, Standard notes it, Direct does not look.
             Without this flag the hash is only compared with the order as it is now, which a worker can rewrite.
  --hash FILE  print the SHA-256 that ORDER_SHA256 compares (line endings counted as LF) and the DISPATCH line to log

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
           "證據": "evidence", "evidence": "evidence", "狀態": "status", "status": "status"}
LEGACY_COLUMNS = ["requirement", "how verified", "expected", "actual", "evidence", "status"]
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
DATED_BY = {"order": r"^\s*ISSUED_BY\s*=.*?(\d{4}-\d{2}-\d{2})", "resume": r"^UPDATED\s*:.*?(\d{4}-\d{2}-\d{2})"}
VAGUE = re.compile(r"視情況|相關檔案|相關的檔案|等等|之類|適當|盡量|儘量|必要時|(?<![\w./\-])(?:as needed|etc|tbd|todo)(?![\w/\-]|\.\w)", re.I)  # not inside a name like todo.py
PLACEHOLDER = re.compile(r"<[^<>@\n]+>")  # <name@host> is an address, not a placeholder
CODE = re.compile(r"`[^`\n]*`")  # <...> inside a code span is format text, not a placeholder
EVIDENCE_FILE = re.compile(r"[\w.-]+\.json\b")
SHA = re.compile(r"[0-9a-fA-F]{7,40}")
DISPATCH = re.compile(r"\bDISPATCH\s+(\S+?)(?:\.md)?\s+rev=(\d+)\s+sha=([0-9a-fA-F]{64})\b")
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
    """Items of a `KEY:` line followed by `- item` lines; None when the key is missing."""
    lines = text.splitlines()
    for n, line in enumerate(lines):
        if re.fullmatch(rf"\s*{key}\s*[:：]\s*", line):
            items = []
            for item in lines[n + 1:]:
                m = re.match(r"\s*-\s+(.*)", item)
                if not m:
                    break
                items.append(re.split(r"\s+#", m.group(1))[0].strip())
            return items
    return None


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


def order_ids(text, path=None):
    """The names a dispatch line may call this order: the first word of its title and its file name without .md."""
    ids = []
    title = re.search(r"^#\s+(\S+)", text, re.M)
    if title:
        ids.append(title.group(1))
    if path is not None:
        ids.append(pathlib.Path(path).stem)
    return ids


def order_revision(text):
    m = re.search(r"^[ \t]*REVISION[ \t]*=[ \t]*(\d+)", text, re.M)
    return m.group(1) if m else "1"


def dispatch_records(text):
    """{order id: (rev, sha)} from `DISPATCH <WO-ID> rev=<n> sha=<hash>` lines; the last line for an id wins."""
    return {m.group(1): (m.group(2), m.group(3).lower()) for m in DISPATCH.finditer(text)}


def check_dispatch(order_text, order_path, now, dispatch, log_name, problems, notes):
    """The order's hash now against the hash the Director logged when dispatching it."""
    governance = re.search(r"^\s*GOVERNANCE\s*=\s*(\S+)", order_text, re.M)
    governance = governance.group(1) if governance else "Standard"
    ids = order_ids(order_text, order_path)
    hits = [(name, dispatch[name]) for name in ids if name in dispatch]
    if not hits:
        if governance == "Direct":
            return
        line = f"DISPATCH {ids[0] if ids else '<WO-ID>'} rev={order_revision(order_text)} sha={now}"
        text = f"DISPATCH: no line for {' / '.join(ids) or order_path} in {log_name}; log `{line}` when dispatching"
        (problems if governance == "Strict" else notes).append(text)
        return
    name, (rev, sha) = hits[-1]
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
    if not ac_table(text, problems):
        notes.append("ACCEPTANCE: no table; give each AC of the order its own row and check it with --match")
    return problems


def report_head_value(text):
    """What a report writes as HEAD: the value after `HEAD:`, or its place in
    `TASK_ID / ... / HEAD / WORKTREE_CLEAN: ... / <value> / yes` (counted from the right, so a branch name with slashes
    does not shift it). None when no line names HEAD."""
    for line in text.splitlines():
        keys, sep, values = line.partition(":")
        names = [key.strip() for key in keys.split("/")]
        if sep and "HEAD" in names:
            parts = [value.strip() for value in values.split("/")]
            back = len(names) - names.index("HEAD")
            if len(parts) >= back:
                return parts[-back]
    return None


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


def evidence_module():
    """evidence_record.py next to this file, for its record checks."""
    import importlib.util
    path = pathlib.Path(__file__).resolve().parent / "evidence_record.py"
    spec = importlib.util.spec_from_file_location("evidence_record", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_evidence(ac, evidence, folder, head, problems, notes, strict=False):
    """An AUTO row marked PASS against the evidence_record.py files its 證據 cell names.
    strict: uncommitted changes or a label naming another AC fail instead of being noted."""
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
            notes.append(f"{ac}: {name}: legacy record without `schema`; only command, exit_code and artifacts checked")
        code, git = record["exit_code"], record.get("git") or {}
        if code != 0 or record.get("timed_out"):
            problems.append(f"{ac}: {name}: the command exited {code}{' (timed out)' if record.get('timed_out') else ''}")
        lost = [item.get("path") for item in record.get("artifacts", []) if item.get("sha256") is None]
        if lost:
            problems.append(f"{ac}: {name}: artifact missing when recorded: {lost[0]}")
        recorded = (git.get("head") or "").lower()
        if head and recorded and not (recorded.startswith(head) or head.startswith(recorded)):
            problems.append(f"{ac}: {name}: recorded at HEAD {recorded[:12]}, the report says {head[:12]}; "
                            "record again after the last commit")
        elif head and not recorded:
            notes.append(f"{ac}: {name}: recorded with no git HEAD; not compared with the report's")
        if git.get("dirty"):
            (problems if strict else notes).append(
                f"{ac}: {name}: recorded with uncommitted changes" + ("; Strict: commit, then record again" if strict else ""))
        label = record.get("label")
        if label is not None and ac not in re.split(r"[\s,;/+]+", str(label)):
            (problems if strict else notes).append(
                f"{ac}: {name}: its label is {label}, not {ac}" + ("; Strict: record once per AC, or label both" if strict else ""))


def check_match(report, order, notes, evidence_dir=None, dispatch=None, order_path=None, log_name=None):
    """The report's ACCEPTANCE rows against the order's acceptance criteria and its hash.
    dispatch: the records of --dispatch-log (None when the flag is absent), order_path: the order file's path."""
    problems = []
    order_text = order.decode("utf-8-sig")
    order_problems = []
    wanted, got = ac_table(order_text, order_problems), ac_table(report, problems)
    problems.extend(f"order: {p}" for p in order_problems)
    strict = bool(re.search(r"^\s*GOVERNANCE\s*=\s*Strict\b", order_text, re.M))
    head_value = check_head(report, problems, notes, strict)
    head = report_head(report) if evidence_dir else None
    if evidence_dir and not head:
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
            check_evidence(ac, evidence, evidence_dir, head, problems, notes, strict)
        if status in ("PASS", "FAIL") and blank(row.get("actual", "")):
            problems.append(f"{ac}: {status} with 實際 empty")
    for ac in sorted(got.keys() - wanted.keys()):
        problems.append(f"{ac}: in the report but not in the order")
    if report_fields(report).get("RESULT", "").strip() == "PASS":
        open_rows = sorted(ac for ac, row in got.items() if row.get("status", "") in UNFINISHED)
        if open_rows:
            problems.append(f"RESULT PASS with {' / '.join(UNFINISHED)} rows: {', '.join(open_rows)}")
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
        notes.append("DISPATCH: Strict order checked without --dispatch-log; the hash was only compared with the order as it is now")
    return problems


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


CHECKS = {"resume": check_resume, "order": check_order, "report": check_report, "verdict": check_verdict}


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
    ap.add_argument("--hash", nargs="+", default=[], metavar="FILE", help="print the hash ORDER_SHA256 compares and the DISPATCH line")
    ap.add_argument("--warn", action="store_true", help="report problems as WARN and exit 0")
    ap.add_argument("--since", metavar="YYYY-MM-DD", help="skip files dated before this day")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    jobs = [(kind, path) for kind in CHECKS for path in getattr(a, kind)] + [("match", pair) for pair in a.match]
    missing = [path for path in a.hash if not pathlib.Path(path).is_file()]
    for path in a.hash:
        if path in missing:
            print(f"FAIL hash {path}\n  - file not found")
            continue
        data = pathlib.Path(path).read_bytes()
        text, digest = data.decode("utf-8-sig", errors="replace"), order_hash(data)
        ids = order_ids(text, path)
        print(f"{digest}  {path}\n  DISPATCH {ids[0] if ids else pathlib.Path(path).stem} rev={order_revision(text)} sha={digest}")
    if not jobs and a.hash:
        return 1 if missing else 0
    if not jobs:
        ap.error("give at least one of --resume / --order / --report / --verdict / --match / --hash")
    if a.since and not DATE.fullmatch(a.since):
        ap.error("--since takes a date: YYYY-MM-DD")
    if a.evidence_dir and not a.match:
        ap.error("--evidence-dir works with --match")
    if a.evidence_dir and not pathlib.Path(a.evidence_dir).is_dir():
        ap.error(f"--evidence-dir: folder not found: {a.evidence_dir}")
    if a.dispatch_log and not a.match:
        ap.error("--dispatch-log works with --match")
    if a.dispatch_log and not pathlib.Path(a.dispatch_log).is_file():
        ap.error(f"--dispatch-log: file not found: {a.dispatch_log}")
    dispatch = dispatch_records(pathlib.Path(a.dispatch_log).read_text(encoding="utf-8-sig")) if a.dispatch_log else None

    failed = skipped = undated = 0
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
            problems = check_match(text, files[1].read_bytes(), notes, a.evidence_dir, dispatch, files[1], a.dispatch_log)
        else:
            problems = CHECKS[kind](text, notes)
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
