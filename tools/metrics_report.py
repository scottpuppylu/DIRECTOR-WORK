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

  metrics_report.py [--director DIRECTOR] --run RUN_DIR [--compare BASE_RUN_DIR]     (2.1.0, shadow: only reads)

--run adds the rehearsal numbers of one run folder (docs/06b 接手演練; format in tools/README.md): time to the first
usable preview, decisions by decision_id (asked, answered, waiting, withdrawn), re-asks (per topic_id + scope_id, the
distinct ask_id count minus 1) and PO operations (po_action, each `count` times, default 1). Events come from
RUN_DIR/events/*.json; a repeated event_id counts once; an event with a missing field or a time without its zone is
listed and left out. The start is run.json `started_at`, else the earliest run_started event. --compare prints
saved = baseline - this run; the percentage is UNKNOWN when the baseline is 0. Exit 1 when a run folder is missing.
Without --run the output is the same as before.

2.2 (F16): a number is only as good as what was recorded. run.json may carry
  "sampling": {"version": 1, "complete": true, "scenario": "<劇本 ID>", "counted": ["po_action", "asked", ...],
               "kinds": ["click", "type", ...]}
complete=true says every event of the counted types was recorded (no "counted" = all types). Each number is shown as
確認 (complete), 部分 (a marker that is not complete, or a type it does not count) or 完整度未知 (no marker: every
run before 2.2); 0 PO operations without a complete marker prints UNKNOWN, never 0. --compare only subtracts when both
runs are complete for that number with the same scenario and sampling version; otherwise UNKNOWN with the reason.
A po_action whose kind is not a short name (a list, a number, an empty text), or not in sampling.kinds when that is
given, is quarantined: listed, never counted, and the report does not crash. An answer_received counts only when an
asked event with the same decision_id and ask_id came no later; the others are listed as 回覆對不到發問.
"""
import argparse
import datetime
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
RUN_VERSION = 1
SAMPLING_VERSION = 1
KIND = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}")
REQUIRED = {"run_started": (), "asked": ("decision_id", "topic_id", "scope_id", "ask_id"),
            "answer_received": ("decision_id", "ask_id"), "applied": ("decision_id",), "closed": ("decision_id",),
            "withdrawn": ("decision_id",), "po_action": (), "preview_ready": ()}  # event type -> the string fields it needs


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


def stamp(value):
    """An ISO 8601 time with its zone, as an aware datetime; None when it is missing, unreadable or has no zone."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.datetime.fromisoformat(value.strip()[:-1] + "+00:00" if value.strip().endswith("Z") else value.strip())
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def run_events(folder):
    """(events, notes) from folder/events/*.json, each file one event or a list of them. An event needs v=1, a string
    event_id, a known type and an `at` time with its zone; a repeated event_id counts once (the first in file order)."""
    events, seen, notes = [], {}, {"bad": [], "duplicate": 0, "conflict": 0}
    for path in sorted((folder / "events").glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as e:
            notes["bad"].append(f"{path.name}（{type(e).__name__}）")
            continue
        for n, event in enumerate(data if isinstance(data, list) else [data]):
            where = f"{path.name}#{n + 1}" if isinstance(data, list) else path.name
            fields = REQUIRED.get(event.get("type")) if isinstance(event, dict) and isinstance(event.get("type"), str) else None
            if (fields is None or event.get("v") != RUN_VERSION or not isinstance(event.get("event_id"), str)
                    or stamp(event.get("at")) is None or any(not isinstance(event.get(key), str) for key in fields)):
                notes["bad"].append(where)
                continue
            if event["type"] == "po_action" and "kind" in event and not (
                    isinstance(event["kind"], str) and KIND.fullmatch(event["kind"])):
                notes.setdefault("quarantined", []).append(f"{where}（kind {json.dumps(event['kind'], ensure_ascii=False)[:40]}）")
                continue
            if event["event_id"] in seen:
                notes["duplicate"] += 1
                notes["conflict"] += seen[event["event_id"]] != event
                continue
            seen[event["event_id"]] = event
            events.append(event)
    return events, notes


def run_numbers(folder):
    """The rehearsal numbers of one run folder (docs/06b 接手演練): decisions, re-asks, PO operations, first preview."""
    events, notes = run_events(folder)
    of = lambda kind: [event for event in events if event["type"] == kind]
    asked = {event["decision_id"] for event in of("asked")}
    when = {}  # (decision_id, ask_id) -> the earliest time it was asked
    for event in of("asked"):
        key, moment = (event["decision_id"], event["ask_id"]), stamp(event["at"])
        when[key] = min(when.get(key, moment), moment)
    answered, stray = set(), []
    for event in of("answer_received"):
        asked_at = when.get((event["decision_id"], event["ask_id"]))
        if asked_at is not None and asked_at <= stamp(event["at"]):
            answered.add(event["decision_id"])
        else:
            stray.append(event["event_id"])
    withdrawn = {event["decision_id"] for event in of("withdrawn")} & asked - answered
    asks = {}
    for event in of("asked"):
        asks.setdefault((event["topic_id"], event["scope_id"]), set()).add(event["ask_id"])
    counts = [event.get("count", 1) for event in of("po_action")]
    bad_count = sum(1 for count in counts if not (isinstance(count, int) and not isinstance(count, bool) and count > 0))
    started, sampling = None, None
    run_file = folder / "run.json"
    if run_file.is_file():
        try:
            run = json.loads(run_file.read_text(encoding="utf-8-sig"))
            started = stamp(run.get("started_at"))
            sampling = run.get("sampling")
        except (OSError, ValueError, AttributeError):
            notes["bad"].append("run.json")
    sampling, sampling_note = read_sampling(sampling)
    if sampling_note:
        notes["bad"].append(f"run.json sampling（{sampling_note}）")
    allowed = set(sampling["kinds"]) if sampling and sampling.get("kinds") is not None else None
    kinds = {}
    for event in of("po_action"):
        count, kind = event.get("count", 1), event.get("kind", "?")
        if allowed is not None and kind not in allowed:
            notes.setdefault("quarantined", []).append(f"{event['event_id']}（kind {kind} 不在 sampling.kinds）")
            continue
        if isinstance(count, int) and not isinstance(count, bool) and count > 0:
            kinds[kind] = kinds.get(kind, 0) + count
    starts = [stamp(event["at"]) for event in of("run_started")]
    if started is None and starts:
        started = min(starts)
    previews = [stamp(event["at"]) for event in of("preview_ready")]
    first = (min(previews) - started).total_seconds() / 60 if started and previews else None
    return {"events": len(events), "notes": notes, "asked": len(asked), "answered": len(answered), "stray": stray,
            "sampling": sampling,
            "withdrawn": len(withdrawn), "waiting": len(asked - answered - withdrawn),
            "reasks": sum(len(ids) - 1 for ids in asks.values()), "po": sum(kinds.values()) if events else None,
            "po_kinds": kinds, "po_bad_count": bad_count, "started": started is not None, "previews": len(previews),
            "first_preview": first if first is None or first >= 0 else None, "preview_before_start": first is not None and first < 0}


def read_sampling(value):
    """(the run's sampling marker or None, what is wrong with it or None)."""
    if value is None:
        return None, None
    if not isinstance(value, dict) or value.get("version") != SAMPLING_VERSION or not isinstance(value.get("complete"), bool):
        return None, f"需要 version {SAMPLING_VERSION} 和 complete true/false；當成沒有標記"
    for key in ("counted", "kinds"):
        if value.get(key) is not None and not (isinstance(value[key], list) and all(isinstance(v, str) for v in value[key])):
            return None, f"{key} 不是文字清單；當成沒有標記"
    return value, None


def completeness(n, kind):
    """確認 / 部分 / 未知 for the numbers that come from one event type."""
    s = n["sampling"]
    if s is None:
        return "未知"
    return "確認" if s["complete"] and (s.get("counted") is None or kind in s["counted"]) else "部分"


def comparable(b, n, kind):
    """None when two runs can be compared for one event type, else why not."""
    states = (completeness(b, kind), completeness(n, kind))
    if states != ("確認", "確認"):
        return f"採樣不完整（基準 {states[0]}、本次 {states[1]}）"
    if b["sampling"].get("scenario") != n["sampling"].get("scenario"):
        return "劇本不同"
    return None


def preview_cell(n):
    if n["first_preview"] is not None:
        return f"{n['first_preview']:.1f} 分鐘"
    if n["preview_before_start"]:
        return "UNKNOWN：第一個 preview_ready 早於開始時間"
    return "UNKNOWN：" + ("沒有開始時間（run.json 的 started_at 或 run_started 事件）" if not n["started"] else "沒有 preview_ready 事件")


def run_report(folder, base_folder):
    """Print the --run section (and --compare): only reads the run folders."""
    n = run_numbers(folder)
    notes = n["notes"]
    print(f"\n# 接手演練數字\n\nrun：{folder.name}。事件 {n['events']} 筆" + (f"；重複 event_id 略過 {notes['duplicate']} 筆" if notes["duplicate"] else "")
          + (f"（其中內容不同 {notes['conflict']} 筆，取第一筆）" if notes["conflict"] else "")
          + (f"；格式不對沒算 {len(notes['bad'])} 筆：{'、'.join(notes['bad'])}" if notes["bad"] else "") + "。\n")
    if notes.get("quarantined"):
        print(f"隔離（kind 不認得，沒算）{len(notes['quarantined'])} 筆：{'、'.join(notes['quarantined'])}\n")
    if n["stray"]:
        print(f"回覆對不到發問（沒有同 decision_id + ask_id 且更早的 asked，沒算已回覆）{len(n['stray'])} 筆："
              f"{'、'.join(n['stray'])}\n")
    s = n["sampling"]
    print("採樣：" + ("沒有完整度標記（2.2 以前的 run），每個數字的完整度未知" if s is None else
                    f"version {s['version']}，{'完整' if s['complete'] else '不完整'}，劇本 {s.get('scenario') or '—'}，"
                    f"計入 {'、'.join(s['counted']) if s.get('counted') is not None else '全部類型'}") + "\n")
    print("| 指標 | 數字 | 來源 |\n|---|---|---|")
    print(f"| 第一個可用預覽 | {preview_cell(n)} | 開始時間 → 最早的 `preview_ready` |")
    decisions = (f"提出 {n['asked']}、已回覆 {n['answered']}、還在等 {n['waiting']}、撤回 {n['withdrawn']}" if n["asked"]
                 else "UNKNOWN：沒有 asked 事件")
    print(f"| 決策 | {decisions} | `asked` / `answer_received` / `withdrawn`，依 decision_id 去重 |")
    print(f"| 重問 | {n['reasks'] if n['asked'] else 'UNKNOWN：沒有 asked 事件'} | 同一 topic_id + scope_id 的不同 ask_id 數減 1 |")
    state = completeness(n, "po_action")
    if n["po"] is None:
        ops = "UNKNOWN：沒有事件"
    elif n["po"] == 0 and state != "確認":
        ops = f"UNKNOWN：沒有 po_action，採樣完整度{state}，0 可能是沒記"
    else:
        ops = (f"{n['po']}" + (f"（{'、'.join(f'{k} {v}' for k, v in sorted(n['po_kinds'].items()))}）" if n["po_kinds"] else "")
               + f"；完整度{state}")
    if n["po_bad_count"]:
        ops += f"；count 不是正整數沒算 {n['po_bad_count']} 筆"
    print(f"| PO 操作 | {ops} | `po_action`（每筆 count 次，預設 1） |")
    if base_folder is None:
        return
    b = run_numbers(base_folder)
    print(f"\n## 和基準比\n\n基準 run：{base_folder.name}。省下 = 基準 − 本次；正數是本次比較少。\n")
    print("| 指標 | 基準 | 本次 | 省下 |\n|---|---|---|---|")
    why = comparable(b, n, "po_action")
    if b["po"] is None or n["po"] is None:
        saved = "UNKNOWN：有一邊沒有事件"
    elif why:
        saved = f"UNKNOWN：{why}"
    else:
        saved = f"{b['po'] - n['po']}" + (f"（{(b['po'] - n['po']) * 100 / b['po']:.0f}%）" if b["po"]
                                          else "（百分比 UNKNOWN：基準是 0）")
    cell = lambda r: (f"{r['po']}（{completeness(r, 'po_action')}）" if r["po"] is not None else "UNKNOWN")
    print(f"| PO 操作 | {cell(b)} | {cell(n)} | {saved} |")
    both = b["first_preview"] is not None and n["first_preview"] is not None
    why = comparable(b, n, "preview_ready")
    print(f"| 第一個可用預覽 | {preview_cell(b)} | {preview_cell(n)} | "
          + (f"UNKNOWN：{why} |" if both and why else f"{b['first_preview'] - n['first_preview']:.1f} 分鐘 |" if both else "UNKNOWN |"))
    why = comparable(b, n, "asked")
    print(f"| 重問 | {b['reasks']} | {n['reasks']} | " + (f"UNKNOWN：{why} |" if b["asked"] and n["asked"] and why else
                                                        f"{b['reasks'] - n['reasks']} |" if b["asked"] and n["asked"] else "UNKNOWN |"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--director", help="the DIRECTOR folder")
    ap.add_argument("--since", metavar="YYYY-MM-DD")
    ap.add_argument("--config", help="director_work.json (default: DIRECTOR/director_work.json when it exists)")
    ap.add_argument("--run", metavar="RUN_DIR", help="a rehearsal run folder: events/*.json and run.json (docs/06b)")
    ap.add_argument("--compare", metavar="BASE_RUN_DIR", help="with --run: the baseline run to subtract from")
    a = ap.parse_args()
    if not a.director and not a.run:
        ap.error("give --director, --run, or both")
    if a.compare and not a.run:
        ap.error("--compare needs --run")
    sys.stdout.reconfigure(encoding="utf-8")
    code = director_report(a, ap) if a.director else 0
    if code == 0 and a.run:
        for folder in filter(None, (a.run, a.compare)):
            if not pathlib.Path(folder).is_dir():
                print(f"FAIL run folder not found: {folder}")
                return 1
        run_report(pathlib.Path(a.run), pathlib.Path(a.compare) if a.compare else None)
    return code


def director_report(a, ap):
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
    try:
        sys.exit(main())
    except UnicodeDecodeError as error:  # 2.2: one line and NOT_RUN (exit 2), never a traceback
        print(f"METRICS_REPORT: NOT_RUN {gate.not_utf8(error)}")
        sys.exit(2)
