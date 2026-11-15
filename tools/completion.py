"""Score how complete a work order is, item by item, and how much that moved since last week (DIRECTOR-WORK 2.3.0, N1).

Asked "how complete is it?", a model gave its own items 100 with nothing behind the number. Here an item's score is one
of 0 / 25 / 50 / 75 / 100, and 100 needs an evidence path that exists (the record of the real behaviour being checked:
a capture, a run log, a side-by-side comparison). An item written 100 without one counts as 75 and gets a WARN line.

  completion.py TABLE [--previous SNAPSHOT.json] [--save SNAPSHOT.json] [--root DIR] [--strict]

TABLE is a Markdown file with a table whose header has an ID column and a score column (ID / 編號, score / 分數), and
optionally item / 項目, evidence / 證據, critical / 關鍵, weight / 權重; or a JSON file: a list of items, or
{"items": [...]}, each {"id", "item", "score", "evidence", "critical", "weight"}.
  evidence  one or more paths (separated by `;` or `,`), relative to --root (default: the table's folder); each must be
            a non-empty file or a folder holding a file
  critical  yes / true / x / ✓ / 是 marks the item as on the critical path; the critical items not at 100 are listed
            after the table, so the next step is the one that unblocks the most
  weight    a number, default 1; the total is the weighted mean of the counted scores
  visibility  (2.3.0) how much a player sees the item: high / medium / low (高 / 中 / 低). A high item whose phase
            says it is deferred ("after alpha", 延後, later) needs a recorded owner decision in decision / 決定
            (a decision ID or a file); without one it gets a WARN: what the player sees is not pushed out unasked

--previous reads a snapshot written by --save (an earlier run, e.g. last week's) and adds a `prev` and `delta` column
and the total's delta. --save writes this run's snapshot (schema completion-v1: date, counted score per ID, total).
Prints a Markdown table, the total, the critical path and one WARN / FAIL line per problem. Exit 0; 1 when an item has
a score that is not 0/25/50/75/100, a duplicate ID or no ID, or (with --strict) any WARN; 2 when the input cannot be
read. Only reads, except --save. Not a per-turn read: run it when someone asks how far the work is, or weekly.
"""
import argparse
import datetime
import importlib.util
import json
import pathlib
import re
import sys

LEVELS = (0, 25, 50, 75, 100)
CAP = 75
HEADERS = {"id": ("id", "編號", "#"), "item": ("item", "項目", "內容", "name"), "score": ("score", "分數", "完成度"),
           "evidence": ("evidence", "證據"), "critical": ("critical", "關鍵", "關鍵路徑"), "weight": ("weight", "權重"),
           "visibility": ("visibility", "player visibility", "可見度", "玩家可見度"),
           "phase": ("phase", "when", "scope", "階段", "時程"), "decision": ("decision", "owner decision", "決定")}
VISIBILITY = {"high": "high", "medium": "medium", "low": "low", "高": "high", "中": "medium", "低": "low", "": ""}
DEFERRED = re.compile(r"after\s*-?\s*alpha|post\s*-?\s*alpha|alpha\s*(?:後|之後)|延後|deferred|later", re.I)
YES = {"yes", "y", "true", "x", "✓", "✔", "是", "1", "critical"}
SCHEMA = "completion-v1"


def gate_module():
    """gate_check.py next to this file, for its table-cell splitter (a `|` inside backticks does not split)."""
    spec = importlib.util.spec_from_file_location("gate_check", pathlib.Path(__file__).resolve().parent / "gate_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def column_of(name):
    key = name.strip().strip("*`").strip().lower()
    for field, names in HEADERS.items():
        if key in names:
            return field
    return None


def md_items(text):
    """The rows of the first table with an ID and a score column, as dicts."""
    split = gate_module().split_cells
    lines = text.splitlines()
    for i, line in enumerate(lines[:-1]):
        if not line.strip().startswith("|") or not re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
            continue
        fields = [column_of(c) for c in split(line)]
        if "id" not in fields or "score" not in fields:
            continue
        rows = []
        for row in lines[i + 2:]:
            if not row.strip().startswith("|"):
                break
            cells = split(row)
            rows.append({f: cells[n] if n < len(cells) else "" for n, f in enumerate(fields) if f})
        return rows
    raise ValueError("no Markdown table with an ID column and a score column (ID / 編號, score / 分數)")


def load_items(path):
    text = pathlib.Path(path).read_text(encoding="utf-8-sig")
    if pathlib.Path(path).suffix.lower() == ".json":
        data = json.loads(text)
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list) or not all(isinstance(x, dict) for x in items):
            raise ValueError("a JSON table is a list of items or {\"items\": [...]}, each an object")
        return items
    return md_items(text)


def blank(value):
    return str(value or "").strip().strip("*`").upper() in ("", "NONE", "-", "—", "N/A", "無")


def flag(value):
    return value is True or str(value or "").strip().strip("*`").lower() in YES


def evidence_paths(value):
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [p.strip().strip("`") for p in re.split(r"[;,]", str(value or "")) if p.strip().strip("`")
            and p.strip().strip("`").upper() not in ("NONE", "-", "—", "N/A")]


def present(path):
    """A non-empty file, or a folder holding at least one file."""
    if path.is_file():
        return path.stat().st_size > 0
    return path.is_dir() and any(p.is_file() for p in path.rglob("*"))


def score_items(items, root):
    """[(row dict with counted score), ...], [problems], [warnings]."""
    rows, problems, warnings, seen = [], [], [], set()
    for n, item in enumerate(items, 1):
        ident = str(item.get("id") or "").strip().strip("*`")
        if not ident:
            problems.append(f"row {n}: no ID")
            continue
        if ident in seen:
            problems.append(f"{ident}: duplicate ID")
            continue
        seen.add(ident)
        raw = str(item.get("score", "")).strip().rstrip("%")
        try:
            written = int(raw)
        except ValueError:
            written = None
        if written not in LEVELS:
            problems.append(f"{ident}: score {raw!r} is not one of 0/25/50/75/100")
            continue
        try:
            weight = float(item.get("weight") or 1)
        except (TypeError, ValueError):
            problems.append(f"{ident}: weight {item.get('weight')!r} is not a number")
            continue
        paths = evidence_paths(item.get("evidence"))
        missing = [p for p in paths if not present(root / p if not pathlib.Path(p).is_absolute() else pathlib.Path(p))]
        counted, note = written, ""
        if written == 100 and (not paths or missing):
            counted = CAP
            why = f"evidence not found: {', '.join(missing)}" if missing else "no evidence path"
            note = f"capped at {CAP}: {why}"
            warnings.append(f"{ident}: written 100, counted {CAP} ({why}; 100 needs the real-behaviour check's record)")
        elif missing:
            note = f"evidence not found: {', '.join(missing)}"
            warnings.append(f"{ident}: {note}")
        seen_by = VISIBILITY.get(str(item.get("visibility") or "").strip().lower())
        if seen_by is None:
            problems.append(f"{ident}: visibility {item.get('visibility')!r} is not high / medium / low")
            continue
        if seen_by == "high" and DEFERRED.search(str(item.get("phase") or "")) and blank(item.get("decision")):
            warnings.append(f"{ident}: high player visibility marked {str(item.get('phase')).strip()!r} without a "
                            "recorded owner decision (write the decision ID or file in decision / 決定)")
        rows.append({"id": ident, "visibility": seen_by, "item": str(item.get("item") or "").strip(), "written": written, "score": counted,
                     "weight": weight, "critical": flag(item.get("critical")), "evidence": paths, "note": note})
    return rows, problems, warnings


def total_of(rows):
    weight = sum(r["weight"] for r in rows)
    return round(sum(r["score"] * r["weight"] for r in rows) / weight, 1) if weight else 0.0


def cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def render(rows, previous):
    seen = any(r["visibility"] for r in rows)
    head = ["ID", "item", "score"] + (["prev", "delta"] if previous is not None else []) + ["critical"] + (
        ["visibility"] if seen else []) + ["evidence", "note"]
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        cells = [r["id"], r["item"], r["score"]]
        if previous is not None:
            before = previous.get("items", {}).get(r["id"])
            cells += ["new" if before is None else before, "" if before is None else f"{r['score'] - before:+d}"]
        cells += ["yes" if r["critical"] else ""] + ([r["visibility"]] if seen else []) + ["; ".join(r["evidence"]), r["note"]]
        out.append("| " + " | ".join(cell(c) for c in cells) + " |")
    return out


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")  # before parse_args: --help prints during parsing
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("table", help="Markdown or JSON table of work-order items")
    ap.add_argument("--previous", metavar="SNAPSHOT", help="an earlier --save snapshot, for the delta")
    ap.add_argument("--save", metavar="SNAPSHOT", help="write this run's snapshot (JSON)")
    ap.add_argument("--root", metavar="DIR", help="folder evidence paths are relative to (default: the table's folder)")
    ap.add_argument("--strict", action="store_true", help="exit 1 on any WARN too")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        items = load_items(a.table)
        previous = json.loads(pathlib.Path(a.previous).read_text(encoding="utf-8-sig")) if a.previous else None
    except (OSError, ValueError) as error:
        print(f"COMPLETION: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        return 2
    if previous is not None and (not isinstance(previous, dict) or previous.get("schema") != SCHEMA):
        print(f"COMPLETION: NOT_RUN --previous is not a {SCHEMA} snapshot (write one with --save)")
        return 2
    root = pathlib.Path(a.root) if a.root else pathlib.Path(a.table).resolve().parent
    rows, problems, warnings = score_items(items, root)
    total = total_of(rows)
    for line in render(rows, previous):
        print(line)
    print()
    delta = f" (prev {previous.get('total')}, delta {total - float(previous.get('total') or 0):+.1f})" if previous else ""
    print(f"TOTAL: {total}{delta} items={len(rows)} capped={sum(r['note'].startswith('capped') for r in rows)}")
    if previous is not None:
        gone = sorted(set(previous.get("items", {})) - {r["id"] for r in rows})
        if gone:
            warnings.append(f"in the previous snapshot, not in this table: {', '.join(gone)}")
    open_critical = [r for r in rows if r["critical"] and r["score"] < 100]
    print("CRITICAL_PATH: " + (" -> ".join(f"{r['id']} ({r['score']})" for r in open_critical) if open_critical
                               else "all critical items at 100" if any(r["critical"] for r in rows) else "none marked"))
    for w in warnings:
        print(f"WARN {w}")
    for p in problems:
        print(f"FAIL {p}")
    if a.save:
        snapshot = {"schema": SCHEMA, "date": datetime.date.today().isoformat(), "table": pathlib.Path(a.table).name,
                    "items": {r["id"]: r["score"] for r in rows}, "total": total}
        pathlib.Path(a.save).write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"SAVED {a.save}")
    return 1 if problems or (a.strict and warnings) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, UnicodeError, ValueError) as error:  # one line, never a Traceback
        print(f"COMPLETION: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        sys.exit(2)
