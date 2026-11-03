"""Free probe of a session's fixed context cost. Does NOT call the model and spends no quota.

It starts `claude` in stream-json mode, sends only two control requests (initialize, get_context_usage),
closes stdin and reads the get_context_usage answer: token categories, autoCompactThreshold, memory files,
skills. Run it from (or with --cwd) the project folder whose settings you want to see.

Never measure with `claude -p "/context"`: that really calls the model and spends quota.
"""
import argparse
import json
import shutil
import subprocess
import sys

REQ = ('{"type":"control_request","request_id":"i1","request":{"subtype":"initialize"}}\n'
       '{"type":"control_request","request_id":"c1","request":{"subtype":"get_context_usage"}}\n')


def rows_of(value):
    if isinstance(value, dict):
        for key in ("skillFrontmatter", "files", "tools", "items"):
            if isinstance(value.get(key), list):
                return value[key]
        return []
    return value if isinstance(value, list) else []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--claude", help="path to the claude executable (default: 'claude' from PATH)")
    ap.add_argument("--cwd", default=".", help="project folder to probe (default: current folder)")
    ap.add_argument("--model", help="optional --model passed to claude (only selects; still no model call)")
    ap.add_argument("--top", type=int, default=8, help="how many memory files / skills to list (default 8)")
    ap.add_argument("--timeout", type=int, default=150, help="seconds to wait (default 150)")
    ap.add_argument("--json-out", help="also save the raw get_context_usage response to this file")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    exe = a.claude or shutil.which("claude")
    if not exe:
        sys.exit("claude executable not found; pass --claude <path>")
    args = [exe, "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
            "--no-session-persistence"] + (["--model", a.model] if a.model else [])
    try:
        out = subprocess.run(args, input=REQ, cwd=a.cwd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=a.timeout).stdout
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")

    resp = None
    for line in out.splitlines():
        if '"c1"' not in line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        r = o.get("response", {})
        resp = r.get("response", r) if isinstance(r, dict) else None
        break
    if not isinstance(resp, dict):
        print("NO_ANSWER: get_context_usage did not answer (old CLI version, login needed, or timeout).")
        return 1
    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as fh:
            json.dump(resp, fh, ensure_ascii=False, indent=2)

    print("probe: control requests only, no model call")
    for k, v in resp.items():  # scalar fields: totalTokens, maxTokens, autoCompactThreshold, ...
        if isinstance(v, (int, float, str, bool)):
            print(f"{k}: {v}")
    cats = [c for c in resp.get("categories", []) if isinstance(c, dict)]
    if cats:
        print("categories (tokens):")
        for c in sorted(cats, key=lambda c: -(c.get("tokens") or 0)):
            print(f"  {c.get('tokens', 0):>9}  {c.get('name')}")
    for key in ("memoryFiles", "skills", "agents", "mcpTools"):
        rows = [x for x in rows_of(resp.get(key)) if isinstance(x, dict)]
        if not rows:
            continue
        rows.sort(key=lambda x: -(x.get("tokens") or 0))
        total = sum(x.get("tokens") or 0 for x in rows)
        print(f"{key}: {len(rows)} entries, {total} tokens; top {min(a.top, len(rows))}:")
        for x in rows[:a.top]:
            print(f"  {x.get('tokens', 0):>9}  {x.get('path') or x.get('name')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
