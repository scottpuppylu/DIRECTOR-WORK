"""Count PURPOSE.md's five effectiveness numbers from the Director's own files, so each change to the rules can be
judged before and after (PURPOSE.md, 怎麼判斷有沒有效). Only reads; prints Markdown.

  metrics_report.py --director DIRECTOR [--since YYYY-MM-DD]

Where each number comes from (every *.md under DIRECTOR is searched):
  返工次數           gate verdicts (`## A`) whose 下一步 sends the work back: CONTINUE_SAME_WORKER, SWITCH_TO_OTHER_WORKER;
                     also orders changed after dispatch (REVISION above 1)
  中斷後遺失的工作   DIRECTOR_LOG lines with `RESUMED <TASK_ID> ... redo=<what had to be redone>`; redo=NONE loses nothing
  PO 介入次數        PO_PENDING.md entries `ID: OD-..` (a decision) and `ID: ACT-..` (an action)
  新專案導入卡住     DIRECTOR_LOG lines with `BOOTSTRAP_STUCK`
  額度用量           not read here: run usage_report.py
and the spec review cost: DIRECTOR_LOG lines `SPEC_REVIEW ... tokens=N issues=... adopted=N`.

A number whose source file is missing prints UNKNOWN, never 0. --since drops log lines, verdicts and orders dated
before the day; PO_PENDING entries carry no date and are always all counted. Exit 0, or 1 when DIRECTOR is missing.
"""
import argparse
import importlib.util
import pathlib
import re
import sys

spec = importlib.util.spec_from_file_location("gate_check", pathlib.Path(__file__).resolve().parent / "gate_check.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)  # reuse its date and section parsing; `python -I` does not put this folder on sys.path

SENT_BACK = ("CONTINUE_SAME_WORKER", "SWITCH_TO_OTHER_WORKER")


def documents(folder, marker, kind, since):
    """(path, text) of the .md files holding marker, dated on or after since (undated files are kept)."""
    found = []
    for path in sorted(pathlib.Path(folder).rglob("*.md")):
        text = path.read_text(encoding="utf-8-sig")
        day = gate.dated(kind, text) if since else None
        if re.search(marker, text, re.M) and not (day and day < since):
            found.append((path, text))
    return found


def next_step(text):
    section = re.search(r"^##\s*A\b.*?$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    step = next((line for line in section.group(1).splitlines() if line.strip().startswith("下一步")), "") if section else ""
    return re.split(r"[:：]", step, maxsplit=1)[-1].strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--director", required=True, help="the DIRECTOR folder")
    ap.add_argument("--since", metavar="YYYY-MM-DD")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    root = pathlib.Path(a.director)
    if not root.is_dir():
        print(f"FAIL folder not found: {a.director}")
        return 1
    if a.since and not gate.DATE.fullmatch(a.since):
        ap.error("--since takes a date: YYYY-MM-DD")

    log_file, pending_file = root / "DIRECTOR_LOG.md", root / "PO_PENDING.md"
    log = None
    if log_file.is_file():
        log = [line for line in log_file.read_text(encoding="utf-8-sig").splitlines()
               if not (a.since and gate.DATE.match(line.strip()) and line.strip()[:10] < a.since)]

    # a verdict's ## A section has a 下一步 line; a decision register or an order also has ## A
    verdicts = [(path, text) for path, text in documents(root, r"^##\s*A\b", "verdict", a.since) if next_step(text)]
    steps = [next_step(text) for _, text in verdicts]
    back = {word: steps.count(word) for word in SENT_BACK}
    orders = documents(root, r"^\s*ISSUED_BY\s*=", "order", a.since)
    revised = [int(m.group(1)) - 1 for _, text in orders
               for m in [re.search(r"^[ \t]*REVISION[ \t]*=[ \t]*(\d+)", text, re.M)] if m and int(m.group(1)) > 1]
    if verdicts or orders:
        rework = (f"{sum(back.values())}（{'、'.join(f'{k} {v}' for k, v in back.items())}）；"
                  f"工單改版 {sum(revised)} 次（{len(revised)} 份工單）")
    else:
        rework = "UNKNOWN：找不到裁決或工單"

    if log is None:
        lost = stuck = "UNKNOWN：沒有 DIRECTOR_LOG.md"
        reviews = []
    else:
        resumed = [line for line in log if re.search(r"\bRESUMED\b", line)]
        redo = [m.group(1) for line in resumed for m in [re.search(r"\bredo=([^;|]*)", line)] if m]
        lost_count = sum(1 for value in redo if value.strip().upper() not in ("NONE", ""))
        lost = f"{lost_count} / 恢復 {len(resumed)} 次" + (f"；{len(resumed) - len(redo)} 次沒寫 redo=" if len(redo) < len(resumed) else "")
        stuck = str(sum(1 for line in log if "BOOTSTRAP_STUCK" in line))
        reviews = [line for line in log if re.search(r"\bSPEC_REVIEW\b.*\btokens=", line)]

    if pending_file.is_file():
        text = pending_file.read_text(encoding="utf-8-sig")
        asks = re.findall(r"^\s*ID\s*:\s*(OD|ACT)-\w+", text, re.M)
        waiting = len(re.findall(r"^\s*STATUS\s*:\s*open\b", text, re.M))
        po = f"{len(asks)}（OD {asks.count('OD')}、ACT {asks.count('ACT')}），還在等 PO {waiting}"
    else:
        po = "UNKNOWN：沒有 PO_PENDING.md"

    print(f"# 成效數字\n\n範圍：{f'{a.since} 起' if a.since else '全部'}。數字是檔案裡記下的次數，沒記的事不會被算到。\n")
    print("| 指標 | 數字 | 來源 |\n|---|---|---|")
    print("| 額度用量 | UNKNOWN：跑 `usage_report.py` | 對話紀錄（本工具不讀） |")
    print(f"| 返工次數 | {rework} | 裁決 {len(verdicts)} 份、工單 {len(orders)} 份 |")
    print(f"| 中斷後遺失的工作 | {lost} | DIRECTOR_LOG 的 `RESUMED ... redo=` |")
    print(f"| PO 介入次數 | {po} | PO_PENDING.md |")
    print(f"| 新專案導入卡住 | {stuck} | DIRECTOR_LOG 的 `BOOTSTRAP_STUCK` |")
    numbers = lambda key: [int(m.group(1)) for line in reviews for m in [re.search(rf"\b{key}=(\d+)", line)] if m]
    tokens, adopted = numbers("tokens"), numbers("adopted")
    print(f"\n## 規格審查\n\n{len(reviews)} 次" + (f"，tokens 合計 {sum(tokens)}，採用的問題 {sum(adopted)} 個" if reviews else "")
          + ("" if len(tokens) == len(reviews) == len(adopted) else "；有幾行少了 tokens= 或 adopted="))
    return 0


if __name__ == "__main__":
    sys.exit(main())
