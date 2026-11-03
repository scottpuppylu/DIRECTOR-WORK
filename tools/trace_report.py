"""Build the trace table requirement -> work order -> AC -> evidence -> verdict from the files that already exist,
so nobody keeps a separate table up to date. Only reads; prints Markdown.

  trace_report.py --orders DIRECTOR/orders --reports <folder> [--verdicts DIRECTOR/reviews] [--config director_work.json]

An order is a .md file with ISSUED_BY; it lists what it serves in `TRACES_TO = DD-03, OD-12` (NONE when nothing).
A report (a .md file with TASK_ID) belongs to the order whose file name its `ORDER:` line holds, else to the order
whose ID its TASK_ID starts with; a verdict (a .md file with `## A`) to the order whose ID its title holds. When
several match, the last by path is shown. `trace_id_pattern` in the config (a regex) flags IDs written in another
format; without it every ID is accepted. Exit 0, or 1 when a folder is missing.
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


def files(folder, marker):
    return [(path, path.read_text(encoding="utf-8-sig")) for path in sorted(pathlib.Path(folder).rglob("*.md"))
            if re.search(marker, path.read_text(encoding="utf-8-sig"), re.M)]


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


def cell(value):
    return (value or "").replace("|", "/").strip() or "—"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--orders", required=True)
    ap.add_argument("--reports", required=True)
    ap.add_argument("--verdicts")
    ap.add_argument("--config")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    missing = [f for f in (a.orders, a.reports, a.verdicts) if f and not pathlib.Path(f).is_dir()]
    if missing:
        print(f"FAIL folder not found: {', '.join(missing)}")
        return 1
    cfg = json.loads(pathlib.Path(a.config).read_text(encoding="utf-8-sig")) if a.config else {}
    if cfg.get("schema_version", 1) != CONFIG_VERSION:
        sys.exit(f"{a.config}: schema_version {cfg['schema_version']} is not {CONFIG_VERSION}; see CHANGELOG.md")
    pattern = re.compile(cfg["trace_id_pattern"]) if cfg.get("trace_id_pattern") else None

    orders = []
    for path, text in files(a.orders, r"^\s*ISSUED_BY\s*="):
        m = re.search(r"^\s*TRACES_TO\s*=\s*([^#\n]*)", text, re.M)
        ids = [i for i in re.split(r"[\s,，、]+", m.group(1)) if i and i.upper() != "NONE"] if m else None
        orders.append({"path": path, "id": first_id(text, path.stem), "traces": ids, "acs": gate.ac_table(text),
                       "report": None, "verdict": None})
    stray = []
    for path, text in files(a.reports, r"^\s*TASK_ID\b"):
        order = owner(orders, text, by_name=True)
        if order:
            order["report"] = gate.ac_table(text)
        else:
            stray.append(path)
    for path, text in files(a.verdicts, r"^##\s*A\b") if a.verdicts else []:
        order = owner(orders, text, by_name=False)
        section = re.search(r"^##\s*A\b.*?$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
        lines = [line.strip() for line in section.group(1).splitlines() if line.strip()] if section else []
        if order:
            order["verdict"] = lines[0] if lines else "—"

    rows = []
    for order in orders:
        for req in order["traces"] or ["（無）"]:
            for ac, spec_row in order["acs"].items():
                got = order["report"].get(ac) if order["report"] is not None else None
                status = got.get("status") if got else "沒有報告" if order["report"] is None else "報告缺這條"
                rows.append((req, order["id"], ac, spec_row.get("type"), status, got and got.get("evidence"), order["verdict"]))
    print(f"# 追溯表\n\n工單 {len(orders)} 份，報告 {sum(o['report'] is not None for o in orders)} 份對到工單。\n")
    print("| 需求 | 工單 | AC | 類型 | 狀態 | 證據 | 裁決 |\n|---|---|---|---|---|---|---|")
    for row in sorted(rows, key=lambda r: (r[0] == "（無）", r[0], r[1], r[2])):
        print("| " + " | ".join(cell(v) for v in row) + " |")
    untraced = [o["id"] for o in orders if o["traces"] is None]
    odd = [f"{o['id']}: {i}" for o in orders for i in o["traces"] or [] if pattern and not pattern.fullmatch(i)]
    for title, items in (("沒有 TRACES_TO 的工單", untraced), ("編號格式不符 trace_id_pattern", odd),
                         ("對不到工單的報告", [str(p) for p in stray])):
        print(f"\n## {title}\n" + ("\n".join(f"- {i}" for i in items) if items else "- 無"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
