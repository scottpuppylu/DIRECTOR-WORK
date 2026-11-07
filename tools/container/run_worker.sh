#!/bin/bash
# Start one DW worker in a container (1.1.0). Run inside WSL, where docker is.
#
#   run_worker.sh --worktree /mnt/d/.../wt --director /mnt/d/.../DIRECTOR \
#                 --git-common /mnt/d/.../repo/.git [--worktree-name NAME] \
#                 [--offline | --login | --allow HOST ...] [--image IMG] \
#                 [--dry-run] [-- COMMAND ...]
#
# What the container gets:
#   /work       the worker's worktree, the only project folder it can write
#   /director   DIRECTOR, read-only
#   .git        main checkout (no --worktree-name): /work/.git itself.
#               linked worktree: the repository's .git at /repo-git, and a
#               read-only /work/.git file that points at
#               /repo-git/worktrees/NAME (the host's own .git file names a
#               Windows path, which Linux git cannot follow).
#               Writable (see K1 in tools/README.md), except hooks/ and
#               config, which are read-only: they run on the host later;
#               and worktrees/, read-only except the worker's own record.
#   /home/dw/.claude  docker volume dw-claude-home: Claude's own login only
#   environment: only the variables listed below; nothing from the host.
#               No GIT_DIR: it would send every git in the container, also
#               ones run in other folders, to this repository.
#   network: TCP 443 to api.anthropic.com only (--login adds the sign-in
#            hosts, --allow adds others, --offline means no network at all)
# Not mounted: the host home, ~/.ssh, ~/.config/gh, AppData, any token.
#
# --dry-run prints the docker command and runs nothing.
set -euo pipefail

IMAGE="dw-worker:1.1.0"
WORKTREE="" DIRECTOR="" GITCOMMON="" WTNAME=""
OFFLINE=0 DRY=0
ALLOW=("api.anthropic.com")
LOGIN_HOSTS=("claude.ai" "platform.claude.com" "console.anthropic.com")

die() { echo "run_worker: $*" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --worktree) WORKTREE="${2:?}"; shift 2 ;;
    --director) DIRECTOR="${2:?}"; shift 2 ;;
    --git-common) GITCOMMON="${2:?}"; shift 2 ;;
    --worktree-name) WTNAME="${2:?}"; shift 2 ;;
    --image) IMAGE="${2:?}"; shift 2 ;;
    --allow) ALLOW+=("${2:?}"); shift 2 ;;
    --login) ALLOW+=("${LOGIN_HOSTS[@]}"); shift ;;
    --offline) OFFLINE=1; shift ;;
    --dry-run) DRY=1; shift ;;
    --) shift; break ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -n "$WORKTREE" ] && [ -d "$WORKTREE" ] || die "--worktree must be an existing folder"
[ -n "$DIRECTOR" ] && [ -d "$DIRECTOR" ] || die "--director must be an existing folder"
[ -n "$GITCOMMON" ] && [ -d "$GITCOMMON" ] || die "--git-common must be the repository's .git folder"
# hooks/ and config run on the host later (git hooks, core.hooksPath, aliases), so the container gets them read-only.
[ -d "$GITCOMMON/hooks" ] && [ -f "$GITCOMMON/config" ] || die "--git-common needs hooks/ and config (mkdir hooks if it is missing)"

# .git/worktrees/ holds the other worktrees' records. Their gitdir files name
# Windows paths, which look missing here, so "git worktree prune" in the
# container would delete them: the container gets worktrees/ read-only.
GITMOUNTS=()
if [ -n "$WTNAME" ]; then
  [ -d "$GITCOMMON/worktrees/$WTNAME" ] || die "no worktree named $WTNAME under --git-common"
  [ -f "$WORKTREE/.git" ] || die "--worktree-name needs a linked worktree (its .git is a file)"
  GEN="$(mktemp -d)"
  printf 'gitdir: /repo-git/worktrees/%s\n' "$WTNAME" > "$GEN/dotgit"
  printf '/work/.git\n' > "$GEN/gitdir"
  # Its own record stays writable (index, HEAD, logs); its gitdir file points at /work/.git, so prune keeps it.
  GITMOUNTS=(-v "$GITCOMMON:/repo-git"
    -v "$GITCOMMON/hooks:/repo-git/hooks:ro"
    -v "$GITCOMMON/config:/repo-git/config:ro"
    -v "$GITCOMMON/worktrees:/repo-git/worktrees:ro"
    -v "$GITCOMMON/worktrees/$WTNAME:/repo-git/worktrees/$WTNAME"
    -v "$GEN/gitdir:/repo-git/worktrees/$WTNAME/gitdir:ro"
    -v "$GEN/dotgit:/work/.git:ro")
else
  [ "$GITCOMMON" -ef "$WORKTREE/.git" ] || die "without --worktree-name, --git-common must be <worktree>/.git"
  GITMOUNTS=(-v "$GITCOMMON/hooks:/work/.git/hooks:ro"
    -v "$GITCOMMON/config:/work/.git/config:ro")
  if [ -d "$GITCOMMON/worktrees" ]; then
    GITMOUNTS+=(-v "$GITCOMMON/worktrees:/work/.git/worktrees:ro")
  fi
fi

ARGS=(docker run --rm --init
  --cap-drop ALL --cap-add NET_ADMIN --cap-add NET_RAW --cap-add SETUID --cap-add SETGID --cap-add SETPCAP
  --security-opt no-new-privileges
  --read-only --tmpfs /tmp --tmpfs /run
  --pids-limit 512 --memory 4g --cpus 4
  -v "$WORKTREE:/work"
  -v "$DIRECTOR:/director:ro"
  "${GITMOUNTS[@]}"
  -v "dw-claude-home:/home/dw/.claude"
  -e CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1
  -e CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
  -e XDG_CACHE_HOME=/tmp/cache
  # The other worktrees' paths are Windows paths, missing here: never let git prune them.
  -e GIT_CONFIG_COUNT=2
  -e GIT_CONFIG_KEY_0=gc.auto -e GIT_CONFIG_VALUE_0=0
  -e GIT_CONFIG_KEY_1=gc.worktreePruneExpire -e GIT_CONFIG_VALUE_1=never
)
if [ "$OFFLINE" = 1 ]; then
  ARGS+=(--network none)
else
  ARGS+=(-e "DW_ALLOW_DOMAINS=${ALLOW[*]}")
fi
if [ -t 0 ] && [ -t 1 ]; then ARGS+=(-it); else ARGS+=(-i); fi
ARGS+=("$IMAGE")
[ $# -gt 0 ] && ARGS+=("$@")

if [ "$DRY" = 1 ]; then
  printf '%q ' "${ARGS[@]}"
  echo
  exit 0
fi
exec "${ARGS[@]}"
