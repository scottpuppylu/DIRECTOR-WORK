"""Count PURPOSE.md's five effectiveness numbers from the Director's own files, so each change to the rules can be
judged before and after (PURPOSE.md, 怎麼判斷有沒有效). Only reads; prints Markdown.

  metrics_report.py --director DIRECTOR [--since YYYY-MM-DD] [--config director_work.json]

Where each number comes from (every *.md under DIRECTOR is searched):
  返工次數           gate verdicts (`## A`) whose 下一步 sends the work back: CONTINUE_SAME_WORKER, SWITCH_TO_OTHER_WORKER;
                     also orders changed after dispatch (REVISION above 1)
  中斷後遺失的工作   DIRECTOR_LOG lines with `RESUMED <TASK_ID> ... redo=<what had to be redone>`; redo=NONE loses nothing
  PO 介入次數        PO_PENDING.md entries `ID: OD-..` (a decision) and `ID: ACT-..` (an action); an entry runs to
                     the next one, is open when it holds `STATUS: open`, and is dated by `CREATED: YYYY-MM-DD`.
                     A project that keeps them elsewhere sets, in the config (default DIRECTOR/director_work.json):
                       po_pending_files  files under DIRECTOR to read, default ["PO_PENDING.md"]
                       po_item_pattern   regex that starts an entry; group 1 is its kind (OD, ACT, ...)
                       po_open_pattern   regex that marks an entry still waiting for the PO
  新專案導入卡住     DIRECTOR_LOG lines with `BOOTSTRAP_STUCK`
  額度用量           not read here: run usage_report.py
and the spec review cost: DIRECTOR_LOG lines `SPEC_REVIEW ... tokens=N issues=... adopted=N`.

A number with nothing to count from prints UNKNOWN, never 0: no verdict, no order, no RESUMED line, or a missing
source file. --since drops log lines, verdicts and orders dated before the day, and PO entries CREATED before it;
a PO entry with no CREATED date is counted and shown as UNDATED. Files that look like orders (WO-*.md, or under a folder named orders) but were not counted
are listed by name at the end, with the reason. Exit 0, or 1 when DIRECTOR is missing.
"""
import argparse
import importlib.util
import json
import pathlib
import re
import sys

spec = importlib.util.spec_from_file_location("gate_check", pathlib.Path(__file__).resolve().parent / "gate_check.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)  # reuse its date and section parsing; `python -I` does not put this folder on sys.path

SENT_BACK = ("CONTINUE_SAME_WORKER", "SWITCH_TO_OTHER_WORKER")
CONFIG_VERSION = 1
PO_DEFAULTS = {"po_pending_files": ["PO_PENDING.md"], "po_item_pattern": r"^\s*ID\s*:\s*(OD|ACT)-\w+",
               "po_open_pattern": r"^\s*STATUS\s*:\s*open\b"}
CREATED = re.compile(r"\bCREATED\s*:\s*(\d{4}-\d{2}-\d{2})")


def po_entries(text, item):
    """(kind, entry text) for each entry: from one item match to the next."""
    hits = list(item.finditer(text))
    return [(m.group(1) if m.groups() else "?", text[m.start():hits[n + 1].start() if n + 1 < len(hits) else len(text)])
            for n, m in enumerate(hits)]


def po_count(root, cfg, since):
    """The PO 介入 cell and the files it read."""
    names = cfg.get("po_pending_files", PO_DEFAULTS["po_pending_files"])
    names = [names] if isinstance(names, str) else names
    item = re.compile(cfg.get("po_item_pattern", PO_DEFAULTS["po_item_pattern"]), re.M)
    still_open = re.compile(cfg.get("po_open_pattern", PO_DEFAULTS["po_open_pattern"]), re.M)
    present = [root / name for name in names if (root / name).is_file()]
    if not present:
        return f"UNKNOWN：沒有 {'、'.join(names)}", names
    entries = [entry for path in present for entry in po_entries(path.read_text(encoding="utf-8-sig"), item)]
    kept, dropped, undated = [], 0, 0
    for kind, body in entries:
        m = CREATED.search(body)
        if not m:
            undated += 1
        elif since and m.group(1) < since:
            dropped += 1
            continue
        kept.append((kind, body))
    if not kept and not entries:
        return f"UNKNOWN：{'、'.join(names)} 裡沒有符合 po_item_pattern 的項目", names
    kinds = sorted({kind for kind, _ in kept})
    waiting = sum(1 for _, body in kept if still_open.search(body))
    cell = f"{len(kept)}（{'、'.join(f'{k} {sum(1 for kind, _ in kept if kind == k)}' for k in kinds)}），還在等 PO {waiting}"
    if undated:
        cell += f"；UNDATED {undated}（沒寫 CREATED{'，照算' if since else ''}）"
    if dropped:
        cell += f"；--since 前 {dropped} 項沒算"
    return cell, names


def documents(folder, marker, kind, since, dropped=None, undated=None):
    """(path, text) of the .md files holding marker, dated on or after since (undated files are kept).
    dropped / undated, when given, collect the paths left out by since and the paths kept with no date."""
    found = []
    for path in sorted(pathlib.Path(folder).rglob("*.md")):
        text = path.read_text(encoding="utf-8-sig")
        if not re.search(marker, text, re.M):
            continue
        day = gate.dated(kind, text) if since else None
        if day and day < since:
            if dropped is not None:
                dropped.append(path)
            continue
        if since and not day and undated is not None:
            undated.append(path)
        found.append((path, text))
    return found


def order_like(root):
    """.md files named WO-* or kept under a folder named orders: what a reader would count as work orders."""
    return [path for path in sorted(root.rglob("*.md"))
            if path.name.upper().startswith("WO-") or "orders" in (p.name.lower() for p in path.relative_to(root).parents)]


def next_step(text):
    section = re.search(r"^##\s*A\b.*?$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    step = next((line for line in section.group(1).splitlines() if line.strip().startswith("下一步")), "") if section else ""
    return re.split(r"[:：]", step, maxsplit=1)[-1].strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--director", required=True, help="the DIRECTOR folder")
    ap.add_argument("--since", metavar="YYYY-MM-DD")
    ap.add_argument("--config", help="director_work.json (default: DIRECTOR/director_work.json when it exists)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    root = pathlib.Path(a.director)
    if not root.is_dir():
        print(f"FAIL folder not found: {a.director}")
        return 1
    if a.since and not gate.DATE.fullmatch(a.since):
        ap.error("--since takes a date: YYYY-MM-DD")

    config = pathlib.Path(a.config) if a.config else root / "director_work.json"
    try:
        cfg = json.loads(config.read_text(encoding="utf-8-sig")) if a.config or config.is_file() else {}
        for key in ("po_item_pattern", "po_open_pattern"):
            re.compile(cfg.get(key, PO_DEFAULTS[key]))
    except (OSError, ValueError, re.error) as e:
        print(f"FAIL config {config}: {e}")
        return 1
    if cfg.get("schema_version", 1) != CONFIG_VERSION:
        print(f"FAIL {config}: schema_version {cfg['schema_version']} is not {CONFIG_VERSION}; see CHANGELOG.md")
        return 1
    log_file = root / "DIRECTOR_LOG.md"
    log = None
    if log_file.is_file():
        log = [line for line in log_file.read_text(encoding="utf-8-sig").splitlines()
               if not (a.since and gate.DATE.match(line.strip()) and line.strip()[:10] < a.since)]

    # a verdict's ## A section has a 下一步 line; a decision register or an order also has ## A
    verdicts = [(path, text) for path, text in documents(root, r"^##\s*A\b", "verdict", a.since) if next_step(text)]
    steps = [next_step(text) for _, text in verdicts]
    back = {word: steps.count(word) for word in SENT_BACK}
    dropped, undated = [], []
    orders = documents(root, r"^\s*ISSUED_BY\s*=", "order", a.since, dropped, undated)
    revised = [int(m.group(1)) - 1 for _, text in orders
               for m in [re.search(r"^[ \t]*REVISION[ \t]*=[ \t]*(\d+)", text, re.M)] if m and int(m.group(1)) > 1]
    rework = (f"{sum(back.values())}（{'、'.join(f'{k} {v}' for k, v in back.items())}）" if verdicts
              else "UNKNOWN：找不到裁決") + "；" + (
              f"工單改版 {sum(revised)} 次（{len(revised)} 份工單）" if orders else "工單改版 UNKNOWN：找不到工單")
    counted = {path for path, _ in orders} | set(dropped)
    skipped = [path for path in order_like(root) if path not in counted]

    if log is None:
        lost = stuck = "UNKNOWN：沒有 DIRECTOR_LOG.md"
        reviews = []
    else:
        resumed = [line for line in log if re.search(r"\bRESUMED\b", line)]
        redo = [m.group(1) for line in resumed for m in [re.search(r"\bredo=([^;|]*)", line)] if m]
        lost_count = sum(1 for value in redo if value.strip().upper() not in ("NONE", ""))
        lost = (f"{lost_count} / 恢復 {len(resumed)} 次" + (f"；{len(resumed) - len(redo)} 次沒寫 redo=" if len(redo) < len(resumed) else "")
                if resumed else "UNKNOWN：DIRECTOR_LOG 沒有 RESUMED 行（沒中斷過，或沒記）")
        stuck = str(sum(1 for line in log if "BOOTSTRAP_STUCK" in line))
        reviews = [line for line in log if re.search(r"\bSPEC_REVIEW\b.*\btokens=", line)]

    po, po_files = po_count(root, cfg, a.since)

    print(f"# 成效數字\n\n範圍：{f'{a.since} 起' if a.since else '全部'}。數字是檔案裡記下的次數，沒記的事不會被算到。\n")
    print("| 指標 | 數字 | 來源 |\n|---|---|---|")
    print("| 額度用量 | UNKNOWN：跑 `usage_report.py` | 對話紀錄（本工具不讀） |")
    print(f"| 返工次數 | {rework} | 裁決 {len(verdicts)} 份、工單 {len(orders)} 份 |")
    print(f"| 中斷後遺失的工作 | {lost} | DIRECTOR_LOG 的 `RESUMED ... redo=` |")
    print(f"| PO 介入次數 | {po} | {'、'.join(po_files)} |")
    print(f"| 新專案導入卡住 | {stuck} | DIRECTOR_LOG 的 `BOOTSTRAP_STUCK` |")
    numbers = lambda key: [int(m.group(1)) for line in reviews for m in [re.search(rf"\b{key}=(\d+)", line)] if m]
    tokens, adopted = numbers("tokens"), numbers("adopted")
    print(f"\n## 規格審查\n\n{len(reviews)} 次" + (f"，tokens 合計 {sum(tokens)}，採用的問題 {sum(adopted)} 個" if reviews else "")
          + ("" if len(tokens) == len(reviews) == len(adopted) else "；有幾行少了 tokens= 或 adopted="))
    names = lambda paths: "、".join(str(path.relative_to(root)) for path in paths)
    print("\n## 沒計入的檔案\n")
    print(f"- 像工單但沒有 `ISSUED_BY =` 行，返工和改版都沒算到：{len(skipped)} 份" + (f"：{names(skipped)}" if skipped else ""))
    if a.since:
        print(f"- 工單日期在 {a.since} 之前，照 --since 略過：{len(dropped)} 份" + (f"：{names(dropped)}" if dropped else ""))
        print(f"- 工單沒有日期，照算：{len(undated)} 份" + (f"：{names([p for p in undated])}" if undated else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
