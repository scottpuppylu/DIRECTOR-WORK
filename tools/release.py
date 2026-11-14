"""Release this repository in one pass (2.2.2, ported from the DeepSeek port's ds.3): fetch, compare with the remote
branch, check VERSION / CHANGELOG / tag order, run the selftest, scan what is about to go public, then push the
branch, tag it and create the GitHub Release.

  python -I -X utf8 tools/release.py [--repo DIR] [--merge] [--execute] [--config FILE] [--version X]

Default is a dry run: it fetches (a fetch only updates remote-tracking refs) and runs every check, then prints the
remote steps it would take. Nothing on the remote changes without --execute.
A release is made from a commit, never the working tree: VERSION and CHANGELOG.md are read from HEAD
(`git show HEAD:VERSION`), and a tracked file that is modified or staged stops every run, dry run too, with the next
step to take (2.2.2: a VERSION edited but not committed used to pass the dry run).

Steps, in order; each prints `STEP <name>: OK | FAIL | SKIP | PLAN ...`, and a FAIL stops with a `NEXT:` line:
  fetch      git fetch <remote> --tags (no --prune-tags: local tags are left alone)
  worktree   no tracked file is modified or staged (untracked files are not released and do not count)
  state      HEAD against <remote>/<branch>: UP_TO_DATE, AHEAD n, BEHIND n or DIVERGED ahead n / behind n.
             BEHIND (nothing new to release) stops. DIVERGED stops unless --merge: then the dry run predicts conflicts
             with `git merge-tree`, and --execute makes branch release/<version> from <remote>/<branch>, merges HEAD
             into it with --no-ff and stops on a conflict, listing the conflicted files (resolve, commit, run again
             from that branch)
  version    VERSION at HEAD equals the first `## ` heading of CHANGELOG.md at HEAD; tag v<version> is not on the
             remote yet, or already points at HEAD (a rerun); <version> sorts above every remote tag of the same shape
             (<major>.<minor>.<patch>[-<label>.<n>]) - 2.2.0-x.2 after 2.2.1-x.1 fails; and <n> is above the <n> of
             every remote tag with the same label: a -<label>.N serial never restarts when the base version moves on
             (after v2.2.1-x.2 comes 2.2.2-x.3, not 2.2.2-x.1)
  selftest   the selftest command exits 0 (default `python -I -X utf8 tools/selftest.py`)
  scan       <remote>/<branch>..HEAD, everything that goes public: paths (DIRECTOR/, CLAUDE.local.md,
             .claude/settings.local.json, Claude session transcripts), added lines (secret formats from
             secret_mask.py, key = value secrets with a real-looking value, email addresses other than noreply and
             *.invalid, <drive>:/Users/<name> paths), commit messages and commit author / committer emails. gitleaks
             runs too when it is on PATH (not required)
  push       git push <remote> HEAD:refs/heads/<branch> (never --force), then ls-remote must equal HEAD
  tag        git tag -a v<version> on HEAD, git push <remote> refs/tags/v<version> (one tag, never --tags), then
             ls-remote must show the tag peeled to HEAD
  release    gh release create v<version> --verify-tag --latest, notes = the CHANGELOG section of <version>, title from
             the config; then gh release view must show the release
A rerun after a failure skips what is already done (branch already at HEAD, tag already at HEAD, release present).

Config: the optional "release" object of director_work.json (--config), keys remote, branch, title ({version} is
filled in), tag_message, selftest (a command line), gh_repo (owner/name; default from the remote URL). Missing keys
use the defaults above.

Ends with `RELEASE: DRY_RUN|DONE|FAIL ...`. Exit codes: 0 dry run clean or release done, 1 a step failed, 2 cannot run.
Standard library plus git; gh only for the release step.
"""
import argparse
import importlib.util
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
DEFAULTS = {"remote": "origin", "branch": "main", "title": "DIRECTOR-WORK {version}",
            "tag_message": "DIRECTOR-WORK {version}", "selftest": "python -I -X utf8 tools/selftest.py", "gh_repo": None}
VERSION_SHAPE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([A-Za-z]+)\.(\d+))?$")
PRIVATE_PATHS = [(re.compile(r"(^|/)DIRECTOR/"), "a DIRECTOR/ file (project state, never public)"),
                 (re.compile(r"(^|/)CLAUDE\.local\.md$"), "CLAUDE.local.md (local instructions)"),
                 (re.compile(r"(^|/)\.claude/settings\.local\.json$"), ".claude/settings.local.json (local settings)"),
                 (re.compile(r"(^|/)\.claude/projects/|(^|/)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
                             r"\.jsonl$"), "a Claude session transcript")]
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
USER_PATH = re.compile(r"(?i)\b[A-Z]:(?:[\\/]|\\\\)+Users(?:[\\/]|\\\\)+")
REAL_VALUE = re.compile(r"^[A-Za-z0-9/+_=.-]{12,}$")


class Stop(Exception):
    """A step failed; message is the reason, next_step what to do about it."""
    def __init__(self, message, next_step):
        super().__init__(message)
        self.next_step = next_step


def run(args, repo, check=False, input_text=None):
    proc = subprocess.run([str(a) for a in args], cwd=str(repo), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", input=input_text)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(map(str, args))}: {(proc.stderr or proc.stdout).strip()[:400]}")
    return proc


def git(repo, *args, check=True):
    proc = run(["git", *args], repo)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(proc.stderr or proc.stdout).strip()[:400]}")
    return proc.stdout.strip() if check else proc


def version_key(text):
    """(major, minor, patch, has_label, label, n) or None. A plain x.y.z sorts after its own x.y.z-label.n."""
    m = VERSION_SHAPE.match(text.strip())
    if not m:
        return None
    major, minor, patch, label, n = m.groups()
    return (int(major), int(minor), int(patch), 0 if label else 1, label or "", int(n or 0))


def changelog_top(text):
    """(version of the first `## ` heading, its section text without the heading)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("## "):
            m = re.match(r"##\s+v?(\S+?)(?:[（(\s]|$)", line)
            body = []
            for other in lines[i + 1:]:
                if other.startswith("## "):
                    break
                body.append(other)
            return (m.group(1) if m else ""), "\n".join(body).strip() + "\n"
    return None, ""


def load_config(path):
    config = dict(DEFAULTS)
    if path:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
        block = data.get("release") or {}
        if not isinstance(block, dict):
            raise ValueError("\"release\" in the config is not an object")
        unknown = sorted(set(block) - set(DEFAULTS) - {"_comment"})
        if unknown:
            raise ValueError(f"\"release\" has keys this tool does not read: {', '.join(unknown)}")
        config.update({k: v for k, v in block.items() if k in DEFAULTS and v is not None})
    return config


def gh_repo_from_url(url):
    m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url or "")
    return f"{m.group(1)}/{m.group(2)}" if m else None


def secret_module():
    spec = importlib.util.spec_from_file_location("secret_mask", HERE / "secret_mask.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def email_allowed(address):
    local, _, domain = address.lower().partition("@")
    return "noreply" in local or domain.endswith("users.noreply.github.com") or domain.endswith(".invalid") \
        or domain == "invalid"


def line_findings(text, secrets):
    """What in one added line must not go public: [(kind, shown)]; a secret is never shown, only its kind."""
    found = []
    for kind, pattern in secrets.PATTERNS:
        if pattern.search(text):
            found.append((kind, f"[{kind}]"))
    for kind, pattern in secrets.KEEP_PREFIX:
        if kind != "assignment":
            continue
        for m in pattern.finditer(text):
            value = m.group(2).strip("\"'\\")
            if REAL_VALUE.match(value) and re.search(r"\d", value) and re.search(r"[A-Za-z]", value):
                found.append(("secret_assignment", "[secret value]"))
    for address in EMAIL.findall(text):
        if not email_allowed(address):
            found.append(("email", address))
    for m in USER_PATH.finditer(text):
        found.append(("user_path", text[m.start():m.end() + 20].strip()))
    return found


def scan(repo, base, head):
    """Problems in base..head, each `<where>: <what>`; and notes."""
    problems, notes = [], []
    secrets = secret_module()
    names = git(repo, "diff", "--name-only", "--no-renames", "--diff-filter=ACMR", f"{base}..{head}").splitlines()
    for name in names:
        for pattern, what in PRIVATE_PATHS:
            if pattern.search(name):
                problems.append(f"{name}: {what}")
    diff = run(["git", "-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff", "-U0", f"{base}..{head}"], repo)
    current, number = "?", 0
    for raw in diff.stdout.splitlines():
        if raw.startswith("+++ "):
            current = raw[6:] if raw.startswith("+++ b/") else raw[4:]
            continue
        hunk = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", raw)
        if hunk:
            number = int(hunk.group(1))
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            for kind, shown in line_findings(raw[1:], secrets):
                problems.append(f"{current}:{number}: {kind} {shown}")
            number += 1
    log = git(repo, "log", "--format=%H%x1f%an <%ae>%x1f%cn <%ce>%x1f%B%x1e", f"{base}..{head}")
    for record in filter(None, (r.strip() for r in log.split("\x1e"))):
        sha, author, committer, body = (record.split("\x1f") + ["", "", ""])[:4]
        for who, value in (("author", author), ("committer", committer)):
            for address in EMAIL.findall(value):
                if not email_allowed(address):
                    problems.append(f"commit {sha[:10]} {who}: email {address}")
        for kind, shown in line_findings(body, secrets):
            problems.append(f"commit {sha[:10]} message: {kind} {shown}")
    if shutil.which("gitleaks"):
        proc = run(["gitleaks", "detect", "--source", ".", "--no-banner", "--redact",
                    f"--log-opts={base}..{head}"], repo)
        if proc.returncode == 1:
            problems.append("gitleaks found a leak (run it again without --redact locally to see where)")
        elif proc.returncode != 0:
            notes.append(f"gitleaks did not run cleanly (exit {proc.returncode}); its result is not counted")
        else:
            notes.append("gitleaks: no leaks")
    else:
        notes.append("gitleaks is not on PATH; only this tool's own patterns ran")
    return problems, notes, len(names)


class Release:
    def __init__(self, repo, config, execute, merge, version):
        self.repo, self.config, self.execute, self.merge, self.version = repo, config, execute, merge, version
        self.remote, self.branch = config["remote"], config["branch"]
        self.upstream = f"{self.remote}/{self.branch}"
        self.planned = []

    def step(self, name, status, detail=""):
        print(f"STEP {name}: {status}" + (f" {detail}" if detail else ""))

    def head(self):
        return git(self.repo, "rev-parse", "HEAD")

    def fetch(self):
        proc = git(self.repo, "fetch", self.remote, "--tags", check=False)
        if proc.returncode != 0:
            raise Stop(f"git fetch {self.remote} failed: {(proc.stderr or proc.stdout).strip()[:300]}",
                       "check the network and the remote, then run again; without a fetch the remote state is unknown")
        self.step("fetch", "OK", f"{self.remote} (remote-tracking refs and tags only)")

    def state(self):
        if git(self.repo, "rev-parse", "--verify", "-q", self.upstream, check=False).returncode != 0:
            raise Stop(f"{self.upstream} does not exist after the fetch", f"check --config remote / branch")
        counts = git(self.repo, "rev-list", "--left-right", "--count", f"{self.upstream}...HEAD").split()
        behind, ahead = int(counts[0]), int(counts[1])
        current = git(self.repo, "rev-parse", "--abbrev-ref", "HEAD")
        where = f"HEAD ({current} {self.head()[:10]}) vs {self.upstream} ({git(self.repo, 'rev-parse', self.upstream)[:10]})"
        if behind == 0 and ahead == 0:
            self.step("state", "OK", f"UP_TO_DATE {where}: nothing new to push; tag and release still run")
            return "up_to_date"
        if behind and not ahead:
            raise Stop(f"BEHIND {behind} {where}: the remote has commits this branch does not, and nothing new here",
                       f"git merge --ff-only {self.upstream}, then add the release commits and run again")
        if ahead and not behind:
            self.step("state", "OK", f"AHEAD {ahead} {where}: a fast-forward push")
            return "ahead"
        detail = f"DIVERGED ahead {ahead} / behind {behind} {where}"
        if not self.merge:
            raise Stop(detail, f"run again with --merge (makes release/<version> from {self.upstream} and merges "
                               f"HEAD into it with --no-ff), or merge by hand")
        if not self.execute:
            proc = git(self.repo, "merge-tree", "--write-tree", "--name-only", "--no-messages", self.upstream, "HEAD",
                       check=False)
            if proc.returncode == 1:
                files = [f for f in proc.stdout.splitlines()[1:] if f.strip()]
                self.step("state", "PLAN", f"{detail}; --execute would merge into release/<version> and stop on "
                          f"{len(files)} conflicted file(s): {', '.join(files)}")
            elif proc.returncode == 0:
                self.step("state", "PLAN", f"{detail}; --execute would merge into release/<version> with no conflicts")
            else:
                self.step("state", "PLAN", f"{detail}; could not predict conflicts ({proc.stderr.strip()[:200]})")
            print("  ~ the checks below run on HEAD before the merge; --execute runs them again on the merge")
            return "diverged"
        return self.do_merge(detail)

    def do_merge(self, detail):
        version = self.read_version()
        target = f"release/{version}"
        if git(self.repo, "rev-parse", "--verify", "-q", f"refs/heads/{target}", check=False).returncode == 0:
            raise Stop(f"{detail}; branch {target} already exists",
                       f"switch to {target} and run again from there, or delete it if it is stale")
        source = git(self.repo, "rev-parse", "--abbrev-ref", "HEAD")
        source_ref = source if source != "HEAD" else self.head()
        git(self.repo, "switch", "-c", target, self.upstream)
        proc = git(self.repo, "merge", "--no-ff", "--no-edit", "-m", f"Merge {source_ref} into {self.branch} for v{version}",
                   source_ref, check=False)
        if proc.returncode != 0:
            files = git(self.repo, "diff", "--name-only", "--diff-filter=U").splitlines()
            raise Stop(f"{detail}; merge into {target} has {len(files)} conflicted file(s): {', '.join(files) or '?'}",
                       f"you are on {target} with the merge in progress: resolve those files, git add them, "
                       f"git commit, then run release.py again from {target}")
        self.step("state", "OK", f"{detail}; merged into {target} ({self.head()[:10]})")
        return "merged"

    def at_head(self, name):
        """A file's text as committed at HEAD (never the working tree), or None when HEAD has no such file."""
        proc = git(self.repo, "show", f"HEAD:{name}", check=False)
        return proc.stdout.lstrip("\ufeff") if proc.returncode == 0 else None

    def read_version(self):
        if self.version:
            return self.version
        text = self.at_head("VERSION")
        if text is None:
            raise Stop("no VERSION file at HEAD", "write the version into VERSION and commit it, or pass --version")
        return text.strip()

    def check_version(self):
        version = self.read_version()
        key = version_key(version)
        if not key:
            raise Stop(f"version {version!r} is not <major>.<minor>.<patch>[-<label>.<n>]", "fix VERSION")
        changelog = self.at_head("CHANGELOG.md")
        top, section = changelog_top(changelog) if changelog is not None else (None, "")
        if top != version:
            raise Stop(f"VERSION is {version} but the first CHANGELOG.md heading at HEAD is {top or 'missing'}",
                       "put the new version's section on top of CHANGELOG.md (or fix VERSION) and commit it")
        if not section.strip():
            raise Stop(f"the CHANGELOG section of {version} is empty", "write the release notes")
        self.notes = section
        tag = f"v{version}"
        remote_tags = {}
        for line in git(self.repo, "ls-remote", "--tags", self.remote).splitlines():
            sha, _, ref = line.partition("\t")
            name = ref.replace("refs/tags/", "")
            if name.endswith("^{}"):
                remote_tags[name[:-3]] = sha
            else:
                remote_tags.setdefault(name, sha)
        self.tag, self.tag_done = tag, False
        if tag in remote_tags:
            if remote_tags[tag] == self.head():
                self.tag_done = True
            else:
                raise Stop(f"tag {tag} is already on the remote at {remote_tags[tag][:10]}, not HEAD {self.head()[:10]}",
                           "pick a new version (VERSION and CHANGELOG); a pushed tag is never moved")
        higher = sorted((name for name in remote_tags if name != tag and version_key(name)
                         and version_key(name) >= key), key=version_key)
        if higher:
            raise Stop(f"{tag} does not sort above the remote tag(s) {', '.join(higher)}",
                       f"use a version above {higher[-1]} (for example bump the base version, not only the -label.n)")
        if key[4]:
            # a -<label>.N counter is its own serial: it only goes up, also when the base version moves on
            # (2.2.1-x.2 -> 2.2.2-x.3, never 2.2.2-x.1)
            same = sorted((name for name in remote_tags if name != tag and version_key(name)
                           and version_key(name)[4] == key[4] and version_key(name)[5] >= key[5]),
                          key=lambda name: version_key(name)[5])
            if same:
                top_n = version_key(same[-1])[5]
                raise Stop(f"{tag}: -{key[4]}.{key[5]} is not above the -{key[4]}.N of the remote tag(s) "
                           f"{', '.join(same)}; the -{key[4]}.N serial never restarts",
                           f"use -{key[4]}.{top_n + 1} (VERSION and CHANGELOG)")
        others = [name for name in remote_tags if not version_key(name)]
        self.step("version", "OK", f"{version} = CHANGELOG top; {tag} " + ("already at HEAD (rerun)" if self.tag_done
                  else "is new") + f"; above {len(remote_tags) - len(others) - (1 if self.tag_done else 0)} remote tag(s)"
                  + (f"; {len(others)} tag(s) of another shape not compared" if others else ""))
        return version

    def check_worktree(self):
        dirty = run(["git", "-c", "core.quotepath=false", "status", "--porcelain", "--untracked-files=no"], self.repo)
        if dirty.returncode != 0:
            raise RuntimeError(f"git status: {(dirty.stderr or dirty.stdout).strip()[:400]}")
        names = [line[3:] for line in dirty.stdout.splitlines() if line.strip()]
        if names:
            said = ""
            if "VERSION" in names and not self.version:
                work = (self.repo / "VERSION").read_text(encoding="utf-8-sig").strip() if (self.repo / "VERSION").is_file() else "gone"
                said = f"; VERSION in the working tree is {work}, at HEAD {(self.at_head('VERSION') or 'missing').strip()}"
            raise Stop(f"tracked files are modified or staged: {', '.join(names[:5])}"
                       + (f" and {len(names) - 5} more" if len(names) > 5 else "") + said,
                       "git add and git commit them (or git restore them), then run release.py again; a release is made "
                       "from HEAD, never the working tree")
        self.step("worktree", "OK", "no tracked file modified or staged (untracked files are not released)")

    def selftest(self):
        command = shlex.split(self.config["selftest"], posix=os.name != "nt") if self.config["selftest"] else []
        if command and command[0] in ("python", "python3", "py"):
            command[0] = sys.executable
        if not command:
            raise Stop("no selftest command", "set \"release\": {\"selftest\": \"...\"} in the config")
        proc = run(command, self.repo)
        last = [l for l in (proc.stdout or "").splitlines() if l.strip()]
        if proc.returncode != 0:
            raise Stop(f"selftest exit {proc.returncode}: {last[-1] if last else (proc.stderr or '').strip()[:300]}",
                       "fix the failing test and run again")
        self.step("selftest", "OK", last[-1] if last else f"exit 0 ({' '.join(command)})")

    def scan(self):
        problems, notes, files = scan(self.repo, self.upstream, "HEAD")
        for note in notes:
            print(f"  ~ {note}")
        if problems:
            for problem in problems[:40]:
                print(f"  - {problem}")
            if len(problems) > 40:
                print(f"  - ... and {len(problems) - 40} more")
            raise Stop(f"{len(problems)} item(s) must not go public ({self.upstream}..HEAD)",
                       "remove them from the commits (amend or a new commit that deletes them is not enough for "
                       "history: rewrite the unpushed commits), then run again")
        self.step("scan", "OK", f"{self.upstream}..HEAD: {files} changed file(s), commits, authors: nothing private")

    def push(self):
        head = self.head()
        remote_sha = self.remote_branch_sha()
        if remote_sha == head:
            self.step("push", "SKIP", f"{self.remote} {self.branch} is already {head[:10]}")
            return
        if not self.execute:
            self.planned.append(f"git push {self.remote} HEAD:refs/heads/{self.branch}  (fast-forward, no --force)")
            return
        proc = git(self.repo, "push", self.remote, f"HEAD:refs/heads/{self.branch}", check=False)
        if proc.returncode != 0:
            raise Stop(f"push rejected: {(proc.stderr or proc.stdout).strip()[-300:]}",
                       "someone pushed meanwhile: run release.py again (it fetches and compares again); never --force")
        if self.remote_branch_sha() != head:
            raise Stop(f"after the push ls-remote {self.branch} is {self.remote_branch_sha()}, not {head}",
                       "look at the remote by hand before going on")
        self.step("push", "OK", f"ls-remote {self.branch} = {head}")

    def remote_branch_sha(self):
        out = git(self.repo, "ls-remote", self.remote, f"refs/heads/{self.branch}")
        return out.split("\t")[0] if out else None

    def tag_step(self, version):
        head = self.head()
        if self.tag_done:
            self.step("tag", "SKIP", f"{self.tag} is already on the remote at HEAD")
            return
        message = self.config["tag_message"].format(version=version)
        if not self.execute:
            self.planned.append(f"git tag -a {self.tag} -m {message!r} {head[:10]}; git push {self.remote} refs/tags/{self.tag}")
            return
        local = git(self.repo, "rev-parse", "-q", "--verify", f"refs/tags/{self.tag}^{{commit}}", check=False)
        if local.returncode == 0 and local.stdout.strip() != head:
            raise Stop(f"a local tag {self.tag} points at {local.stdout.strip()[:10]}, not HEAD",
                       f"look at it (git show {self.tag}); delete the local one only if it is a mistake")
        if local.returncode != 0:
            git(self.repo, "tag", "-a", self.tag, "-m", message, head)
        proc = git(self.repo, "push", self.remote, f"refs/tags/{self.tag}", check=False)
        if proc.returncode != 0:
            raise Stop(f"tag push failed: {(proc.stderr or proc.stdout).strip()[-300:]}", "run again; never --force")
        peeled = git(self.repo, "ls-remote", "--tags", self.remote, f"refs/tags/{self.tag}^{{}}")
        if not peeled or peeled.split("\t")[0] != head:
            raise Stop(f"ls-remote does not show {self.tag} peeled to {head[:10]}: {peeled or 'nothing'}",
                       "look at the remote tags by hand")
        self.step("tag", "OK", f"{self.tag}^{{}} = {head}")

    def release_step(self, version):
        repo_name = self.config["gh_repo"] or gh_repo_from_url(git(self.repo, "remote", "get-url", self.remote))
        title = self.config["title"].format(version=version)
        gh = shutil.which("gh")
        if not self.execute and not (repo_name and gh):
            self.planned.append(f"gh release create {self.tag} -R {repo_name or '<owner/name: set release.gh_repo>'} "
                                f"--title {title!r} --notes-file <CHANGELOG section> --latest --verify-tag"
                                + ("" if gh else "  (gh is not on PATH: --execute will stop here)"))
            return
        if not repo_name:
            raise Stop("cannot tell the GitHub repository from the remote URL", "set \"release\": {\"gh_repo\": ...}")
        if not gh:
            raise Stop("gh (GitHub CLI) is not on PATH", "install gh and gh auth login, then run again")
        view = run([gh, "release", "view", self.tag, "-R", repo_name, "--json", "url,tagName,isDraft"], self.repo)
        if view.returncode == 0:
            self.step("release", "SKIP", f"already there: {json.loads(view.stdout).get('url')}")
            return
        if not self.execute:
            self.planned.append(f"gh release create {self.tag} -R {repo_name} --title {title!r} --notes-file <CHANGELOG "
                                f"section, {len(self.notes.splitlines())} lines> --latest --verify-tag")
            return
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
            handle.write(self.notes)
            notes_file = handle.name
        try:
            proc = run([gh, "release", "create", self.tag, "-R", repo_name, "--title", title, "--notes-file", notes_file,
                        "--latest", "--verify-tag"], self.repo)
        finally:
            os.unlink(notes_file)
        if proc.returncode != 0:
            raise Stop(f"gh release create failed: {(proc.stderr or proc.stdout).strip()[-300:]}",
                       "fix the cause (gh auth status, tag on the remote) and run again; branch and tag are kept")
        view = run([gh, "release", "view", self.tag, "-R", repo_name, "--json", "url,tagName,isDraft"], self.repo)
        if view.returncode != 0:
            raise Stop("gh release view cannot see the new release", f"look at https://github.com/{repo_name}/releases")
        data = json.loads(view.stdout)
        self.step("release", "OK", f"{data.get('url')} (draft={data.get('isDraft')})")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="the repository to release (default: current folder)")
    ap.add_argument("--config", help="director_work.json with an optional \"release\" object")
    ap.add_argument("--version", help="the version to release (default: the VERSION file)")
    ap.add_argument("--merge", action="store_true", help="when HEAD and the remote branch diverged, merge into release/<version>")
    ap.add_argument("--execute", action="store_true", help="change the remote (default: dry run)")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    repo = pathlib.Path(a.repo).resolve()
    try:
        config = load_config(a.config)
    except (OSError, ValueError) as error:
        print(f"RELEASE: NOT_RUN config: {error}")
        return 2
    if run(["git", "rev-parse", "--git-dir"], repo).returncode != 0:
        print(f"RELEASE: NOT_RUN {repo} is not a git repository")
        return 2
    job = Release(repo, config, a.execute, a.merge, a.version)
    mode = "EXECUTE" if a.execute else "DRY_RUN"
    print(f"RELEASE {mode} repo={repo} remote={job.remote} branch={job.branch}")
    try:
        job.fetch()
        job.check_worktree()
        state = job.state()
        version = job.check_version()
        job.selftest()
        job.scan()
        if state == "diverged" and not a.execute:
            job.planned.insert(0, f"git switch -c release/{version} {job.upstream}; git merge --no-ff <current branch>")
            job.planned.append(f"git push {job.remote} HEAD:refs/heads/{job.branch}  (the merge, fast-forward)")
            job.planned.append(f"git tag -a {job.tag} on the merge; git push {job.remote} refs/tags/{job.tag}")
            job.planned.append(f"gh release create {job.tag} --verify-tag --latest")
        else:
            job.push()
            job.tag_step(version)
            job.release_step(version)
    except Stop as stop:
        print(f"STEP FAIL: {stop}\nNEXT: {stop.next_step}\nRELEASE: FAIL")
        return 1
    except RuntimeError as error:
        print(f"STEP FAIL: {error}\nNEXT: read the git message above and run again\nRELEASE: FAIL")
        return 1
    if not a.execute:
        for line in job.planned:
            print(f"PLAN {line}")
        print(f"RELEASE: DRY_RUN {len(job.planned)} remote step(s) planned; run with --execute to do them")
        return 0
    print(f"RELEASE: DONE v{version} at {job.head()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
