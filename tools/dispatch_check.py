"""Check the Director's dispatch records before and after dispatching (2.5.0). Only reads; warns by default.

Effort per dispatch (N1, lesson: work was dispatched without setting effort by difficulty). Every DISPATCH line in
DIRECTOR_LOG.md names the difficulty class and the effort it set, in its `| basis` column:

  DISPATCH WO-012 rev=1 sha=<64 hex> | class=dev effort=high model=opus

The default table (docs/05; levels as in the official Claude Code effort docs: low medium high xhigh max):

  routine                                  medium high
  dev, ui                                  high
  root_cause, fix_after_fail, realism, core_engine   xhigh
  repeated_failure                         xhigh max    (max only after repeated failure, then back down)

A record without class= or effort=, an unknown class or level, or an effort outside the table prints
`~ WARN EFFORT <WO-ID> line <n>: ...`. `--table FILE` replaces the table (JSON {"class": ["level", ...]}).

  dispatch_check.py --log DIRECTOR_LOG.md [--table FILE] [--strict]

Last line `DISPATCH_CHECK: OK|WARN records=n warnings=n`. Exit 0 (warnings included) unless --strict, then 1 on a
warning; 2 on an input error (missing file, bad table).
"""
import argparse
import json
import pathlib
import re
import sys

LEVELS = ("low", "medium", "high", "xhigh", "max")
TABLE = {
    "routine": ["medium", "high"],
    "dev": ["high"],
    "ui": ["high"],
    "root_cause": ["xhigh"],
    "fix_after_fail": ["xhigh"],
    "realism": ["xhigh"],
    "core_engine": ["xhigh"],
    "repeated_failure": ["xhigh", "max"],
}
# a DISPATCH event line as gate_check reads it: optional `<date> |` column, the event, optional `| basis` columns
DISPATCH = re.compile(r"^(?:[^|`]*\|[ \t]*)?DISPATCH[ \t]+([^\s|`]+?)(?:\.md)?[ \t]+rev=\d+[ \t]+sha=[0-9a-fA-F]{64}"
                      r"[ \t]*(\|[^`]*)?$")
FIELD = re.compile(r"\b(class|effort|model)\s*=\s*([^\s|]+)")


def load_table(path):
    if not path:
        return TABLE
    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict) or not raw or not all(
            isinstance(k, str) and isinstance(v, list) and v and all(x in LEVELS for x in v) for k, v in raw.items()):
        raise ValueError('want {"class": ["level", ...]} with levels from ' + " ".join(LEVELS))
    return raw


def dispatch_records(text):
    """(line number, order id, {class, effort, model}) for every DISPATCH event line."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        m = DISPATCH.match(line.rstrip())
        if m:
            out.append((n, m.group(1), {k.lower(): v.lower() for k, v in FIELD.findall(m.group(2) or "")}))
    return out


def effort_warnings(records, table):
    warns = []
    for n, wo, fields in records:
        cls, effort = fields.get("class"), fields.get("effort")
        where = f"{wo} line {n}"
        if not cls or not effort:
            missing = " and ".join(k + "=" for k in ("class", "effort") if not fields.get(k))
            warns.append(f"~ WARN EFFORT {where}: no {missing} (write `| class=<class> effort=<level>` on the DISPATCH line)")
        elif cls not in table:
            warns.append(f"~ WARN EFFORT {where}: unknown class={cls} (known: {' '.join(table)})")
        elif effort not in LEVELS:
            warns.append(f"~ WARN EFFORT {where}: unknown effort={effort} (levels: {' '.join(LEVELS)})")
        elif effort not in table[cls]:
            warns.append(f"~ WARN EFFORT {where}: class={cls} wants effort {'/'.join(table[cls])}, got {effort}")
    return warns


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Check dispatch records: effort per difficulty class (warn only).",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--log", required=True, metavar="FILE", help="DIRECTOR_LOG.md with the DISPATCH lines")
    ap.add_argument("--table", metavar="FILE", help='JSON {"class": ["level", ...]} replacing the default table')
    ap.add_argument("--strict", action="store_true", help="exit 1 when there is a warning")
    a = ap.parse_args(argv)
    try:
        table = load_table(a.table)
        text = pathlib.Path(a.log).read_text(encoding="utf-8-sig")
    except (OSError, ValueError) as error:
        print(f"FAIL input: {type(error).__name__}: {error}")
        return 2
    records = dispatch_records(text)
    warns = effort_warnings(records, table)
    for w in warns:
        print(w)
    print(f"DISPATCH_CHECK: {'WARN' if warns else 'OK'} records={len(records)} warnings={len(warns)}")
    return 1 if warns and a.strict else 0


if __name__ == "__main__":
    sys.exit(main())
