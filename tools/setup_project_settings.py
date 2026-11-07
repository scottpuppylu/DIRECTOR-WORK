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
--guard-mode remind|ask|block (config guard_mode) is what a call the hook flags gets. remind, the default, lets it
run with a one-line reminder; ask hands it to the user's permission prompt; block (exit 2) is the explicit opt-in
strict mode. Do not install block on worker lines by default: a guard that stops work the user approved makes the
agent afraid to act. remind writes no --mode; another mode adds --mode X to the command. Without --guard-mode an
installed --mode is kept, and an entry without one counts as remind.
--protect-director DIR makes that hook also cover Write / Edit with --protect DIR (no edits to DIR/orders/** and
DIR/DIRECTOR_LOG.md); the worktree named by --director-worktree keeps the plain hook. An installed hook_guard entry
with another matcher or --protect shows MISSING (hooks.PreToolUse matcher); one whose command is not exactly the one
this copy would write (another Python, a hook_guard.py that moved) shows MISSING (hooks.PreToolUse command). --apply
replaces it in place. Without --protect-director the installed entry's --protect is kept. A hook that is in place is
then run twice, on a command it must allow and on one it must flag (also a Write into DIR/orders/ when protected);
the allowed one must exit 0 with nothing on stdout, the flagged one must give its mode's answer (block: exit 2; ask:
the ask JSON; remind: exit 0 and the reminder JSON), else HOOK_FAIL.
--guard-profile worker|director|cleaner (implies --hooks) makes the hook check every tool call (matcher *) against
guard_rules.json (next to this file) with that profile, and sets "onFailure": "block" so a hook that breaks blocks
instead of letting the call through. The --director-worktree always gets the director profile. In block mode each
rule's "permissions" go into permissions.deny or permissions.ask, by the profile's decision for that rule (second
layer: deny and ask rules hold in every permission mode); a rule permission sitting in the other list is moved. In
ask mode they all go into permissions.ask. In remind mode none is written, and the ones an earlier install wrote are
taken out of both lists (a permission rule would stop the call the hook only reminds of). The exception: a "secret"
rule (G50) the profile denies keeps its permissions.deny in every mode, as hook_guard denies it in every mode. Missing or stray ones show
MISSING (permissions.deny / permissions.ask). Without --guard-profile an installed entry keeps its
--profile, like --protect. The hook test then also asks for an empty stdout on the allowed call and runs one MCP
call every profile denies (G30), which shows the rules file loaded.
--session-map FILE (config session_map; implies --guard-profile worker as the fallback) is for one settings file that
several sessions share, because a session reads settings only from the folder it was started in: the hook gets
--sessions FILE and picks each call's profile (director / worker / cleaner) by session_id; FILE is checked with
hook_guard's loader (templates/guard_sessions.json). The permission lists then take, per rule, the mildest decision
of every profile FILE can give, so no session is denied by a permission rule that its own profile only asks or allows.
Another FILE than the installed one shows MISSING (hooks.PreToolUse matcher).
With the worker profile the hook also gets --pause-flag FILE (pause_ctl.py on|off): --pause-flag or config pause_flag,
else DIR/PAUSE when --protect-director DIR is known. The Director's worktree never gets it: the Director stops the
process trees while the workers are paused. Without --guard-profile an installed entry keeps its --pause-flag.
--audit-log FILE (config audit_log; implies --hooks) adds PostToolUse and PostToolUseFailure hooks (matcher *) that
run audit_log.py append --log FILE, and gives the hook_guard entry --audit FILE so denies and asks are logged too.
{worktree} in FILE becomes the worktree folder name, for one log per worker; {container} is left for audit_log.py
to fill in when the hook runs (12 characters of the container ID, "host" outside one). Missing ones show MISSING
(hooks.PostToolUse / hooks.PostToolUseFailure); --apply replaces an audit_log entry in place. The hook test runs
hook_guard without --audit or --pause-flag, so no test line goes into the log and no test deny counts
toward an auto-pause. Without --audit-log an installed --audit is kept.
--guard-review (config guard_review: true) gives guarded entries hook_guard --review: asks of the rules' review
categories go to a second model first (claude -p, uses quota). Without it an installed --review is kept. The hook
test drops --review, so a test call never starts a review.
--runtime-guard (config runtime_guard: true) writes what templates/settings.runtime-guard.json shows: --guard-profile
worker unless another profile is given, --audit-log <git common dir>/director-audit/{worktree}-{container}.jsonl
unless another log is given, and env.CLAUDE_CODE_SUBPROCESS_ENV_SCRUB = "1" (subprocesses get no Anthropic / cloud
credentials from the environment; GITHUB_TOKEN, GH_TOKEN, proxy credentials and GIT_CONFIG_* are kept by design). A missing one shows
MISSING (env.CLAUDE_CODE_SUBPROCESS_ENV_SCRUB). doctor.py then reports what is really in force.
"""
import argparse
import datetime
import hashlib
import importlib.util
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
SCRUB_KEY = "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"
GUARD = pathlib.Path(__file__).resolve().parent / "hook_guard.py"
RULES = GUARD.parent / "guard_rules.json"
AUDIT = GUARD.parent / "audit_log.py"
POST_EVENTS = ("PostToolUse", "PostToolUseFailure")
HOOK = {"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command":
        f'"{pathlib.Path(sys.executable).as_posix()}" -I -X utf8 "{GUARD.as_posix()}"'}]}
PROFILES = ("worker", "director", "cleaner")
MODES = ("remind", "ask", "block")
STRICTNESS = {"none": 0, "ask": 1, "deny": 2}


def hook_entry(protect, profile=None, pause=None, audit=None, review=False, sessions=None, mode="remind"):
    """The PreToolUse entry wanted: the plain HOOK, one that also covers Write / Edit for a protected DIRECTOR,
    or, with a guard profile, one that checks every tool call against the rules file and blocks when it fails.
    With audit, hook_guard also logs its decisions there. A mode other than remind adds --mode."""
    log = f' --audit "{audit.as_posix()}"' if audit else ""
    base = HOOK["hooks"][0]["command"] + (f" --mode {mode}" if mode and mode != "remind" else "")
    if not protect and not profile:
        return {"matcher": HOOK["matcher"], "hooks": [{"type": "command", "command": base + log}]} if base + log != HOOK["hooks"][0]["command"] else HOOK
    command = base + (f' --protect "{protect.as_posix()}"' if protect else "")
    if not profile:
        return {"matcher": "Bash|PowerShell|Write|Edit", "hooks": [{"type": "command", "command": command + log}]}
    command += f' --rules "{RULES.as_posix()}" --profile {profile}' + (f' --pause-flag "{pause.as_posix()}"' if pause else "")
    command += f' --sessions "{sessions.as_posix()}"' if sessions else ""
    command += " --review" if review else ""
    return {"matcher": "*", "hooks": [{"type": "command", "command": command + log, "onFailure": "block"}]}


def post_entry(audit):
    """The PostToolUse / PostToolUseFailure entry that adds every call to the action log."""
    return {"matcher": "*", "hooks": [{"type": "command", "command":
            f'"{pathlib.Path(sys.executable).as_posix()}" -I -X utf8 "{AUDIT.as_posix()}" append --log "{audit.as_posix()}"'}]}


def audit_entries(data, event):
    entries = (data.get("hooks") or {}).get(event) or []
    return [e for e in entries if isinstance(e, dict) and any(
        isinstance(h, dict) and "audit_log.py" in str(h.get("command", "")) for h in e.get("hooks") or [])]


def install_post(data, event, want):
    """Put want where the first audit_log entry of event was (or at the end); drop other audit_log hooks."""
    entries = data.setdefault("hooks", {}).setdefault(event, [])
    at, kept = None, []
    for e in entries:
        if isinstance(e, dict) and e in audit_entries(data, event):
            at = len(kept) if at is None else at
            rest = [h for h in e.get("hooks") or [] if not (isinstance(h, dict) and "audit_log.py" in str(h.get("command", "")))]
            if rest:
                kept.append(dict(e, hooks=rest))
        else:
            kept.append(e)
    kept.insert(len(kept) if at is None else at, want)
    data["hooks"][event] = kept


def load_audit_log():
    spec = importlib.util.spec_from_file_location("audit_log", AUDIT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_guard():
    spec = importlib.util.spec_from_file_location("hook_guard", GUARD)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    return guard


def load_guard_rules():
    """The rules file, checked by hook_guard's own loader; exits with the reason when it is bad."""
    guard = load_guard()
    try:
        return guard.load_rules(RULES)
    except guard.RulesError as error:
        sys.exit(f"bad rules file: {error}")


def session_profiles(path, fallback):
    """Every profile the sessions file can give (its sessions and its default), checked by hook_guard's loader."""
    guard = load_guard()
    try:
        data = guard.load_sessions(path)
    except guard.RulesError as error:
        sys.exit(f"bad sessions file: {error}")
    named = [e["profile"] if isinstance(e, dict) else e for e in data.get("sessions", {}).values()]
    return sorted(set(named) | {data.get("default", fallback)})


def rule_permissions(rules):
    """Every permission any rule names: the ones this tool writes, moves and takes out."""
    return {item for rule in rules["rules"] for item in rule.get("permissions", [])}


def wanted_permissions(rules, profile, mode="block"):
    """{"deny": [...], "ask": [...]}: each rule's permissions under the list its decision for this profile names.
    For a list of profiles (one settings file for several sessions, --session-map) the mildest decision of them
    counts: a permission rule holds for every session of the folder, so it may not be stricter than the hook is for
    any of them. Ask mode puts every deny under ask; remind mode wants none (the hook only reminds). A denied rule of
    a hook_guard.HARD_DENY category (secret) stays under deny in every mode."""
    lists = {"deny": [], "ask": []}
    guard = load_guard()
    profiles = [profile] if isinstance(profile, str) else list(profile)
    for rule in rules["rules"]:
        decision = min((guard.rule_decision(rule, p) for p in profiles), key=STRICTNESS.get)
        if decision == "deny" and rule.get("category") in guard.HARD_DENY:
            pass
        elif mode == "remind":
            continue
        elif mode == "ask" and decision == "deny":
            decision = "ask"
        for item in rule.get("permissions", []):
            if decision in lists and item not in lists[decision]:
                lists[decision].append(item)
    return lists


def permission_problems(data, perms, ours=None):
    """Lists that miss a wanted rule permission, or hold one of ours (rule_permissions) that does not belong there."""
    have = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
    ours = {p for items in perms.values() for p in items} if ours is None else set(ours)
    miss = []
    for name, items in perms.items():
        current = have.get(name) if isinstance(have.get(name), list) else []
        stray = [p for p in current if p in ours and p not in items]
        if stray or any(p not in current for p in items):
            miss.append(f"permissions.{name}")
    return miss


def install_permissions(data, perms, ours=None):
    """Append missing rule permissions; take one of ours out of a list that does not name it."""
    if not isinstance(data.get("permissions"), dict):
        data["permissions"] = {}
    have = data["permissions"]
    ours = {p for items in perms.values() for p in items} if ours is None else set(ours)
    for name, items in perms.items():
        if name not in have and not items:
            continue
        current = have.get(name) if isinstance(have.get(name), list) else []
        current = [p for p in current if p not in ours or p in items]
        have[name] = current + [p for p in items if p not in current]


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


def pause_arg(command):
    found = re.search(r'--pause-flag "([^"]*)"', command)
    return found.group(1) if found else None


def audit_arg(command):
    found = re.search(r'--audit "([^"]*)"', command)
    return found.group(1) if found else None


def review_arg(command):
    return bool(re.search(r"(?:^| )--review(?= |$)", command))


def profile_arg(command):
    found = re.search(r"--profile (\w+)", command)
    return found.group(1) if found else None


def mode_arg(command):
    """The --mode of a hook_guard command; remind when it has none (the hook's default)."""
    found = re.search(r"--mode (\w+)", command)
    return found.group(1) if found else "remind"


def sessions_arg(command):
    found = re.search(r'--sessions "([^"]*)"', command)
    return found.group(1) if found else None


def guard_hook(entry):
    """The one hook_guard hook object of an entry; None when it has none or several."""
    guard = [h for h in entry.get("hooks") or [] if isinstance(h, dict) and "hook_guard.py" in str(h.get("command", ""))]
    return guard[0] if len(guard) == 1 else None


def hook_command(entry):
    """The one hook_guard command of an entry; None when it has none or several."""
    guard = [str(h.get("command", "")) for h in entry.get("hooks") or []
             if isinstance(h, dict) and "hook_guard.py" in str(h.get("command", ""))]
    return guard[0] if len(guard) == 1 else None


def hook_entry_matches(entry, want, exact=True):
    """Same matcher, --protect, --profile, --pause-flag and onFailure as want; with exact, also the same command, word
    for word (H04)."""
    hook = guard_hook(entry)
    command = hook_command(entry)
    wanted = want["hooks"][0]["command"]
    return (entry.get("matcher") == want["matcher"] and command is not None and hook is not None
            and protect_arg(command) == protect_arg(wanted) and profile_arg(command) == profile_arg(wanted)
            and pause_arg(command) == pause_arg(wanted) and audit_arg(command) == audit_arg(wanted)
            and review_arg(command) == review_arg(wanted) and sessions_arg(command) == sessions_arg(wanted)
            and mode_arg(command) == mode_arg(wanted)
            and hook.get("onFailure") == want["hooks"][0].get("onFailure") and (not exact or command == wanted))


def answer(done):
    """What one hook run gave: 2, 0 (nothing on stdout), "ask", "remind", "0+stdout" or another exit code."""
    if done.returncode != 0 or not done.stdout.strip():
        return done.returncode
    try:
        out = json.loads(done.stdout)
        hso = out.get("hookSpecificOutput") or {}
    except (ValueError, AttributeError):
        return "0+stdout"
    if hso.get("permissionDecision") == "ask":
        return "ask"
    if str(hso.get("additionalContext", "")).startswith("hook_guard reminder") and "permissionDecision" not in hso:
        return "remind"
    return "0+stdout"


FLAGGED = {"block": 2, "ask": "ask", "remind": "remind"}


def hook_works(command, protect):
    """Run an installed hook_guard command on calls it must allow (exit 0, nothing on stdout) and flag (its mode's
    answer: exit 2, the ask JSON or the reminder JSON): (ok, detail) (H04)."""
    try:
        argv = shlex.split(command)
    except ValueError as error:
        return False, f"command does not parse: {error}"
    for option in ("--audit", "--pause-flag"):  # test calls: not in the action log, not counted toward an auto-pause
        if option in argv[:-1]:
            at = argv.index(option)
            del argv[at:at + 2]
    argv = [w for w in argv if w != "--review"]  # a test call never starts a second-model review
    flag = FLAGGED.get(mode_arg(command), 2)
    calls = [("allow", {"tool_name": "Bash", "tool_input": {"command": "git status"}}, 0),
             ("block", {"tool_name": "Bash", "tool_input": {"command": "git push"}}, flag)]
    if protect:
        calls.append(("block-write", {"tool_name": "Write", "tool_input": {"file_path": str(pathlib.Path(protect) / "orders" / "hook-test.md")}}, flag))
    if profile_arg(command):
        calls.append(("block-rule", {"tool_name": "mcp__hook_test__buy_item", "tool_input": {}}, flag))
    results, ok = [], True
    for name, call, code in calls:
        try:
            done = subprocess.run(argv, input=json.dumps(call), capture_output=True, text=True, encoding="utf-8", timeout=60)
            got = answer(done)
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
    print(f"{label:11} {wt} (hook test: {detail})" if ok else
          f"HOOK_FAIL   {wt} (hook test: {detail}; expected allow=0 block={FLAGGED.get(mode_arg(command), 2)})")
    return 0 if ok else 1


def wanted_missing(data, window, plugins_off, hooks=False, want=None, perms=None, audit=None, scrub=False, ours=None):
    miss = []
    if data.get("autoCompactWindow") != window:
        miss.append("autoCompactWindow")
    if (data.get("env") or {}).get(ENV_KEY) != str(window):
        miss.append("env." + ENV_KEY)
    if scrub and (data.get("env") or {}).get(SCRUB_KEY) != "1":
        miss.append("env." + SCRUB_KEY)
    ep = data.get("enabledPlugins") or {}
    miss += [f"enabledPlugins.{p}" for p in plugins_off if ep.get(p) is not False]
    if hooks and not has_hook(data):
        miss.append("hooks.PreToolUse")
    elif hooks and want is not None and not any(hook_entry_matches(e, want, exact=False) for e in guard_entries(data)):
        miss.append("hooks.PreToolUse matcher")
    elif hooks and want is not None and not any(hook_entry_matches(e, want) for e in guard_entries(data)):
        miss.append("hooks.PreToolUse command")
    if audit:
        miss += [f"hooks.{event}" for event in POST_EVENTS if post_entry(audit) not in audit_entries(data, event)]
    if perms:
        miss += permission_problems(data, perms, ours)
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
    ap.add_argument("--director-worktree", help="the Director's own worktree, which keeps the plain hook, or gets the "
                    "director profile with --guard-profile (config: director_worktree)")
    ap.add_argument("--guard-profile", choices=PROFILES, help="check every tool call against guard_rules.json with this "
                    "profile and write its permission rules (implies --hooks; config: guard_profile)")
    ap.add_argument("--session-map", help="sessions file for hook_guard --sessions (templates/guard_sessions.json): one "
                    "settings file serves several sessions, each with its own profile (implies --guard-profile worker "
                    "as the fallback; config: session_map)")
    ap.add_argument("--pause-flag", help="pause flag file for the worker hook (default DIR/PAUSE of --protect-director; "
                    "config: pause_flag)")
    ap.add_argument("--guard-mode", choices=MODES, help="what a flagged call gets: remind (default: it runs, with a "
                    "one-line reminder), ask (the user decides) or block (exit 2; explicit opt-in strict mode; config: "
                    "guard_mode)")
    ap.add_argument("--guard-review", action="store_true", help="give guarded hooks --review: asks of the rules' review "
                    "categories go to a second model first, which uses claude -p quota (config: guard_review)")
    ap.add_argument("--audit-log", help="action log for audit_log.py hooks; {worktree} becomes the worktree folder "
                    "name, {container} the container ID when the hook runs (config: audit_log)")
    ap.add_argument("--runtime-guard", action="store_true", help="write the runtime guard set: worker profile (unless "
                    "--guard-profile), an action log per worktree (unless --audit-log) and env "
                    "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1 (config: runtime_guard)")
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
    runtime = a.runtime_guard or cfg.get("runtime_guard") is True
    common = pathlib.Path(git(["rev-parse", "--git-common-dir"], repo).stdout.strip())
    common = (common if common.is_absolute() else repo / common).resolve()
    profile = a.guard_profile or cfg.get("guard_profile") or ("worker" if runtime else None)
    if profile is not None and profile not in PROFILES:
        sys.exit(f"guard_profile {profile!r} is not one of {', '.join(PROFILES)}")
    smap = a.session_map or cfg.get("session_map")
    smap = pathlib.Path(smap).resolve() if smap else None
    if smap and not profile:
        profile = "worker"
    map_profiles = session_profiles(smap, profile) if smap else []
    rules = load_guard_rules() if profile else None
    pause = a.pause_flag or cfg.get("pause_flag")
    pause = pathlib.Path(pause).resolve() if pause else None
    audit = a.audit_log or cfg.get("audit_log") or ((common / "director-audit" / "{worktree}-{container}.jsonl").as_posix() if runtime else None)
    if audit:
        try:
            load_audit_log().expand(audit, only=())  # only checks: no placeholder other than {worktree} / {container}
        except ValueError as error:
            sys.exit(f"audit_log: {error}")
    review = a.guard_review or cfg.get("guard_review") is True
    mode = a.guard_mode or cfg.get("guard_mode")
    if mode is not None and mode not in MODES:
        sys.exit(f"guard_mode {mode!r} is not one of {', '.join(MODES)}")
    hooks = a.hooks or cfg.get("hooks") is True or protect is not None or profile is not None or bool(audit)

    if a.backup_dir or cfg.get("backup_dir"):
        backup = pathlib.Path(a.backup_dir or cfg["backup_dir"])
    else:
        backup = common / "director-settings-backup"

    print(f"repo={repo} window={window} plugins_off={plugins_off or 'none'} config={cfg_path or 'none'} "
          f"hooks={'on' if hooks else 'off'}{f' protect={protect.as_posix()}' if protect else ''}"
          f"{f' guard_profile={profile}' if profile else ''}"
          f"{f' session_map={smap.as_posix()} ({chr(44).join(map_profiles)})' if smap else ''}{f' pause_flag={pause.as_posix()}' if pause else ''}"
          f"{f' audit_log={audit}' if audit else ''}{f' guard_mode={mode}' if mode else ''}{' guard_review=on' if review else ''}{' runtime_guard=on' if runtime else ''} "
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
        is_director = bool(director_wt and wt.resolve() == director_wt)
        wt_profile = ("director" if is_director else profile) if profile else None
        installed = [hook_command(e) for e in guard_entries(data)]
        installed = installed[0] if installed and installed[0] else None
        wt_audit = pathlib.Path(audit.replace("{worktree}", wt.name)).resolve() if audit else None
        kept_audit = audit_arg(installed) if installed else None
        wt_audit_arg = wt_audit or (pathlib.Path(kept_audit) if kept_audit else None)
        wt_mode = mode or (mode_arg(installed) if installed else "remind")
        want = None
        if protect is not None or wt_profile:
            wt_protect = None if is_director else protect
            if protect is None and not is_director and installed and protect_arg(installed):  # keep an installed --protect
                wt_protect = pathlib.Path(protect_arg(installed))
            wt_pause = pause or (wt_protect / "PAUSE" if wt_protect else None) if wt_profile == "worker" else None
            want = hook_entry(wt_protect, wt_profile, wt_pause, wt_audit_arg, review or bool(installed and review_arg(installed)),
                              smap, wt_mode)
        if hooks and want is None:  # without --protect-director / --guard-profile the installed entry keeps both
            kept = protect_arg(installed) if installed else None
            kept_profile = profile_arg(installed) if installed else None
            kept_pause = pause_arg(installed) if installed else None
            want = hook_entry(pathlib.Path(kept) if kept else None, kept_profile if kept_profile in PROFILES else None,
                              pathlib.Path(kept_pause) if kept_pause else None, wt_audit_arg,
                              review or bool(installed and review_arg(installed)), mode=wt_mode)
        perms = (wanted_permissions(rules, sorted(set(map_profiles) | {wt_profile}) if smap else wt_profile, wt_mode)
                 if wt_profile else None)
        ours = rule_permissions(rules) if rules else None
        miss = wanted_missing(data, window, plugins_off, hooks, want, perms, wt_audit, runtime, ours)
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
        if runtime:
            data["env"][SCRUB_KEY] = "1"
        if plugins_off:
            data.setdefault("enabledPlugins", {}).update({p: False for p in plugins_off})
        if hooks and any(m.startswith("hooks.PreToolUse") for m in miss):
            install_hook(data, want or HOOK)
        for event in POST_EVENTS:
            if f"hooks.{event}" in miss:
                install_post(data, event, post_entry(wt_audit))
        if perms and any(m.startswith("permissions.") for m in miss):
            install_permissions(data, perms, ours)
        path.parent.mkdir(exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:  # Path.write_text(newline=) needs 3.10
            fh.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, path)
        again = wanted_missing(json.loads(path.read_text(encoding="utf-8")), window, plugins_off, hooks, want, perms, wt_audit,
                               runtime, ours)
        if again:
            print(f"FAIL        {wt} (still missing: {', '.join(again)})")
            problems += 1
        else:
            problems += tested(wt, "SET", want if hooks else None)
    print("RESULT", "OK" if not problems else f"{problems} worktree(s) need attention")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
