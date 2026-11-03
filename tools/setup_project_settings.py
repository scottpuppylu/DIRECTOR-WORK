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
Plugins that come from the desktop app / claude.ai cannot be turned off this way.
--hooks also adds a PreToolUse hook that runs hook_guard.py (next to this file) before every Bash / PowerShell call.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys

REL = pathlib.Path(".claude") / "settings.local.json"
ENV_KEY = "CLAUDE_CODE_AUTO_COMPACT_WINDOW"
GUARD = pathlib.Path(__file__).resolve().parent / "hook_guard.py"
HOOK = {"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command":
        f'"{pathlib.Path(sys.executable).as_posix()}" -I -X utf8 "{GUARD.as_posix()}"'}]}


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


def has_hook(data):
    entries = (data.get("hooks") or {}).get("PreToolUse") or []
    return any("hook_guard.py" in str(h.get("command", "")) for e in entries if isinstance(e, dict)
               for h in e.get("hooks") or [] if isinstance(h, dict))


def wanted_missing(data, window, plugins_off, hooks=False):
    miss = []
    if data.get("autoCompactWindow") != window:
        miss.append("autoCompactWindow")
    if (data.get("env") or {}).get(ENV_KEY) != str(window):
        miss.append("env." + ENV_KEY)
    ep = data.get("enabledPlugins") or {}
    miss += [f"enabledPlugins.{p}" for p in plugins_off if ep.get(p) is not False]
    if hooks and not has_hook(data):
        miss.append("hooks.PreToolUse")
    return miss


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="any folder inside the target git repo (default: current git repo)")
    ap.add_argument("--window", type=int, help="auto-compact window in tokens, 100000-1000000 (default 250000)")
    ap.add_argument("--plugins-off", help="comma list name@marketplace to turn off for this project only")
    ap.add_argument("--config", help="director_work.json (default: <repo>/, <repo>/DIRECTOR/, <repo>/../DIRECTOR/)")
    ap.add_argument("--backup-dir", help="where to copy existing files before writing (default: <git common dir>/director-settings-backup)")
    ap.add_argument("--hooks", action="store_true", help='also add the hook_guard.py PreToolUse hook (config: "hooks": true)')
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
    hooks = a.hooks or cfg.get("hooks") is True

    if a.backup_dir or cfg.get("backup_dir"):
        backup = pathlib.Path(a.backup_dir or cfg["backup_dir"])
    else:
        common = pathlib.Path(git(["rev-parse", "--git-common-dir"], repo).stdout.strip())
        backup = (common if common.is_absolute() else repo / common).resolve() / "director-settings-backup"

    print(f"repo={repo} window={window} plugins_off={plugins_off or 'none'} config={cfg_path or 'none'} "
          f"hooks={'on' if hooks else 'off'} mode={'APPLY' if a.apply else 'REPORT'}")
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
            print(f"NOT_IGNORED {wt} left untouched (add .claude/settings.local.json to .gitignore first)")
            problems += 1
            continue
        miss = wanted_missing(data, window, plugins_off, hooks)
        if not miss:
            print(f"OK          {wt}")
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
        if hooks and not has_hook(data):
            data.setdefault("hooks", {}).setdefault("PreToolUse", []).append(HOOK)
        path.parent.mkdir(exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:  # Path.write_text(newline=) needs 3.10
            fh.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, path)
        again = wanted_missing(json.loads(path.read_text(encoding="utf-8")), window, plugins_off, hooks)
        if again:
            print(f"FAIL        {wt} (still missing: {', '.join(again)})")
            problems += 1
        else:
            print(f"SET         {wt}")
    print("RESULT", "OK" if not problems else f"{problems} worktree(s) need attention")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
