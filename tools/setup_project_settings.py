"""Write the auto-compact window (and optional plugin switches) into every worktree of ONE git repo.

Writes only <worktree>/.claude/settings.local.json of the chosen repo's worktrees. Never touches user-level
settings (~/.claude/...). Without --apply it only reports.

Per worktree it prints one of:
  OK           already set
  MISSING      not set yet (report mode)            -> exit 1
  SET          written and re-read OK (--apply)
  NOT_IGNORED  .claude/settings.local.json is not git-ignored there; left untouched -> exit 1
  BAD_JSON     existing file is not valid JSON; left untouched                     -> exit 1
  GONE         worktree folder no longer exists (git worktree prune is the PO's call)
  FAIL         written but the re-read did not match                                -> exit 1

Why both keys: a plain CLI run honours "autoCompactWindow"; in the desktop app only the env var
CLAUDE_CODE_AUTO_COMPACT_WINDOW was confirmed to work. Both are written.
Plugins: "enabledPlugins": {"name@marketplace": false} turns off a USER-installed plugin for this project only.
Plugins that come from the desktop app / claude.ai: whether this setting turns them off is not tested.
--hooks also adds a PreToolUse hook that runs hook_guard.py (next to this file) before every Bash / PowerShell call.
--protect-director DIR makes that hook also cover Write / Edit with --protect DIR (no edits to DIR/orders/** and
DIR/DIRECTOR_LOG.md); the worktree named by --director-worktree keeps the plain hook. An installed hook_guard entry
with another matcher or --protect shows MISSING (hooks.PreToolUse matcher); one whose command is not exactly the one
this copy would write (another Python, a hook_guard.py that moved) shows MISSING (hooks.PreToolUse command). --apply
replaces it in place. Without --protect-director the installed entry's --protect is kept. A hook that is in place is
then run twice, on a command it must allow and on one it must block (also a Write into DIR/orders/ when protected);
a hook that does not answer 0 and 2 is HOOK_FAIL.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys

REL = pathlib.Path(".claude") / "settings.local.json"
CONFIG_VERSION = 1  # director_work.json without schema_version counts as 1
ENV_KEY = "CLAUDE_CODE_AUTO_COMPACT_WINDOW"
GUARD = pathlib.Path(__file__).resolve().parent / "hook_guard.py"
HOOK = {"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command":
        f'"{pathlib.Path(sys.executable).as_posix()}" -I -X utf8 "{GUARD.as_posix()}"'}]}


def hook_entry(protect):
    """The PreToolUse entry wanted: the plain HOOK, or one that also covers Write / Edit for a protected DIRECTOR."""
    if not protect:
        return HOOK
    command = HOOK["hooks"][0]["command"] + f' --protect "{protect.as_posix()}"'
    return {"matcher": "Bash|PowerShell|Write|Edit", "hooks": [{"type": "command", "command": command}]}


def git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")


def find_config(repo, explicit):
    if explicit:
        return pathlib.Path(explicit)
    for cand in (repo / "director_work.json", repo / "DIRECTOR" / "director_work.json",
                 repo.parent / "DIRECTOR" / "director_work.json"):
        if cand.is_file():
            return cand
    return None


def worktrees(repo):
    out = git(["worktree", "list", "--porcelain"], repo)
    if out.returncode != 0:
        sys.exit(f"git worktree list failed in {repo}: {out.stderr.strip()}")
    for line in out.stdout.splitlines():
        if line.startswith("worktree "):
            yield pathlib.Path(line[len("worktree "):].strip())


def guard_entries(data):
    entries = (data.get("hooks") or {}).get("PreToolUse") or []
    return [e for e in entries if isinstance(e, dict) and any(
        isinstance(h, dict) and "hook_guard.py" in str(h.get("command", "")) for h in e.get("hooks") or [])]


def has_hook(data):
    return bool(guard_entries(data))


def protect_arg(command):
    found = re.search(r'--protect "([^"]*)"', command)
    return found.group(1) if found else None


def hook_command(entry):
    """The one hook_guard command of an entry; None when it has none or several."""
    guard = [str(h.get("command", "")) for h in entry.get("hooks") or []
             if isinstance(h, dict) and "hook_guard.py" in str(h.get("command", ""))]
    return guard[0] if len(guard) == 1 else None


def hook_entry_matches(entry, want, exact=True):
    """Same matcher and same --protect (or none) as want; with exact, also the same command, word for word (H04)."""
    command = hook_command(entry)
    wanted = want["hooks"][0]["command"]
    return (entry.get("matcher") == want["matcher"] and command is not None
            and protect_arg(command) == protect_arg(wanted) and (not exact or command == wanted))


def hook_works(command, protect):
    """Run an installed hook_guard command on calls it must allow (exit 0) and block (exit 2): (ok, detail) (H04)."""
    try:
        argv = shlex.split(command)
    except ValueError as error:
        return False, f"command does not parse: {error}"
    calls = [("allow", {"tool_name": "Bash", "tool_input": {"command": "git status"}}, 0),
             ("block", {"tool_name": "Bash", "tool_input": {"command": "git push"}}, 2)]
    if protect:
        calls.append(("block-write", {"tool_name": "Write", "tool_input": {"file_path": str(pathlib.Path(protect) / "orders" / "hook-test.md")}}, 2))
    results, ok = [], True
    for name, call, code in calls:
        try:
            got = subprocess.run(argv, input=json.dumps(call), capture_output=True, text=True, timeout=60).returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            got = type(error).__name__
        results.append(f"{name}={got}")
        ok = ok and got == code
    return ok, " ".join(results)


def install_hook(data, want):
    """Put want where the first hook_guard entry was (or at the end); drop other hook_guard hooks."""
    entries = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    at, kept = None, []
    for e in entries:
        if isinstance(e, dict) and e in guard_entries(data):
            at = len(kept) if at is None else at
            rest = [h for h in e.get("hooks") or [] if not (isinstance(h, dict) and "hook_guard.py" in str(h.get("command", "")))]
            if rest:
                kept.append(dict(e, hooks=rest))
        else:
            kept.append(e)
    kept.insert(len(kept) if at is None else at, want)
    data["hooks"]["PreToolUse"] = kept


def tested(wt, label, want):
    """Print the OK / SET line; with a hook, run it first (H04). Returns 1 when the hook does not work."""
    if want is None:
        print(f"{label:11} {wt}")
        return 0
    command = want["hooks"][0]["command"]
    ok, detail = hook_works(command, protect_arg(command))
    print(f"{label:11} {wt} (hook test: {detail})" if ok else f"HOOK_FAIL   {wt} (hook test: {detail}; expected allow=0 block=2)")
    return 0 if ok else 1


def wanted_missing(data, window, plugins_off, hooks=False, want=None):
    miss = []
    if data.get("autoCompactWindow") != window:
        miss.append("autoCompactWindow")
    if (data.get("env") or {}).get(ENV_KEY) != str(window):
        miss.append("env." + ENV_KEY)
    ep = data.get("enabledPlugins") or {}
    miss += [f"enabledPlugins.{p}" for p in plugins_off if ep.get(p) is not False]
    if hooks and not has_hook(data):
        miss.append("hooks.PreToolUse")
    elif hooks and want is not None and not any(hook_entry_matches(e, want, exact=False) for e in guard_entries(data)):
        miss.append("hooks.PreToolUse matcher")
    elif hooks and want is not None and not any(hook_entry_matches(e, want) for e in guard_entries(data)):
        miss.append("hooks.PreToolUse command")
    return miss


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="any folder inside the target git repo (default: current git repo)")
    ap.add_argument("--window", type=int, help="auto-compact window in tokens, 100000-1000000 (default 250000)")
    ap.add_argument("--plugins-off", help="comma list name@marketplace to turn off for this project only")
    ap.add_argument("--config", help="director_work.json (default: <repo>/, <repo>/DIRECTOR/, <repo>/../DIRECTOR/)")
    ap.add_argument("--backup-dir", help="where to copy existing files before writing (default: <git common dir>/director-settings-backup)")
    ap.add_argument("--hooks", action="store_true", help='also add the hook_guard.py PreToolUse hook (config: "hooks": true)')
    ap.add_argument("--protect-director", help="DIRECTOR folder: the hook also blocks Write / Edit on its orders/ and "
                    "DIRECTOR_LOG.md (implies --hooks; config: protect_director)")
    ap.add_argument("--director-worktree", help="the Director's own worktree, which keeps the plain hook (config: director_worktree)")
    ap.add_argument("--only-this", action="store_true", help="only the worktree given by --repo, not all worktrees")
    ap.add_argument("--skip", action="append", default=[], help="skip worktrees whose path contains this text (repeatable)")
    ap.add_argument("--apply", action="store_true", help="write; without it nothing is written")
    a = ap.parse_args()

    top = git(["rev-parse", "--show-toplevel"], a.repo or os.getcwd())
    if top.returncode != 0:
        sys.exit("not inside a git repo; pass --repo <path>")
    repo = pathlib.Path(top.stdout.strip())

    cfg_path = find_config(repo, a.config)
    cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig")) if cfg_path else {}
    if cfg.get("schema_version", 1) != CONFIG_VERSION:
        sys.exit(f"{cfg_path}: schema_version {cfg['schema_version']} is not {CONFIG_VERSION}; see CHANGELOG.md for how to migrate")
    window = a.window or cfg.get("window") or 250000
    if not 100000 <= window <= 1000000:
        sys.exit(f"--window {window} outside 100000-1000000")
    if a.plugins_off is not None:
        plugins_off = [p.strip() for p in a.plugins_off.split(",") if p.strip()]
    else:
        plugins_off = [p for p in cfg.get("plugins_off", []) if p and not p.startswith("example-plugin@")]
    bad_names = [p for p in plugins_off if "@" not in p]
    if bad_names:
        sys.exit(f"plugin names must be name@marketplace: {bad_names}")
    skip = a.skip + list(cfg.get("skip_worktrees", []))
    protect = a.protect_director or cfg.get("protect_director")
    protect = pathlib.Path(protect).resolve() if protect else None
    director_wt = a.director_worktree or cfg.get("director_worktree")
    director_wt = pathlib.Path(director_wt).resolve() if director_wt else None
    hooks = a.hooks or cfg.get("hooks") is True or protect is not None

    if a.backup_dir or cfg.get("backup_dir"):
        backup = pathlib.Path(a.backup_dir or cfg["backup_dir"])
    else:
        common = pathlib.Path(git(["rev-parse", "--git-common-dir"], repo).stdout.strip())
        backup = (common if common.is_absolute() else repo / common).resolve() / "director-settings-backup"

    print(f"repo={repo} window={window} plugins_off={plugins_off or 'none'} config={cfg_path or 'none'} "
          f"hooks={'on' if hooks else 'off'}{f' protect={protect.as_posix()}' if protect else ''} "
          f"mode={'APPLY' if a.apply else 'REPORT'}")
    home = pathlib.Path.home().resolve()
    targets = [repo] if a.only_this else list(worktrees(repo))
    problems = 0
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    for wt in targets:
        if any(s and s in wt.as_posix() for s in skip):
            print(f"SKIP        {wt}")
            continue
        if not wt.is_dir():
            print(f"GONE        {wt}")
            continue
        if wt.resolve() == home:
            print(f"REFUSED     {wt} (home folder: user-level settings are never touched)")
            problems += 1
            continue
        path = wt / REL
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
            if not isinstance(data, dict):
                raise ValueError("top level is not an object")
        except ValueError as e:
            print(f"BAD_JSON    {wt} ({e}) left untouched")
            problems += 1
            continue
        if git(["check-ignore", "-q", REL.as_posix()], wt).returncode != 0:
            print(f"NOT_IGNORED {wt} left untouched (add .claude/settings.local.json to .git/info/exclude; "
                  ".gitignore changes the repo and needs the PO)")
            problems += 1
            continue
        want = None if protect is None else hook_entry(None if director_wt and wt.resolve() == director_wt else protect)
        if hooks and want is None:  # without --protect-director the installed entry keeps its --protect (or none)
            installed = [hook_command(e) for e in guard_entries(data)]
            kept = protect_arg(installed[0]) if installed and installed[0] else None
            want = hook_entry(pathlib.Path(kept) if kept else None)
        miss = wanted_missing(data, window, plugins_off, hooks, want)
        if not miss:
            problems += tested(wt, "OK", want if hooks else None)
            continue
        if not a.apply:
            print(f"MISSING     {wt} ({', '.join(miss)})")
            problems += 1
            continue
        if path.exists():
            backup.mkdir(parents=True, exist_ok=True)
            tag = hashlib.sha1(str(wt.resolve()).encode("utf-8")).hexdigest()[:8]
            shutil.copy2(path, backup / f"{wt.name}-{tag}-{stamp}.settings.local.json")
        data["autoCompactWindow"] = window
        data.setdefault("env", {})[ENV_KEY] = str(window)
        if plugins_off:
            data.setdefault("enabledPlugins", {}).update({p: False for p in plugins_off})
        if hooks and any(m.startswith("hooks.PreToolUse") for m in miss):
            install_hook(data, want or HOOK)
        path.parent.mkdir(exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:  # Path.write_text(newline=) needs 3.10
            fh.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, path)
        again = wanted_missing(json.loads(path.read_text(encoding="utf-8")), window, plugins_off, hooks, want)
        if again:
            print(f"FAIL        {wt} (still missing: {', '.join(again)})")
            problems += 1
        else:
            problems += tested(wt, "SET", want if hooks else None)
    print("RESULT", "OK" if not problems else f"{problems} worktree(s) need attention")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
