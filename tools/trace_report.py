"""Build the trace table requirement -> work order -> AC -> evidence -> verdict from the files that already exist,
so nobody keeps a separate table up to date. Only reads; prints Markdown.

  trace_report.py --orders DIRECTOR/orders --reports <folder> [--verdicts DIRECTOR/reviews] [--config director_work.json]
                  [--decisions <需求或決定檔.md> ...]

An order is a .md file with ISSUED_BY; it lists what it serves in `TRACES_TO = DD-03, OD-12` (NONE when nothing).
A report (a .md file with TASK_ID) belongs to the order whose file name its `ORDER:` line holds, else to the order
whose ID its TASK_ID starts with; a verdict (a .md file with `## A`) to the order whose ID its title holds. A .md
file in one of the folders that is not what that folder holds is listed by name at the end, never skipped quietly.
When several reports belong to one order, the table uses the newest, never the last by file name: the higher order
REVISION on the `ORDER:` line, then the higher `ATTEMPT: n`, then the later first date (YYYY-MM-DD[ HH:MM]) in the
report. HEAD is listed but cannot order commits without git. When the best two tie on all three, the table takes
neither and says so. Every such order is listed with all its reports, the chosen one marked. A verdict is paired with
the chosen report by the REVISION on its `ORDER:` line: only a verdict for that revision is shown (the later date
first; neither when two tie). With none, a sole verdict that names no revision is shown marked 未標版次, else the cell
says no verdict has that revision. Verdicts for other revisions, and a `CANDIDATE_HEAD:` that is not the report's HEAD,
are never shown in the table (with none left the cell says 未配對) and are listed under 裁決對不到報告版次. `trace_id_pattern` in the config (a regex) flags IDs written in another format;
without it every ID is accepted. `--decisions FILE` (repeatable) reads the IDs (`XX-number`) in the first column of the
Markdown table rows of the project's requirement or decision files: a TRACES_TO ID found in none of them is listed under
TRACES_TO 找不到的編號, and an ID there that no order traces under 沒有工單的需求. Without the flag the output is the
same as before. Exit 0, or 1 when a folder or a --decisions file is missing.

1.3.3 (shadow mode: hints only, nothing blocks; gate_check --match is unchanged). A chosen report whose `ORDER:`
REVISION is not the order's REVISION now, or whose ORDER_SHA256 is not the order's hash, no longer shows its status as
if current: the cell says 過期 / 版次不符 and what the old report wrote, and the order is listed under 報告過期或版次不符.
Rows are one per AC, never TRACES_TO x AC: an order may give each AC its own IDs in an optional 追溯 (traces) column of
its AC table (one row per ID and AC; an AC left empty shows （未指定）); without that column, two or more TRACES_TO IDs
share one row per AC marked （工單層）. With the column, IDs an AC traces that TRACES_TO lacks, and TRACES_TO IDs no AC
traces, are listed at the end.

2.1 (WO-DW-210-W2, shadow: views and hints only; without these flags the output is the same as before):
  --brief BRIEF.md [--director-log DIRECTOR_LOG.md] [--evidence-dir DIR] [--acceptance PO_ACCEPTANCE.json ...]
  adds 初衷卡三欄（每條 B 一列）: for each brief row 有人負責 (the orders that trace it), 這版有驗證紀錄 (the order
  pins the row's fingerprint as the brief has it now, its chosen report is not stale and an AC that traces the row is
  PASS; with --evidence-dir the evidence file must be there) and 你看過這個成品嗎 (the latest whole line
  `PO_PRODUCT_REVIEW <WO-ID> candidate=<sha> outcome=seen|changes|accepted [ref=..] [brief=B-2:<sha256>,..]` in
  --director-log for the report's HEAD, or a bound PO_ACCEPTANCE record for that commit). It also lists
  gate_check's BRIEF_STALE / BRIEF_UNCONFIRMED hints per order, and the log's BRIEF_LOCKED basis (a draft is not it).
  --acceptance alone lists the records that do not bind a reply to one product (UNBOUND_PO_REPLY).
  --decisions: an ID that starts a list item (`- DD-1 用標準函式庫`, as the BRIEF lists the Director's decisions)
  counts as known but is not listed under 沒有工單的需求; a missing ID whose prefix no table in the files has gets a hint
  to add the decision register.
"""
import argparse
import importlib.util
import json
import pathlib
import re
import sys

spec = importlib.util.spec_from_file_location("gate_check", pathlib.Path(__file__).resolve().parent / "gate_check.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)  # reuse its AC table parser; `python -I` does not put this folder on sys.path

CONFIG_VERSION = 1


def files(folder, marker, skipped=None):
    """(path, text) of the .md files in folder holding marker; the others go to skipped, when given."""
    found = []
    for path in sorted(pathlib.Path(folder).rglob("*.md")):
        text = path.read_text(encoding="utf-8-sig")
        if re.search(marker, text, re.M):
            found.append((path, text))
        elif skipped is not None:
            skipped.append(path)
    return found


def first_id(text, fallback):
    m = re.search(r"^#\s+(\S+)", text, re.M)
    return m.group(1) if m else fallback


def owner(orders, text, by_name):
    """The order a report or verdict belongs to, or None."""
    if by_name:
        m = re.search(r"^\s*ORDER\s*:\s*(.+)$", text, re.M)
        hit = [o for o in orders if m and o["path"].name in m.group(1)]
        if hit:
            return hit[-1]
        m = re.search(r"^\s*TASK_ID\b[^:\n]*:\s*([^/\n]+)", text, re.M)
        key = m.group(1).strip() if m else ""
        hit = [o for o in orders if re.match(re.escape(o["id"]) + r"(?![\w])", key)]
    else:
        title = next((line for line in text.splitlines() if line.startswith("#")), "")
        hit = [o for o in orders if re.search(re.escape(o["id"]) + r"(?![\w])", title)]
    return hit[-1] if hit else None


def first_date(text):
    when = re.search(r"(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}))?", text)
    return " ".join(g for g in when.groups() if g) if when else None


def verdict_info(path, text):
    """A verdict's first line of section A, the order REVISION and CANDIDATE_HEAD it names, and its first date."""
    section = re.search(r"^##\s*A\b.*?$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    lines = [line.strip() for line in section.group(1).splitlines() if line.strip()] if section else []
    named = gate.order_line(text)
    head = re.search(r"^\s*CANDIDATE_HEAD\s*:\s*([0-9a-fA-F]{7,40})\b", text, re.M)
    return {"path": path, "verdict": lines[0] if lines else "—", "rev": named[1] if named else None,
            "head": head.group(1).lower() if head else None, "when": first_date(text)}


def pick_verdict(order, problems):
    """The verdict cell for an order: the verdict for the chosen report's REVISION, else a sole verdict that names no
    revision (marked 未標版次). Verdicts for other revisions and a CANDIDATE_HEAD unlike the report's HEAD go to problems
    and are never shown: with none left the cell says 未配對."""
    verdicts, report = order["verdicts"], (order["reports"][0] if order["reports"] and not order["tie"] else None)
    if not verdicts:
        return None
    rev = report["rev"] if report else None
    if rev is None:
        same = verdicts
    else:
        same = [v for v in verdicts if v["rev"] == rev]
        problems += [f"{order['id']}：{v['path']} 是 REVISION {v['rev']}，表內報告是 REVISION {rev}"
                     for v in verdicts if v["rev"] is not None and v["rev"] != rev]
    if not same:
        unmarked = [v for v in verdicts if v["rev"] is None]
        if len(unmarked) == 1:
            return unmarked[0]["verdict"] + "（未標版次）"
        return f"沒有 REVISION {rev} 的裁決"
    head = report["head"].lower() if report and report["head"] and gate.SHA.fullmatch(report["head"]) else None
    other = [v for v in same if v["head"] and head and not (v["head"].startswith(head) or head.startswith(v["head"]))]
    problems += [f"{order['id']}：{v['path']} 的 CANDIDATE_HEAD {v['head'][:12]} 不是報告的 HEAD {head[:12]}"
                 for v in other]
    same = [v for v in same if v not in other]
    if not same:
        return f"未配對：沒有 HEAD {head[:12]} 的裁決"
    same.sort(key=lambda v: (-1 if v["rev"] is None else v["rev"], v["when"] or ""), reverse=True)
    if len(same) > 1 and (same[0]["rev"], same[0]["when"]) == (same[1]["rev"], same[1]["when"]):
        return "多份裁決分不出先後"
    chosen = same[0]
    return chosen["verdict"] + ("（未標版次）" if chosen["rev"] is None else "")


def report_info(path, text):
    """What tells one report for an order from another: order revision, attempt, first date, HEAD; and the order hash
    it claims (ORDER_SHA256), to tell whether the order changed after it."""
    named = gate.order_line(text)
    attempt = re.search(r"^\s*ATTEMPT\s*[:=]\s*(\d+)", text, re.M | re.I)
    sha = re.search(r"^\s*ORDER_SHA256\s*[:=]\s*([0-9a-fA-F]{64})\b", text, re.M)
    info = {"path": path, "table": gate.ac_table(text), "head": gate.report_head_value(text),
            "rev": named[1] if named else None, "attempt": int(attempt.group(1)) if attempt else None,
            "when": first_date(text), "sha": sha.group(1).lower() if sha else None}
    info["key"] = (-1 if info["rev"] is None else info["rev"], -1 if info["attempt"] is None else info["attempt"],
                   info["when"] or "")
    return info


def describe(info):
    return (f"{info['path']}：REVISION {info['rev'] if info['rev'] is not None else '—'}、"
            f"ATTEMPT {info['attempt'] if info['attempt'] is not None else '—'}、日期 {info['when'] or '—'}、"
            f"HEAD {info['head'] or '—'}")


def stale_reason(order, info):
    """Why the chosen report no longer speaks for the order as it is now, or None (1.3.3). A report without an ORDER
    line or ORDER_SHA256 is not judged (older reports)."""
    if info["rev"] is not None and info["rev"] != order["rev"]:
        if info["rev"] < order["rev"]:
            return f"過期：報告是 REVISION {info['rev']}，工單現在是 REVISION {order['rev']}"
        return f"版次不符：報告寫 REVISION {info['rev']}，工單只到 REVISION {order['rev']}"
    if info["sha"] and info["sha"] != order["hash"]:
        return "過期：工單在報告之後改過（ORDER_SHA256 不符）"
    return None


def id_list(value):
    """IDs in a TRACES_TO value or a 追溯 cell; NONE, — and - mean none."""
    return [i for i in re.split(r"[\s,，、]+", value or "") if i and i.upper() != "NONE" and i not in ("—", "-")]


def cell(value):
    return (value or "").replace("|", "/").strip() or "—"


def decision_ids(text):
    """IDs like DD-03 in the first column of the Markdown table rows of a requirements or decisions file."""
    ids = []
    for line in text.splitlines():
        cells = line.strip().split("|")
        if len(cells) > 2 and not cells[0]:
            first = cells[1].strip().strip("*`").strip()
            if re.fullmatch(r"[A-Z]+-\d+", first):
                ids.append(first)
    return ids


LIST_ID = re.compile(r"[ \t]*[-*+][ \t]+(?:\[[ xX]\][ \t]+)?\**`?([A-Z]+-\d+)`?\**(?![\w-])")


def listed_ids(text):
    """IDs that start a list item outside a fence (`- DD-1 用標準函式庫`): the BRIEF lists the Director's decisions so
    (2.1, 題1 F-2). Known, so not missing; not requirements of their own, so not under 沒有工單的需求."""
    return [m.group(1) for m in (LIST_ID.match(line) for line in gate.log_lines(text)) if m]


def missing_hint(name, table_prefixes):
    prefix = gate.id_prefix(name)
    if not table_prefixes or prefix in table_prefixes:
        return ""
    return (f"（--decisions 的表格沒有 {prefix} 開頭的編號；初衷卡只列 "
            + "／".join(sorted(table_prefixes)) + "，DD／PO 編號請再加 --decisions DECISION_REGISTER.md）")


def every(order):
    """The IDs an order traces: TRACES_TO, then those of its 追溯 column."""
    return list(dict.fromkeys((order["traces"] or []) + [i for ids in (order["per_ac"] or {}).values() for i in ids]))


def acs_for(order, name):
    """The ACs of an order that verify one requirement: by its 追溯 column, else every AC when TRACES_TO names it."""
    if order["per_ac"] is not None:
        return [ac for ac, ids in order["per_ac"].items() if name in ids]
    return list(order["acs"]) if name in (order["traces"] or []) else []


def chosen_head(order):
    report = order["reports"][0] if order["reports"] and not order["tie"] else None
    head = (report["head"] or "").lower() if report else ""
    return head if re.fullmatch(r"[0-9a-f]{7,40}", head) else None


def same_commit(one, other):
    return bool(one and other and (one.startswith(other) or other.startswith(one)))


def verified_state(order, name, fingerprint, evidence_dir):
    """這版有驗證紀錄 for one order and one brief row."""
    if fingerprint is None:
        return f"{gate.UNCONFIRMED}（初衷卡這條列了兩次或不是 4 格）"
    _, pins = gate.order_brief(order["text"])
    if not pins or name not in pins:
        return f"{gate.UNCONFIRMED}（工單沒有釘這條的指紋）"
    if pins[name] != fingerprint:
        return "沒有：工單是照舊條件寫的，新條件待重驗"
    if order["tie"] or order["report"] is None:
        return "沒有：還沒有報告" if not order["tie"] else "沒有：多份報告分不出先後"
    if order["stale"]:
        return f"沒有：{order['stale']}"
    states = []
    for ac in acs_for(order, name):
        got = order["report"].get(ac) or {}
        status = got.get("status") or "報告缺這條"
        files = re.findall(r"[\w.-]+\.json", got.get("evidence") or "")
        if status == "PASS" and evidence_dir and any(not (pathlib.Path(evidence_dir) / f).is_file() for f in files):
            status = "PASS 但證據檔找不到"
        states.append((ac, status))
    passed = [ac for ac, status in states if status == "PASS"]
    shown = "、".join(f"{ac} {status}" for ac, status in states) or "沒有 AC 驗這條"
    return ("有" if passed else "還沒有") + f"（{shown}）"


SEEN = {"seen": "看過", "changes": "看過，要求修改", "accepted": "已接受"}


def seen_state(order, name, fingerprint, reviews, accepted):
    """你看過這個成品嗎 for one order and one brief row: the latest PO_PRODUCT_REVIEW for the report's HEAD, else a
    bound PO_ACCEPTANCE record for that commit."""
    head = chosen_head(order)
    mine = [r for r in reviews if r["order"] == order["id"] and not r["problem"]]
    if mine:
        review = mine[-1]
        if head and not same_commit(review["candidate"], head):
            return f"看過別的成品（{review['candidate'][:12]}），這版（{head[:12]}）還沒看"
        said = SEEN[review["outcome"]] + (f"（{review['ref']}）" if review["ref"] else "")
        if fingerprint and review["brief"].get(name) not in (None, fingerprint):
            return f"{said}，但當時是舊條件，新條件還沒看"
        return said
    bound = [r for r in accepted if head and same_commit(r["commit"].lower(), head)]
    if bound:
        record = bound[-1]
        outcome = gate.PO_OUTCOMES.get(record.get("outcome") or "")
        return (SEEN[outcome] + f"（{record['reply_ref']}）") if outcome else f"已送出，還沒回覆（{record['offered_message_ref']}）"
    return "還沒看"


def brief_sections(a, orders):
    """2.1: print 初衷卡三欄 (with --brief) and return the hint sections: the brief's basis and BRIEF_STALE /
    BRIEF_UNCONFIRMED per order, and PO replies that do not bind to one product."""
    log_text = pathlib.Path(a.director_log).read_text(encoding="utf-8-sig") if a.director_log else None
    reviews = gate.po_reviews(log_text) if log_text else []
    accepted, unbound = [], []
    for path in a.acceptance:
        records, problem = gate.acceptance_records(pathlib.Path(path).read_text(encoding="utf-8-sig"))
        if problem:
            unbound.append(f"{path}：{problem}")
        for n, record in enumerate(records, 1):
            bad = gate.acceptance_problems(record)
            if bad:
                unbound.append(f"{path} #{n}：" + "；".join(bad))
            else:
                accepted.append(record)
    ids = {o["id"] for o in orders}
    unbound += [f"{a.director_log}：{r['line']}：{r['problem'] or '沒有這張工單'}" for r in reviews
                if r["problem"] or r["order"] not in ids]
    sections = []
    if a.brief:
        notes = []
        brief = gate.load_brief(a.brief, log_text, a.director_log, notes)
        names = sorted(set(brief["rows"]) | brief["ambiguous"], key=gate.id_sort)
        print("\n## 初衷卡三欄（每條 B 一列）\n\n"
              f"初衷卡 {brief['label']}，版次 {brief['revision'] if brief['revision'] is not None else '—'}。"
              "提示用，不擋任何關卡。\n")
        print("| 需求 | 內容 | 有人負責 | 這版有驗證紀錄 | 你看過這個成品嗎 |\n|---|---|---|---|---|")
        for name in names:
            row = brief["rows"].get(name)
            fingerprint = gate.brief_fingerprint(row) if row else None
            serving = [o for o in orders if name in every(o)]
            cells = (name, row[2] if row else f"{gate.UNCONFIRMED}（列了兩次或不是 4 格）",
                     "、".join(o["id"] for o in serving) or "沒有工單",
                     "；".join(f"{o['id']}：{verified_state(o, name, fingerprint, a.evidence_dir)}" for o in serving) or "—",
                     "；".join(f"{o['id']}：{seen_state(o, name, fingerprint, reviews, accepted)}" for o in serving) or "—")
            print("| " + " | ".join(cell(v) for v in cells) + " |")
        hints = ([brief["problem"]] if brief["problem"] else []) + notes
        for order in orders:
            gate.brief_notes(order["text"], order["path"], brief, hints)
        sections.append(("初衷卡依據提示（BRIEF_STALE／BRIEF_UNCONFIRMED，shadow，不擋）", hints))
    if a.acceptance or a.director_log:
        sections.append(("PO 回覆沒綁到成品（UNBOUND_PO_REPLY）", unbound))
    return sections


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--orders", required=True)
    ap.add_argument("--reports", required=True)
    ap.add_argument("--verdicts")
    ap.add_argument("--config")
    ap.add_argument("--decisions", action="append", default=[])
    ap.add_argument("--brief", help="2.1: the BRIEF; adds 初衷卡三欄 and the BRIEF_STALE hints")
    ap.add_argument("--director-log", help="with --brief: PO_PRODUCT_REVIEW and BRIEF_LOCKED lines")
    ap.add_argument("--evidence-dir", help="with --brief: the evidence files a PASS must name")
    ap.add_argument("--acceptance", action="append", default=[], help="PO_ACCEPTANCE.json (repeatable)")
    a = ap.parse_args()
    if (a.director_log or a.evidence_dir) and not a.brief:
        ap.error("--director-log and --evidence-dir work with --brief")
    sys.stdout.reconfigure(encoding="utf-8")
    missing = [f for f in (a.orders, a.reports, a.verdicts, a.evidence_dir) if f and not pathlib.Path(f).is_dir()]
    if missing:
        print(f"FAIL folder not found: {', '.join(missing)}")
        return 1
    missing = [f for f in a.decisions + [a.brief, a.director_log] + a.acceptance if f and not pathlib.Path(f).is_file()]
    if missing:
        print(f"FAIL file not found: {', '.join(missing)}")
        return 1
    decision_texts = [pathlib.Path(f).read_text(encoding="utf-8-sig") for f in a.decisions]
    known = list(dict.fromkeys(i for text in decision_texts for i in decision_ids(text)))
    listed = {i for text in decision_texts for i in listed_ids(text)} - set(known)
    table_prefixes = {gate.id_prefix(i) for i in known}
    cfg = json.loads(pathlib.Path(a.config).read_text(encoding="utf-8-sig")) if a.config else {}
    if cfg.get("schema_version", 1) != CONFIG_VERSION:
        sys.exit(f"{a.config}: schema_version {cfg['schema_version']} is not {CONFIG_VERSION}; see CHANGELOG.md")
    pattern = re.compile(cfg["trace_id_pattern"]) if cfg.get("trace_id_pattern") else None

    orders, skipped = [], {"工單資料夾裡沒有 `ISSUED_BY =` 行的檔案（沒算成工單）": [],
                           "報告資料夾裡沒有 `TASK_ID` 行的檔案（沒算成報告）": [],
                           "裁決資料夾裡沒有 `## A` 的檔案（沒算成裁決）": []}
    slots = list(skipped.values())
    for path, text in files(a.orders, r"^\s*ISSUED_BY\s*=", slots[0]):
        m = re.search(r"^\s*TRACES_TO\s*=\s*([^#\n]*)", text, re.M)
        ids = id_list(m.group(1)) if m else None
        acs = gate.ac_table(text)
        orders.append({"path": path, "id": first_id(text, path.stem), "traces": ids, "acs": acs, "text": text,
                       "per_ac": {ac: id_list(row.get("traces")) for ac, row in acs.items()}
                       if any(id_list(row.get("traces")) for row in acs.values()) else None,
                       "rev": int(gate.order_revision(text)), "hash": gate.order_hash(path.read_bytes()),
                       "reports": [], "report": None, "tie": False, "stale": None, "verdicts": [], "verdict": None})
    stray = []
    for path, text in files(a.reports, r"^\s*TASK_ID\b", slots[1]):
        order = owner(orders, text, by_name=True)
        if order:
            order["reports"].append(report_info(path, text))
        else:
            stray.append(path)
    for order in orders:
        order["reports"].sort(key=lambda r: r["key"], reverse=True)
        if len(order["reports"]) > 1 and order["reports"][0]["key"] == order["reports"][1]["key"]:
            order["tie"] = True
        elif order["reports"]:
            order["report"] = order["reports"][0]["table"]
            order["stale"] = stale_reason(order, order["reports"][0])
    for path, text in files(a.verdicts, r"^##\s*A\b", slots[2]) if a.verdicts else []:
        order = owner(orders, text, by_name=False)
        if order:
            order["verdicts"].append(verdict_info(path, text))
    unpaired = []
    for order in orders:
        order["verdict"] = pick_verdict(order, unpaired)

    rows, last = [], ("（無）", "（未指定）")
    for order in orders:
        traces = order["traces"] or []
        for ac, spec_row in order["acs"].items():
            if order["per_ac"] is not None:  # the order says which requirement each AC verifies
                reqs = order["per_ac"][ac] or ["（未指定）"]
            elif len(traces) > 1:  # only the order as a whole names them: never pair each ID with each AC
                reqs = ["、".join(traces) + "（工單層）"]
            else:
                reqs = traces or ["（無）"]
            got = order["report"].get(ac) if order["report"] is not None else None
            status = (got.get("status") if got else "多份報告分不出先後" if order["tie"]
                      else "沒有報告" if order["report"] is None else "報告缺這條")
            if order["stale"]:
                status = f"{order['stale']}（報告寫 {status}）"
            for req in reqs:
                rows.append((req, order["id"], ac, spec_row.get("type"), status, got and got.get("evidence"),
                             order["verdict"]))
    left = sum(len(paths) for paths in skipped.values())
    print(f"# 追溯表\n\n工單 {len(orders)} 份，報告 {sum(len(o['reports']) for o in orders)} 份對到工單。"
          + (f"沒計入的檔案 {left} 份，列在文末。" if left else "") + "\n")
    print("| 需求 | 工單 | AC | 類型 | 狀態 | 證據 | 裁決 |\n|---|---|---|---|---|---|---|")
    for row in sorted(rows, key=lambda r: (r[0] in last, r[0], r[1], r[2])):
        print("| " + " | ".join(cell(v) for v in row) + " |")
    extra = brief_sections(a, orders) if a.brief or a.acceptance else []
    untraced = [o["id"] for o in orders if o["traces"] is None]
    odd = [f"{o['id']}: {i}" for o in orders for i in every(o) if pattern and not pattern.fullmatch(i)]
    sections = [("沒有 TRACES_TO 的工單", untraced), ("編號格式不符 trace_id_pattern", odd),
                ("對不到工單的報告", [str(p) for p in stray]), ("裁決對不到報告版次", unpaired),
                ("報告過期或版次不符（表內狀態是舊報告寫的，不是現在的工單）",
                 [f"{o['id']}：{o['stale']}，{o['reports'][0]['path']}" for o in orders if o["stale"]])]
    mapped = [o for o in orders if o["per_ac"] is not None]
    if mapped:
        sections += [("AC 的追溯不在工單 TRACES_TO 裡", [f"{o['id']} {ac}: {i}" for o in mapped
                                                    for ac, ids in o["per_ac"].items() for i in ids
                                                    if i not in (o["traces"] or [])]),
                     ("TRACES_TO 裡沒有 AC 驗證的編號", [f"{o['id']}: {i}" for o in mapped for i in o["traces"] or []
                                                  if not any(i in ids for ids in o["per_ac"].values())])]
    if a.decisions:
        traced = {i for o in orders for i in every(o)}
        sections += [("TRACES_TO 找不到的編號", [f"{o['id']}: {i}" + missing_hint(i, table_prefixes) for o in orders
                                                 for i in every(o) if i not in known and i not in listed]),
                     ("沒有工單的需求", [i for i in known if i not in traced])]
    sections += extra
    for title, items in sections:
        print(f"\n## {title}\n" + ("\n".join(f"- {i}" for i in items) if items else "- 無"))
    several = [o for o in orders if len(o["reports"]) > 1]
    print("\n## 同一工單有多份報告（依 REVISION、ATTEMPT、日期選，不看檔名）")
    if not several:
        print("- 無")
    for order in several:
        print(f"- {order['id']}：" + ("最新的幾份 REVISION、ATTEMPT、日期都相同，分不出先後，表內兩份都不取；請在報告寫 ATTEMPT"
                                      if order["tie"] else f"選 {order['reports'][0]['path']}"))
        for n, info in enumerate(order["reports"]):
            print(f"  - {describe(info)}" + (" ← 選這份" if n == 0 and not order["tie"] else ""))
    print("\n## 沒計入的檔案")
    for title, paths in skipped.items():
        print(f"\n{title}：{len(paths)} 份" + "".join(f"\n- {p}" for p in paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
