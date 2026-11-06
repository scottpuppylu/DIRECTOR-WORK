"""Run gate_check, trace_report, metrics_report, scope_check, evidence_record and hook_guard against good and bad cases
in a temporary folder, and check that the fixed words, the size of the must-read docs, PURPOSE.md and the CHANGELOG have
not drifted.
Prints one line per failed case and a summary; exit 1 when anything fails. Writes only to the temporary folder.
"""
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

TOOLS = pathlib.Path(__file__).resolve().parent
TEMPLATES = TOOLS.parent / "templates"

RESUME = """PROGRESS: tests pass at abc123
DOING: AC-2 of WO-001
NEXT_STEP: run the parser test
COMMS: NONE

# RESUME_STATE
UPDATED: 2026-01-02 10:00 +08:00
"""
ORDER = """# WO-001
```text
ISSUED_BY      = director 2026-01-02 10:00
PRIMARY_WORKER = session a
MODEL / EFFORT = sonnet / medium
FALLBACK       = same session
GOVERNANCE     = Standard
BASE_REF       = main @ {base}
```
```text
SCOPE:
- src/**
- .config/app.json  # the one config file
FORBIDDEN:
- src/frozen/**
```
| ID | req | how | expected | actual | evidence | status |
|---|---|---|---|---|---|---|
| AC-1 | parser accepts empty input | run test_parser | exit 0 | | | |

- DELIVERABLES: commit on the branch
- STOP_RULES: stop after 2 rounds without progress
"""
REPORT = """done
```text
TASK_ID / WORKER / MODEL / BRANCH / BASE / HEAD / WORKTREE_CLEAN: T / a / sonnet / b / c / d0d0d0d / yes
RESULT: {result}
  ENGINEERING: builds
  PRODUCT（成品）: not applicable
DONE: parser fix, evidence e.json
TESTS: {tests}
SCOPE_CHECK: {scope}
EVIDENCE: {evidence}
UNVERIFIED: NONE
KNOWN_ISSUES: NONE
NEXT: NONE
```
"""
TYPED_ORDER = ORDER.replace("BASE_REF       = main @ {base}\n",
                            "BASE_REF       = main @ {base}\nREVISION       = 1\nTRACES_TO      = DD-1\n").replace(
    """| ID | req | how | expected | actual | evidence | status |
|---|---|---|---|---|---|---|
| AC-1 | parser accepts empty input | run test_parser | exit 0 | | | |
""", """| ID | 類型 | 要求 | 驗證方法 | 預期 |
|---|---|---|---|---|
| AC-1 | AUTO | parser accepts empty input | run test_parser | exit 0 |
| AC-2 | REVIEW | the output reads right | reviewer reads out.txt in full | no WRONG answer |
| AC-3 | PO | PO accepts the wording | PO reads out.txt | PO says yes |
""")
ACCEPTANCE = {"AC-1": "| AC-1 | exit 0 | e.json | PASS |", "AC-2": "| AC-2 | out.txt written | out.txt | READY_FOR_REVIEW |",
              "AC-3": "| AC-3 | wording drafted | out.txt | PENDING_PO |"}
VERDICT = """# GATE VERDICT
## A. 判定
{verdict}
分面向：工程 PASS / 成品 未看 / PO 驗收：未做
下一步：{step}

## F. 停止狀態
NO MERGE / NO PUSH
"""

failures, total = [], 0


def run(tool, *args, cwd=None):
    done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / tool), *map(str, args)], cwd=cwd,
                          capture_output=True, encoding="utf-8")
    return done.returncode, done.stdout


def expect(name, tool, code, *args, cwd=None, says=None, lacks=None):
    """says / lacks: a string or a list of strings the output must hold / must not hold."""
    global total
    total += 1
    got, out = run(tool, *args, cwd=cwd)
    says, lacks = [says] if isinstance(says, str) else says or [], [lacks] if isinstance(lacks, str) else lacks or []
    if got != code or any(s not in out for s in says) or any(s in out for s in lacks):
        failures.append(f"{name}: expected exit {code} with {says!r} and without {lacks!r}, got {got}: {out.strip()[-300:]}")


def gate(tmp, name, kind, text, code, says=None):
    file = tmp / f"{name}.md"
    file.write_text(text, encoding="utf-8")
    expect(name, "gate_check.py", code, f"--{kind}", file, says=says)


def test_gate(tmp):
    for kind, template in (("resume", "RESUME_STATE"), ("order", "WORK_ORDER"), ("report", "TASK_REPORT"), ("verdict", "GATE_VERDICT")):
        expect(f"blank template {template} is refused", "gate_check.py", 1, f"--{kind}", TEMPLATES / f"{template}.md")
    good_report = dict(result="PASS", tests="unit 12/12", scope="PASS base=abc changed=2 forbidden=0 outside=0", evidence="e.json")
    gate(tmp, "resume_ok", "resume", RESUME, 0)
    gate(tmp, "resume_order", "resume", RESUME.replace("PROGRESS", "X", 1).replace("DOING", "PROGRESS", 1).replace("X:", "DOING:", 1), 1)
    gate(tmp, "resume_empty", "resume", RESUME.replace("COMMS: NONE", "COMMS:"), 1, "COMMS: empty")
    gate(tmp, "resume_date", "resume", RESUME.replace("2026-01-02", "today"), 1, "UPDATED")
    gate(tmp, "order_ok", "order", ORDER.format(base="abc123"), 0)
    gate(tmp, "order_vague", "order", ORDER.format(base="abc123").replace("- src/**", "- 相關檔案"), 1, "vague")
    gate(tmp, "order_file_named_todo", "order", ORDER.format(base="abc123").replace("- src/**", "- todo.py"), 0)
    gate(tmp, "order_etc", "order", ORDER.format(base="abc123").replace("- src/**", "- src/** etc."), 1, "vague")
    gate(tmp, "order_broad", "order", ORDER.format(base="abc123").replace("- src/**", "- **"), 1, "too broad")
    gate(tmp, "order_absolute", "order", ORDER.format(base="abc123").replace("- src/**", "- C:/src"), 1, "relative")
    gate(tmp, "order_noscope", "order", ORDER.format(base="abc123").replace("SCOPE:", "NOTES:"), 1, "SCOPE: missing")
    gate(tmp, "order_ac", "order", ORDER.format(base="abc123").replace("run test_parser", ""), 1, "how verified")
    gate(tmp, "order_gov", "order", ORDER.format(base="abc123").replace("Standard", "Loose"), 1, "GOVERNANCE")
    # v0.13: optional REQUIRED_CHANGES must lie inside SCOPE and outside FORBIDDEN
    required = lambda item: ORDER.format(base="abc123").replace("- src/frozen/**\n", "- src/frozen/**\nREQUIRED_CHANGES:\n- " + item + "\n")
    gate(tmp, "order_required_ok", "order", required("src/parser.py"), 0)
    gate(tmp, "order_required_forbidden", "order", required("src/frozen/b.py"), 1, "is FORBIDDEN")
    gate(tmp, "order_required_outside", "order", required("docs/x.md"), 1, "outside SCOPE")
    gate(tmp, "report_ok", "report", REPORT.format(**good_report), 0)
    done_line = "DONE: parser fix, evidence e.json"
    gate(tmp, "report_code_span", "report", REPORT.format(**good_report).replace(done_line, done_line + ", ids are `AC-<n>`, mail <a@b.example>"), 0)
    gate(tmp, "report_placeholder", "report", REPORT.format(**good_report).replace(done_line, done_line + ", <what changed>"), 1, "placeholder")
    gate(tmp, "report_scope_prefix", "report", REPORT.format(**{**good_report, "scope": "SCOPE_CHECK: " + good_report["scope"]}), 0)
    gate(tmp, "report_scope_prefix_violation", "report", REPORT.format(**{**good_report, "scope": "SCOPE_CHECK: VIOLATION base=abc"}), 1, "scope violation")
    gate(tmp, "report_word", "report", REPORT.format(**{**good_report, "result": "DONE"}), 1, "RESULT")
    gate(tmp, "report_notrun", "report", REPORT.format(**{**good_report, "tests": "unit NOT_RUN"}), 1, "NOT_RUN")
    gate(tmp, "report_partial_notrun", "report", REPORT.format(**{**good_report, "result": "PARTIAL", "tests": "unit NOT_RUN"}), 0)
    gate(tmp, "report_scope", "report", REPORT.format(**{**good_report, "scope": "VIOLATION base=abc"}), 1, "scope violation")
    gate(tmp, "report_scope_notrun", "report", REPORT.format(**{**good_report, "scope": "NOT_RUN no git"}), 1, "not checked")
    gate(tmp, "report_partial_scope_notrun", "report", REPORT.format(**{**good_report, "result": "PARTIAL", "scope": "NOT_RUN no git"}), 0)
    gate(tmp, "report_noevidence", "report", REPORT.format(**{**good_report, "evidence": "NONE"}), 1, "reason")
    gate(tmp, "report_reason", "report", REPORT.format(**{**good_report, "evidence": "NONE: docs only"}), 0)
    gate(tmp, "verdict_ok", "verdict", VERDICT.format(verdict="PASS_WITH_WARNINGS", step="ACCEPT_AND_CLOSE"), 0)
    gate(tmp, "verdict_word", "verdict", VERDICT.format(verdict="GOOD", step="ACCEPT_AND_CLOSE"), 1, "verdict")
    gate(tmp, "verdict_step", "verdict", VERDICT.format(verdict="PASS", step="ACCEPT_AND_CLOSE / CONTINUE_SAME_WORKER"), 1, "下一步")
    gate(tmp, "verdict_aspects", "verdict", VERDICT.format(verdict="PASS", step="ACCEPT_AND_CLOSE").replace("成品 未看 / ", ""), 1, "aspect")
    expect("missing file", "gate_check.py", 1, "--resume", tmp / "nope.md", says="file not found")
    expect("no arguments", "gate_check.py", 2)

    old = tmp / "order_old.md"
    old.write_text(ORDER.format(base="abc123").replace("2026-01-02", "2025-12-31").replace("- src/**", "- 相關檔案"), encoding="utf-8")
    new = tmp / "order_new.md"
    new.write_text(ORDER.format(base="abc123").replace("- src/**", "- 相關檔案"), encoding="utf-8")
    undated = tmp / "report_undated.md"
    undated.write_text(REPORT.format(**{**good_report, "result": "DONE"}), encoding="utf-8")
    expect("an old file still fails without flags", "gate_check.py", 1, "--order", old, says="FAIL")
    expect("--warn reports and does not block", "gate_check.py", 0, "--warn", "--order", old, new, says="warned 2")
    expect("--since skips an old order", "gate_check.py", 0, "--since", "2026-01-01", "--order", old, says="SKIP")
    expect("--since still checks a new order", "gate_check.py", 1, "--since", "2026-01-01", "--order", old, new, says="skipped 1")
    expect("an undated file is checked without --since", "gate_check.py", 1, "--report", undated, says="FAIL")
    expect("--since skips an undated file and counts it", "gate_check.py", 1, "--since", "2026-01-01", "--report", undated,
           "--order", old, new, says=["SKIP report", "UNDATED: no date", "checked 1, failed 1, skipped 1, UNDATED 1 (not checked)"])
    expect("--since without undated files prints no UNDATED count", "gate_check.py", 0, "--since", "2026-01-01", "--order", old,
           lacks="UNDATED")
    expect("--since skips an old RESUME_STATE", "gate_check.py", 0, "--since", "2026-02-01", "--resume", tmp / "resume_empty.md", says="SKIP")
    expect("--since needs a date", "gate_check.py", 2, "--since", "yesterday", "--order", new)


def match_report(rows, result="PASS", sha=None):
    """A report whose ACCEPTANCE table holds rows, pointing at WO-001-parser.md."""
    head = "ORDER: WO-001-parser.md REVISION 1\n" + (f"ORDER_SHA256: {sha}\n" if sha else "")
    table = "ACCEPTANCE:\n| ID | 實際 | 證據 | 狀態 |\n|---|---|---|---|\n" + "\n".join(rows) + "\n"
    text = REPORT.format(result=result, tests="unit 12/12", scope="PASS base=abc changed=2 forbidden=0 outside=0", evidence="e.json")
    return text.replace("RESULT:", head + "RESULT:", 1).replace("UNVERIFIED: NONE", table + "UNVERIFIED: NONE")


def test_acceptance(tmp):
    """v0.10: typed acceptance criteria in the order, results in the report, --match and --hash. Old files only get notes."""
    global total
    total += 1
    if "| AC-3 | PO |" not in TYPED_ORDER or "TRACES_TO" not in TYPED_ORDER:
        failures.append("TYPED_ORDER did not build from ORDER; update the replace() in selftest.py")
    typed = TYPED_ORDER.format(base="abc123")
    gate(tmp, "typed_ok", "order", typed, 0)
    expect("a typed order gets no notes", "gate_check.py", 0, "--order", tmp / "typed_ok.md", lacks="  ~ ")
    expect("an old order passes with notes", "gate_check.py", 0, "--order", tmp / "order_ok.md",
           says=["OK", "~ acceptance: no 類型 column", "~ REVISION: missing", "~ TRACES_TO: missing", "~ acceptance: 實際"])
    gate(tmp, "typed_kind", "order", typed.replace("| AUTO |", "| AUTOMATIC |"), 1, "類型: must be one of")
    gate(tmp, "typed_rev_word", "order", typed.replace("REVISION       = 1", "REVISION       = two"), 1, "must be a number")
    gate(tmp, "typed_rev_nolog", "order", typed.replace("REVISION       = 1", "REVISION       = 2"), 1, "no row for revision 2")
    gate(tmp, "typed_rev_log", "order", typed.replace("REVISION       = 1", "REVISION       = 2")
         + "\n| 版本 | 時間 | 誰改 | 原因 | 影響的 AC |\n|---|---|---|---|---|\n| 2 | 2026-01-03 | director | split AC-1 | AC-1 |\n", 0)
    expect("a report without ACCEPTANCE still passes", "gate_check.py", 0, "--report", tmp / "report_ok.md", says="~ ACCEPTANCE: no table")

    order = tmp / "WO-001-parser.md"
    order.write_bytes(typed.encode("utf-8"))
    sha = hashlib.sha256(typed.encode("utf-8")).hexdigest()
    crlf = tmp / "WO-001-crlf.md"
    crlf.write_bytes(typed.replace("\n", "\r\n").encode("utf-8"))
    expect("--hash prints the order hash", "gate_check.py", 0, "--hash", order, says=f"{sha}  ")
    expect("--hash counts CRLF as LF", "gate_check.py", 0, "--hash", crlf, says=f"{sha}  ")
    expect("--hash of a missing file", "gate_check.py", 1, "--hash", tmp / "nope.md", says="file not found")

    def match(name, code, rows, says=None, result="PASS", digest=sha, against=order, lacks=None):
        report = tmp / f"{name}.md"
        report.write_text(match_report(rows, result, digest), encoding="utf-8")
        expect(name, "gate_check.py", code, "--match", report, against, says=says, lacks=lacks)
        return report

    good = list(ACCEPTANCE.values())
    match("match_ok", 0, good, says="OK   match", lacks="  ~ ")
    match("match_crlf_order", 0, good, against=crlf)
    match("match_missing_ac", 1, good[:2], "AC-3: in the order but not in the report")
    match("match_extra_ac", 1, good + ["| AC-4 | x | y.json | PASS |"], "AC-4: in the report but not in the order")
    match("match_review_pass", 1, [good[0], "| AC-2 | looks fine | out.txt | PASS |", good[2]],
          ["AC-2 (REVIEW): status must be one of", "a reviewer, then the Director, judges it"])
    match("match_po_pass", 1, good[:2] + ["| AC-3 | drafted | out.txt | PASS |"], ["AC-3 (PO)", "only the PO judges it"])
    match("match_no_evidence", 1, ["| AC-1 | exit 0 | | PASS |"] + good[1:], "AC-1: PASS without evidence")
    match("match_none_evidence", 1, ["| AC-1 | exit 0 | NONE | PASS |"] + good[1:], "AC-1: PASS without evidence")
    match("match_no_actual", 1, ["| AC-1 | | e.json | PASS |"] + good[1:], "AC-1: PASS with 實際 empty")
    match("match_pass_blocked", 1, ["| AC-1 | crashed | log.txt | BLOCKED |"] + good[1:], "RESULT PASS with")
    match("match_partial_blocked", 0, ["| AC-1 | crashed | log.txt | BLOCKED |"] + good[1:], result="PARTIAL")
    match("match_no_hash", 1, good, "ORDER_SHA256: missing", digest=None)
    changed = tmp / "WO-001-changed.md"
    changed.write_text(typed.replace("exit 0 |", "exit 0 or 1 |"), encoding="utf-8")
    match("match_changed_order", 1, good, "the order is not the one the worker hashed", against=changed)
    old = tmp / "WO-old.md"
    old.write_text(ORDER.format(base="abc123"), encoding="utf-8")
    old_sha = hashlib.sha256(ORDER.format(base="abc123").encode("utf-8")).hexdigest()  # write_text may add CR
    match("match_untyped_as_auto", 0, [good[0]], "~ AC-1: the order gives no 類型; checked as AUTO", digest=old_sha, against=old)
    match("match_untyped_review", 1, ["| AC-1 | x | y.json | READY_FOR_REVIEW |"], "AC-1 (AUTO)", digest=old_sha, against=old)
    expect("--order with --report does not cross-check", "gate_check.py", 0, "--order", order, "--report",
           tmp / "match_missing_ac.md", lacks="in the order but not")
    expect("--match missing file", "gate_check.py", 1, "--match", tmp / "nope.md", order, says="file not found")


def test_table(tmp):
    r"""v0.12: the ACCEPTANCE table parser rejects a duplicate AC row, a duplicate column name and a row whose cell count
    differs from the header's; `|` inside backticks or escaped as `\|` does not split a cell."""
    global total
    total += 1
    typed = TYPED_ORDER.format(base="abc123")
    order = tmp / "WO-010-table.md"
    order.write_text(typed, encoding="utf-8")
    sha = hashlib.sha256(typed.encode("utf-8")).hexdigest()
    good = list(ACCEPTANCE.values())

    def match(name, code, rows, says=None, lacks=None, against=order, digest=sha, header=None):
        report = tmp / f"{name}.md"
        text = match_report(rows, "PASS", digest)
        if header:
            text = text.replace("| ID | 實際 | 證據 | 狀態 |", header)
        report.write_text(text, encoding="utf-8")
        expect(name, "gate_check.py", code, "--match", report, against, says=says, lacks=lacks)

    match("table_dup_ac_fail_then_pass", 1, ["| AC-1 | exit 1 | e.json | FAIL |"] + good,
          ["AC-1: listed twice; one row per AC", "RESULT PASS with FAIL"])
    match("table_dup_ac_pass_then_pass", 1, good + [good[0]], "AC-1: listed twice")
    match("table_short_row", 1, ["| AC-1 | PASS |"] + good[1:], "AC-1: 2 cells, the header has 4")
    match("table_long_row", 1, ["| AC-1 | exit 0 | e.json | PASS | extra |"] + good[1:], "AC-1: 5 cells, the header has 4")
    match("table_dup_column", 1, good, "column actual appears twice in the header", header="| ID | 實際 | 實際 | 狀態 |")
    gate(tmp, "table_dup_ac_order", "order", typed.replace("| AC-2 |", "| AC-1 |", 1), 1, "AC-1: listed twice")
    gate(tmp, "table_short_row_order", "order", typed.replace("| run test_parser | exit 0 |", "| run test_parser |"), 1,
         "AC-1: 4 cells, the header has 5")
    gate(tmp, "table_dup_column_order", "order", typed.replace("| ID | 類型 | 要求 | 驗證方法 | 預期 |", "| ID | 類型 | 要求 | 要求 | 預期 |"), 1,
         "column requirement appears twice")
    piped = typed.replace("| run test_parser |", "| run `cat a.txt \\| grep -E \"x\\|y\"` and `a | b`, then `c` |")
    if piped == typed:
        failures.append("test_table: TYPED_ORDER has no `run test_parser` cell; update the replace()")
    pipe_order = tmp / "WO-001-pipe.md"
    pipe_order.write_text(piped, encoding="utf-8")
    pipe_sha = hashlib.sha256(piped.encode("utf-8")).hexdigest()
    expect("a `|` inside backticks does not split the order's cell", "gate_check.py", 0, "--order", pipe_order, lacks=["cells", "  ~ "])
    match("table_pipe_in_report_cell", 0, ["| AC-1 | `a | b` and `x\\|y` ran, exit 0 | e.json | PASS |"] + good[1:],
          "OK   match", against=pipe_order, digest=pipe_sha)
    match("table_escaped_pipe_in_cell", 0, ["| AC-1 | saw a \\| b | e.json | PASS |"] + good[1:], "OK   match",
          against=pipe_order, digest=pipe_sha)
    match("table_unclosed_backtick_is_short", 1, ["| AC-1 | `a | e.json | PASS |"] + good[1:], "cells, the header has 4",
          against=pipe_order, digest=pipe_sha)


def test_dispatch(tmp):
    """v0.12: --match --dispatch-log compares the order's hash with the DISPATCH line the Director logged, so an order
    rewritten and re-hashed by the worker is caught. Without the flag only the order as it is now is compared."""
    typed = TYPED_ORDER.format(base="abc123")
    order = tmp / "WO-001-parser.md"
    order.write_bytes(typed.encode("utf-8"))
    sha = hashlib.sha256(typed.encode("utf-8")).hexdigest()
    good = list(ACCEPTANCE.values())

    def log(name, *lines):
        file = tmp / f"{name}.md"
        file.write_text("# DIRECTOR_LOG\n" + "".join(f"2026-01-02 10:00 +08:00 | {line}\n" for line in lines), encoding="utf-8")
        return file

    def match(name, code, against=order, rows=good, says=None, lacks=None, dispatch_log=None):
        report = tmp / f"{name}.md"
        digest = hashlib.sha256(against.read_bytes().replace(b"\r\n", b"\n")).hexdigest()  # write_text may add CR
        report.write_text(match_report(rows, "PASS", digest), encoding="utf-8")
        extra = ("--dispatch-log", dispatch_log) if dispatch_log else ()
        expect(name, "gate_check.py", code, "--match", report, against, *extra, says=says, lacks=lacks)
        return report

    logged = log("log_ok", f"DISPATCH WO-001 rev=1 sha={sha}")
    match("dispatch_ok", 0, says="OK   match", lacks="  ~ ", dispatch_log=logged)
    match("dispatch_by_file_name", 0, says="OK   match", lacks="  ~ ", dispatch_log=log("log_stem", f"DISPATCH WO-001-parser.md rev=1 sha={sha}"))
    match("dispatch_latest_line_wins", 0, says="OK   match", dispatch_log=log("log_two", f"DISPATCH WO-001 rev=1 sha={'0' * 64}",
                                                                              f"DISPATCH WO-001 rev=1 sha={sha}"))
    match("dispatch_stale_line_fails", 1, says="not the one logged at dispatch", dispatch_log=log("log_stale", f"DISPATCH WO-001 rev=1 sha={sha}",
                                                                                                 f"DISPATCH WO-001 rev=2 sha={'0' * 64}"))
    # the worker weakens AC-1, drops the REVIEW / PO rows, or turns REVIEW into AUTO, then re-hashes: the report agrees
    # with the order as it is now, only the dispatch record disagrees
    weakened = tmp / "WO-001-weak.md"
    weakened.write_text(typed.replace("| AC-1 | AUTO | parser accepts empty input | run test_parser | exit 0 |",
                                      "| AC-1 | AUTO | parser exists | ls | file listed |"), encoding="utf-8")
    match("dispatch_weakened_rehashed", 1, against=weakened, says="the order changed after dispatch", dispatch_log=logged)
    expect("the same rewrite passes without --dispatch-log", "gate_check.py", 0, "--match", tmp / "dispatch_weakened_rehashed.md", weakened)
    dropped = tmp / "WO-001-dropped.md"
    dropped.write_text("\n".join(line for line in typed.splitlines() if "| AC-2 |" not in line and "| AC-3 |" not in line) + "\n", encoding="utf-8")
    match("dispatch_rows_dropped_rehashed", 1, against=dropped, rows=good[:1], says="the order changed after dispatch", dispatch_log=logged)
    retyped = tmp / "WO-001-retyped.md"
    retyped.write_text(typed.replace("| AC-2 | REVIEW |", "| AC-2 | AUTO |"), encoding="utf-8")
    match("dispatch_review_to_auto_rehashed", 1, against=retyped, rows=[good[0], "| AC-2 | reads right | e.json | PASS |", good[2]],
          says="the order changed after dispatch", dispatch_log=logged)
    # v0.13 (G01): given a log, an order it does not show as dispatched fails in every governance, so lowering the mode
    # in the order (Strict -> Direct) does not skip the check
    for governance, code, mark in (("Strict", 1, "  - DISPATCH: no line for WO-001 / WO-001-"), ("Standard", 1, "  - DISPATCH: no line for"),
                                   ("Direct", 1, "  - DISPATCH: no line for")):
        other = tmp / f"WO-001-{governance}.md"
        other.write_text(typed.replace("GOVERNANCE     = Standard", f"GOVERNANCE     = {governance}"), encoding="utf-8")
        match(f"dispatch_no_record_{governance}", code, against=other, says=mark,
              dispatch_log=log("log_other", f"DISPATCH WO-999 rev=1 sha={'1' * 64}"))
    strict = tmp / "WO-001-Strict.md"
    match("strict_without_dispatch_log_fails", 1, against=strict, says="- DISPATCH: Strict order checked without --dispatch-log")
    match("standard_without_dispatch_log_silent", 0, lacks="DISPATCH")
    expect("--dispatch-log needs --match", "gate_check.py", 2, "--order", order, "--dispatch-log", logged)
    expect("--dispatch-log file missing", "gate_check.py", 2, "--match", tmp / "dispatch_ok.md", order, "--dispatch-log", tmp / "nope.md")
    expect("--hash prints the DISPATCH line to log", "gate_check.py", 0, "--hash", order, says=f"\n  DISPATCH WO-001 rev=1 sha={sha}")


def test_revision(tmp):
    """v0.13: the DISPATCH line, the order and the report's ORDER line name the same REVISION (A03, A11); a report
    without one is a problem for a Strict order and a note otherwise."""
    typed = TYPED_ORDER.format(base="abc123")
    rev2 = typed.replace("REVISION       = 1", "REVISION       = 2") + (
        "\n| 版本 | 時間 | 誰改 | 原因 | 影響的 AC |\n|---|---|---|---|---|\n| 2 | 2026-01-03 | director | split AC-1 | AC-1 |\n")
    if rev2.startswith(typed):
        failures.append("test_revision: TYPED_ORDER has no `REVISION       = 1` line; update the replace()")

    def case(name, code, text, says=None, lacks=None, log_line=None, edit=None, governance="Standard"):
        folder = tmp / "revision" / name
        folder.mkdir(parents=True)
        text = text.replace("GOVERNANCE     = Standard", f"GOVERNANCE     = {governance}")
        order = folder / "WO-001-parser.md"
        order.write_bytes(text.encode("utf-8"))
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        report = folder / "report.md"
        report_text = match_report(list(ACCEPTANCE.values()), "PASS", sha)
        report.write_text(edit(report_text) if edit else report_text, encoding="utf-8")
        extra = ()
        if log_line:
            (folder / "log.md").write_text(f"# DIRECTOR_LOG\n2026-01-02 10:00 +08:00 | {log_line.format(sha=sha)}\n", encoding="utf-8")
            extra = ("--dispatch-log", folder / "log.md")
        expect(name, "gate_check.py", code, "--match", report, order, *extra, says=says, lacks=lacks)

    case("rev_dispatch_same", 0, typed, "OK   match", "  ~ ", log_line="DISPATCH WO-001 rev=1 sha={sha}")
    case("rev_dispatch_other_rev", 1, typed, "- DISPATCH: the latest line for WO-001 logs rev=99, the order is at REVISION 1",
         log_line="DISPATCH WO-001 rev=99 sha={sha}")
    case("rev_report_older", 1, rev2, "- ORDER: the report is for REVISION 1, the order is at REVISION 2")
    case("rev_report_matches_rev2", 0, rev2, "OK   match", "  - ", log_line="DISPATCH WO-001 rev=2 sha={sha}",
         edit=lambda r: r.replace("REVISION 1", "REVISION 2"))
    no_rev = lambda r: r.replace("ORDER: WO-001-parser.md REVISION 1", "ORDER: WO-001-parser.md")
    case("rev_report_none_standard", 0, typed, "~ ORDER: the report names no order revision; write `ORDER: WO-001-parser.md REVISION 1`",
         edit=no_rev)
    case("rev_report_none_strict", 1, typed, "- ORDER: the report names no order revision", edit=no_rev, governance="Strict",
         log_line="DISPATCH WO-001 rev=1 sha={sha}")


def test_verdict_binding(tmp):
    """v0.13 (G04): with --match the verdict's ORDER line names a matched order at its REVISION; with --candidate its
    CANDIDATE_HEAD is the commit under review. A missing line fails Strict and is a note otherwise."""
    typed = TYPED_ORDER.format(base="abc123")
    candidate = "d0d0d0d" + "0" * 33

    def case(name, code, verdict_head, says=None, lacks=None, candidate_flag=True, match=True, governance="Standard"):
        folder = tmp / "verdict_binding" / name
        folder.mkdir(parents=True)
        text = typed.replace("GOVERNANCE     = Standard", f"GOVERNANCE     = {governance}")
        order = folder / "WO-001-parser.md"
        order.write_bytes(text.encode("utf-8"))
        report = folder / "report.md"
        report.write_text(match_report(list(ACCEPTANCE.values()), "PASS", hashlib.sha256(text.encode("utf-8")).hexdigest()),
                          encoding="utf-8")
        verdict = folder / "verdict.md"
        verdict.write_text(VERDICT.format(verdict="PASS", step="ACCEPT_AND_CLOSE").replace(
            "# GATE VERDICT", "# GATE VERDICT WO-001\n" + verdict_head), encoding="utf-8")
        args = ["--verdict", verdict] + (["--match", report, order] if match else [])
        args += ["--candidate", candidate] if candidate_flag else []
        expect(name, "gate_check.py", code, *args, says=says, lacks=lacks)

    case("verdict_bound", 0, f"ORDER: WO-001-parser.md REVISION 1\nCANDIDATE_HEAD: {candidate}\n", "OK   verdict", "  - ")
    case("verdict_wrong_commit", 1, f"ORDER: WO-001-parser.md REVISION 1\nCANDIDATE_HEAD: {'d' * 40}\n",
         "- CANDIDATE_HEAD: the verdict is for dddddddddddd, the candidate is d0d0d0d00000; the verdict judged another commit")
    case("verdict_wrong_commit_without_match", 1, f"CANDIDATE_HEAD: {'d' * 40}\n", "- CANDIDATE_HEAD: the verdict is for",
         match=False)
    case("verdict_old_revision", 1, f"ORDER: WO-001-parser.md REVISION 2\nCANDIDATE_HEAD: {candidate}\n",
         "- ORDER: the verdict is for REVISION 2, the order is at REVISION 1")
    case("verdict_other_order", 1, f"ORDER: WO-777-other.md REVISION 1\nCANDIDATE_HEAD: {candidate}\n",
         "- ORDER: the verdict names WO-777-other.md, which is none of the --match orders")
    case("verdict_no_lines_standard", 0, "", ["~ ORDER: the verdict names no order", "~ CANDIDATE_HEAD: the verdict names no commit"])
    case("verdict_no_head_strict", 1, "ORDER: WO-001-parser.md REVISION 1\n",
         "- CANDIDATE_HEAD: the verdict names no commit", governance="Strict")
    case("verdict_short_head_strict", 1, f"ORDER: WO-001-parser.md REVISION 1\nCANDIDATE_HEAD: {candidate[:12]}\n",
         "- CANDIDATE_HEAD: the verdict is for d0d0d0d00000", governance="Strict")
    case("verdict_alone_unchanged", 0, "", "OK   verdict", "  ~ ", candidate_flag=False, match=False)


def test_dispatch_events(tmp):
    """v0.13 (R01 G01 G02): only a whole DISPATCH line is a dispatch event; the same words in a NOTE, backticks, a quote,
    an indented line or a fence are data. The order's title, file name and the report's ORDER line name one order."""
    typed = TYPED_ORDER.format(base="abc123")
    if "# WO-001" not in typed:
        failures.append("test_dispatch_events: TYPED_ORDER has no `# WO-001` title; update the replace()")
    root = tmp / "events"
    root.mkdir()
    sha, other = hashlib.sha256(typed.encode("utf-8")).hexdigest(), "1" * 64

    def case(name, code, lines, says=None, lacks=None, text=typed, edit=None):
        folder = root / name
        folder.mkdir()
        order = folder / "WO-001-parser.md"
        order.write_bytes(text.encode("utf-8"))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        report = match_report(list(ACCEPTANCE.values()), "PASS", digest)
        (folder / "report.md").write_text(edit(report) if edit else report, encoding="utf-8")
        (folder / "log.md").write_text("# DIRECTOR_LOG\n" + "".join(line.format(sha=sha, digest=digest, other=other) + "\n"
                                                                   for line in lines), encoding="utf-8")
        expect(name, "gate_check.py", code, "--match", folder / "report.md", order, "--dispatch-log", folder / "log.md",
               says=says, lacks=lacks)
        return order

    stale = "not the one logged at dispatch"
    case("event_bare_line", 0, ["DISPATCH WO-001 rev=1 sha={digest}"], says="OK   match", lacks="  ~ ")
    case("event_date_and_basis_columns", 0, ["2026-01-02 10:00 +08:00 | DISPATCH WO-001 rev=1 sha={digest} | DD-1 PO said 開"],
         says="OK   match")
    case("event_quoted_in_note_ignored", 1, ["2026-01-02 10:00 +08:00 | DISPATCH WO-001 rev=1 sha={other}",
                                             "2026-01-03 10:00 +08:00 | NOTE: rejected proposal `DISPATCH WO-001 rev=1 sha={digest}`"],
         says=stale)
    case("event_in_note_column_ignored", 1, ["DISPATCH WO-001 rev=1 sha={other}",
                                             "2026-01-03 10:00 +08:00 | NOTE: rejected | DISPATCH WO-001 rev=1 sha={digest}"], says=stale)
    case("event_in_backtick_fence_ignored", 1, ["DISPATCH WO-001 rev=1 sha={other}", "```text", "DISPATCH WO-001 rev=1 sha={digest}", "```"],
         says=stale)
    case("event_in_tilde_fence_ignored", 1, ["DISPATCH WO-001 rev=1 sha={other}", "~~~", "DISPATCH WO-001 rev=1 sha={digest}", "~~~"],
         says=stale)
    case("event_in_quote_ignored", 1, ["DISPATCH WO-001 rev=1 sha={other}", "> DISPATCH WO-001 rev=1 sha={digest}"], says=stale)
    case("event_indented_ignored", 1, ["DISPATCH WO-001 rev=1 sha={other}", "    DISPATCH WO-001 rev=1 sha={digest}"], says=stale)
    case("event_after_closed_fence_counts", 0, ["```", "DISPATCH WO-001 rev=1 sha={other}", "```", "DISPATCH WO-001 rev=1 sha={digest}"],
         says="OK   match")
    case("event_only_quoted_is_no_line", 1, ["2026-01-03 10:00 +08:00 | NOTE: `DISPATCH WO-001 rev=1 sha={digest}`"],
         says="- DISPATCH: no line for WO-001")
    case("event_latest_across_names", 1, ["DISPATCH WO-001-parser rev=1 sha={digest}", "DISPATCH WO-001 rev=1 sha={other}"], says=stale)
    # G01: the worker renames the order in its title and lowers Strict to Direct; the log still has the real dispatch
    renamed = typed.replace("# WO-001", "# WO-999").replace("GOVERNANCE     = Standard", "GOVERNANCE     = Direct")
    order = case("order_title_renamed_and_direct", 1, ["DISPATCH WO-001 rev=1 sha={sha}"], text=renamed,
                 says=["- order: the title names WO-999, the file name WO-001-parser.md names WO-001", stale])
    expect("--hash shows a title / file name mismatch", "gate_check.py", 0, "--hash", order,
           says=["DISPATCH WO-999 rev=1", "- order: the title names WO-999"])
    # G02: the report answers another order
    case("report_names_another_order", 1, ["DISPATCH WO-001 rev=1 sha={digest}"],
         edit=lambda r: r.replace("ORDER: WO-001-parser.md", "ORDER: WO-999-other.md"),
         says="- ORDER: the report names WO-999-other.md, the order is WO-001")


def evidence_file(folder, name, head, exit_code=0, timed_out=False, dirty=False, label="AC-1", sha256="written", drop=(), **override):
    """An evidence_record.py file with every field `run` writes, written directly so the case does not depend on git.
    With sha256="written" its artifact out.txt is written next to it and hashed. drop: field names to leave out; override: field
    values to replace."""
    if sha256 == "written":
        (folder / "out.txt").write_bytes(b"x")
        sha256 = hashlib.sha256(b"x").hexdigest()
    record = {"schema": 1, "label": label, "command": ["python", "-c", "0"], "cwd": str(folder), "started": "2026-01-02T10:00:00+08:00",
              "finished": "2026-01-02T10:00:01+08:00", "seconds": 1.0, "exit_code": exit_code, "timed_out": timed_out,
              "git": {"head": head, "dirty": dirty}, "output_lines": 1, "output_tail": ["ok"], "log": None,
              "artifacts": [{"path": "out.txt", "kind": "file", "size": 1, "sha256": sha256}]}
    record.update(override)
    for key in drop:
        record.pop(key, None)
    (folder / name).write_text(json.dumps(record), encoding="utf-8")


def test_evidence_match(tmp):
    """v0.11: --match --evidence-dir reads the evidence records an AUTO PASS row names. Without the flag nothing changes."""
    typed = TYPED_ORDER.format(base="abc123")
    order = tmp / "WO-001-parser.md"
    order.write_bytes(typed.encode("utf-8"))
    sha = hashlib.sha256(typed.encode("utf-8")).hexdigest()
    head = "0123456789abcdef0123456789abcdef01234567"
    folder = tmp / "records"
    folder.mkdir()
    good = list(ACCEPTANCE.values())

    strict_text = typed.replace("GOVERNANCE     = Standard", "GOVERNANCE     = Strict")
    if strict_text == typed:
        failures.append("TYPED_ORDER has no `GOVERNANCE     = Standard` line; update test_evidence_match")
    strict = tmp / "WO-001-strict.md"
    strict.write_bytes(strict_text.encode("utf-8"))
    strict_sha = hashlib.sha256(strict_text.encode("utf-8")).hexdigest()
    strict_log = tmp / "strict_log.md"
    strict_log.write_text(f"# DIRECTOR_LOG\n2026-01-02 10:00 +08:00 | DISPATCH WO-001-strict rev=1 sha={strict_sha}\n", encoding="utf-8")

    def ev(name, code, record=None, says=None, lacks=None, rows=good, title=f"/ c / {head} / yes", extra="", result="PASS",
           against=order, digest=sha):
        """A Strict order is matched with --candidate and --dispatch-log too (v0.13), so each case shows one fault."""
        if record is not None:
            evidence_file(folder, "e.json", **{"head": head, **record})
        report = tmp / f"{name}.md"
        text = match_report(rows, result, digest).replace("RESULT:", extra + "RESULT:", 1)
        if title is None:  # a title line that does not name HEAD at all
            text = text.replace(" / HEAD / WORKTREE_CLEAN: T / a / sonnet / b / c / d0d0d0d / yes", " / WORKTREE_CLEAN: T / a / sonnet / b / c / yes", 1)
        else:
            text = text.replace("/ c / d0d0d0d / yes", title, 1)
        report.write_text(text, encoding="utf-8")
        bind = ("--candidate", head, "--dispatch-log", strict_log) if against == strict else ()
        expect(name, "gate_check.py", code, "--match", report, against, "--evidence-dir", folder, *bind, says=says, lacks=lacks)
        return report

    ev("ev_ok", 0, {}, "OK   match", "  ~ ")  # AC-2 (REVIEW) names out.txt: only AUTO rows are read
    ev("ev_short_head", 0, {}, "OK   match", title=f"/ c / {head[:7]} / yes")
    ev("ev_exit", 1, {"exit_code": 3}, "AC-1: e.json: the command exited 3")
    ev("ev_timeout", 1, {"exit_code": 124, "timed_out": True}, "(timed out)")
    ev("ev_artifact", 1, {"sha256": None}, "artifact missing when recorded: out.txt")
    ev("ev_head", 1, {"head": "fedcba9876543210fedcba9876543210fedcba98"}, "record again after the last commit")
    ev("ev_notes", 0, {"dirty": True, "label": "AC-9"},
       ["~ AC-1: e.json: recorded with uncommitted changes", "~ AC-1: e.json: its label is AC-9"])
    ev("ev_no_json", 1, {}, "AC-1: PASS names no evidence_record file (.json) in 證據",
       rows=["| AC-1 | exit 0 | log.txt | PASS |"] + good[1:])
    ev("ev_missing_record", 1, {}, "AC-1: gone.json is not an evidence_record file",
       rows=["| AC-1 | exit 0 | gone.json | PASS |"] + good[1:])
    ev("ev_head_line", 0, {}, "OK   match", "  ~ ", title=None, extra=f"HEAD: {head}\n")
    ev("ev_branch_slash", 0, {}, "OK   match", "  ~ ", title=f"/ feature/x / c / {head} / yes")
    ev("ev_no_head", 0, {"head": "fedcba9876543210fedcba9876543210fedcba98"},
       ["~ HEAD: pending is not a commit hash (7 to 40 hex digits)", "~ HEAD: the report names no commit hash (see above); evidence HEAD not compared"],
       title="/ c / pending / yes")
    # v0.12: a record must have every field `run` writes; HEAD must be a commit hash; Strict fails on dirty / other label
    (folder / "e.json").write_text('{"exit_code": 0}', encoding="utf-8")
    ev("ev_shell_record", 1, None, "AC-1: e.json is not an evidence_record file: missing field command (+1 more)")
    ev("ev_wrong_type", 1, {"exit_code": "0"}, "is not an evidence_record file: field exit_code is not int")
    ev("ev_bool_exit", 1, {"exit_code": False}, "field exit_code is not int")
    ev("ev_bad_record_head", 1, {"head": "not-a-commit"}, "git.head is not a commit hash: not-a-commit")
    ev("ev_bad_artifact_entry", 1, {"artifacts": [{"kind": "file"}]}, "artifact 1 has no path or sha256")
    ev("ev_artifacts_not_list", 1, {"artifacts": 42}, "is not an evidence_record file: field artifacts is not list")
    ev("ev_legacy_record", 0, {"drop": ("schema", "cwd", "started", "finished")},
       ["OK   match", "~ AC-1: e.json: legacy record without `schema`; only command, exit_code and artifacts checked"])
    ev("ev_legacy_still_needs_core", 1, {"drop": ("schema", "artifacts")}, "is not an evidence_record file: missing field artifacts")
    ev("ev_record_without_git_head", 0, {"head": None}, "~ AC-1: e.json: recorded with no git HEAD; not compared with the report's")
    ev("ev_bad_head_standard_notes", 0, {}, ["OK   match", "~ HEAD: not-a-commit is not a commit hash (7 to 40 hex digits)"],
       title="/ c / not-a-commit / yes")
    ev("ev_bad_head_strict_fails", 1, {}, "- HEAD: not-a-commit is not a commit hash (7 to 40 hex digits)",
       title="/ c / not-a-commit / yes", against=strict, digest=strict_sha)
    ev("ev_strict_dirty_fails", 1, {"dirty": True}, "- AC-1: e.json: recorded with uncommitted changes; Strict: commit, then record again",
       against=strict, digest=strict_sha)
    ev("ev_strict_other_label_fails", 1, {"label": "AC-9"}, "- AC-1: e.json: its label is AC-9, not AC-1; Strict: record once per AC, or label both",
       against=strict, digest=strict_sha)
    ev("ev_strict_label_lists_both", 0, {"label": "AC-1 AC-2"}, "OK   match", against=strict, digest=strict_sha)
    ev("ev_strict_clean_ok", 0, {}, "OK   match", lacks="  - ", against=strict, digest=strict_sha)
    # v0.13 batch 3: one HEAD / ORDER line (G02b); Strict reads only schema 1 and git.dirty false (G03 G03a);
    # the artifacts a record lists are hashed again (G03c)
    two_heads = ev("ev_two_heads", 1, {}, "- HEAD: the report names HEAD 2 times (0123456789ab, eeeeeeeeeeee); write it once",
                   extra=f"HEAD: {'e' * 40}\n")
    expect("--report fails a report that names HEAD twice", "gate_check.py", 1, "--report", two_heads,
           says="- HEAD: the report names HEAD 2 times")
    ev("ev_two_order_lines", 1, {}, "- ORDER: the report has 2 ORDER: lines; write it once",
       extra="ORDER: WO-001-parser.md REVISION 1\n")
    ev("ev_schema_strict", 1, {"schema": 99}, "- AC-1: e.json: schema 99 is not one this tool reads (1); Strict",
       against=strict, digest=strict_sha)
    ev("ev_schema_standard", 0, {"schema": 99}, ["OK   match", "~ AC-1: e.json: schema 99 is not one this tool reads (1)"])
    ev("ev_dirty_null_strict", 1, {"dirty": None}, "- AC-1: e.json: git.dirty is null, not false",
       against=strict, digest=strict_sha)
    ev("ev_dirty_null_standard", 0, {"dirty": None}, "OK   match", lacks="git.dirty")
    ev("ev_artifact_changed_strict", 1, {"sha256": "ab" * 32},
       "- AC-1: e.json: artifact changed since it was recorded: out.txt; Strict", against=strict, digest=strict_sha)
    ev("ev_artifact_changed_standard", 0, {"sha256": "ab" * 32},
       ["OK   match", "~ AC-1: e.json: artifact changed since it was recorded: out.txt"])
    gone = str(tmp / "never-written.txt")
    ev("ev_artifact_gone_strict", 1, {"artifacts": [{"path": gone, "kind": "file", "size": 1, "sha256": "ab" * 32}]},
       f"- AC-1: e.json: artifact gone since it was recorded: {gone}", against=strict, digest=strict_sha)
    expect("--report notes a HEAD that is not a commit hash", "gate_check.py", 0, "--report", tmp / "ev_bad_head_standard_notes.md",
           says="~ HEAD: not-a-commit is not a commit hash")
    ev("ev_fail_row_unchecked", 0, {"exit_code": 3}, "OK   match", rows=["| AC-1 | exit 3 | e.json | FAIL |"] + good[1:],
       result="FAIL")
    plain = ev("ev_flag_off_base", 1, {"exit_code": 3})
    expect("without --evidence-dir a failed record is not read", "gate_check.py", 0, "--match", plain, order, says="OK   match")
    expect("--evidence-dir needs --match", "gate_check.py", 2, "--report", plain, "--evidence-dir", folder)
    expect("--evidence-dir folder missing", "gate_check.py", 2, "--match", plain, order, "--evidence-dir", tmp / "nope")


def test_candidate(tmp):
    """v0.13 (A01 A02 A04): a Strict --match is bound to the candidate commit. With --candidate, --dispatch-log and
    --evidence-dir and a full-hash report it passes; leaving out one piece is exactly one problem for Strict and nothing
    to fail for Standard. A candidate the report or record does not match fails in both."""
    global total
    head = "0123456789abcdef0123456789abcdef01234567"
    other = "f" * 40
    for governance in ("Strict", "Standard"):
        text = TYPED_ORDER.format(base="abc123").replace("GOVERNANCE     = Standard", f"GOVERNANCE     = {governance}")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

        def case(name, record=None, title=head, drop=(), candidate=head):
            folder = tmp / "candidate" / governance / name
            folder.mkdir(parents=True)
            order = folder / "WO-001-parser.md"
            order.write_bytes(text.encode("utf-8"))
            evidence_file(folder, "e.json", **{"head": head, **(record or {})})
            (folder / "log.md").write_text(f"# DIRECTOR_LOG\n2026-01-02 10:00 +08:00 | DISPATCH WO-001 rev=1 sha={digest}\n",
                                           encoding="utf-8")
            report_text = match_report(list(ACCEPTANCE.values()), "PARTIAL", digest)
            if title is None:
                report_text = report_text.replace(" / HEAD / WORKTREE_CLEAN: T / a / sonnet / b / c / d0d0d0d / yes",
                                                  " / WORKTREE_CLEAN: T / a / sonnet / b / c / yes", 1)
            else:
                report_text = report_text.replace("/ c / d0d0d0d / yes", f"/ c / {title} / yes", 1)
            (folder / "report.md").write_text(report_text, encoding="utf-8")
            flags = {"--evidence-dir": folder, "--dispatch-log": folder / "log.md", "--candidate": candidate}
            args = [part for flag, value in flags.items() if flag not in drop for part in (flag, value)]
            code, out = run("gate_check.py", "--match", folder / "report.md", order, *args)
            return code, [line for line in out.splitlines() if line.startswith("  - ")], out

        def check(name, want, **kw):
            """want: the one problem Strict must report; Standard must pass. None: both pass with no problem."""
            global total
            total += 1
            code, problems, out = case(name, **kw)
            if want is None or governance == "Standard":
                ok = code == 0 and not problems
            else:
                ok = code == 1 and len(problems) == 1 and want in problems[0]
            if not ok:
                failures.append(f"candidate {governance} {name}: exit {code}, problems {problems}: {out.strip()[-300:]}")

        check("bound", None)
        check("no_dispatch_log", "DISPATCH: Strict order checked without --dispatch-log", drop=("--dispatch-log",))
        check("no_evidence_dir", "EVIDENCE: Strict order checked without --evidence-dir; the records of AUTO PASS rows AC-1",
              drop=("--evidence-dir",))
        check("no_candidate", "CANDIDATE: a Strict match needs --candidate", drop=("--candidate",))
        check("legacy_record", "AC-1: e.json: legacy record without `schema`; Strict: record again",
              record={"drop": ("schema", "cwd", "started", "finished")})
        check("record_without_head", "AC-1: e.json: recorded with no git HEAD; Strict: record again", record={"head": None})
        check("short_report_head", "HEAD: a Strict report names the full commit (40 hex digits), got 0123456", title=head[:7])
        check("no_report_head", "HEAD: a Strict report names the full commit (40 hex digits), got none", title=None)
        for name, kw, want in (("other_candidate", {"candidate": other}, "the report names 0123456789ab, the candidate is ffffffffffff"),
                               ("record_not_at_candidate", {"record": {"head": other}},
                                "recorded at HEAD ffffffffffff, the candidate is 0123456789ab")):
            total += 1
            code, problems, out = case(name, **kw)
            if code != 1 or not any(want in p for p in problems):
                failures.append(f"candidate {governance} {name}: exit {code}, problems {problems}: {out.strip()[-300:]}")
    expect("--candidate needs the full hash", "gate_check.py", 2, "--match", tmp / "candidate" / "Strict" / "bound" / "report.md",
           tmp / "candidate" / "Strict" / "bound" / "WO-001-parser.md", "--candidate", head[:7])
    expect("--candidate needs --match", "gate_check.py", 2, "--report", tmp / "candidate" / "Strict" / "bound" / "report.md",
           "--candidate", head)


def test_one_fault(tmp):
    """v0.12: one fault at a time in an otherwise complete record, run the way an outside audit runs gate_check
    (--order, --report, --match and --evidence-dir together). The record starts as what `evidence_record.py run` wrote,
    so no case stops early at a missing field. Strict: each fault alone exits 1 with that one problem. Standard: a record
    from another commit still fails; uncommitted changes, another AC's label and a report HEAD that is not a hash are notes."""
    global total
    base = tmp / "one_fault"
    work = base / "work"
    work.mkdir(parents=True)
    expect("one fault: recording the base record", "evidence_record.py", 0, "run", "--out-dir", base / "out", "--label", "AC-1",
           "--cwd", work, "--", sys.executable, "-c", "print('ok')", says="exit=0")
    written = json.loads(next((base / "out").glob("*.json")).read_text(encoding="utf-8"))
    head = "0123456789abcdef0123456789abcdef01234567"
    written["git"] = {"head": head, "dirty": False}  # run outside git leaves both None; set them, change nothing else
    faults = {
        "clean": ({}, head, None),
        "report_head_not_hash": ({}, "not-a-commit", "HEAD: not-a-commit is not a commit hash"),
        "record_from_other_commit": ({"git": {"head": "f" * 40, "dirty": False}}, head, "recorded at HEAD ffffffffffff"),
        "dirty": ({"git": {"head": head, "dirty": True}}, head, "recorded with uncommitted changes"),
        "other_label": ({"label": "AC-OTHER"}, head, "its label is AC-OTHER, not AC-1"),
    }
    fails_in_standard = {"record_from_other_commit"}
    for governance in ("Strict", "Standard"):
        text = TYPED_ORDER.format(base="a" * 40).replace("GOVERNANCE     = Standard", f"GOVERNANCE     = {governance}")
        for case, (change, report_head, problem) in faults.items():
            folder = base / governance / case
            folder.mkdir(parents=True)
            order = folder / "WO-001-parser.md"
            order.write_bytes(text.encode("utf-8"))
            (folder / "e.json").write_text(json.dumps({**written, **change}), encoding="utf-8")
            report = folder / "report.md"
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            report.write_text(match_report(list(ACCEPTANCE.values()), "PARTIAL", digest)
                              .replace("/ c / d0d0d0d / yes", f"/ c / {report_head} / yes", 1), encoding="utf-8")
            (folder / "log.md").write_text(f"# DIRECTOR_LOG\n2026-01-02 10:00 +08:00 | DISPATCH WO-001 rev=1 sha={digest}\n",
                                           encoding="utf-8")
            code, out = run("gate_check.py", "--order", order, "--report", report, "--match", report, order, "--evidence-dir", folder,
                            "--dispatch-log", folder / "log.md", "--candidate", head)
            problems = [line for line in out.splitlines() if line.startswith("  - ")]
            notes = [line for line in out.splitlines() if line.startswith("  ~ ") and problem and problem in line]
            if problem is None:
                ok = code == 0 and not problems
            elif governance == "Strict" or case in fails_in_standard:
                ok = code == 1 and len(problems) == 1 and problem in problems[0]
            else:
                ok = code == 0 and not problems and notes
            total += 1
            if not ok:
                failures.append(f"one fault {governance} {case}: exit {code}, problems {problems}, notes {notes}: {out.strip()[-300:]}")


def test_metrics(tmp):
    """metrics_report.py counts PURPOSE.md's numbers from the Director's files; a missing source is UNKNOWN, not 0."""
    root = tmp / "metrics" / "DIRECTOR"
    for folder in ("orders", "reviews"):
        (root / folder).mkdir(parents=True)
    typed = TYPED_ORDER.format(base="abc123")
    (root / "orders" / "WO-001.md").write_text(typed.replace("REVISION       = 1", "REVISION       = 3"), encoding="utf-8")
    (root / "orders" / "WO-002.md").write_text(typed.replace("# WO-001", "# WO-002"), encoding="utf-8")
    (root / "reviews" / "v1.md").write_text(VERDICT.format(verdict="FAIL", step="CONTINUE_SAME_WORKER"), encoding="utf-8")
    (root / "reviews" / "v2.md").write_text(VERDICT.format(verdict="PASS", step="ACCEPT_AND_CLOSE"), encoding="utf-8")
    (root / "DECISION_REGISTER.md").write_text("# DECISION_REGISTER\n## A. 決策\n| ID | 決定 |\n|---|---|\n| DD-1 | use json |\n",
                                               encoding="utf-8")  # has ## A but no 下一步: not a verdict
    (root / "DIRECTOR_LOG.md").write_text(
        "# DIRECTOR_LOG\n"
        "2025-12-30 10:00 +08:00 | RESUMED WO-000 at x; next=y; waiting=NONE\n"
        "2026-01-02 10:00 +08:00 | RESUMED WO-001 at AC-1; next=run; waiting=NONE; redo=NONE\n"
        "2026-01-03 10:00 +08:00 | RESUMED WO-001 at AC-2; next=run; waiting=NONE; redo=capture.mp4\n"
        "2026-01-02 11:00 +08:00 | BOOTSTRAP_STUCK 第 4 步 tool missing\n"
        "2026-01-02 12:00 +08:00 | SPEC_REVIEW WO-001 tokens=1200 issues=0/1/2 adopted=2\n", encoding="utf-8")
    (root / "PO_PENDING.md").write_text("ID: OD-1\nCREATED: 2026-01-06 09:00\nSTATUS: open\n\nID: OD-2\nCREATED: 2025-12-01 09:00\n"
                                        "STATUS: closed\n\nID: ACT-1\nSTATUS: answered\n", encoding="utf-8")
    (root / "orders" / "WO-009-old.md").write_text("# WO-009 old style\nGOVERNANCE = Strict\n", encoding="utf-8")
    (root / "orders" / "WO-010.md").write_text(typed.replace("# WO-001", "# WO-010").replace("ISSUED_BY      = director 2026-01-02 10:00",
                                                                                            "ISSUED_BY      = director"), encoding="utf-8")
    expect("metrics counts", "metrics_report.py", 0, "--director", root,
           says=["| 返工次數 | 1（CONTINUE_SAME_WORKER 1、SWITCH_TO_OTHER_WORKER 0）；工單改版 2 次（1 份工單） | 裁決 2 份、工單 3 份 |",
                 "- 像工單但沒有 `ISSUED_BY =` 行，返工和改版都沒算到：1 份：" + str(pathlib.Path("orders", "WO-009-old.md")),
                 "| 中斷後遺失的工作 | 1 / 恢復 3 次；1 次沒寫 redo= |", "| PO 介入次數 | 3（ACT 1、OD 2），還在等 PO 1；UNDATED 1（沒寫 CREATED） | PO_PENDING.md |",
                 "| 新專案導入卡住 | 1 |", "1 次，tokens 合計 1200，採用的問題 2 個", "UNKNOWN：跑 `usage_report.py`"])
    expect("metrics --since drops older lines", "metrics_report.py", 0, "--director", root, "--since", "2026-01-01",
           says=["| 中斷後遺失的工作 | 1 / 恢復 2 次 |", "範圍：2026-01-01 起"])
    expect("metrics --since drops older orders", "metrics_report.py", 0, "--director", root, "--since", "2026-01-05",
           says=["工單改版 0 次（0 份工單）", "| 新專案導入卡住 | 0 |", "0 次", "| 中斷後遺失的工作 | UNKNOWN：DIRECTOR_LOG 沒有 RESUMED 行",
                 "照 --since 略過：2 份", "- 工單沒有日期，照算：1 份",
                 "| PO 介入次數 | 2（ACT 1、OD 1），還在等 PO 1；UNDATED 1（沒寫 CREATED，照算）；--since 前 1 項沒算 |"])
    elsewhere = tmp / "metrics" / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "DECISIONS_FOR_OWNER.md").write_text(
        "| ID | 問題 | 狀態 |\n|---|---|---|\n| Q-1 | a | 等待 |\n| Q-2 | b | 已決 |\n", encoding="utf-8")
    po_cfg = elsewhere / "po.json"
    po_cfg.write_text(json.dumps({"schema_version": 1, "po_pending_files": ["DECISIONS_FOR_OWNER.md"],
                                  "po_item_pattern": r"^\|\s*(Q)-\d+", "po_open_pattern": r"等待"}), encoding="utf-8")
    expect("metrics reads PO entries from the files the config names", "metrics_report.py", 0, "--director", elsewhere,
           "--config", po_cfg, says="| PO 介入次數 | 2（Q 2），還在等 PO 1；UNDATED 2（沒寫 CREATED） | DECISIONS_FOR_OWNER.md |")
    (elsewhere / "director_work.json").write_text(po_cfg.read_text(encoding="utf-8"), encoding="utf-8")
    expect("metrics finds director_work.json in DIRECTOR", "metrics_report.py", 0, "--director", elsewhere, says="2（Q 2）")
    no_po = tmp / "metrics" / "no_po"
    no_po.mkdir()
    expect("metrics without a PO file named in the config", "metrics_report.py", 0, "--director", no_po,
           "--config", po_cfg, says="UNKNOWN：沒有 DECISIONS_FOR_OWNER.md")
    po_cfg.write_text(json.dumps({"schema_version": 1, "po_item_pattern": "(unclosed"}), encoding="utf-8")
    expect("metrics refuses a broken PO pattern", "metrics_report.py", 1, "--director", elsewhere, "--config", po_cfg,
           says="FAIL config")
    po_cfg.write_text(json.dumps({"schema_version": 9}), encoding="utf-8")
    expect("metrics refuses an unknown config version", "metrics_report.py", 1, "--director", elsewhere, "--config", po_cfg,
           says="schema_version 9 is not 1")
    no_verdict = tmp / "metrics" / "no_verdict"
    shutil.copytree(root / "orders", no_verdict / "orders")
    expect("metrics with orders but no verdict says UNKNOWN, not 0", "metrics_report.py", 0, "--director", no_verdict,
           says="| 返工次數 | UNKNOWN：找不到裁決；工單改版 2 次（1 份工單） | 裁決 0 份、工單 3 份 |", lacks="| 返工次數 | 0")
    empty = tmp / "metrics" / "empty"
    empty.mkdir()
    expect("metrics with nothing recorded", "metrics_report.py", 0, "--director", empty,
           says=["UNKNOWN：找不到裁決；工單改版 UNKNOWN：找不到工單", "UNKNOWN：沒有 DIRECTOR_LOG.md", "UNKNOWN：沒有 PO_PENDING.md",
                 "沒有 `ISSUED_BY =` 行，返工和改版都沒算到：0 份"], lacks="| 0 |")
    expect("metrics bad --since", "metrics_report.py", 2, "--director", root, "--since", "Jan 1")
    expect("metrics missing folder", "metrics_report.py", 1, "--director", tmp / "metrics" / "nope", says="folder not found")


def test_trace(tmp):
    """trace_report.py joins orders, reports and verdicts; flags orders without TRACES_TO and IDs off the pattern."""
    root = tmp / "trace"
    for folder in ("orders", "reports", "reviews"):
        (root / folder).mkdir(parents=True)
    typed = TYPED_ORDER.format(base="abc123")
    (root / "orders" / "WO-001-parser.md").write_text(typed, encoding="utf-8")
    (root / "orders" / "WO-002-ui.md").write_text(ORDER.format(base="abc123").replace("# WO-001", "# WO-002"), encoding="utf-8")
    (root / "orders" / "WO-003-api.md").write_text(typed.replace("# WO-001", "# WO-003").replace("DD-1", "REQ7"), encoding="utf-8")
    (root / "reports" / "r1.md").write_text(match_report(list(ACCEPTANCE.values()), "PARTIAL"), encoding="utf-8")
    (root / "reports" / "stray.md").write_text(REPORT.format(result="PASS", tests="t", scope="PASS", evidence="e"), encoding="utf-8")
    (root / "reviews" / "v1.md").write_text(VERDICT.format(verdict="PASS_WITH_WARNINGS", step="ACCEPT_AND_CLOSE")
                                            .replace("# GATE VERDICT", "# GATE VERDICT WO-001"), encoding="utf-8")
    (root / "orders" / "WO-004-old.md").write_text("# WO-004 old style\nGOVERNANCE = Strict\n", encoding="utf-8")
    (root / "reports" / "notes.md").write_text("# notes\n", encoding="utf-8")
    (root / "reviews" / "draft.md").write_text("# draft verdict\n", encoding="utf-8")
    config = root / "director_work.json"
    config.write_text(json.dumps({"schema_version": 1, "trace_id_pattern": r"^(DD|OD)-\d+$"}), encoding="utf-8")
    base = ("--orders", root / "orders", "--reports", root / "reports")
    expect("trace table", "trace_report.py", 0, *base, "--verdicts", root / "reviews", "--config", config,
           says=["| DD-1 | WO-001 | AC-2 | REVIEW | READY_FOR_REVIEW | out.txt | PASS_WITH_WARNINGS（未標版次） |",
                 "| DD-1 | WO-001 | AC-1 | AUTO | PASS | e.json | PASS_WITH_WARNINGS（未標版次） |",
                 "## 裁決對不到報告版次\n- 無",
                 "| REQ7 | WO-003 | AC-1 | AUTO | 沒有報告 |", "## 沒有 TRACES_TO 的工單\n- WO-002",
                 "## 編號格式不符 trace_id_pattern\n- WO-003: REQ7", "stray.md", "沒計入的檔案 3 份，列在文末。",
                 "工單資料夾裡沒有 `ISSUED_BY =` 行的檔案（沒算成工單）：1 份\n- ", "WO-004-old.md",
                 "報告資料夾裡沒有 `TASK_ID` 行的檔案（沒算成報告）：1 份\n- ", "notes.md",
                 "裁決資料夾裡沒有 `## A` 的檔案（沒算成裁決）：1 份\n- ", "draft.md"])
    expect("trace without a pattern accepts any ID", "trace_report.py", 0, *base, says="## 編號格式不符 trace_id_pattern\n- 無")
    many = tmp / "trace_many"
    (many / "reports").mkdir(parents=True)
    shutil.copytree(root / "orders", many / "orders")
    passed = match_report(list(ACCEPTANCE.values()), "PARTIAL")
    failed = passed.replace("| AC-1 | exit 0 | e.json | PASS |", "| AC-1 | exit 1 | e.json | FAIL |")
    (many / "reports" / "report-9.md").write_text(passed, encoding="utf-8")
    (many / "reports" / "report-10.md").write_text(failed.replace("REVISION 1", "REVISION 2"), encoding="utf-8")
    trace_many = ("--orders", many / "orders", "--reports", many / "reports")
    expect("trace picks the higher order revision, not the last file name", "trace_report.py", 0, *trace_many,
           says=["| DD-1 | WO-001 | AC-1 | AUTO | FAIL | e.json |", "報告 2 份對到工單",
                 f"- WO-001：選 {many / 'reports' / 'report-10.md'}", "REVISION 2、ATTEMPT —、日期 —、HEAD d0d0d0d ← 選這份",
                 "report-9.md：REVISION 1"])
    (many / "reports" / "report-10.md").write_text(failed.replace("RESULT:", "ATTEMPT: 1\nRESULT:", 1), encoding="utf-8")
    (many / "reports" / "report-9.md").write_text(passed.replace("RESULT:", "ATTEMPT: 2\nRESULT:", 1), encoding="utf-8")
    expect("trace picks the higher ATTEMPT at the same revision", "trace_report.py", 0, *trace_many,
           says=["| DD-1 | WO-001 | AC-1 | AUTO | PASS |", f"選 {many / 'reports' / 'report-9.md'}"])
    (many / "reports" / "report-10.md").write_text(failed.replace("RESULT:", "2026-01-04 09:00\nRESULT:", 1), encoding="utf-8")
    (many / "reports" / "report-9.md").write_text(passed.replace("RESULT:", "2026-01-03 18:00\nRESULT:", 1), encoding="utf-8")
    expect("trace picks the later date when revision and attempt tie", "trace_report.py", 0, *trace_many,
           says=["| DD-1 | WO-001 | AC-1 | AUTO | FAIL |", "日期 2026-01-04 09:00"])
    (many / "reports" / "report-10.md").write_text(failed, encoding="utf-8")
    (many / "reports" / "report-9.md").write_text(passed, encoding="utf-8")
    expect("trace takes neither of two reports it cannot order", "trace_report.py", 0, *trace_many,
           says=["| DD-1 | WO-001 | AC-1 | AUTO | 多份報告分不出先後 |", "分不出先後，表內兩份都不取"], lacks="← 選這份")
    expect("trace with one report per order lists none", "trace_report.py", 0, *base,
           says="## 同一工單有多份報告（依 REVISION、ATTEMPT、日期選，不看檔名）\n- 無")
    expect("trace with a missing folder", "trace_report.py", 1, "--orders", root / "nope", "--reports", root / "reports",
           says="folder not found")

    # v0.13 (A10): --decisions checks TRACES_TO against the project's requirement files, both ways
    decisions = root / "decisions.md"
    decisions.write_text("# 決定\n\n| ID | 決定 |\n|---|---|\n| DD-1 | parser |\n| **DD-2** | 沒人做 |\n"
                         "| 說明 | DD-3 不是第一欄 |\n", encoding="utf-8")
    expect("trace --decisions lists a TRACES_TO ID found in no decision file", "trace_report.py", 0, *base,
           "--decisions", decisions, says="## TRACES_TO 找不到的編號\n- WO-003: REQ7", lacks="- WO-001: DD-1")
    expect("trace --decisions lists a requirement no order traces", "trace_report.py", 0, *base,
           "--decisions", decisions, says="## 沒有工單的需求\n- DD-2\n", lacks="- DD-3")
    expect("trace without --decisions prints neither section", "trace_report.py", 0, *base,
           lacks=["TRACES_TO 找不到的編號", "沒有工單的需求"])
    expect("trace --decisions with a missing file", "trace_report.py", 1, *base, "--decisions", root / "nope.md",
           says="FAIL file not found")

    # v0.13 (A09): a verdict is shown only next to the report of its own REVISION
    paired = tmp / "trace_verdicts"
    for folder in ("reports", "reviews"):
        (paired / folder).mkdir(parents=True)
    shutil.copytree(root / "orders", paired / "orders")
    (paired / "reports" / "r2.md").write_text(failed.replace("REVISION 1", "REVISION 2"), encoding="utf-8")

    def verdict(name, verdict_word, rev, extra=""):
        text = VERDICT.format(verdict=verdict_word, step="ACCEPT_AND_CLOSE").replace(
            "# GATE VERDICT", f"# GATE VERDICT WO-001\nORDER: WO-001-parser.md REVISION {rev}\n{extra}")
        (paired / "reviews" / name).write_text(text, encoding="utf-8")

    verdict("v1.md", "PASS", 1)
    trace_paired = ("--orders", paired / "orders", "--reports", paired / "reports", "--verdicts", paired / "reviews")
    expect("trace does not put a revision 1 verdict next to a revision 2 report", "trace_report.py", 0, *trace_paired,
           says=["| DD-1 | WO-001 | AC-1 | AUTO | FAIL | e.json | 沒有 REVISION 2 的裁決 |", "## 裁決對不到報告版次\n- WO-001：",
                 "v1.md 是 REVISION 1，表內報告是 REVISION 2"], lacks="| FAIL | e.json | PASS |")
    verdict("v2a.md", "FAIL", 2, "2026-01-05 10:00\n")
    verdict("v2b.md", "REWORK", 2, "2026-01-05 10:00\n")
    expect("trace takes neither of two verdicts it cannot order", "trace_report.py", 0, *trace_paired,
           says="| DD-1 | WO-001 | AC-1 | AUTO | FAIL | e.json | 多份裁決分不出先後 |")
    verdict("v2b.md", "REWORK", 2, "2026-01-06 10:00\nCANDIDATE_HEAD: abcdef0123\n")
    expect("trace never shows a verdict whose CANDIDATE_HEAD is not the report's (G04b), even when it is later",
           "trace_report.py", 0, *trace_paired,
           says=["| DD-1 | WO-001 | AC-1 | AUTO | FAIL | e.json | FAIL |", "v2b.md 的 CANDIDATE_HEAD abcdef0123 不是報告的 HEAD d0d0d0d"],
           lacks="| REWORK |")
    (paired / "reviews" / "v2a.md").rename(paired / "v2a.md")
    expect("trace marks the cell 未配對 when the only verdict of the revision judged another commit (G04b)",
           "trace_report.py", 0, *trace_paired, says="| FAIL | e.json | 未配對：沒有 HEAD d0d0d0d 的裁決 |", lacks="| REWORK |")
    (paired / "v2a.md").rename(paired / "reviews" / "v2a.md")
    verdict("v2b.md", "REWORK", 2, "2026-01-06 10:00\nCANDIDATE_HEAD: d0d0d0d\n")
    expect("trace accepts a CANDIDATE_HEAD equal to the report's HEAD", "trace_report.py", 0, *trace_paired,
           says="| REWORK |", lacks="不是報告的 HEAD")


def test_purpose():
    """PURPOSE.md keeps its 7 aims and 9 cores and says only the PO edits it; every CHANGELOG version answers to it."""
    global total
    root = TOOLS.parent
    text = (root / "PURPOSE.md").read_text(encoding="utf-8")
    for heading, count in (("初衷", 7), ("不能破壞的核心", 9)):
        total += 1
        section = re.search(rf"^## {heading}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        items = re.findall(r"^\d+\. \*\*", section.group(1), re.M) if section else []
        if len(items) != count:
            failures.append(f"PURPOSE.md: ## {heading} should list {count} items, found {len(items)}; only the PO changes it")
    total += 1
    if "只有 PO 能改本檔" not in text:
        failures.append("PURPOSE.md no longer says 只有 PO 能改本檔")
    for version, body in re.findall(r"^## (\d+\.\d+\.\d+)[^\n]*\n(.*?)(?=^## |\Z)", (root / "CHANGELOG.md").read_text(encoding="utf-8"), re.M | re.S):
        total += 1
        if "對齊初衷" not in body:
            failures.append(f"CHANGELOG {version}: no 對齊初衷 line (PURPOSE.md, 改規則前的檢查)")


def test_vocabulary():
    """vocabulary.json is the one source; the docs and templates that spell the lists out must still match it."""
    global total
    vocab = json.loads((TOOLS / "vocabulary.json").read_text(encoding="utf-8"))
    root = TOOLS.parent
    wanted = [("docs/02_work_orders_gates.md", f"`{' / '.join(vocab[key])}`") for key in ("verdicts", "next_steps", "evidence_levels")]
    wanted += [("docs/02_work_orders_gates.md", f"**{word}**") for word in vocab["governance"]]
    wanted += [("templates/TASK_REPORT.md", " | ".join(vocab["report_results"])),
               ("templates/GATE_VERDICT.md", " | ".join(vocab["verdicts"])),
               ("templates/GATE_VERDICT.md", " | ".join(vocab["next_steps"])),
               ("templates/WORK_ORDER.md", " | ".join(vocab["governance"])),
               ("docs/02_work_orders_gates.md", f"`{' / '.join(vocab['ac_worker_statuses'])}`"),
               ("templates/WORK_ORDER.md", " / ".join(vocab["ac_worker_statuses"])),
               ("templates/TASK_REPORT.md", " / ".join(vocab["ac_worker_statuses"]["AUTO"]))]
    wanted += [(path, vocab["ac_worker_statuses"][kind][0]) for kind in ("REVIEW", "PO")
               for path in ("docs/02_work_orders_gates.md", "templates/TASK_REPORT.md")]
    for path, text in wanted:
        total += 1
        if text not in (root / path).read_text(encoding="utf-8"):
            failures.append(f"vocabulary: {path} no longer contains {text!r}; change tools/vocabulary.json and the docs together")


MUST_READ_LIMIT = 12359  # bytes of the 每輪必讀 docs on 2026-11-06 (v0.13 moved pure reasons to docs/10); every round re-reads them, so growth costs quota


def test_must_read_size():
    """The docs README marks 每輪必讀 must stay under MUST_READ_LIMIT; raise it only with a reason in the commit."""
    global total
    total += 1
    root = TOOLS.parent
    files = re.findall(r"^\| `(docs/[^`]+)` \|.*\*\*每輪必讀\*\*", (root / "README.md").read_text(encoding="utf-8"), re.M)
    size = sum(len((root / f).read_bytes().replace(b"\r\n", b"\n")) for f in files)
    if not files or size > MUST_READ_LIMIT:
        failures.append(f"must-read docs {files}: {size} bytes, limit {MUST_READ_LIMIT}; trim them or explain the new limit")


def test_must_read_reasons():
    """v0.13 moved the pure reasons of the must-read docs to docs/10; keep the pointer, the section and the template fields."""
    global total
    root = TOOLS.parent
    ten = (root / "docs/10_lessons_learned.md").read_text(encoding="utf-8")
    wanted = [("docs/10_lessons_learned.md", ten, "## 每輪必讀規則的理由")]
    wanted += [("docs/10_lessons_learned.md", ten, f"### {title}") for title in ("01 角色與權限", "03 溝通", "06 無損續航", "08 安全規則")]
    for doc in ("01_roles_authority", "03_communication", "06_resume_lossless", "08_safety_rules"):
        text = (root / f"docs/{doc}.md").read_text(encoding="utf-8")
        wanted.append((f"docs/{doc}.md", text.split("## 為什麼")[-1], "- 其他理由見 docs/10。"))
    template = (root / "templates/RESUME_STATE.md").read_text(encoding="utf-8")
    for field in ("ORDER:", "SESSION:", "WORKTREE / BRANCH / BASE / HEAD:", "LAST_VERIFIED_CHECKPOINT:", "COMPLETED_STEPS:", "（證據：",
                  "背景程序 PID", "啟動時間", "輸出路徑", "完成判定方式", "自己設的計時器", "等待程序",
                  "PARTIAL_OUTPUTS_TO_DISCARD:", "OPEN_DECISIONS:", "DO_NOT_REPEAT:"):
        wanted.append(("templates/RESUME_STATE.md", template, field))
    for path, text, needle in wanted:
        total += 1
        if needle not in text:
            failures.append(f"must-read reasons: {path} lacks {needle!r}; the must-read docs point to docs/10 and the template for it")


def test_scope(tmp):
    repo = tmp / "repo"
    (repo / "src" / "frozen").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / ".config").mkdir()

    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=repo, check=True, capture_output=True)

    def base_head():
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()

    for path in ("src/a.py", "src/frozen/b.py", "docs/old.md", ".config/app.json", ".config/other.json"):
        (repo / path).write_text("1\n", encoding="utf-8")
    (repo / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    base = base_head()
    order = tmp / "WO.md"
    order.write_text(ORDER.format(base=base), encoding="utf-8")
    check = ("--order", order, "--repo", repo)

    expect("no change passes", "scope_check.py", 0, *check, says="changed=0")
    (repo / "src" / "a.py").write_text("2\n", encoding="utf-8")
    expect("change in scope passes", "scope_check.py", 0, *check, says="changed=1")
    (repo / ".config" / "app.json").write_text("2\n", encoding="utf-8")
    expect("dot folder entry matches", "scope_check.py", 0, *check, says="changed=2")
    (repo / "ignored").mkdir()
    (repo / "ignored" / "x.txt").write_text("x", encoding="utf-8")
    expect("ignored file is not counted", "scope_check.py", 0, *check, says="changed=2")
    git("add", "src/a.py")
    git("commit", "-q", "-m", "work")
    expect("committed change is still seen", "scope_check.py", 0, *check, says="changed=2")
    expect("run from a subfolder", "scope_check.py", 0, "--order", order, "--repo", repo / "src", says="changed=2")

    (repo / "docs" / "new.md").write_text("x", encoding="utf-8")
    expect("untracked outside scope", "scope_check.py", 1, *check, says="outside=1")
    (repo / "docs" / "new.md").unlink()
    (repo / ".config" / "other.json").write_text("2\n", encoding="utf-8")
    expect("sibling of an allowed file is outside", "scope_check.py", 1, *check, says="other.json")
    git("checkout", "-q", "--", ".config/other.json")
    (repo / "src" / "frozen" / "b.py").write_text("2\n", encoding="utf-8")
    expect("forbidden wins over scope", "scope_check.py", 1, *check, says="forbidden=1")
    git("checkout", "-q", "--", "src/frozen/b.py")
    git("mv", "docs/old.md", "src/old.md")
    expect("rename out of an outside path is seen", "scope_check.py", 1, *check, says="docs/old.md")
    git("mv", "src/old.md", "docs/old.md")
    expect("back to clean", "scope_check.py", 0, *check)
    expect("--base overrides", "scope_check.py", 0, *check, "--base", base)
    expect("unknown base", "scope_check.py", 2, *check, "--base", "no-such-ref", says="NOT_RUN")
    expect("order not found", "scope_check.py", 2, "--order", tmp / "nope.md", "--repo", repo, says="NOT_RUN")
    gate_less = tmp / "bare.md"
    gate_less.write_text("BASE_REF = main\n", encoding="utf-8")
    expect("order without lists", "scope_check.py", 2, "--order", gate_less, "--repo", repo, says="NOT_RUN")
    for name, old, new in (("blank line after SCOPE", "SCOPE:\n", "SCOPE:\n\n"), ("star bullets", "- src/**", "* src/**")):
        bad = tmp / f"{name}.md"
        bad.write_text(ORDER.format(base=base).replace(old, new, 1), encoding="utf-8")
        expect(name, "scope_check.py", 2, "--order", bad, "--repo", repo, says="NOT_RUN")
    slash = tmp / "slash.md"
    slash.write_text(ORDER.format(base=base).replace("- src/**", "- /src/**"), encoding="utf-8")
    (repo / "src" / "a.py").write_text("3\n", encoding="utf-8")
    expect("leading slash in a glob", "scope_check.py", 0, "--order", slash, "--repo", repo, says="changed=2")
    git("checkout", "-q", "--", "src/a.py")

    # v0.13 (A05): a FORBIDDEN change that is committed or staged, then undone in the worktree, is still seen
    frozen = repo / "src" / "frozen" / "b.py"
    frozen.write_text("2\n", encoding="utf-8")
    git("add", "src/frozen/b.py")
    expect("staged change with the same worktree change", "scope_check.py", 1, *check, says=["forbidden=1", "staged=1"])
    frozen.write_text("1\n", encoding="utf-8")
    expect("staged change undone in the worktree", "scope_check.py", 1, *check, says=["src/frozen/b.py", "staged=1", "forbidden=1"])
    git("reset", "-q", "--", "src/frozen/b.py")
    frozen.write_text("2\n", encoding="utf-8")
    git("add", "src/frozen/b.py")
    git("commit", "-q", "-m", "frozen")
    frozen.write_text("1\n", encoding="utf-8")
    expect("committed change undone in the worktree", "scope_check.py", 1, *check, says=["src/frozen/b.py", "committed=2", "forbidden=1"])
    git("reset", "-q", "HEAD~1")  # back to the work commit; the worktree already holds the old content
    expect("unstaged-only change", "scope_check.py", 0, *check, says=["STATES: committed=1 staged=0", "untracked=0", "changed=2"])
    (repo / "src" / "frozen" / "new.py").write_text("x", encoding="utf-8")
    expect("untracked-only forbidden file", "scope_check.py", 1, *check, says=["untracked=1", "forbidden=1"])
    (repo / "src" / "frozen" / "new.py").unlink()

    # v0.13 batch 3 (S01): three diffs, base..HEAD, HEAD..index, index..worktree: a staged rename is not unstaged too
    git("mv", "docs/old.md", "docs/older.md")
    expect("a staged rename counts as staged only (S01)", "scope_check.py", 1, *check,
           says=["STATES: committed=1 staged=2 unstaged=1 untracked=0", "outside=2"])
    git("mv", "docs/older.md", "docs/old.md")
    # S03: a file marked skip-worktree or assume-unchanged is hashed against the index
    git("update-index", "--skip-worktree", "src/frozen/b.py")
    frozen.write_text("2\n", encoding="utf-8")
    expect("a skip-worktree file does not hide a forbidden change (S03)", "scope_check.py", 1, *check,
           says=["FORBIDDEN src/frozen/b.py", "FLAGGED: 1 file(s) marked assume-unchanged or skip-worktree; 1 differ", "forbidden=1"])
    frozen.write_text("1\n", encoding="utf-8")
    expect("a marked file that matches the index passes", "scope_check.py", 0, *check, says=["; 0 differ", "changed=2"])
    git("update-index", "--no-skip-worktree", "src/frozen/b.py")
    git("update-index", "--assume-unchanged", "src/frozen/b.py")
    frozen.unlink()
    expect("an assume-unchanged file deleted from the worktree", "scope_check.py", 1, *check, says=["FORBIDDEN src/frozen/b.py", "forbidden=1"])
    git("update-index", "--no-assume-unchanged", "src/frozen/b.py")
    git("checkout", "-q", "--", "src/frozen/b.py")
    # S02: an item in backticks keeps ` #`; without them ` #` starts a comment, and gate_check --order says so
    hashed = repo / "src" / "x #draft.txt"
    hashed.write_text("x", encoding="utf-8")
    for name, item, code, says in (("a backticked FORBIDDEN item keeps ` #` (S02)", "`src/x #draft.txt`  # the draft", 1,
                                    ["FORBIDDEN src/x #draft.txt", "forbidden=1"]),
                                   ("without backticks ` #` starts a comment", "src/x #draft.txt", 0, "forbidden=0")):
        listed = tmp / f"{name[:12]}.md"
        listed.write_text(ORDER.format(base=base).replace("- src/frozen/**\n", "- src/frozen/**\n- " + item + "\n"), encoding="utf-8")
        expect(name, "scope_check.py", code, "--order", listed, "--repo", repo, says=says)
    expect("--order notes an item cut at ` #`", "gate_check.py", 0, "--order", listed,
           says="~ FORBIDDEN: `src/x #draft.txt` is read as `src/x` (` #` starts a comment); if ` #` is part of the name")
    hashed.unlink()

    # v0.13: optional REQUIRED_CHANGES; the changes now are src/a.py and .config/app.json
    expect("no REQUIRED_CHANGES keeps the old last line", "scope_check.py", 0, *check, says="outside=0", lacks="missing=")
    for name, item, code, says in (("required file not changed", "src/parser.py", 1, ["MISSING   src/parser.py", "VIOLATION", "outside=0 missing=1"]),
                                   ("required file changed", "src/a.py", 0, ["PASS", "missing=0"])):
        wanted = tmp / f"{name}.md"
        wanted.write_text(ORDER.format(base=base).replace("- src/frozen/**\n", "- src/frozen/**\nREQUIRED_CHANGES:\n- " + item + "\n"), encoding="utf-8")
        expect(name, "scope_check.py", code, "--order", wanted, "--repo", repo, says=says)


def test_submodule_ignore(tmp):
    """v0.13 batch 3 (S04): `submodule.<name>.ignore=all` does not hide a staged change of a FORBIDDEN submodule."""
    root = tmp / "submodule"
    source, outer = root / "source", root / "outer"
    source.mkdir(parents=True)
    outer.mkdir()

    def git(where, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                               "-c", "protocol.file.allow=always", *args], cwd=where, check=True, capture_output=True,
                              text=True).stdout.strip()

    git(source, "init", "-q", "-b", "main")
    (source / "f.txt").write_text("a", encoding="utf-8")
    git(source, "add", "-A")
    git(source, "commit", "-q", "-m", "a")
    first = git(source, "rev-parse", "HEAD")
    (source / "f.txt").write_text("b", encoding="utf-8")
    git(source, "commit", "-q", "-am", "b")
    git(outer, "init", "-q", "-b", "main")
    git(outer, "submodule", "add", "-q", str(source), "vendor/lib")
    git(outer / "vendor" / "lib", "checkout", "-q", "--detach", first)
    git(outer, "add", "-A")
    git(outer, "commit", "-q", "-m", "base")
    base = git(outer, "rev-parse", "HEAD")
    order = root / "WO.md"
    order.write_text(f"BASE_REF = {base}\nSCOPE:\n- src/**\nFORBIDDEN:\n- vendor/lib\n", encoding="utf-8")
    git(outer / "vendor" / "lib", "checkout", "-q", "main")
    git(outer, "add", "vendor/lib")
    git(outer, "config", "submodule.vendor/lib.ignore", "all")
    git(outer, "config", "diff.ignoreSubmodules", "all")
    expect("submodule ignore=all does not hide a staged forbidden gitlink (S04)", "scope_check.py", 1, "--order", order,
           "--repo", outer, says=["FORBIDDEN vendor/lib", "staged=1", "forbidden=1"])


def test_shared_code():
    global total
    total += 1
    blocks = [re.search(r"^def parse_list.*?(?=^\S)", (TOOLS / tool).read_text(encoding="utf-8"), re.M | re.S)
              for tool in ("gate_check.py", "scope_check.py")]
    if not all(blocks) or blocks[0].group() != blocks[1].group():
        failures.append("parse_list differs between gate_check.py and scope_check.py; keep the two copies identical")


def test_hook_protect(tmp):
    """v0.13: --protect blocks Write / Edit on DIRECTOR/orders/** and DIRECTOR_LOG.md; setup migrates old entries."""
    global total
    director = tmp / "protect" / "DIRECTOR"
    (director / "orders").mkdir(parents=True)
    (director / "orders" / "WO-001-a.md").write_text("x\n", encoding="utf-8")
    (director / "DIRECTOR_LOG.md").write_text("x\n", encoding="utf-8")
    worker = tmp / "protect" / "worker"
    worker.mkdir()

    def guard(name, code, tool, file_path, protect=True, cwd=None):
        global total
        total += 1
        call = {"tool_name": tool, "tool_input": {"file_path": str(file_path), "content": "y"}}
        if cwd:
            call["cwd"] = str(cwd)
        args = ["--protect", str(director)] if protect else []
        done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py"), *args], capture_output=True,
                              encoding="utf-8", input=json.dumps(call))
        if done.returncode != code:
            failures.append(f"hook_guard protect {name}: expected exit {code}, got {done.returncode}: {done.stderr.strip()}")
        elif code == 2 and ("BLOCKED" not in done.stderr or re.search(r"<[^>]*>", done.stderr)):
            failures.append(f"hook_guard protect {name}: message {done.stderr.strip()!r}")

    guard("Write to orders", 2, "Write", director / "orders" / "WO-002-new.md")
    guard("Edit of DIRECTOR_LOG", 2, "Edit", director / "DIRECTOR_LOG.md")
    guard("relative path from the hook cwd", 2, "Write", "../DIRECTOR/orders/WO-001-a.md", cwd=worker)
    guard("backslashes", 2, "Edit", str(director / "orders" / "WO-001-a.md").replace("/", "\\"))
    guard(".. detour", 2, "Write", director / "orders" / ".." / "orders" / "sub" / "x.md")
    if os.name == "nt":
        guard("other case on Windows", 2, "Edit", str(director / "ORDERS" / "wo-001-a.md").upper())
    guard("other file in DIRECTOR", 0, "Write", director / "notes.md")
    guard("folder named like orders", 0, "Write", director / "orders-old" / "x.md")
    guard("worker file", 0, "Edit", worker / "src.py")
    guard("without --protect", 0, "Write", director / "orders" / "WO-001-a.md", protect=False)
    guard("Bash is still checked", 0, "Bash", director / "orders" / "WO-001-a.md")
    total += 1
    done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py"), "--protect", str(director)],
                          capture_output=True, encoding="utf-8", input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push"}}))
    if done.returncode != 2:
        failures.append(f"hook_guard --protect stopped checking Bash: exit {done.returncode}")
    if os.name != "nt":
        print("SKIP hook_guard junction and 8.3 cases: not Windows")
    else:
        link = tmp / "protect" / "dirlink"
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(director)], capture_output=True,
                              encoding="utf-8", errors="replace")
        if made.returncode != 0:
            print(f"SKIP hook_guard junction case: mklink /J failed: {(made.stdout + made.stderr).strip()}")
        else:
            guard("junction to DIRECTOR", 2, "Write", link / "orders" / "WO-009.md")
            os.rmdir(link)  # removes the junction only, not its target
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        longdir = tmp / "protect" / "Long Folder Name For Short"
        longdir.mkdir()
        (longdir / "orders").mkdir()
        n = ctypes.windll.kernel32.GetShortPathNameW(str(longdir), buf, len(buf))
        short = buf.value if n else str(longdir)
        if os.path.normcase(short) == os.path.normcase(str(longdir)):
            print("SKIP hook_guard 8.3 case: no short name on this volume (8.3 names are off)")
        else:
            total += 1
            done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py"), "--protect", str(longdir)],
                                  capture_output=True, encoding="utf-8",
                                  input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": short + "\\orders\\x.md"}}))
            if done.returncode != 2:
                failures.append(f"hook_guard protect 8.3 name {short}: expected exit 2, got {done.returncode}")

    repo = tmp / "protect" / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".git" / "info" / "exclude").write_text(".claude/settings.local.json\n", encoding="utf-8")
    setup = ("--repo", repo, "--only-this")
    expect("plain hook installed", "setup_project_settings.py", 0, *setup, "--hooks", "--apply", says="SET")
    expect("old entry is not enough once protected", "setup_project_settings.py", 1, *setup, "--protect-director", director,
           says=["MISSING", "hooks.PreToolUse matcher"])
    expect("protected entry replaces the old one", "setup_project_settings.py", 0, *setup, "--protect-director", director,
           "--apply", says="SET")
    expect("protected entry kept on rerun", "setup_project_settings.py", 0, *setup, "--protect-director", director, says="OK")
    expect("plain --hooks accepts a protected entry (v0.12 rule)", "setup_project_settings.py", 0, *setup, "--hooks", says="OK")
    entries = json.loads((repo / ".claude" / "settings.local.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    total += 1
    if len(entries) != 1 or entries[0]["matcher"] != "Bash|PowerShell|Write|Edit" or "--protect" not in entries[0]["hooks"][0]["command"]:
        failures.append(f"setup --protect-director: PreToolUse is {entries}")
    expect("the Director's worktree wants the plain hook", "setup_project_settings.py", 1, *setup, "--protect-director", director,
           "--director-worktree", repo, says="hooks.PreToolUse matcher")
    expect("the Director's worktree gets the plain hook back", "setup_project_settings.py", 0, *setup, "--protect-director", director,
           "--director-worktree", repo, "--apply", says="SET")
    entries = json.loads((repo / ".claude" / "settings.local.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    total += 1
    if len(entries) != 1 or entries[0]["matcher"] != "Bash|PowerShell" or "--protect" in entries[0]["hooks"][0]["command"]:
        failures.append(f"setup --director-worktree: PreToolUse is {entries}")


def test_hook(tmp):
    global total
    blocked = ["git push origin main", "git -C . push", "git --no-pager -c a=b push --force", "cd x && git push",
               'bash -c "git push"', "git reset --hard HEAD~1", "git clean -fdx", "git stash", "git stash pop",
               "git stash push -u", "git worktree remove ../wt", "git branch -D old", "taskkill /F /IM python.exe",
               "pkill node", "Stop-Process -Name node", "& 'C:/Program Files/Git/bin/git.exe' push",
               r"C:\Git\bin\git.exe push origin main", "sh -c 'git reset --hard'", 'powershell -Command "git push"',
               'cmd /c "git push"', 'echo "$(git push)"', 'taskkill /F /FI "IMAGENAME eq app.exe"',
               ("Get-Process app | Stop-Process -Force", "PowerShell"),
               (r'& "C:\Program Files\Git\bin\git.exe" push', "PowerShell"), ('iex "git push"', "PowerShell"),
               (r'cd "C:\dir\"; git push', "PowerShell")]
    allowed = ["git status", 'git commit -m "docs: explain the git push rule"', "git stash push -u -m wip-1",
               "git stash apply abc123", "git clean -n", "git reset --soft HEAD~1", "taskkill /PID 1234", "echo push",
               'grep -n "git stash" rules.md', 'git commit -m "note; git reset --hard is forbidden"', "kill -9 1234",
               r'echo "a \" ; git push"', "rm -rf build",  # deleting files is out of scope (tools/README.md)
               ("Stop-Process -Id 1234", "PowerShell"), ("Remove-Item -Recurse build", "PowerShell")]
    for command, code in [(c, 2) for c in blocked] + [(c, 0) for c in allowed]:
        command, tool = command if isinstance(command, tuple) else (command, "Bash")
        total += 1
        done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py")], capture_output=True,
                              encoding="utf-8", input=json.dumps({"tool_name": tool, "tool_input": {"command": command}}))
        if done.returncode != code:
            failures.append(f"hook_guard {command!r}: expected exit {code}, got {done.returncode}: {done.stderr.strip()}")
        elif re.search(r"<[^>]*>", done.stderr):  # a worker quoting it in KNOWN_ISSUES would fail gate_check
            failures.append(f"hook_guard {command!r}: message has a <...> placeholder: {done.stderr.strip()}")
    repo = tmp / "hooked"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".git" / "info" / "exclude").write_text(".claude/settings.local.json\n", encoding="utf-8")
    setup = ("setup_project_settings.py", "--repo", repo, "--only-this", "--hooks")
    expect("hooks missing", *setup[:1], 1, *setup[1:], says="hooks.PreToolUse")
    expect("hooks written", *setup[:1], 0, *setup[1:], "--apply", says="SET")
    expect("hooks kept on rerun", *setup[:1], 0, *setup[1:], "--apply", says="OK")
    data = json.loads((repo / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    total += 1
    if len(data["hooks"]["PreToolUse"]) != 1:
        failures.append("setup_project_settings --hooks added the hook twice")
    future = tmp / "future.json"
    future.write_text('{"schema_version": 2, "window": 250000}', encoding="utf-8")
    expect("unknown config version is refused", *setup[:1], 1, "--repo", repo, "--only-this", "--config", future)
    future.write_text('{"window": 250000}', encoding="utf-8")
    expect("config without a version counts as 1", *setup[:1], 0, "--repo", repo, "--only-this", "--config", future, says="OK")


def test_evidence(tmp):
    out = tmp / "evidence"
    work = tmp / "work"
    work.mkdir()
    art = work / "built.txt"
    py = sys.executable
    make = f"open('built.txt','w').write('same');print('hello')"
    common = ("evidence_record.py", )

    expect("recording a passing command", *common, 0, "run", "--out-dir", out, "--label", "AC-1", "--cwd", work,
           "--artifact", "built.txt", "--", py, "-c", make, says="exit=0")
    records = sorted(out.glob("*.json"))
    record = records[-1]
    data = json.loads(record.read_text(encoding="utf-8"))
    global total
    total += 1
    if data["output_tail"] != ["hello"] or len(data["artifacts"]) != 1 or data["artifacts"][0]["sha256"] is None:
        failures.append(f"record content: {data}")
    expect("verify same", *common, 0, "verify", record, says="EVIDENCE_VERIFY: OK integrity=same test=not-rerun artifacts=1 missing=0 rerun=no")
    expect("verify with the recorded command", *common, 0, "verify", record, "--rerun-recorded",
           says="EVIDENCE_VERIFY: OK integrity=same test=recorded-command-passed artifacts=1 missing=0 rerun=yes source=record",
           lacks="test=passed")
    art.write_text("changed", encoding="utf-8")
    expect("verify sees a changed artifact", *common, 1, "verify", record, says=["artifact changed: ", "MISMATCH integrity=changed"])
    expect("rerun rebuilds it", *common, 0, "verify", record, "--rerun-recorded", says="OK")
    art.unlink()
    expect("verify sees a gone artifact", *common, 1, "verify", record, says=["artifact gone: ", "MISMATCH integrity=same test=not-rerun artifacts=1 missing=1"])
    expect("rerun rebuilds a gone artifact", *common, 0, "verify", record, "--rerun-recorded", says="OK")
    shell = out / "shell.json"
    shell.write_text('{"exit_code": 0}', encoding="utf-8")
    expect("verify refuses a record without the fields", *common, 2, "verify", shell, says=["- missing field command", "- missing field artifacts", "NOT_RUN not an evidence record (2 problems)"])
    legacy = json.loads(record.read_text(encoding="utf-8"))
    for key in ("schema", "cwd", "started", "finished"):
        legacy.pop(key)
    (out / "legacy.json").write_text(json.dumps(legacy), encoding="utf-8")
    expect("verify reads a legacy record with a note", *common, 0, "verify", out / "legacy.json", says=["~ legacy record without `schema`", "OK"])
    # v0.13 (A08): a field of the wrong type is a clean NOT_RUN, never a traceback
    whole = json.loads(record.read_text(encoding="utf-8"))
    for name, change, problem in (("artifacts_int", {"artifacts": 42}, "- field artifacts is not list"),
                                  ("command_int_part", {"command": [1]}, "- command: every part must be a string"),
                                  ("legacy_git_str", {"git": "abc", "schema": None}, "- field git is not dict")):
        broken = {**whole, **change}
        broken = {key: value for key, value in broken.items() if not (key == "schema" and value is None)}
        (out / f"{name}.json").write_text(json.dumps(broken), encoding="utf-8")
        expect(f"verify refuses {name} cleanly", *common, 2, "verify", out / f"{name}.json",
               says=[problem, "EVIDENCE_VERIFY: NOT_RUN not an evidence record"])

    expect("exit code passes through", *common, 7, "run", "--out-dir", out, "--label", "AC-2", "--", py, "-c", "raise SystemExit(7)")
    expect("missing artifact fails", *common, 3, "run", "--out-dir", out, "--label", "AC-3", "--artifact", tmp / "nope", "--", py, "-c", "0", says="missing=1")
    expect("verify never passes a record whose artifact was missing", *common, 1, "verify", next(out.glob("*-AC-3.json")),
           says=["artifact missing when recorded: ", "MISMATCH integrity=same test=not-rerun artifacts=1 missing=1"])
    expect("verify never passes a record whose artifact was missing, even rerun", *common, 1, "verify", next(out.glob("*-AC-3.json")),
           "--rerun-recorded", says=["artifact missing when recorded: ",
                                     "MISMATCH integrity=same test=recorded-command-passed artifacts=1 missing=1 rerun=yes"])
    expect("verify reports a failing command as test=failed", *common, 1, "verify", next(out.glob("*-AC-2.json")),
           says="MISMATCH integrity=same test=failed(recorded exit 7) artifacts=0 missing=0")
    expect("unknown command", *common, 127, "run", "--out-dir", out, "--label", "AC-4", "--", "no-such-command-xyz")
    expect("timeout", *common, 124, "run", "--out-dir", out, "--label", "AC-5", "--timeout", "1", "--", py, "-c", "import time;time.sleep(30)")
    expect("no command", *common, 2, "run", "--out-dir", out, "--label", "AC-6")
    expect("bad record", *common, 2, "verify", tmp / "nope.json", says="NOT_RUN")

    expect("two runs do not overwrite", *common, 0, "run", "--out-dir", out, "--label", "same", "--", py, "-c", "0")
    expect("two runs do not overwrite (2)", *common, 0, "run", "--out-dir", out, "--label", "same", "--", py, "-c", "0")
    total += 1
    if len(list(out.glob("*-same*.json"))) != 2:
        failures.append("two runs in a row should leave two records")

    expect("long output", *common, 0, "run", "--out-dir", out, "--label", "long", "--", py, "-c", "for i in range(200000): print('x'*1000)")
    big = next(out.glob("*-long.json"))
    total += 1
    if big.stat().st_size > 32 * 1024:
        failures.append(f"record too big: {big.stat().st_size} bytes")

    folder = work / "folder"
    (folder / "sub").mkdir(parents=True)
    (folder / "sub" / "a.txt").write_text("a", encoding="utf-8")
    expect("folder artifact", *common, 0, "run", "--out-dir", out, "--label", "dir", "--artifact", folder, "--", py, "-c", "0")
    rec = next(out.glob("*-dir.json"))
    expect("folder verify", *common, 0, "verify", rec, says="OK")
    (folder / "sub" / "b.txt").write_text("b", encoding="utf-8")
    expect("folder sees a new file", *common, 1, "verify", rec, says="MISMATCH")


def with_checks(order, *lines):
    """The order with a `CHECKS:` list of lines placed after its acceptance table."""
    return order.replace("\n- DELIVERABLES", "\nCHECKS:\n" + "".join(f"- {line}\n" for line in lines) + "\n- DELIVERABLES", 1)


def test_order_checks(tmp):
    """v0.13 (A06 A07): the order's CHECKS list. --order checks its form; --match --evidence-dir compares each record's
    command with the approved one (Strict fails, Standard notes); orders without CHECKS give the same result as before."""
    global total
    order = TYPED_ORDER.format(base="abc123")
    good = '"python", "-c", "0"'
    gate(tmp, "checks_good", "order", with_checks(order, f"AC-1: [{good}]"), 0)
    for name, line, says in (("checks_not_json", "AC-1: python -c 0", "CHECKS: `AC-1: python -c 0` is not `AC-n:"),
                             ("checks_empty_array", "AC-1: []", "CHECKS: `AC-1: []` is not"),
                             ("checks_review_ac", f"AC-2: [{good}]", "CHECKS: AC-2 is REVIEW; only an AUTO criterion"),
                             ("checks_unknown_ac", f"AC-9: [{good}]", "CHECKS: AC-9 is not an acceptance criterion")):
        gate(tmp, name, "order", with_checks(order, line), 1, says=says)
    strict = order.replace("GOVERNANCE     = Standard", "GOVERNANCE     = Strict")
    gate(tmp, "checks_strict_missing_noted", "order", strict, 0, says="~ CHECKS: Strict order without an approved check for AUTO AC-1")
    head = "0123456789abcdef0123456789abcdef01234567"
    for governance, text in (("Strict", strict), ("Standard", order)):
        for name, command, code in (("same", ["python", "-c", "0"], 0), ("other", ["python", "-c", "1"], None)):
            folder = tmp / "order_checks" / governance / name
            folder.mkdir(parents=True)
            body = with_checks(text, f"AC-1: [{good}]")
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            (folder / "WO-001-parser.md").write_text(body, encoding="utf-8")
            (folder / "log.md").write_text(f"DISPATCH WO-001 rev=1 sha={digest}\n", encoding="utf-8")
            evidence_file(folder, "e.json", head, command=command)
            (folder / "report.md").write_text(match_report(list(ACCEPTANCE.values()), "PARTIAL", digest).replace(
                "/ c / d0d0d0d / yes", f"/ c / {head} / yes", 1), encoding="utf-8")
            want = "AC-1: e.json: its command is not the order's approved check (CHECKS AC-1)"
            if code is None:
                code, says = (1, f"- {want}; Strict") if governance == "Strict" else (0, f"~ {want}")
            else:
                says = None
            expect(f"match CHECKS {governance} {name}", "gate_check.py", code, "--match", folder / "report.md",
                   folder / "WO-001-parser.md", "--evidence-dir", folder, "--dispatch-log", folder / "log.md",
                   "--candidate", head, says=says, lacks=None if says else "approved check")


def test_trusted_rerun(tmp):
    """v0.13 (A06 A07): `verify --rerun` runs the order's approved check at the candidate commit, in a clean checkout,
    and only after the order matches its DISPATCH line. The record's command is compared, never run."""
    global total
    root = tmp / "trusted"
    repo, out = root / "repo", root / "records"
    repo.mkdir(parents=True)
    py = sys.executable

    def git(*args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=repo, check=True,
                              capture_output=True, text=True).stdout.strip()

    (repo / "check.py").write_text("print('checked')\n", encoding="utf-8")
    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-q", "-m", "a")
    first = git("rev-parse", "HEAD")
    order = root / "WO-001-parser.md"
    body = with_checks(TYPED_ORDER.format(base=first), f"AC-1: {json.dumps([py, 'check.py'])}")
    order.write_text(body, encoding="utf-8")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    log = root / "log.md"
    log.write_text(f"DISPATCH WO-001 rev=1 sha={digest}\n", encoding="utf-8")
    expect("trusted: record the approved check", "evidence_record.py", 0, "run", "--out-dir", out, "--label", "AC-1",
           "--cwd", repo, "--", py, "check.py", says="exit=0")
    record = next(out.glob("*-AC-1.json"))
    data = json.loads(record.read_text(encoding="utf-8"))

    def variant(name, **change):
        path = root / f"{name}.json"
        path.write_text(json.dumps({**data, **change}), encoding="utf-8")
        return path

    def verify(name, code, path, says=None, lacks=None, candidate=None, dispatch=log, **flags):
        args = ["--order", order, "--dispatch-log", dispatch, "--repo", repo, "--candidate", candidate or first]
        expect(f"trusted: {name}", "evidence_record.py", code, "verify", path, "--rerun", *args, says=says, lacks=lacks)

    verify("approved check at the candidate", 0, record,
           says=f"EVIDENCE_VERIFY: OK integrity=same test=passed artifacts=0 missing=0 rerun=yes check=AC-1 source=order candidate={first[:12]}")
    expect("trusted: --rerun alone is refused", "evidence_record.py", 2, "verify", record, "--rerun",
           says="NOT_RUN --rerun runs the order's approved check and needs --order --dispatch-log --repo --candidate")
    expect("trusted: --rerun-recorded never says passed", "evidence_record.py", 0, "verify", record, "--rerun-recorded",
           says="test=recorded-command-passed", lacks="test=passed")
    expect("trusted: --order needs --rerun", "evidence_record.py", 2, "verify", record, "--order", order)
    expect("trusted: --candidate needs 40 hex digits", "evidence_record.py", 2, "verify", record, "--rerun", "--order", order,
           "--dispatch-log", log, "--repo", repo, "--candidate", first[:7])
    marker = root / "tampered.txt"
    tampered = variant("tampered", command=[py, "-c", f"open({str(marker)!r}, 'w').write('ran')"])
    verify("a tampered command is compared, not run", 1, tampered,
           says=["- record command differs from the approved check", "MISMATCH", "test=passed"])
    total += 1
    if marker.exists():
        failures.append("trusted: the tampered command in the record ran")
    verify("a label without an approved check", 2, variant("other_label", label="AC-2"),
           says="NOT_RUN the record's label 'AC-2' names no AC with an approved check")
    for name, line, says in (("another hash", f"DISPATCH WO-001 rev=1 sha={'0' * 64}", "is not the one logged at dispatch"),
                             ("another revision", f"DISPATCH WO-001 rev=2 sha={digest}", "logs rev=2, the order is at REVISION 1"),
                             ("no line", "nothing here", "NOT_RUN no DISPATCH line for WO-001 / WO-001-parser"),
                             # R01b: a quoted DISPATCH with the new hash is data, not a newer dispatch
                             ("quoted line", f"DISPATCH WO-001 rev=1 sha={'0' * 64}\n2026-01-03 10:00 +08:00 | NOTE: rejected "
                              f"proposal `DISPATCH WO-001 rev=1 sha={digest}`", "is not the one logged at dispatch"),
                             ("fenced line", f"DISPATCH WO-001 rev=1 sha={'0' * 64}\n```\nDISPATCH WO-001 rev=1 sha={digest}\n```",
                              "is not the one logged at dispatch")):
        other_log = root / f"log_{name.replace(' ', '_')}.md"
        other_log.write_text(line + "\n", encoding="utf-8")
        verify(f"DISPATCH {name}", 2, record, says=says, dispatch=other_log)
    (repo / "stray.txt").write_text("x\n", encoding="utf-8")
    verify("an untracked file refuses", 2, record, says="has changed or untracked files")
    (repo / "stray.txt").unlink()
    (repo / "notes.md").write_text("b\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "b")
    second = git("rev-parse", "HEAD")
    verify("the repo is not at the candidate", 2, record, says=f"is at {second[:12]}, not the candidate {first[:12]}")
    verify("a record from another commit", 1, record, candidate=second,
           says=[f"- recorded at HEAD {first[:12]}, the candidate is {second[:12]}", "MISMATCH"])


def test_trusted_isolation(tmp):
    """v0.13 (R02-R06): the trusted rerun refuses hidden index flags, replace refs and PATH-chosen programs, runs the
    check in a copy of the candidate's tree, hashes artifacts there, and reads REPO again after the check."""
    global total
    root = tmp / "isolation"
    repo = root / "repo"
    repo.mkdir(parents=True)
    py = sys.executable

    def git(*args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=repo, check=True,
                              capture_output=True, text=True).stdout.strip()

    (repo / "check.py").write_text("from pathlib import Path\nPath('build.txt').write_bytes(b'new\\n')\n"
                                   "raise SystemExit(0 if Path('payload.txt').read_text() == 'A\\n' else 3)\n", encoding="utf-8")
    (repo / "payload.txt").write_text("A\n", encoding="utf-8")
    (repo / ".gitignore").write_text("build.txt\n", encoding="utf-8")
    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-q", "-m", "a")
    first = git("rev-parse", "HEAD")
    git("checkout", "-q", "-b", "other")
    (repo / "payload.txt").write_text("B\n", encoding="utf-8")
    git("commit", "-q", "-am", "b")
    second = git("rev-parse", "HEAD")
    git("checkout", "-q", "main")
    (repo / "build.txt").write_text("stale\n", encoding="utf-8")
    out = root / "records"
    expect("isolation: record the check", "evidence_record.py", 0, "run", "--out-dir", out, "--label", "AC-1", "--cwd", repo,
           "--", py, "check.py", says="exit=0")
    data = json.loads(next(out.glob("*-AC-1.json")).read_text(encoding="utf-8"))
    (repo / "build.txt").write_text("stale\n", encoding="utf-8")

    def sha(text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def case(name, code, says, command=None, artifacts=(), lacks=None):
        command = command or [py, "check.py"]
        folder = root / name
        folder.mkdir()
        body = with_checks(TYPED_ORDER.format(base=first), f"AC-1: {json.dumps(command)}")
        order = folder / "WO-001-parser.md"
        order.write_text(body, encoding="utf-8")
        log = folder / "log.md"
        log.write_text(f"DISPATCH WO-001 rev=1 sha={sha(body)}\n", encoding="utf-8")
        record = folder / "record.json"
        record.write_text(json.dumps({**data, "command": command, "artifacts": list(artifacts)}), encoding="utf-8")
        expect(f"isolation: {name}", "evidence_record.py", code, "verify", record, "--rerun", "--order", order,
               "--dispatch-log", log, "--repo", repo, "--candidate", first, says=says, lacks=lacks)

    def artifact(path, text):
        return {"path": str(path), "kind": "file", "size": len(text), "sha256": sha(text)}

    case("the check runs in a copy of the tree", 0, ["in a new folder holding the 3 committed files", "test=passed"])
    (repo / "payload.txt").write_text("changed\n", encoding="utf-8")
    git("update-index", "--assume-unchanged", "payload.txt")
    case("an assume-unchanged file refuses (R02)", 2, "marks 1 file(s) assume-unchanged or skip-worktree (first: payload.txt)")
    git("update-index", "--no-assume-unchanged", "payload.txt")
    git("update-index", "--skip-worktree", "payload.txt")
    case("a skip-worktree file refuses", 2, "assume-unchanged or skip-worktree")
    git("update-index", "--no-skip-worktree", "payload.txt")
    git("checkout", "-q", "--", "payload.txt")
    git("replace", first, second)
    case("a replace ref refuses (R03)", 2, "has refs/replace/ refs")
    git("replace", "-d", first)
    case("a bare program name refuses (R04)", 2, "a bare name the PATH would resolve", command=["git", "--version"])
    case("a relative program outside the tree refuses", 2, "which is not a file inside the candidate",
         command=["./missing.exe"])
    case("the artifact is hashed in the rerun folder (R05)", 0, "artifacts=1 missing=0",
         artifacts=[artifact(repo / "build.txt", "new\n")])
    case("the artifact made by the rerun differs (R05)", 1,
         ["- artifact changed:", "(in the rerun folder: build.txt)", "MISMATCH integrity=changed"],
         artifacts=[artifact(repo / "build.txt", "stale\n")])
    case("an artifact outside the record's cwd", 1, "- artifact outside the record's cwd, so the rerun cannot make it",
         artifacts=[artifact(root / "elsewhere.txt", "x")])
    late = repo / "late.txt"
    case("a file written into the repo during the check (R06)", 1,
         ["- the repo changed while the check ran:", "has changed or untracked files", "MISMATCH"],
         command=[py, "-c", f"open({str(late)!r}, 'w').write('x')"])
    late.unlink()
    case("HEAD moved during the check (R06)", 1, [f"- the repo changed while the check ran: {repo} is at {second[:12]}", "MISMATCH"],
         command=[py, "-c", f"import subprocess; subprocess.run(['git', '-C', {str(repo)!r}, 'checkout', '-q', 'other'])"])
    git("checkout", "-q", "main")
    total += 1
    if (repo / "build.txt").read_text(encoding="utf-8") != "stale\n":
        failures.append("isolation: the rerun wrote build.txt in REPO instead of the copy")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="director_work_selftest_")).resolve()
    try:
        test_gate(tmp)
        test_acceptance(tmp)
        test_table(tmp)
        test_dispatch(tmp)
        test_revision(tmp)
        test_dispatch_events(tmp)
        test_verdict_binding(tmp)
        test_evidence_match(tmp)
        test_candidate(tmp)
        test_one_fault(tmp)
        test_trace(tmp)
        test_metrics(tmp)
        test_purpose()
        test_scope(tmp)
        test_submodule_ignore(tmp)
        test_shared_code()
        test_vocabulary()
        test_must_read_size()
        test_must_read_reasons()
        test_hook(tmp)
        test_hook_protect(tmp)
        test_evidence(tmp)
        test_order_checks(tmp)
        test_trusted_rerun(tmp)
        test_trusted_isolation(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for failure in failures:
        print(f"FAIL {failure}")
    print(f"selftest: {total - len(failures)}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
