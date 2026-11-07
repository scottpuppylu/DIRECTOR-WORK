"""Where the quota goes, by what each call chose to do. Prints shares only; message content is never printed.

Reads the local Claude Code transcripts (~/.claude/projects/<project-dir>/**/*.jsonl, subagent transcripts included)
and gives every model call its cost in quota-equivalent units:

    input 1 + cache write 1.25 + cache read 0.1 + output 5   (per token)

A call's cost is split equally over the tool calls it chose (none: `text_reply`). One message.id can be written as
several lines (the usage on one, the tool calls on the next); they are merged first, otherwise most of the cost lands
on `text_reply` (lesson L-035). A message.id seen in an earlier file (a forked or resumed session) is counted once.

Each tool call gets a fine category, and the fine categories add up to five groups:

    讀和查       shell_other file_ops shell_search sys_query log_check list_files git search read_code read_md
                 read_data disk web
    協調         coord_msg plan_ui po_page subagent_spawn text_reply write_resume write_md other
    看圖與審查   view_image review_read review_tools
    實際動手     edit_code edit_py write_other render engine_run engine_mcp python_other build
    等待         wait wait_board

A Bash / PowerShell command takes the first of: wait_board render engine_run log_check git disk, then a python run
(python_other, or review_tools when it names a review tool), build (compile / build / package tools), list_files,
shell_search (grep, rg, findstr, Select-String), file_ops (cat, sed, cp, mv, mkdir, rm, echo, Copy-Item, Set-Content
...), sys_query (processes, versions, environment, network); what is left is shell_other (1.3.1).

The targets (DD-049) are 讀和查 <= 30% and 實際動手 >= 30%. With --check the exit is 1 when either is missed.

RESTART lines measure whether opening a new session saves anything (docs/04): the context of a new session's first
call, how many calls and how much quota pass from a new session (or a compaction) until the first 實際動手 call, the
cost per call by context size, and the break-even point that follows from them.

--by-session prints one line per session (a session's subagents count with it): its share of the total, calls,
quota, its five group shares and its costliest fine categories (1.3.1).

--patterns FILE adds project words to the shell and file patterns (a game's exe, its review tool), so the defaults
stay generic:  {"schema_version": 1, "patterns": {"engine_run": "mygame\\\\.exe"}, "groups": {"write_md": "實際動手"}}
A pattern is a regular expression OR-ed with the default one; `groups` moves a fine category to another group.

Times are UTC: --since / --until take YYYY-MM-DD or an ISO time (2026-11-06T10:00, offsets allowed).
The transcript format is not an official interface; when nothing is read the result is NO_DATA, never a measured 0.
"""
import argparse
import collections as C
import datetime as D
import json
import os
import pathlib
import re
import statistics
import sys

WEIGHTS = {"input_tokens": 1.0, "cache_creation_input_tokens": 1.25, "cache_read_input_tokens": 0.1, "output_tokens": 5.0}
GROUPS = ("讀和查", "協調", "看圖與審查", "實際動手", "等待")
GROUP_OF = {}
for _group, _names in (
        ("讀和查", "shell_other file_ops shell_search sys_query log_check list_files git search read_code read_md "
                   "read_data disk web"),
        ("協調", "coord_msg plan_ui po_page subagent_spawn text_reply write_resume write_md other"),
        ("看圖與審查", "view_image review_read review_tools"),
        ("實際動手", "edit_code edit_py write_other render engine_run engine_mcp python_other build"),
        ("等待", "wait wait_board")):
    for _name in _names.split():
        GROUP_OF[_name] = _group
TARGETS = {"讀和查": ("<=", 0.30), "實際動手": (">=", 0.30)}
PATTERN_KEYS = ("wait_board", "render", "engine_run", "log_check", "git", "disk", "review_tools", "list_files",
                "review_read", "engine_mcp", "python", "build", "shell_search", "file_ops", "sys_query")
DEFAULT_PATTERNS = {
    "wait_board": r"board\.py|gpu_queue|quietwait|start-sleep|\bsleep\b|wait_go|idle_watch",
    "render": r"blender",
    "engine_run": r"unity\.exe|-batchmode|-executemethod|unity_capture|player\.exe|godot|unrealeditor",
    "log_check": r"\btail\b|-tail\b|\.log\b|get-content|\bgc\b",
    "git": r"\bgit\b",
    "disk": r"\bdf\b|get-psdrive|freespace|get-volume|\bdu -",
    "review_tools": r"review|pack|contact|crop|zoom|diff|eye|sheet|manifest|blind",
    "list_files": r"\bls\b|get-childitem|\bfind\b|test-path|\bdir\b",
    "review_read": r"review|pack|blind|answer_key",
    "engine_mcp": r"^mcp__(blender|unity|godot|unreal)",
    # 1.3.1: what used to be shell_other
    "python": r"python|\bpy(\.exe)?\s+-|\bpytest\b|\buv\s+run\b|(^|[;&|(]\s*)[\w./\\:-]*\.py\b",
    "build": r"\b(make|cmake|msbuild|dotnet|cargo|gradlew?|mvn|tsc|gcc|clang|ninja|npm|npx|pnpm|yarn|node|rustc|javac"
             r"|xcodebuild|pip3?|bazel|meson|webpack|vite|esbuild)\b|\bg\+\+|\bgo\s+(build|test|run|vet)\b"
             r"|\bswift\s+(build|test)\b|\buv\s+(pip|sync|build|lock)\b",
    "shell_search": r"\b(grep|egrep|fgrep|rg|findstr|ack)\b|select-string|\bsls\b",
    "file_ops": r"\b(cat|head|sed|awk|cp|mv|mkdir|rm|rmdir|touch|wc|echo|printf|tee|ln|chmod|stat|sort|uniq|cut|tr"
                r"|xargs|diff|cmp|tar|zip|unzip|7z|sha256sum|md5sum|type|copy|move|del|ren|robocopy|xcopy)\b"
                r"|copy-item|move-item|new-item|remove-item|rename-item|set-content|add-content|out-file|get-filehash"
                r"|get-item|expand-archive|compress-archive|resolve-path|split-path|join-path|write-output",
    "sys_query": r"get-process|tasklist|\bps\b|nvidia-smi|get-ciminstance|get-wmiobject|\bwmic\b|\bwhere(\.exe)?\b"
                 r"|\bwhich\b|get-command|\$env:|\bprintenv\b|\bwhoami\b|\bhostname\b|\bdate\b|get-date|\buname\b"
                 r"|systeminfo|--version|\$psversiontable|get-itemproperty|\breg\s+query\b|\bnetstat\b"
                 r"|get-nettcpconnection|test-netconnection|\bcurl\b|invoke-webrequest|\bping\b",
}
IMAGE = re.compile(r"\.(png|jpe?g|webp|gif|bmp)$", re.I)
CODE_EXT = (".cs", ".shader", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".swift", ".c", ".cc",
            ".cpp", ".h", ".hpp", ".gd", ".lua", ".rb")
BUCKETS = (("<60K", 60e3), ("60-120K", 120e3), ("120-170K", 170e3), (">=170K", float("inf")))
RESET = 0.6       # a call whose context is below 60% of the previous one follows a compaction
ORIENT_CAP = 400  # calls looked at after a start before giving up on finding a 實際動手 call


class PatternError(ValueError):
    pass


def load_patterns(path=None):
    """The compiled patterns and the fine -> group map, with a --patterns file merged in."""
    texts, groups = dict(DEFAULT_PATTERNS), dict(GROUP_OF)
    if path:
        try:
            data = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as e:
            raise PatternError(f"cannot read {path}: {e}")
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise PatternError(f"{path}: schema_version must be 1")
        for key, extra in (data.get("patterns") or {}).items():
            if key not in PATTERN_KEYS or not isinstance(extra, str) or not extra:
                raise PatternError(f"{path}: patterns.{key}: the keys are {', '.join(PATTERN_KEYS)}, each a non-empty string")
            texts[key] = f"{texts[key]}|{extra}"
        for fine, group in (data.get("groups") or {}).items():
            if fine not in GROUP_OF or group not in GROUPS:
                raise PatternError(f"{path}: groups.{fine}: a fine category ({', '.join(sorted(GROUP_OF))}) "
                                   f"mapped to one of {', '.join(GROUPS)}")
            groups[fine] = group
    compiled = {}
    for key, text in texts.items():
        try:
            compiled[key] = re.compile(text, re.I)
        except re.error as e:
            raise PatternError(f"pattern {key}: {e}")
    return compiled, groups


def classify(name, inp, pats):
    """The fine category of one tool call."""
    inp = inp if isinstance(inp, dict) else {}
    if name in ("SendMessage", "ListAgents", "ReadNotifications", "FetchInboxMessage") or "send_message" in name:
        return "coord_msg"
    if "update_plan" in name or "wrap_up" in name or "mark_chapter" in name:
        return "plan_ui"
    if name in ("Artifact", "ArtifactData", "ArtifactComments"):
        return "po_page"
    if name in ("Agent", "Task"):
        return "subagent_spawn"
    if name in ("TaskOutput", "TaskStop", "Monitor", "ScheduleWakeup"):
        return "wait"
    if name in ("Bash", "PowerShell"):
        cmd = str(inp.get("command", "")).lower()
        for key in ("wait_board", "render", "engine_run", "log_check", "git", "disk"):
            if pats[key].search(cmd):
                return key
        if pats["python"].search(cmd):
            return "review_tools" if pats["review_tools"].search(cmd) else "python_other"
        for key in ("build", "list_files", "shell_search", "file_ops", "sys_query"):
            if pats[key].search(cmd):
                return key
        return "shell_other"
    path = str(inp.get("file_path") or inp.get("notebook_path") or "").replace("\\", "/").lower()
    if name == "Read":
        if IMAGE.search(path):
            return "view_image"
        if pats["review_read"].search(path):
            return "review_read"
        if path.endswith(".md"):
            return "read_md"
        if path.endswith((".py",) + CODE_EXT):
            return "read_code"
        return "read_data"
    if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        if "resume_state" in path:
            return "write_resume"
        if path.endswith(".py"):
            return "edit_py"
        if path.endswith(CODE_EXT):
            return "edit_code"
        if path.endswith(".md"):
            return "write_md"
        return "write_other"
    if name in ("Grep", "Glob", "ToolSearch"):
        return "search"
    if pats["engine_mcp"].search(name):
        return "engine_mcp"
    if any(w in name for w in ("Browser", "chrome", "WebFetch", "WebSearch", "exa")):
        return "web"
    return "other"


def parse_time(text, end=False):
    """UTC datetime from YYYY-MM-DD or an ISO time; a bare --until date means the end of that day."""
    if text is None:
        return None
    t = D.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=D.timezone.utc)
    if end and re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        t += D.timedelta(days=1)
    return t


def stamp(o):
    try:
        return D.datetime.fromisoformat(str(o["timestamp"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None


def project_dir_name(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(pathlib.Path(path).resolve()))


def transcript_files(root, project_dirs=None):
    """(path, session id, is subagent) for every transcript, sorted so a repeated message id goes to the same file."""
    root = pathlib.Path(root)
    dirs = [pathlib.Path(d) if pathlib.Path(d).is_absolute() else root / d for d in project_dirs] if project_dirs \
        else sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    out = []
    for d in dirs:
        for f in sorted(d.rglob("*.jsonl")) if d.is_dir() else []:
            parts = f.relative_to(d).parts
            sub = "subagents" in parts
            sid = parts[parts.index("subagents") - 1] if sub and parts.index("subagents") else f.stem
            out.append((f, sid, sub))
    return out


def read_calls(path, pats, since=None, until=None, seen=None):
    """The model calls of one transcript in order, fragments merged: dicts with id, ctx, eq, cats, time.
    Also returns the session title and whether a call before --since was dropped."""
    seen = set() if seen is None else seen
    calls, by_id, title, dropped = [], {}, None, False
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"customTitle"' in line:
                try:
                    title = json.loads(line).get("customTitle") or title
                except ValueError:
                    pass
            if '"assistant"' not in line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("type") != "assistant":
                continue
            m = o.get("message") if isinstance(o.get("message"), dict) else {}
            mid = m.get("id") or o.get("requestId") or o.get("uuid")
            content = m.get("content") if isinstance(m.get("content"), list) else []
            cats = [classify(b.get("name", ""), b.get("input"), pats) for b in content
                    if isinstance(b, dict) and b.get("type") == "tool_use"]
            usage = m.get("usage") if isinstance(m.get("usage"), dict) else {}
            if mid in by_id:  # a later fragment of the same message
                call = by_id[mid]
                call["cats"].extend(cats)
                for k in WEIGHTS:
                    call["usage"][k] = max(call["usage"].get(k, 0), usage.get(k) or 0)
                continue
            ts = stamp(o)
            if ts is None or (until and ts >= until):
                continue
            if since and ts < since:
                dropped = True
                continue
            if mid in seen:
                continue
            seen.add(mid)
            call = {"id": mid, "time": ts, "cats": cats, "usage": {k: usage.get(k) or 0 for k in WEIGHTS}}
            by_id[mid] = call
            calls.append(call)
    for call in calls:
        u = call.pop("usage")
        call["ctx"] = u["input_tokens"] + u["cache_creation_input_tokens"] + u["cache_read_input_tokens"]
        call["eq"] = sum(u[k] * w for k, w in WEIGHTS.items())
        call["cats"] = call["cats"] or ["text_reply"]
    return calls, title, dropped


def bucket(ctx):
    return next(name for name, top in BUCKETS if ctx < top)


def median(values):
    return statistics.median(values) if values else None


def restart_numbers(sessions, groups):
    """Orientation cost after a new session or a compaction, first-call context and cost per call by context."""
    per_bucket = C.defaultdict(C.Counter)
    first_ctx, post_ctx = [], []
    orient = {"session": [], "compaction": []}
    for s in sessions:
        calls = s["calls"]
        for c in calls:
            b = per_bucket[bucket(c["ctx"])]
            b["calls"] += 1
            b["eq"] += c["eq"]
        if s["sub"] or not calls:
            continue
        starts = [] if s["dropped"] else [(0, "session")]
        if not s["dropped"]:
            first_ctx.append(calls[0]["ctx"])
        for i in range(1, len(calls)):
            if calls[i]["ctx"] < calls[i - 1]["ctx"] * RESET:
                starts.append((i, "compaction"))
                post_ctx.append(calls[i]["ctx"])
        for i, kind in starts:
            n = eq = 0
            for c in calls[i:i + ORIENT_CAP]:
                if any(groups.get(k) == "實際動手" for k in c["cats"]):
                    orient[kind].append((n, eq))
                    break
                n += 1
                eq += c["eq"]
    cost = {name: round(per_bucket[name]["eq"] / per_bucket[name]["calls"]) if per_bucket[name]["calls"] else None
            for name, _ in BUCKETS}
    res = {"main_sessions_started": len(first_ctx), "first_call_ctx_median": median(first_ctx),
           "compactions": len(post_ctx), "post_compaction_ctx_median": median(post_ctx),
           "calls_by_ctx": {name: per_bucket[name]["calls"] for name, _ in BUCKETS}, "eq_per_call_by_ctx": cost}
    for kind, pairs in orient.items():
        res[f"after_{kind}"] = {"reached": len(pairs), "calls_to_first_make_median": median([n for n, _ in pairs]),
                                "eq_to_first_make_median": median([e for _, e in pairs])}
    fresh = bucket(res["first_call_ctx_median"]) if res["first_call_ctx_median"] is not None else None
    high, low = cost.get(">=170K"), cost.get(fresh) if fresh else None
    rebuild = res["after_session"]["eq_to_first_make_median"]
    if None in (high, low, rebuild):
        res["break_even"] = {"result": "UNKNOWN", "why": "not enough calls in the buckets or no new session reached 實際動手"}
    else:
        saving = high - low
        res["break_even"] = {"fresh_bucket": fresh, "eq_per_call_fresh": low, "eq_per_call_>=170K": high,
                             "rebuild_eq": rebuild, "saving_per_call": saving,
                             "calls_to_break_even": round(rebuild / saving) if saving > 0 else None,
                             "result": "NEVER" if saving <= 0 else "CALLS"}
    return res


def summarize(sessions, groups, top=0, by_session=False):
    paid, calls, fine_paid = C.Counter(), C.Counter(), C.Counter()
    per_session, titles = C.defaultdict(C.Counter), {}
    session_fine, session_calls = C.defaultdict(C.Counter), C.Counter()
    total = 0.0
    n_calls = 0
    for s in sessions:
        if s["title"]:
            titles[s["sid"]] = s["title"]
        for c in s["calls"]:
            n_calls += 1
            session_calls[s["sid"]] += 1
            total += c["eq"]
            share = c["eq"] / len(c["cats"])
            for k in c["cats"]:
                g = groups.get(k, "協調")
                paid[g] += share
                calls[g] += 1
                fine_paid[k] += share
                per_session[s["sid"]][g] += share
                session_fine[s["sid"]][k] += share
    shares = {g: (paid[g] / total if total else 0.0) for g in GROUPS}
    targets = {}
    for g, (op, limit) in TARGETS.items():
        ok = shares[g] <= limit if op == "<=" else shares[g] >= limit
        targets[g] = {"target": f"{op}{limit:.0%}", "share": round(shares[g], 4), "ok": ok}
    res = {"calls": n_calls, "eq_total": round(total), "groups": {g: {"share": round(shares[g], 4), "tool_calls": calls[g]}
                                                                  for g in GROUPS},
           "fine": {k: round(v / total, 4) for k, v in fine_paid.most_common()} if total else {},
           "targets": targets, "result": "ON_TARGET" if all(t["ok"] for t in targets.values()) else "OFF_TARGET"}
    if top:
        ranked = sorted(per_session.items(), key=lambda kv: -sum(kv[1].values()))[:top]
        res["sessions"] = [{"session": sid[:8], "title": (titles.get(sid) or "")[:30],
                            "share_of_total": round(sum(cnt.values()) / total, 4),
                            "groups": {g: round(cnt[g] / sum(cnt.values()), 3) for g in GROUPS if cnt[g]}}
                           for sid, cnt in ranked]
    if by_session:
        ranked = sorted(per_session.items(), key=lambda kv: -sum(kv[1].values()))
        res["by_session"] = []
        for sid, cnt in ranked:
            own = sum(cnt.values())
            if not own:
                continue
            res["by_session"].append({
                "session": sid[:8], "title": (titles.get(sid) or "")[:30], "calls": session_calls[sid],
                "eq": round(own), "share_of_total": round(own / total, 4),
                "groups": {g: round(cnt[g] / own, 3) for g in GROUPS if cnt[g]},
                "fine": {k: round(v / own, 3) for k, v in session_fine[sid].most_common(5)}})
    return res


def collect(root, project_dirs, pats, since=None, until=None, session=None):
    seen, sessions, files = set(), [], 0
    titles = {}
    for path, sid, sub in transcript_files(root, project_dirs):
        if since and os.path.getmtime(path) < since.timestamp():
            continue
        files += 1
        calls, title, dropped = read_calls(path, pats, since, until, seen)
        if title:
            titles[sid] = title
        sessions.append({"sid": sid, "sub": sub, "calls": calls, "title": title, "dropped": dropped})
    for s in sessions:
        s["title"] = s["title"] or titles.get(s["sid"])
    if session:
        want = session.lower()
        sessions = [s for s in sessions if s["sid"].lower().startswith(want) or want in (s["title"] or "").lower()]
    return sessions, files


def pct(x):
    return f"{x * 100:5.1f}%"


def kfmt(x):
    return "-" if x is None else f"{x / 1000:.1f}K"


def render(res):
    lines = [f"USAGE_MIX files={res['files']} sessions={res['sessions_read']} calls={res['calls']} "
             f"eq={res['eq_total'] / 1e6:.1f}M range={res['range']}" + (f" session={res['session']}" if res["session"] else "")]
    for g in GROUPS:
        t = res["targets"].get(g)
        mark = f"  target {t['target']} {'OK' if t['ok'] else 'MISSED'}" if t else ""
        lines.append(f"  {g}\t{pct(res['groups'][g]['share'])}  tool_calls {res['groups'][g]['tool_calls']}{mark}")
    lines.append("  fine: " + ", ".join(f"{k} {v * 100:.1f}%" for k, v in list(res["fine"].items())[:12]))
    for s in res.get("sessions", []):
        lines.append(f"  session {s['session']} {s['title']}: {pct(s['share_of_total'])} of total | "
                     + ", ".join(f"{g} {v * 100:.0f}%" for g, v in s["groups"].items()))
    for s in res.get("by_session", []):
        lines.append(f"  by-session {s['session']} {s['title'] or '-'}: {pct(s['share_of_total']).strip()} of total, "
                     f"calls {s['calls']}, eq {kfmt(s['eq'])} | "
                     + ", ".join(f"{g} {v * 100:.0f}%" for g, v in s["groups"].items())
                     + " | top: " + ", ".join(f"{k} {v * 100:.0f}%" for k, v in s["fine"].items()))
    r = res["restart"]
    lines.append(f"RESTART new main sessions {r['main_sessions_started']}, first-call context median "
                 f"{kfmt(r['first_call_ctx_median'])}; compactions {r['compactions']}, after it "
                 f"{kfmt(r['post_compaction_ctx_median'])}")
    for kind, label in (("session", "a new session"), ("compaction", "a compaction")):
        o = r[f"after_{kind}"]
        lines.append(f"RESTART after {label}: {o['reached']} reached 實際動手, median "
                     f"{o['calls_to_first_make_median'] if o['calls_to_first_make_median'] is not None else '-'} calls "
                     f"and {kfmt(o['eq_to_first_make_median'])} eq before the first one")
    lines.append("RESTART eq per call by context: " + ", ".join(
        f"{b} {kfmt(v)} ({r['calls_by_ctx'][b]} calls)" for b, v in r["eq_per_call_by_ctx"].items()))
    be = r["break_even"]
    if be["result"] == "UNKNOWN":
        lines.append(f"RESTART break-even UNKNOWN: {be['why']}")
    elif be["result"] == "NEVER":
        lines.append(f"RESTART break-even NEVER: a call at >=170K costs {kfmt(be['eq_per_call_>=170K'])}, no more than "
                     f"{kfmt(be['eq_per_call_fresh'])} at {be['fresh_bucket']}; a new session only adds "
                     f"{kfmt(be['rebuild_eq'])} of rebuilding")
    else:
        lines.append(f"RESTART break-even after {be['calls_to_break_even']} more calls: rebuilding costs "
                     f"{kfmt(be['rebuild_eq'])}, each call saves {kfmt(be['saving_per_call'])} "
                     f"({kfmt(be['eq_per_call_>=170K'])} at >=170K vs {kfmt(be['eq_per_call_fresh'])} at {be['fresh_bucket']})")
    missed = [f"{g} {pct(t['share']).strip()} (target {t['target']})" for g, t in res["targets"].items() if not t["ok"]]
    lines.append(f"RESULT {res['result']}" + (": " + "; ".join(missed) if missed else ""))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(pathlib.Path.home() / ".claude" / "projects"),
                    help="projects root (default ~/.claude/projects)")
    ap.add_argument("--project-dir", action="append", default=[],
                    help="project folder name under the root, or a full path (repeatable); default the current folder's")
    ap.add_argument("--all", action="store_true", help="every project under the root")
    ap.add_argument("--since", help="UTC; YYYY-MM-DD or ISO time")
    ap.add_argument("--until", help="UTC; YYYY-MM-DD (the whole day) or ISO time")
    ap.add_argument("--session", help="only sessions whose id starts with this, or whose title holds it")
    ap.add_argument("--patterns", metavar="FILE", help="project words added to the default patterns (JSON)")
    ap.add_argument("--top", type=int, default=0, metavar="N", help="also show the N costliest sessions")
    ap.add_argument("--by-session", action="store_true",
                    help="one line per session: share, calls, quota, group shares, costliest fine categories")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    ap.add_argument("--check", action="store_true", help="exit 1 when a DD-049 target is missed")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        since, until = parse_time(a.since), parse_time(a.until, end=True)
    except ValueError as e:
        ap.error(f"--since / --until: {e}")
    try:
        pats, groups = load_patterns(a.patterns)
    except PatternError as e:
        print(f"FAIL patterns: {e}")
        return 2
    dirs = None if a.all else (a.project_dir or [project_dir_name(os.getcwd())])
    sessions, files = collect(a.root, dirs, pats, since, until, a.session)
    res = summarize(sessions, groups, a.top, a.by_session)
    if not res["calls"]:
        print(f"NO_DATA: no model calls found (files read: {files}); this is not a measured 0")
        return 1
    res.update({"files": files, "sessions_read": len(sessions), "session": a.session,
                "range": f"{a.since or 'start'}..{a.until or 'now'} UTC", "restart": restart_numbers(sessions, groups),
                "weights": WEIGHTS})
    print(json.dumps(res, ensure_ascii=False, indent=1) if a.json else render(res))
    return 1 if a.check and res["result"] != "ON_TARGET" else 0


if __name__ == "__main__":
    sys.exit(main())
