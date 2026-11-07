#!/bin/bash
# Start one DW worker in a container. Run inside WSL, where docker is.
#
#   run_worker.sh --clone DIR --name NAME --director /mnt/d/.../DIRECTOR \
#                 [--offline | --login | --allow HOST ...] [--image IMG] \
#                 [--dry-run] [-- COMMAND ...]
#   run_worker.sh --worktree /mnt/d/.../wt --git-common /mnt/d/.../repo/.git \
#                 [--worktree-name WT] [--name NAME] --director ... [same options]
#
# --clone (1.2.0, K1): DIR is the worker's own clone, made by
#   worker_clone.sh create. The original repository is not mounted at all, so
#   the worker cannot change its refs, tags or objects; the Director takes
#   back only the worker's branch with worker_clone.sh collect. NAME goes to
#   DW_WORKER_NAME (the action log file name).
# --worktree/--git-common (1.1.0, legacy mode, still supported in 2.2.0): the
#   repository's shared .git is mounted and writable, so the worker can change
#   other branches and tags (K1). It prints a WARN, doctor reports it
#   NOT_ENFORCED. It is not scheduled for removal in a minor version; it can
#   only go in a major release (3.0 at the earliest). Move to --clone: see the
#   WARN text for the two commands.
#   DW_WORKER_NAME is --name, else --worktree-name, else the folder name.
#
# What the container gets:
#   /work       the clone or the worktree, the only project folder it can write
#   /director   DIRECTOR, read-only. 2.2.0 (F11): DIRECTOR must not be the same
#               folder as, inside, or an ancestor of a writable mount (--clone,
#               --worktree, --git-common), by real path or by inode (symlink,
#               Windows/WSL alias); otherwise the writable mount would show it
#               under /work and the read-only promise would be void: exit 2.
#   .git        --clone: /work/.git, with config and hooks/ read-only.
#               main checkout (no --worktree-name): /work/.git itself.
#               linked worktree: the repository's .git at /repo-git, and a
#               read-only /work/.git file that points at
#               /repo-git/worktrees/NAME (the host's own .git file names a
#               Windows path, which Linux git cannot follow).
#               Writable (see K1 in tools/README.md), except hooks/ and
#               config, which are read-only: they run on the host later;
#               and worktrees/, read-only except the worker's own record.
#   /home/dw/.claude  docker volume dw-claude-home: Claude's own login only,
#               but ONE volume shared by every worker started on this host
#               (F18): not isolated per worker or per account. For another
#               trust scope set DW_CLAUDE_HOME_VOLUME to a different name.
#   environment: only the variables listed below; nothing from the host.
#               No GIT_DIR: it would send every git in the container, also
#               ones run in other folders, to this repository.
#   network: names come from --allow-file (default dns_allow.txt next to this
#            script: api.anthropic.com), plus --allow HOST and, with --login,
#            the sign-in hosts. Only those names resolve (dns_allow.py in the
#            container, no off switch) and only the resolved IPv4 address:443
#            gets TCP (F18): it filters destination IP:port, not the TLS name
#            or HTTP host, so any other site on the same IP is reachable.
#            IPv6: init_firewall.sh sets ip6tables DROP when it can and ignores
#            a failure there, so 2.2.0 also starts the container with
#            --sysctl net.ipv6.conf.all.disable_ipv6=1 (the image is unchanged,
#            still dw-worker:1.2.0). If docker refuses the sysctl the container
#            does not start (fail closed); doctor --probe is the check.
#            --offline means no network at all.
#   DNS upstream: DW_DNS_UPSTREAM (space-separated IPv4) if set, else the
#            IPv4 nameservers in /etc/resolv.conf except 127.x.
# Not mounted: the host home, ~/.ssh, ~/.config/gh, AppData, any token.
#
# --dry-run prints the docker command and runs nothing.
set -euo pipefail

IMAGE="dw-worker:1.2.0"
WORKTREE="" DIRECTOR="" GITCOMMON="" WTNAME="" CLONE="" NAME=""
OFFLINE=0 DRY=0
ALLOW_FILE="$(dirname "$0")/dns_allow.txt"
ALLOW=()
LOGIN_HOSTS=("claude.ai" "platform.claude.com" "console.anthropic.com")

die() { echo "run_worker: $*" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --worktree) WORKTREE="${2:?}"; shift 2 ;;
    --director) DIRECTOR="${2:?}"; shift 2 ;;
    --git-common) GITCOMMON="${2:?}"; shift 2 ;;
    --worktree-name) WTNAME="${2:?}"; shift 2 ;;
    --clone) CLONE="${2:?}"; shift 2 ;;
    --name) NAME="${2:?}"; shift 2 ;;
    --image) IMAGE="${2:?}"; shift 2 ;;
    --allow) ALLOW+=("${2:?}"); shift 2 ;;
    --allow-file) ALLOW_FILE="${2:?}"; shift 2 ;;
    --login) ALLOW+=("${LOGIN_HOSTS[@]}"); shift ;;
    --offline) OFFLINE=1; shift ;;
    --dry-run) DRY=1; shift ;;
    --) shift; break ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -n "$DIRECTOR" ] && [ -d "$DIRECTOR" ] || die "--director must be an existing folder"
[ -z "$NAME" ] || { [[ "$NAME" =~ ^[A-Za-z0-9._-]+$ ]] && [[ "$NAME" != .* ]]; } || die "--name: letters, digits, . _ - only, not starting with ."

GITMOUNTS=() GITENV=() GITMODE=shared
if [ -n "$CLONE" ]; then
  GITMODE=clone
  [ -z "$WORKTREE$GITCOMMON$WTNAME" ] || die "--clone goes without --worktree, --git-common and --worktree-name"
  [ -n "$NAME" ] || die "--clone needs --name"
  [ -d "$CLONE/.git" ] && [ -f "$CLONE/.git/config" ] && [ -d "$CLONE/.git/hooks" ] \
    || die "--clone must be a folder made by worker_clone.sh create (.git/config and .git/hooks)"
  [ -z "$(ls -A "$CLONE/.git/hooks")" ] || die "--clone: .git/hooks must be empty"
  WORKTREE="$CLONE"
  GITMOUNTS=(-v "$CLONE/.git/config:/work/.git/config:ro" -v "$CLONE/.git/hooks:/work/.git/hooks:ro")
else
  echo "run_worker: WARN K1: --git-common is a legacy mode (still supported; removal only in a major release, 3.0 at the earliest) and mounts the shared .git writable. Move to --clone: worker_clone.sh create --repo REPO --base COMMIT --branch BRANCH --dir DIR, then run_worker.sh --clone DIR --name NAME ..." >&2
  [ -n "$WORKTREE" ] && [ -d "$WORKTREE" ] || die "--worktree must be an existing folder"
  [ -n "$GITCOMMON" ] && [ -d "$GITCOMMON" ] || die "--git-common must be the repository's .git folder"
  # hooks/ and config run on the host later (git hooks, core.hooksPath, aliases), so the container gets them read-only.
  [ -d "$GITCOMMON/hooks" ] && [ -f "$GITCOMMON/config" ] || die "--git-common needs hooks/ and config (mkdir hooks if it is missing)"

  # .git/worktrees/ holds the other worktrees' records. Their gitdir files name
  # Windows paths, which look missing here, so "git worktree prune" in the
  # container would delete them: the container gets worktrees/ read-only.
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
  # The other worktrees' paths are Windows paths, missing here: never let git prune them.
  GITENV=(-e GIT_CONFIG_COUNT=2 -e GIT_CONFIG_KEY_0=gc.auto -e GIT_CONFIG_VALUE_0=0
    -e GIT_CONFIG_KEY_1=gc.worktreePruneExpire -e GIT_CONFIG_VALUE_1=never)
  [ -n "$NAME" ] || NAME="${WTNAME:-$(basename "$WORKTREE")}"
fi

# F11 (2.2.0): the read-only DIRECTOR must not be reachable through a writable mount.
# resolve() gives the real path; inside A B is true when A is B or below B, by path text or,
# walking A's parents, by inode (-ef: symlinks, Windows/WSL aliases such as /mnt/D vs /mnt/d).
resolve() { ( cd "$1" 2>/dev/null && pwd -P ) || die "cannot resolve $1"; }
inside() {
  local p="$1" q="$2"
  [ "$q" = / ] && return 0
  [[ "$p/" == "$q/"* ]] && return 0
  if [[ "$p" == /mnt/* && "$q" == /mnt/* ]]; then [[ "${p,,}/" == "${q,,}/"* ]] && return 0; fi
  while :; do
    [ "$p" -ef "$q" ] && return 0
    { [ "$p" = / ] || [ "$p" = . ]; } && break
    p="$(dirname "$p")"
  done
  return 1
}
REAL_DIRECTOR="$(resolve "$DIRECTOR")"
for pair in "--clone/--worktree:$WORKTREE" "--git-common:$GITCOMMON"; do
  label="${pair%%:*}" path="${pair#*:}"
  [ -n "$path" ] && [ -d "$path" ] || continue
  real="$(resolve "$path")"
  if inside "$real" "$REAL_DIRECTOR" || inside "$REAL_DIRECTOR" "$real"; then
    die "--director ($REAL_DIRECTOR) overlaps the writable mount $label ($real): equal, inside or around it, so the worker could write to DIRECTOR through /work. Move DIRECTOR to its own folder outside the worker's folder (back it up first), then pass the new path."
  fi
done
CLAUDE_VOLUME="${DW_CLAUDE_HOME_VOLUME:-dw-claude-home}"
[[ "$CLAUDE_VOLUME" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || die "DW_CLAUDE_HOME_VOLUME: a docker volume name (letters, digits, _ . -)"

ARGS=(docker run --rm --init
  --cap-drop ALL --cap-add NET_ADMIN --cap-add NET_RAW --cap-add SETUID --cap-add SETGID --cap-add SETPCAP
  --security-opt no-new-privileges
  --read-only --tmpfs /tmp --tmpfs /run
  --pids-limit 512 --memory 4g --cpus 4
  -v "$WORKTREE:/work"
  -v "$DIRECTOR:/director:ro"
  "${GITMOUNTS[@]}"
  -v "$CLAUDE_VOLUME:/home/dw/.claude"
  -e CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1
  -e CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
  -e XDG_CACHE_HOME=/tmp/cache
  "${GITENV[@]}"
  -e "DW_WORKER_NAME=$NAME"
  -e "DW_GIT_MODE=$GITMODE"   # doctor: clone = the worker's own .git, shared = K1 NOT_ENFORCED
)
if [ "$OFFLINE" = 1 ]; then
  ARGS+=(--network none)
else
  # The allowlist: the file, then --login and --allow, each name once, in that order.
  [ -f "$ALLOW_FILE" ] || die "--allow-file: no such file: $ALLOW_FILE"
  NAMES=()
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"
    read -ra words <<< "${line//$'\r'/ }"   # read -a: "*.x" is not a glob here
    NAMES+=(${words[@]+"${words[@]}"})
  done < "$ALLOW_FILE"
  NAMES+=("${ALLOW[@]}")
  HOST_RE='^(\*\.)?[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$'
  DOMAINS=()
  for word in "${NAMES[@]}"; do
    word="${word%.}"
    [[ "$word" =~ $HOST_RE ]] && [ "${#word}" -le 253 ] || die "not a host name: $word"
    word="${word,,}"
    [[ " ${DOMAINS[*]} " == *" $word "* ]] || DOMAINS+=("$word")
  done
  [ "${#DOMAINS[@]}" -gt 0 ] || die "the allowlist is empty ($ALLOW_FILE); use --offline for no network"
  # Upstream resolvers for dns_allow.py: 127.x (systemd-resolved, WSL) is not reachable from a container.
  UPSTREAM=()
  if [ -n "${DW_DNS_UPSTREAM:-}" ]; then
    read -ra UPSTREAM <<< "$DW_DNS_UPSTREAM"
  else
    while read -r key value _; do
      value="${value%$'\r'}"
      [ "$key" = nameserver ] && [[ "$value" != 127.* ]] && UPSTREAM+=("$value")
    done < <(cat "${DW_RESOLV_CONF:-/etc/resolv.conf}" 2>/dev/null || true)
    KEEP=()
    for ns in "${UPSTREAM[@]}"; do [[ "$ns" == *:* ]] || KEEP+=("$ns"); done
    UPSTREAM=("${KEEP[@]}")
  fi
  [ "${#UPSTREAM[@]}" -gt 0 ] || die "no IPv4 nameserver outside 127.x in /etc/resolv.conf; set DW_DNS_UPSTREAM"
  for ns in "${UPSTREAM[@]}"; do
    [[ "$ns" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || die "DW_DNS_UPSTREAM: not an IPv4 address: $ns"
  done
  ARGS+=(--sysctl net.ipv6.conf.all.disable_ipv6=1 --sysctl net.ipv6.conf.default.disable_ipv6=1)
  ARGS+=(--dns 127.0.0.1 -e "DW_ALLOW_DOMAINS=${DOMAINS[*]}" -e "DW_DNS_UPSTREAM=${UPSTREAM[*]}")
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
