#!/bin/bash
# K1 (1.2.0): give each container worker its own clone, and take back only
# its one branch. Run inside WSL, where docker is (create and import need git
# only, so they also run in Git Bash).
#
#   worker_clone.sh create  --repo REPO --base REF --branch B --dir DIR
#   worker_clone.sh collect --repo REPO --branch B --dir DIR --name NAME [--image IMG]
#   worker_clone.sh import  --repo REPO --branch B --bundle FILE --name NAME
#
# create: a full copy of REPO at REF in DIR (--no-local: no hardlinks, no
#   alternates), with no remote, only branch B, a fixed .git/config and an
#   empty .git/hooks. Nothing in DIR points back at REPO. --dir has no
#   default; a WSL ext4 folder (~/...) is faster than /mnt/<drive>.
#   Give DIR to run_worker.sh --clone. Never run git in DIR on the host:
#   the worker could have left config, hooks or attributes there for it.
# collect: an offline container with no capabilities, the clone read-only,
#   packs refs/heads/B of DIR into a bundle (the worker's own git files only
#   ever run in that throwaway container), then import.
# import: the bundle is plain data from here on. It must hold exactly one
#   ref, refs/heads/B; git bundle verify must pass in REPO; its objects go to
#   a quarantine repo first and must pass index-pack --strict and fsck
#   --strict there; the tip must be a commit. Only then are the objects copied
#   into REPO and refs/dw-workers/NAME/B set. No other ref of REPO changes, and the
#   worker cannot push: the Director collects.
# Exit 0 with "COLLECTED <ref> <sha>", 2 with a reason on stderr.
set -euo pipefail

IMAGE="dw-worker:1.2.0"
die() { echo "worker_clone: $*" >&2; exit 2; }

[ $# -gt 0 ] || die "usage: worker_clone.sh create|collect|import ..."
CMD="$1"; shift
REPO="" BASE="" BRANCH="" DIR="" NAME="" BUNDLE="" QDIR="" OUT=""
trap 'rm -rf ${QDIR:+"$QDIR"} ${OUT:+"$OUT"}' EXIT
while [ $# -gt 0 ]; do
  [ $# -ge 2 ] || die "$1 needs a value"
  case "$1" in
    --repo) REPO="$2" ;;
    --base) BASE="$2" ;;
    --branch) BRANCH="$2" ;;
    --dir) DIR="$2" ;;
    --name) NAME="$2" ;;
    --bundle) BUNDLE="$2" ;;
    --image) IMAGE="$2" ;;
    *) die "unknown argument: $1" ;;
  esac
  shift 2
done

[ -n "$REPO" ] && git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1 || die "--repo must be a git repository"
[ -n "$BRANCH" ] && git -C "$REPO" check-ref-format --branch "$BRANCH" >/dev/null 2>&1 || die "--branch must be a valid branch name"

name_ok() { [ -n "$NAME" ] && [[ "$NAME" =~ ^[A-Za-z0-9._-]+$ ]] && [[ "$NAME" != .* ]] || die "--name: letters, digits, . _ - only, not starting with ."; }

import_bundle() {  # $1: the bundle file
  local b="$1" heads want dest old q objects pack
  [ -f "$b" ] || die "no bundle file: $b"
  b="$(cd "$(dirname "$b")" && pwd)/$(basename "$b")"
  heads="$(git -C "$REPO" bundle list-heads "$b" 2>/dev/null)" || die "not a bundle: $b"
  [ "$(printf '%s
' "$heads" | grep -c .)" = 1 ] || die "bundle must hold exactly one ref, got: $(printf '%s' "$heads" | tr '
' ' ')"
  set -- $heads
  [ "${2:-}" = "refs/heads/$BRANCH" ] || die "bundle ref is ${2:-none}, expected refs/heads/$BRANCH"
  want="$1"
  git -C "$REPO" bundle verify --quiet "$b" >/dev/null 2>&1 || die "git bundle verify failed (broken, or needs commits REPO lacks)"
  # Quarantine: a throwaway bare repo that borrows REPO's objects (for the
  # bundle's prerequisites) takes the new objects first. git before 2.47 does
  # not fsck objects fetched from a bundle, so index-pack --strict and fsck
  # check them here. REPO gets nothing until they pass.
  QDIR="$(mktemp -d)"
  q="$QDIR"
  git init --quiet --bare "$q/q.git"
  objects="$(git -C "$REPO" rev-parse --path-format=absolute --git-common-dir)/objects"
  printf '%s
' "$objects" > "$q/q.git/objects/info/alternates"
  git -C "$q/q.git" fetch --quiet --no-tags --no-write-fetch-head "$b" "refs/heads/$BRANCH:refs/incoming" 2>/dev/null     || die "fetch from the bundle failed"
  for pack in "$q/q.git/objects/pack/"*.pack; do
    [ -f "$pack" ] || continue
    git -C "$q/q.git" index-pack --strict -o "$q/check.idx" "$pack" >/dev/null 2>&1       || die "bundle objects fail git's strict checks (malformed or corrupt)"
    rm -f "$q/check.idx"
  done
  git -C "$q/q.git" fsck --strict --no-full --no-dangling --no-progress >/dev/null 2>&1     || die "bundle objects fail git fsck --strict (malformed, corrupt or missing)"
  [ "$(git -C "$q/q.git" cat-file -t "$want" 2>/dev/null)" = commit ] || die "bundle tip $want is not a commit"
  # Checked: copy the new objects into REPO (no ref yet), then set the one ref.
  git -C "$REPO" -c transfer.fsckObjects=true fetch --quiet --no-tags --no-write-fetch-head "$q/q.git" refs/incoming 2>/dev/null     || die "copying the checked objects into REPO failed"
  dest="refs/dw-workers/$NAME/$BRANCH"
  old="$(git -C "$REPO" rev-parse --verify --quiet "$dest" || true)"
  git -C "$REPO" update-ref -m "worker_clone import $NAME" "$dest" "$want"
  echo "COLLECTED $dest $want${old:+ (was $old)}"
}

case "$CMD" in
create)
  [ -n "$DIR" ] || die "--dir is required (no default; a WSL ext4 folder is faster)"
  [ -n "$BASE" ] || die "create needs --base"
  [ ! -e "$DIR" ] || die "--dir must not exist yet: $DIR"
  SHA="$(git -C "$REPO" rev-parse --verify --quiet "$BASE^{commit}")" || die "--base is not a commit in --repo: $BASE"
  git clone --quiet --no-local --no-checkout -- "$REPO" "$DIR"
  git -C "$DIR" checkout --quiet -b "$BRANCH" "$SHA"
  FILEMODE="$(git -C "$DIR" config --bool core.filemode || echo false)"
  # Only branch B stays; no remote, no other branch, no tag.
  git -C "$DIR" for-each-ref --format='%(refname)' | while read -r ref; do
    [ "$ref" = "refs/heads/$BRANCH" ] || git -C "$DIR" update-ref -d "$ref"
  done
  cat > "$DIR/.git/config" <<EOF
[core]
	repositoryformatversion = 0
	filemode = $FILEMODE
	bare = false
	logallrefupdates = true
[user]
	name = dw-worker
	email = dw-worker@localhost
EOF
  rm -rf "$DIR/.git/hooks" && mkdir "$DIR/.git/hooks"
  rm -f "$DIR/.git/FETCH_HEAD" "$DIR/.git/ORIG_HEAD"
  git -C "$DIR" reflog expire --expire=now --all
  [ -z "$(git -C "$DIR" remote)" ] || die "internal: remote left in $DIR"
  echo "CREATED dir=$DIR branch=$BRANCH base=$SHA"
  ;;
collect)
  name_ok
  [ -n "$DIR" ] || die "--dir is required"
  [ -d "$DIR/.git" ] || die "--dir has no .git: $DIR"
  OUT="$(mktemp -d)"
  chmod 777 "$OUT"
  # Inside the container: no network, no capabilities, the clone read-only.
  docker run --rm --network none --read-only --tmpfs /tmp \
    --cap-drop ALL --security-opt no-new-privileges --user 1000:1000 \
    -e HOME=/tmp -e GIT_CONFIG_NOSYSTEM=1 \
    -v "$DIR:/work:ro" -v "$OUT:/out" --entrypoint git "$IMAGE" \
    -c safe.directory=/work -C /work bundle create --quiet "/out/$NAME.bundle" "refs/heads/$BRANCH" \
    || die "bundle failed (does branch $BRANCH exist in the clone?)"
  import_bundle "$OUT/$NAME.bundle"
  ;;
import)
  name_ok
  [ -n "$BUNDLE" ] || die "import needs --bundle"
  import_bundle "$BUNDLE"
  ;;
*) die "unknown command: $CMD (create, collect or import)" ;;
esac
