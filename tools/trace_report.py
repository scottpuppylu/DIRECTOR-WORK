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
are listed under 裁決對不到報告版次. `trace_id_pattern` in the config (a regex) flags IDs written in another format;
without it every ID is accepted. `--decisions FILE` (repeatable) reads the IDs (`XX-number`) in the first column of the
Markdown table rows of the project's requirement or decision files: a TRACES_TO ID found in none of them is listed under
TRACES_TO 找不到的編號, and an ID there that no order traces under 沒有工單的需求. Without the flag the output is the
same as before. Exit 0, or 1 when a folder or a --decisions file is missing.
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
    revision (marked 未標版次). Verdicts for other revisions and a CANDIDATE_HEAD unlike the report's HEAD go to problems."""
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
    same.sort(key=lambda v: (-1 if v["rev"] is None else v["rev"], v["when"] or ""), reverse=True)
    if len(same) > 1 and (same[0]["rev"], same[0]["when"]) == (same[1]["rev"], same[1]["when"]):
        return "多份裁決分不出先後"
    chosen = same[0]
    head = report["head"].lower() if report and report["head"] and gate.SHA.fullmatch(report["head"]) else None
    if chosen["head"] and head and not (chosen["head"].startswith(head) or head.startswith(chosen["head"])):
        problems.append(f"{order['id']}：{chosen['path']} 的 CANDIDATE_HEAD {chosen['head'][:12]} 不是報告的 HEAD {head[:12]}")
    return chosen["verdict"] + ("（未標版次）" if chosen["rev"] is None else "")


def report_info(path, text):
    """What tells one report for an order from another: order revision, attempt, first date, HEAD."""
    named = gate.order_line(text)
    attempt = re.search(r"^\s*ATTEMPT\s*[:=]\s*(\d+)", text, re.M | re.I)
    info = {"path": path, "table": gate.ac_table(text), "head": gate.report_head_value(text),
            "rev": named[1] if named else None, "attempt": int(attempt.group(1)) if attempt else None,
            "when": first_date(text)}
    info["key"] = (-1 if info["rev"] is None else info["rev"], -1 if info["attempt"] is None else info["attempt"],
                   info["when"] or "")
    return info


def describe(info):
    return (f"{info['path']}：REVISION {info['rev'] if info['rev'] is not None else '—'}、"
            f"ATTEMPT {info['attempt'] if info['attempt'] is not None else '—'}、日期 {info['when'] or '—'}、"
            f"HEAD {info['head'] or '—'}")


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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--orders", required=True)
    ap.add_argument("--reports", required=True)
    ap.add_argument("--verdicts")
    ap.add_argument("--config")
    ap.add_argument("--decisions", action="append", default=[])
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    missing = [f for f in (a.orders, a.reports, a.verdicts) if f and not pathlib.Path(f).is_dir()]
    if missing:
        print(f"FAIL folder not found: {', '.join(missing)}")
        return 1
    missing = [f for f in a.decisions if not pathlib.Path(f).is_file()]
    if missing:
        print(f"FAIL file not found: {', '.join(missing)}")
        return 1
    known = list(dict.fromkeys(i for f in a.decisions for i in decision_ids(
        pathlib.Path(f).read_text(encoding="utf-8-sig"))))
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
        ids = [i for i in re.split(r"[\s,，、]+", m.group(1)) if i and i.upper() != "NONE"] if m else None
        orders.append({"path": path, "id": first_id(text, path.stem), "traces": ids, "acs": gate.ac_table(text),
                       "reports": [], "report": None, "tie": False, "verdicts": [], "verdict": None})
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
    for path, text in files(a.verdicts, r"^##\s*A\b", slots[2]) if a.verdicts else []:
        order = owner(orders, text, by_name=False)
        if order:
            order["verdicts"].append(verdict_info(path, text))
    unpaired = []
    for order in orders:
        order["verdict"] = pick_verdict(order, unpaired)

    rows = []
    for order in orders:
        for req in order["traces"] or ["（無）"]:
            for ac, spec_row in order["acs"].items():
                got = order["report"].get(ac) if order["report"] is not None else None
                status = (got.get("status") if got else "多份報告分不出先後" if order["tie"]
                          else "沒有報告" if order["report"] is None else "報告缺這條")
                rows.append((req, order["id"], ac, spec_row.get("type"), status, got and got.get("evidence"), order["verdict"]))
    left = sum(len(paths) for paths in skipped.values())
    print(f"# 追溯表\n\n工單 {len(orders)} 份，報告 {sum(len(o['reports']) for o in orders)} 份對到工單。"
          + (f"沒計入的檔案 {left} 份，列在文末。" if left else "") + "\n")
    print("| 需求 | 工單 | AC | 類型 | 狀態 | 證據 | 裁決 |\n|---|---|---|---|---|---|---|")
    for row in sorted(rows, key=lambda r: (r[0] == "（無）", r[0], r[1], r[2])):
        print("| " + " | ".join(cell(v) for v in row) + " |")
    untraced = [o["id"] for o in orders if o["traces"] is None]
    odd = [f"{o['id']}: {i}" for o in orders for i in o["traces"] or [] if pattern and not pattern.fullmatch(i)]
    sections = [("沒有 TRACES_TO 的工單", untraced), ("編號格式不符 trace_id_pattern", odd),
                ("對不到工單的報告", [str(p) for p in stray]), ("裁決對不到報告版次", unpaired)]
    if a.decisions:
        traced = {i for o in orders for i in o["traces"] or []}
        sections += [("TRACES_TO 找不到的編號", [f"{o['id']}: {i}" for o in orders for i in o["traces"] or []
                                                 if i not in known]),
                     ("沒有工單的需求", [i for i in known if i not in traced])]
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
