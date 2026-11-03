"""Check the format of a RESUME_STATE, work order, task report or gate verdict, so a rule fails in a script instead of
relying on the model remembering it.

Prints OK / FAIL per file with one line per problem; exit 1 when anything fails. Only reads.
Passing means the file follows the format and the rules below. It does not mean the work is correct: reviewing the
evidence and the product is still the Director's job (docs/02, docs/07).

  --resume   the four header lines come first, in order, filled in; UPDATED holds a date
  --order    required fields filled in; SCOPE / FORBIDDEN are concrete path lists; acceptance rows are concrete
  --report   required fields filled in; RESULT in the vocabulary; PASS is refused with NOT_RUN tests or a scope violation
  --verdict  verdict and next step in the vocabulary; status split by aspect; stop state written

Bringing in a project that already has files in another format:
  --warn          print WARN instead of FAIL and exit 0, so old files do not block work
  --since DATE    SKIP files dated before DATE (YYYY-MM-DD): ISSUED_BY of an order, UPDATED of a RESUME_STATE, the
                  first date in a report or verdict. Files without a date are still checked.
The fixed words come from vocabulary.json next to this file.
"""
import argparse
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
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
DATED_BY = {"order": r"^\s*ISSUED_BY\s*=.*?(\d{4}-\d{2}-\d{2})", "resume": r"^UPDATED\s*:.*?(\d{4}-\d{2}-\d{2})"}
VAGUE = re.compile(r"視情況|相關檔案|相關的檔案|等等|之類|適當|盡量|儘量|必要時|\b(?:as needed|etc|tbd|todo)\b", re.I)
PLACEHOLDER = re.compile(r"<[^<>\n]+>")
TOO_BROAD = ("*", "**", "**/*", ".", "./", "/")


def blank(value):
    return value.strip() in ("", "...", "…")


def filled(name, value, problems):
    if blank(value):
        problems.append(f"{name}: empty")
    elif PLACEHOLDER.search(value):
        problems.append(f"{name}: placeholder left: {PLACEHOLDER.search(value).group(0)}")
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


def check_resume(text):
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


def check_order(text):
    problems = []
    for key in ORDER_FIELDS:
        m = re.search(rf"^\s*{re.escape(key)}\s*=\s*(.*)$", text, re.M)
        if not m:
            problems.append(f"{key}: missing")
        elif filled(key, m.group(1), problems) and key == "GOVERNANCE" and m.group(1).strip() not in GOVERNANCE:
            problems.append(f"GOVERNANCE: must be one of {', '.join(GOVERNANCE)}")
    check_paths("SCOPE", text, problems)
    check_paths("FORBIDDEN", text, problems)
    rows = re.findall(r"^\|\s*(AC-[\w-]+)\s*\|(.*)$", text, re.M)
    if not rows:
        problems.append("acceptance: no AC-<n> row")
    for ac, rest in rows:
        for name, cell in zip(("requirement", "how verified", "expected"), rest.split("|")):
            if filled(f"{ac} {name}", cell, problems) and VAGUE.search(cell):
                problems.append(f"{ac} {name}: vague: {cell.strip()}")
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


def check_report(text):
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
    scope = fields.get("SCOPE_CHECK", "").strip()
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
    return problems


def check_verdict(text):
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
    ap.add_argument("--warn", action="store_true", help="report problems as WARN and exit 0")
    ap.add_argument("--since", metavar="YYYY-MM-DD", help="skip files dated before this day")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    jobs = [(kind, path) for kind in CHECKS for path in getattr(a, kind)]
    if not jobs:
        ap.error("give at least one of --resume / --order / --report / --verdict")
    if a.since and not DATE.fullmatch(a.since):
        ap.error("--since takes a date: YYYY-MM-DD")

    failed = skipped = 0
    for kind, path in jobs:
        file = pathlib.Path(path)
        text = file.read_text(encoding="utf-8-sig") if file.is_file() else None
        day = dated(kind, text) if text is not None and a.since else None
        if day and day < a.since:
            skipped += 1
            print(f"SKIP {kind} {path} (dated {day}, before --since)")
            continue
        problems = CHECKS[kind](text) if text is not None else ["file not found"]
        failed += bool(problems)
        print(f"{('WARN' if a.warn else 'FAIL') if problems else 'OK  '} {kind} {path}")
        for problem in problems:
            print(f"  - {problem}")
    if a.warn or a.since:
        print(f"checked {len(jobs) - skipped}, {'warned' if a.warn else 'failed'} {failed}, skipped {skipped}")
    return 1 if failed and not a.warn else 0


if __name__ == "__main__":
    sys.exit(main())
