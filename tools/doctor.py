"""Report which runtime guards are really in force for one worktree. Reads only; writes nothing.

  python -I -X utf8 doctor.py [--repo R] [--probe]

Each line is one item:
  ENFORCED                 in force, and checked (a hook was run, a chain was verified, ...)
  CONFIGURED_NOT_VERIFIED  set, but this run cannot show it works
  NOT_ENFORCED             not in force (a setting turns it off, the claude version is too old, ...)
  MISSING                  not set
  WARN / INFO / VERSION    for the reader; not counted as a failure
Last line: DOCTOR: enforced=n not_verified=m not_enforced=k missing=j warn=w; exit 1 when not_enforced or missing.

Settings layers: user (~/.claude/settings.json), project (.claude/settings.json), local (.claude/settings.local.json)
and managed (Windows C:/Program Files/ClaudeCode/managed-settings.json, else /etc/claude-code/managed-settings.json).
Hooks and permission lists add up across layers; env keys and defaultMode take the highest layer that sets them;
disableAllHooks true in any layer turns every hook item into NOT_ENFORCED.

claude versions: the effective one is CLAUDE_CODE_EXECPATH, else the executable of process CLAUDE_PID, else the first
claude on PATH; every claude on PATH is listed too, and one older than 2.1.295 is a WARN (it would let calls through
when the hook breaks, if PATH order changed). onFailure needs >= 2.1.295; on Windows without Git Bash a hook needs
>= 2.1.310; Monitor's commands pass the hook from 2.1.314. Versions come from "<exe> --version" (a local print, no
model call); a .py path runs with this Python (tests).

--probe (run it from Claude's own Bash tool, so it sees what a tool call sees) looks at the NAMES of the environment
variables: a name that looks like a credential, or a proxy variable whose value holds user:password@, makes
env_scrub NOT_ENFORCED and is listed by name. Values are never printed. CLAUDE_CODE_SUBPROCESS_ENV_SCRUB keeps
GITHUB_TOKEN, GH_TOKEN, proxy credentials and GIT_CONFIG_* by design, so they show up here even when it is on.
isolation: outside a container NOT_ENFORCED, so on native Windows doctor always exits 1: there is no OS-level
isolation for shell commands there. In a container (/.dockerenv, /run/.containerenv or a container cgroup) it is
CONFIGURED_NOT_VERIFIED, and with --probe six checks decide it, ENFORCED only when all six pass: a file cannot be
made in / (read-only root), nor in --director DIR (mounted read-only), a TCP connection to example.com:443 fails
(egress allowlist), example.com does not resolve (DNS allowlist, dns_allow.py), the worker's .git is its own (K1),
and no credential-like variable names are left. --probe makes one outbound connection attempt and one DNS lookup.
K1: run_worker.sh sets DW_GIT_MODE. A container started with --git-common (DW_GIT_MODE=shared, or a linked worktree,
whose .git is the repository's) can change every branch and tag of the repository: isolation is NOT_ENFORCED
(K1 shared .git) with or without --probe. A clone made by worker_clone.sh (DW_GIT_MODE=clone, not a linked worktree)
counts as the worker's own worktree. Outside a container DW_GIT_MODE is ignored.
Besides the claudes on PATH, ~/.local/bin and the npm global folder are looked at and listed as "other" (no WARN).
Launch folders: Claude Code reads .claude/settings*.json only from the folder a session was started in, not from the
worktree it later works in. doctor lists, for every worktree of the repo, whether its settings have a hook_guard entry
and how many sessions started there (or below it) in the last --launch-days days (default 30), from the "cwd" of the
first lines of the transcripts in ~/.claude/projects/ whose folder name is that worktree's path (other projects'
transcripts are not opened). WARN "settings unread": a worktree has a hook_guard entry but no session started there;
WARN "launch folder unguarded": sessions start in a worktree without one while another worktree has one. With a
hook_guard --sessions file (setup_project_settings.py --session-map) the permission check takes the mildest decision of
the profiles that file can give, as setup writes it.
"""
import argparse
import datetime
import importlib.util
import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ON_FAILURE, GIT_BASH_FIX, MONITOR = (2, 1, 295), (2, 1, 310), (2, 1, 314)
SCRUB = "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"
CREDENTIAL_NAME = re.compile(r"(?i)(token|secret|passw(or)?d|passphrase|credential|api_?key|access_?key|private_?key|session_?key)")
PROXY_NAME = re.compile(r"(?i)^(https?|all|ftp|no)_proxy$")


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def version_of(exe):
    """(2, 1, 317) from "<exe> --version", or None."""
    if not exe:
        return None
    argv = [sys.executable, "-I", exe] if str(exe).lower().endswith(".py") else [str(exe)]
    try:
        done = subprocess.run(argv + ["--version"], capture_output=True, encoding="utf-8", errors="replace", timeout=30,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = re.search(r"(\d+)\.(\d+)\.(\d+)", done.stdout)
    return tuple(int(x) for x in found.groups()) if done.returncode == 0 and found else None


def exe_of_pid(pid):
    """The executable path of a process, or None."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if os.name != "nt":
        try:
            return os.readlink(f"/proc/{pid}/exe")
        except OSError:
            return None
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        ok = kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
        return buffer.value if ok else None
    finally:
        kernel.CloseHandle(handle)


def path_claudes():
    seen, out = set(), []
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        found = shutil.which("claude", path=folder) if folder else None
        key = os.path.normcase(os.path.realpath(found)) if found else None
        if found and key not in seen:
            seen.add(key)
            out.append(found)
    return out


def other_claudes(listed):
    """claude in ~/.local/bin and the npm global folder that PATH did not already list."""
    seen = {os.path.normcase(os.path.realpath(x)) for x in listed}
    folders = [pathlib.Path.home() / ".local" / "bin"]
    if os.environ.get("APPDATA"):
        folders.append(pathlib.Path(os.environ["APPDATA"]) / "npm")
    out = []
    for folder in folders:
        found = shutil.which("claude", path=str(folder)) if folder.is_dir() else None
        if found and os.path.normcase(os.path.realpath(found)) not in seen:
            seen.add(os.path.normcase(os.path.realpath(found)))
            out.append(found)
    return out


def credential_names():
    """Names (never values) of variables that look like credentials, or proxies that carry user:password@."""
    return sorted(n for n, v in os.environ.items() if CREDENTIAL_NAME.search(n)
                  or (PROXY_NAME.match(n) and re.search(r"://[^/@\s]+@", v)))


def can_write(folder):
    """True when a file can be made in folder (it is removed again)."""
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".doctor-probe-"):
            return True
    except OSError:
        return False


def can_connect(target):
    host, _, port = target.rpartition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=5):
            return True
    except (OSError, ValueError):
        return False


def can_resolve(name):
    try:
        return bool(socket.getaddrinfo(name, None))
    except (OSError, UnicodeError):
        return False


def git_dirs(repo):
    """(git dir, common dir), absolute; empty strings when git cannot tell."""
    return tuple(subprocess.run(["git", "rev-parse", "--path-format=absolute", flag], cwd=repo, capture_output=True,
                                text=True).stdout.strip() for flag in ("--git-dir", "--git-common-dir"))


def git_mode(dirs):
    """In a container: "shared" (run_worker --git-common: the repository's .git), "clone" (worker_clone.sh), else None.
    A linked worktree in a container always means the shared .git, whatever DW_GIT_MODE says."""
    linked = bool(dirs[0] and dirs[1] and os.path.normcase(dirs[0]) != os.path.normcase(dirs[1]))
    mode = os.environ.get("DW_GIT_MODE")
    if linked or mode == "shared":
        return "shared"
    return "clone" if mode == "clone" and dirs[0] else None


def show(version):
    return ".".join(map(str, version)) if version else "unknown"


def read_layer(path):
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def git_bash():
    """Where Git Bash is, or None. CLAUDE_CODE_GIT_BASH_PATH, when set, is the only place looked at."""
    named = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    if named is not None:
        return named if named and pathlib.Path(named).is_file() else None
    for place in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if pathlib.Path(place).is_file():
            return place
    return None


def project_folder_name(path):
    """The ~/.claude/projects folder name Claude Code gives a launch folder: every character but A-Z, a-z, 0-9 is -."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def launch_counts(home, folders, days):
    """{folder: [sessions, last start date]} for sessions whose transcript says they started in that folder or below it
    (the deepest folder wins); None when HOME/.claude/projects does not exist."""
    root = home / ".claude" / "projects"
    if not root.is_dir():
        return None
    key = lambda f: os.path.normcase(os.path.normpath(str(f)))
    folders = sorted({key(f): f for f in folders}.items(), key=lambda kv: -len(kv[0]))
    counts = {f: [0, ""] for _, f in folders}
    names = [project_folder_name(f) for _, f in folders]
    since = datetime.datetime.now().timestamp() - days * 86400
    for project in root.iterdir():
        if not project.is_dir() or not any(project.name == n or project.name.startswith(n + "-") for n in names):
            continue
        for transcript in project.glob("*.jsonl"):
            try:
                if transcript.stat().st_mtime < since:
                    continue
                cwd, when = None, ""
                with open(transcript, encoding="utf-8", errors="replace") as fh:
                    for _, text in zip(range(50), fh):
                        try:
                            entry = json.loads(text)
                        except ValueError:
                            continue
                        if isinstance(entry, dict) and isinstance(entry.get("cwd"), str):
                            cwd, when = entry["cwd"], str(entry.get("timestamp") or "")[:10]
                            break
            except OSError:
                continue
            if not cwd:
                continue
            here = key(cwd)
            for k, folder in folders:
                if here == k or here.startswith(k.rstrip("\\/") + os.sep):
                    counts[folder][0] += 1
                    counts[folder][1] = max(counts[folder][1], when)
                    break
    return counts


def in_container(root):
    if (root / ".dockerenv").exists() or (root / "run" / ".containerenv").exists():
        return True
    try:
        return bool(re.search(r"docker|containerd|kubepods|libpod", (root / "proc" / "1" / "cgroup").read_text(errors="replace")))
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="the worktree to check (default: current folder)")
    ap.add_argument("--probe", action="store_true", help="also check the environment variable names this process sees; "
                    "in a container also the six isolation checks")
    ap.add_argument("--director", help="the DIRECTOR folder, which must be read-only inside a container (--probe)")
    ap.add_argument("--launch-days", type=int, default=30, help="launch folders: transcripts of the last N days (default 30)")
    ap.add_argument("--home", help=argparse.SUPPRESS)  # tests: another user folder
    ap.add_argument("--managed", help=argparse.SUPPRESS)  # tests: another managed-settings.json
    ap.add_argument("--path-claude", action="append", help=argparse.SUPPRESS)  # tests: these instead of PATH
    ap.add_argument("--fs-root", default="/", help=argparse.SUPPRESS)  # tests: where /.dockerenv is looked for
    ap.add_argument("--egress", default="example.com:443", help=argparse.SUPPRESS)  # tests: a host:port that must fail
    ap.add_argument("--dns-name", default="example.com", help=argparse.SUPPRESS)  # tests: a name that must not resolve
    a = ap.parse_args()
    setup = load("setup_project_settings")
    counts = {"ENFORCED": 0, "CONFIGURED_NOT_VERIFIED": 0, "NOT_ENFORCED": 0, "MISSING": 0, "WARN": 0}

    def item(status, name, detail):
        counts[status] = counts.get(status, 0) + 1
        print(f"{status:24} {name}: {detail}")

    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=a.repo or os.getcwd(), capture_output=True, text=True)
    if top.returncode != 0:
        print("doctor: not inside a git repo; pass --repo <worktree>", file=sys.stderr)
        return 2
    repo = pathlib.Path(top.stdout.strip())
    home = pathlib.Path(a.home) if a.home else pathlib.Path.home()
    managed = pathlib.Path(a.managed) if a.managed else pathlib.Path(
        r"C:\Program Files\ClaudeCode\managed-settings.json" if os.name == "nt" else "/etc/claude-code/managed-settings.json")
    layers = [("user", home / ".claude" / "settings.json"), ("project", repo / ".claude" / "settings.json"),
              ("local", repo / ".claude" / "settings.local.json"), ("managed", managed)]
    data = [(name, read_layer(path)) for name, path in layers]
    print(f"repo={repo.as_posix()} layers={' '.join(f'{n}={p.as_posix()}' for n, p in layers if p.exists()) or 'none'}")

    # versions
    effective, via = None, "none"
    if os.environ.get("CLAUDE_CODE_EXECPATH"):
        effective, via = os.environ["CLAUDE_CODE_EXECPATH"], "CLAUDE_CODE_EXECPATH"
    elif exe_of_pid(os.environ.get("CLAUDE_PID")):
        effective, via = exe_of_pid(os.environ.get("CLAUDE_PID")), "CLAUDE_PID"
    on_path = a.path_claude if a.path_claude is not None else path_claudes()
    others = [] if a.path_claude is not None else other_claudes(on_path)
    if effective is None and on_path:
        effective, via = on_path[0], "PATH"
    version = version_of(effective)
    print(f"VERSION                  effective {show(version)} via {via}" + (f" ({pathlib.Path(effective).as_posix()})" if effective else ""))
    for exe in on_path:
        found = version_of(exe)
        print(f"VERSION                  PATH {show(found)} ({pathlib.Path(exe).as_posix()})")
        if found and found < ON_FAILURE:
            item("WARN", "old claude on PATH", f"{show(found)} < 2.1.295 at {pathlib.Path(exe).as_posix()}: a broken hook "
                 "lets calls through there; whether to remove or update it is the PO's call")
    for exe in others:
        print(f"VERSION                  other {show(version_of(exe))} ({pathlib.Path(exe).as_posix()}, not on PATH)")

    # hooks
    disabled = [name for name, d in data if d.get("disableAllHooks") is True]
    hooks = {event: [e for _, d in data for e in ((d.get("hooks") or {}).get(event) or []) if isinstance(e, dict)]
             for event in ("PreToolUse",) + setup.POST_EVENTS}
    guards = setup.guard_entries({"hooks": {"PreToolUse": hooks["PreToolUse"]}})
    command = setup.hook_command(guards[0]) if guards else None
    if disabled:
        item("NOT_ENFORCED", "hook_guard", f"disableAllHooks is true in the {', '.join(disabled)} settings")
    elif not guards or not command:
        item("MISSING", "hook_guard", "no PreToolUse entry runs hook_guard.py (setup_project_settings.py --runtime-guard)")
    elif guards[0].get("matcher") != "*" or setup.guard_hook(guards[0]).get("onFailure") != "block" or not setup.profile_arg(command):
        item("MISSING", "hook_guard", f"entry has matcher {guards[0].get('matcher')!r}, onFailure "
             f"{setup.guard_hook(guards[0]).get('onFailure')!r}, profile {setup.profile_arg(command)!r}; wanted *, block and a profile")
    else:
        works, detail = setup.hook_works(command, setup.protect_arg(command))
        if not works:
            item("NOT_ENFORCED", "hook_guard", f"the hook did not answer as it must ({detail})")
        elif version is None:
            item("CONFIGURED_NOT_VERIFIED", "hook_guard", f"hook test passed ({detail}); claude version unknown, "
                 "onFailure needs >= 2.1.295")
        elif version < ON_FAILURE:
            item("NOT_ENFORCED", "hook_guard", f"claude {show(version)} < 2.1.295 has no onFailure: a broken hook lets calls through")
        else:
            item("ENFORCED", "hook_guard", f"hook test passed ({detail}), mode {setup.mode_arg(command)}, onFailure block, "
                 f"claude {show(version)}")
    if os.name == "nt" and guards and not disabled:
        bash = git_bash()
        if version and version >= GIT_BASH_FIX:
            item("ENFORCED", "hook without Git Bash", f"claude {show(version)} >= 2.1.310")
        elif bash:
            item("ENFORCED", "hook without Git Bash", f"Git Bash found at {pathlib.Path(bash).as_posix()}")
        else:
            item("NOT_ENFORCED", "hook without Git Bash", f"claude {show(version)} < 2.1.310 and no Git Bash: some hook commands are skipped")
    if guards and not disabled:
        if guards[0].get("matcher") not in ("*", "Bash") and "Bash" not in str(guards[0].get("matcher")).split("|"):
            item("NOT_ENFORCED", "Monitor commands", "the hook_guard matcher does not cover Bash")
        elif version and version >= MONITOR:
            item("ENFORCED", "Monitor commands", f"claude {show(version)} >= 2.1.314 sends them through the hook")
        else:
            item("NOT_ENFORCED", "Monitor commands", f"claude {show(version)} < 2.1.314: Monitor commands skip the hook")

    # action log
    posts = {event: [setup.hook_command({"hooks": [h]}) or h.get("command", "") for e in hooks[event]
                     for h in e.get("hooks") or [] if isinstance(h, dict) and "audit_log.py" in str(h.get("command", ""))]
             for event in setup.POST_EVENTS}
    logs = {m.group(1) for cmds in posts.values() for c in cmds for m in [re.search(r'--log "([^"]*)"', c)] if m}
    if disabled:
        item("NOT_ENFORCED", "audit_log", f"disableAllHooks is true in the {', '.join(disabled)} settings")
    elif not all(posts.values()):
        item("MISSING", "audit_log", "no audit_log.py hook for " + ", ".join(e for e, c in posts.items() if not c))
    elif len(logs) != 1:
        item("MISSING", "audit_log", f"the hooks name {len(logs)} logs; wanted one")
    else:
        try:
            log = pathlib.Path(load("audit_log").expand(logs.pop(), repo))  # {worktree} / {container} as the hook does
        except ValueError as error:
            log, problem = None, str(error)
        if log is None:
            item("MISSING", "audit_log", problem)
        elif not log.exists():
            item("CONFIGURED_NOT_VERIFIED", "audit_log", f"hooks set; {log.as_posix()} has no entries yet")
        else:
            done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(HERE / "audit_log.py"), "verify", "--log", str(log)],
                                  capture_output=True, encoding="utf-8", errors="replace")
            last = (done.stdout.strip().splitlines() or [""])[-1]
            item("ENFORCED" if done.returncode == 0 else "NOT_ENFORCED", "audit_log", last or f"verify exit {done.returncode}")

    # permissions, env, mode
    profile = setup.profile_arg(command) if command else None
    smap = setup.sessions_arg(command) if command else None
    profiles = profile
    if profile in setup.PROFILES and smap:
        try:
            profiles = sorted(set(setup.session_profiles(pathlib.Path(smap), profile)) | {profile})
            print(f"INFO                     sessions: {smap} gives {', '.join(profiles)}")
        except SystemExit as error:
            item("MISSING", "sessions file", str(error))
            profiles = None
    if profile in setup.PROFILES and profiles:
        mode = setup.mode_arg(command)
        rules = setup.load_guard_rules()
        wanted = setup.wanted_permissions(rules, profiles, mode)
        have = {k: [p for _, d in data for p in ((d.get("permissions") or {}).get(k) or []) if isinstance(d.get("permissions"), dict)]
                for k in wanted}
        missing = {k: [p for p in v if p not in have[k]] for k, v in wanted.items()}
        ours = setup.rule_permissions(rules)
        stray = {k: [p for p in have[k] if p in ours and p not in wanted[k]] for k in wanted}
        if any(stray.values()):  # a rule permission the mode does not want still stops the call (H04)
            item("MISSING", "permissions", ", ".join(f"{len(v)} rule permission(s) in permissions.{k}" for k, v in stray.items() if v)
                 + f" that {mode} mode does not want (they would still stop the call; setup_project_settings.py --apply)")
        elif mode == "remind" and not any(missing.values()):
            item("CONFIGURED_NOT_VERIFIED", "permissions", "remind mode: only the secret rules' deny is written; other "
                 "flagged calls run with a reminder")
        elif any(missing.values()):
            item("MISSING", "permissions", ", ".join(f"{len(v)} of permissions.{k}" for k, v in missing.items() if v)
                 + f" for the {profile} profile" + (" with the sessions file" if smap else ""))
        else:
            item("CONFIGURED_NOT_VERIFIED", "permissions", f"every {profile} deny / ask rule is set (Claude Code applies "
                 "them; this run does not)")
    env = {}
    for _, d in data:
        env.update(d.get("env") if isinstance(d.get("env"), dict) else {})
    if str(env.get(SCRUB)) != "1":
        item("MISSING", "env_scrub", f"env.{SCRUB} is not 1")
    elif not a.probe:
        item("CONFIGURED_NOT_VERIFIED", "env_scrub", f"{SCRUB}=1; run doctor --probe from Claude's Bash tool to check")
    else:
        names = credential_names()
        if names:
            item("NOT_ENFORCED", "env_scrub", f"{len(names)} credential-like variable(s) still here (names only): {', '.join(names)}")
        else:
            item("ENFORCED", "env_scrub", "no credential-like variable names in this process")
    mode = None
    for _, d in data:
        if isinstance(d.get("permissions"), dict) and d["permissions"].get("defaultMode"):
            mode = d["permissions"]["defaultMode"]
    if mode == "bypassPermissions":
        item("WARN", "permission mode", "defaultMode is bypassPermissions: only the hook and deny / ask rules stand")

    # isolation, worktree, pause, review
    container = in_container(pathlib.Path(a.fs_root))
    dirs = git_dirs(repo)
    mode = git_mode(dirs) if container else None
    if container and not a.probe and mode == "shared":
        item("NOT_ENFORCED", "isolation", "container: K1 shared .git (run_worker --git-common): the worker can change "
             "every branch and tag of the repository; use run_worker --clone")
    elif container and not a.probe:
        item("CONFIGURED_NOT_VERIFIED", "isolation", "in a container; run doctor --probe --director DIR to check its limits")
    elif container:
        checks = [("root read-only", not can_write(a.fs_root)),
                  ("DIRECTOR read-only", bool(a.director) and pathlib.Path(a.director).is_dir() and not can_write(a.director)),
                  (f"no connection to {a.egress}", not can_connect(a.egress)),
                  (f"{a.dns_name} does not resolve", not can_resolve(a.dns_name)),
                  ("own .git (K1)", mode != "shared"),
                  ("no credential names", not credential_names())]
        failed = [name for name, ok in checks if not ok]
        item("NOT_ENFORCED" if failed else "ENFORCED", "isolation", "container: " + ", ".join(
            f"{name} {'FAIL' if name in failed else 'ok'}" for name, _ in checks)
             + (" (no --director given)" if not a.director else ""))
    else:
        item("NOT_ENFORCED", "isolation", "native Windows, no OS-level isolation for shell" if os.name == "nt"
             else "no container: no OS-level isolation for shell")
    if profile == "director":
        print("INFO                     worktree: director profile, not checked")
    else:
        linked = dirs[0] and dirs[1] and os.path.normcase(dirs[0]) != os.path.normcase(dirs[1])
        if mode == "clone":
            item("ENFORCED", "worktree", "the worker's own clone (worker_clone.sh)")
        else:
            item("ENFORCED" if linked else "NOT_ENFORCED", "worktree",
                 "a linked worktree of its own" if linked else "this is the main checkout, not a worker's own worktree")
    if command and setup.pause_arg(command):
        flag = pathlib.Path(setup.pause_arg(command))
        try:
            first = flag.read_text(encoding="utf-8", errors="replace").splitlines()[:1] if flag.exists() else None
        except OSError:
            first = ["(flag unreadable)"]
        print(f"INFO                     pause: {'on: ' + (first[0][:200] if first else '') if first is not None else 'off'} ({flag.as_posix()})")
    if command and setup.review_arg(command):
        print("INFO                     review: on; each review is one claude -p call (no money, uses subscription quota)")

    # launch folders: settings are read only where a session starts
    trees = list(setup.worktrees(repo))
    counts_by = launch_counts(home, trees, a.launch_days)
    if counts_by is None:
        print(f"INFO                     launch folders: no {(home / '.claude' / 'projects').as_posix()}, not checked")
    else:
        guarded = {}
        for tree in trees:
            local = read_layer(tree / ".claude" / "settings.local.json")
            shared = read_layer(tree / ".claude" / "settings.json")
            guarded[tree] = bool(setup.guard_entries(local) or setup.guard_entries(shared))
            n, last = counts_by.get(tree, [0, ""])
            print(f"INFO                     launch: {tree.as_posix()} sessions={n}{f' last={last}' if last else ''} "
                  f"hook_guard={'yes' if guarded[tree] else 'no'}")
        started = [t.as_posix() for t in trees if counts_by.get(t, [0])[0]] or ["none"]
        for tree in trees:
            n = counts_by.get(tree, [0])[0]
            if guarded[tree] and not n:
                item("WARN", "settings unread", f"{tree.as_posix()} has a hook_guard entry, but no session started there in "
                     f"{a.launch_days} days; settings are read only from the launch folder (sessions start in: "
                     f"{', '.join(started)})")
            elif n and not guarded[tree] and any(guarded.values()):
                item("WARN", "launch folder unguarded", f"{n} session(s) started in {tree.as_posix()}, whose settings have "
                     "no hook_guard entry, while another worktree has one (setup_project_settings.py --session-map)")
    c = counts
    print(f"DOCTOR: enforced={c['ENFORCED']} not_verified={c['CONFIGURED_NOT_VERIFIED']} not_enforced={c['NOT_ENFORCED']} "
          f"missing={c['MISSING']} warn={c['WARN']}")
    return 1 if c["NOT_ENFORCED"] or c["MISSING"] else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
