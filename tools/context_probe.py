"""Free probe of a session's fixed context cost. Does NOT call the model and spends no quota.

It starts `claude` in stream-json mode, sends only two control requests (initialize, get_context_usage)
and reads the get_context_usage answer: token categories, autoCompactThreshold, memory files, skills.
It waits --wait seconds between the two requests: asked at once, MCP servers are not connected yet and
their tools and instructions are missing from the numbers. Run it from (or with --cwd) the project folder
whose settings you want to see.

Never measure with `claude -p "/context"`: that really calls the model and spends quota.
"""
import argparse
import json
import shutil
import subprocess
import sys
import threading
import time

INIT = '{"type":"control_request","request_id":"i1","request":{"subtype":"initialize"}}\n'
ASK = '{"type":"control_request","request_id":"c1","request":{"subtype":"get_context_usage"}}\n'


def rows_of(value):
    if isinstance(value, dict):
        for key in ("skillFrontmatter", "files", "tools", "items"):
            if isinstance(value.get(key), list):
                return value[key]
        return []
    return value if isinstance(value, list) else []


def find_answer(lines):
    for line in list(lines):
        if '"c1"' not in line:
            continue
        try:
            r = json.loads(line).get("response", {})
        except ValueError:
            continue
        return r.get("response", r) if isinstance(r, dict) else None
    return None


def ask(args, cwd, wait, timeout):
    p = subprocess.Popen(args, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, encoding="utf-8", errors="replace")
    lines = []
    reader = threading.Thread(target=lambda: lines.extend(p.stdout), daemon=True)
    reader.start()
    resp = None
    try:
        p.stdin.write(INIT)
        p.stdin.flush()
        time.sleep(wait)
        p.stdin.write(ASK)
        p.stdin.flush()
        end = time.time() + timeout
        while resp is None and time.time() < end:
            resp = find_answer(lines)
            if resp is None and p.poll() is not None:
                reader.join(2)
                resp = find_answer(lines)
                break
            time.sleep(0.5)
    except OSError:  # claude exited before reading stdin
        resp = find_answer(lines)
    finally:
        for close in (p.stdin.close, p.terminate):
            try:
                close()
            except OSError:
                pass
    return resp


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--claude", help="path to the claude executable (default: 'claude' from PATH)")
    ap.add_argument("--cwd", default=".", help="project folder to probe (default: current folder)")
    ap.add_argument("--model", help="optional --model passed to claude (only selects; still no model call)")
    ap.add_argument("--top", type=int, default=8, help="how many memory files / skills to list (default 8)")
    ap.add_argument("--wait", type=float, default=20, help="seconds to let MCP servers connect before asking (default 20)")
    ap.add_argument("--timeout", type=int, default=150, help="seconds to wait for the answer (default 150)")
    ap.add_argument("--json-out", help="also save the raw get_context_usage response to this file")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    exe = a.claude or shutil.which("claude")
    if not exe:
        sys.exit("claude executable not found; pass --claude <path>")
    args = [exe, "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
            "--no-session-persistence"] + (["--model", a.model] if a.model else [])
    resp = ask(args, a.cwd, a.wait, a.timeout)
    if not isinstance(resp, dict):
        print("NO_ANSWER: get_context_usage did not answer (old CLI version, login needed, or timeout).")
        return 1
    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as fh:
            json.dump(resp, fh, ensure_ascii=False, indent=2)

    print(f"probe: control requests only, no model call; asked after {a.wait:g}s")
    for k, v in resp.items():  # scalar fields: totalTokens, maxTokens, autoCompactThreshold, ...
        if isinstance(v, (int, float, str, bool)):
            print(f"{k}: {v}")
    cats = [c for c in resp.get("categories", []) if isinstance(c, dict)]
    if cats:
        print("categories (tokens):")
        for c in sorted(cats, key=lambda c: -(c.get("tokens") or 0)):
            note = "  (not in totalTokens)" if "deferred" in str(c.get("name", "")).lower() else ""
            print(f"  {c.get('tokens', 0):>9}  {c.get('name')}{note}")
    for key in ("memoryFiles", "skills", "agents", "mcpTools"):
        rows = [x for x in rows_of(resp.get(key)) if isinstance(x, dict)]
        if not rows:
            continue
        rows.sort(key=lambda x: -(x.get("tokens") or 0))
        total = sum(x.get("tokens") or 0 for x in rows)
        print(f"{key}: {len(rows)} entries, {total} tokens; top {min(a.top, len(rows))}:")
        for x in rows[:a.top]:
            print(f"  {x.get('tokens', 0):>9}  {x.get('path') or x.get('name') or x.get('agentType')}")
    if not any("mcp" in str(c.get("name", "")).lower() and c.get("tokens") for c in cats):
        print(f"note: no MCP tokens; if this project uses MCP servers, rerun with a larger --wait (now {a.wait:g})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
