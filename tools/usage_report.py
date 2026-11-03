"""Usage numbers from local Claude Code transcripts. Prints counts only; message content is never printed.

Reads ~/.claude/projects/<project-dir>/**/*.jsonl (subagent transcripts included) and sums the `usage`
fields: calls, context size per call (input + cache read + cache creation), distribution, models,
large cache rebuilds, compactions, tool-result size per tool, images per tool, main vs subagent.

<project-dir> is the folder name Claude Code uses for a project: the start folder's path with every
character that is not a letter or digit replaced by '-'. Without --project-dir the current folder is used.
"""
import argparse
import collections as C
import datetime as D
import json
import os
import pathlib
import re
import sys


def project_dir_name(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(pathlib.Path(path).resolve()))


def stamp(o):
    try:
        return D.datetime.fromisoformat(o["timestamp"].replace("Z", "+00:00"))
    except Exception:
        return None


def pct(sizes, q):
    return sizes[min(len(sizes) - 1, int(len(sizes) * q))] if sizes else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-dir", action="append", default=[],
                    help="project folder name under the projects root, or a full path (repeatable)")
    ap.add_argument("--root", default=str(pathlib.Path.home() / ".claude" / "projects"),
                    help="projects root (default ~/.claude/projects)")
    ap.add_argument("--since", help="YYYY-MM-DD (UTC); only entries from then on")
    ap.add_argument("--all", action="store_true", help="every project under the root")
    ap.add_argument("--json-out", help="also write the numbers as JSON to this file")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    root = pathlib.Path(a.root)
    if a.all:
        dirs = [p for p in root.iterdir() if p.is_dir()] if root.is_dir() else []
    else:
        names = a.project_dir or [project_dir_name(os.getcwd())]
        dirs = [pathlib.Path(n) if pathlib.Path(n).is_absolute() else root / n for n in names]
    since = D.datetime.fromisoformat(a.since).replace(tzinfo=D.timezone.utc) if a.since else None

    tot, buckets, model, tool_calls, tool_chars, tool_imgs = (C.Counter() for _ in range(6))
    big_create, gap_create, part = C.Counter(), C.Counter(), {"main": C.Counter(), "subagent": C.Counter()}
    sizes, first_ctx, per_turn = [], [], []
    compacts = files = 0
    for d in dirs:
        if not d.is_dir():
            print(f"NOT_FOUND {d.name}")
            continue
        for f in d.rglob("*.jsonl"):
            if since and os.path.getmtime(f) < since.timestamp():
                continue
            files += 1
            kind = "subagent" if "subagents" in f.as_posix() else "main"
            seen, id2tool, last, first, calls_turn = set(), {}, None, True, 0
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"usage"' not in line and '"tool_result"' not in line and "compact_boundary" not in line \
                            and '"type":"user"' not in line and '"tool_use"' not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except ValueError:
                        continue
                    ts = stamp(o)
                    if ts is None or (since and ts < since):
                        continue
                    if o.get("subtype") == "compact_boundary":
                        compacts += 1
                    m = o.get("message") if isinstance(o.get("message"), dict) else {}
                    content = m.get("content")
                    if o.get("type") == "user":
                        is_result = isinstance(content, list) and any(
                            isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
                        if not is_result:
                            if calls_turn:
                                per_turn.append(calls_turn)
                            calls_turn = 0
                        for b in content if isinstance(content, list) else []:
                            if not (isinstance(b, dict) and b.get("type") == "tool_result"):
                                continue
                            name = id2tool.get(b.get("tool_use_id"), "?")
                            c = b.get("content")
                            if isinstance(c, str):
                                tool_chars[name] += len(c)
                            for x in c if isinstance(c, list) else []:
                                if isinstance(x, dict) and x.get("type") == "image":
                                    tool_imgs[name] += 1
                                elif isinstance(x, dict):
                                    tool_chars[name] += len(x.get("text") or "")
                        continue
                    if o.get("type") != "assistant":
                        continue
                    for b in content if isinstance(content, list) else []:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            id2tool[b.get("id")] = b.get("name", "?")
                            tool_calls[b.get("name", "?")] += 1
                    u = m.get("usage")
                    key = m.get("id") or o.get("requestId")
                    if not u or key in seen:
                        continue
                    seen.add(key)
                    calls_turn += 1
                    inp, cr, cc, out = (u.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens",
                                                                 "cache_creation_input_tokens", "output_tokens"))
                    ctx = inp + cr + cc
                    tot["calls"] += 1
                    tot["input"] += inp
                    tot["cache_read"] += cr
                    tot["cache_create"] += cc
                    tot["output"] += out
                    part[kind]["calls"] += 1
                    part[kind]["context"] += ctx
                    model[m.get("model", "?")] += ctx
                    sizes.append(ctx)
                    b = ("<100k" if ctx < 1e5 else "100-250k" if ctx < 2.5e5 else "250-500k" if ctx < 5e5
                         else "500-750k" if ctx < 7.5e5 else ">=750k")
                    buckets[b] += 1
                    buckets[b + " tokens"] += ctx
                    if first and kind == "main":
                        first_ctx.append(ctx)
                    first = False
                    if cc > 50000:
                        gap = (ts - last).total_seconds() / 60 if last else None
                        g = "start" if gap is None else "gap<5m" if gap < 5 else "gap5-60m" if gap < 60 else "gap>60m"
                        big_create["count"] += 1
                        big_create["tokens"] += cc
                        gap_create[g] += 1
                    last = ts
            if calls_turn:
                per_turn.append(calls_turn)
    if not sizes:
        print(f"NO_DATA: no usage records found (files: {files}); this is not a measured 0")
        return 1
    sizes.sort()
    first_ctx.sort()
    per_turn.sort()
    ctx_total = sum(sizes) or 1
    res = {
        "files": files, "totals": dict(tot), "compactions": compacts,
        "main_vs_subagent": {k: dict(v) for k, v in part.items()},
        "context_per_call": {"median": pct(sizes, .5), "p90": pct(sizes, .9),
                             "mean": round(ctx_total / len(sizes)) if sizes else None},
        "context_buckets": {k: buckets[k] for k in ("<100k", "100-250k", "250-500k", "500-750k", ">=750k")},
        "share_of_context_from_calls_>=250k": round(sum(s for s in sizes if s >= 2.5e5) / ctx_total, 3),
        "context_by_model": dict(model.most_common()),
        "large_cache_rebuilds_>50k": dict(big_create), "rebuild_gap_since_previous_call": dict(gap_create),
        "first_call_context_main": {"n": len(first_ctx), "median": pct(first_ctx, .5)},
        "calls_per_user_turn": {"median": pct(per_turn, .5), "p90": pct(per_turn, .9), "turns": len(per_turn)},
        "tool_calls": dict(tool_calls.most_common(15)),
        "tool_result_chars": dict(tool_chars.most_common(10)),
        "tool_result_images": dict(tool_imgs.most_common(8)),
    }
    for k, v in res.items():
        print(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=2)
    return 0 if files else 1


if __name__ == "__main__":
    sys.exit(main())
