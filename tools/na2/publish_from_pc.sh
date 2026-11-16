#!/usr/bin/env bash
# Fetch the release that tools/na2/build_on_device.sh built on the comma, check it,
# and push it to the na2 branch as a normal fast-forward (never a force push).
#
# Usage (Git Bash, from the repo root):
#   tools/na2/publish_from_pc.sh <comma-ip>            # check and push
#   tools/na2/publish_from_pc.sh <comma-ip> --dry-run  # check only
#
# After it succeeds: comma -> Settings -> Software -> Update.
set -euo pipefail

IP="${1:?usage: publish_from_pc.sh <comma-ip> [--dry-run]}"
DRY_RUN="${2:-}"
REMOTE="${REMOTE:-origin}"
RELEASE_BRANCH="${RELEASE_BRANCH:-na2}"
WORK="${WORK:-/data/na2_build}"

log() { echo "[na2-publish] $*"; }

log "Fetching current $REMOTE/$RELEASE_BRANCH"
git fetch "$REMOTE" "+refs/heads/$RELEASE_BRANCH:refs/remotes/$REMOTE/$RELEASE_BRANCH"
CURRENT="$(git rev-parse "refs/remotes/$REMOTE/$RELEASE_BRANCH")"

log "Fetching the release built on the comma ($IP)"
git fetch "ssh://comma@$IP$WORK/release" "+refs/heads/release:refs/remotes/device/release"
RELEASE="$(git rev-parse refs/remotes/device/release)"

log "Checking $RELEASE"
git merge-base --is-ancestor "$CURRENT" "$RELEASE" || { log "Release is not built on top of the current $RELEASE_BRANCH ($CURRENT). Rebuild on the comma."; exit 1; }
for f in prebuilt selfdrive/ui/ui common/params_pyx.so frogpilot/navigation_assist/navigation_assistd.py launch_openpilot.sh; do
  git cat-file -e "$RELEASE:$f" || { log "missing $f"; exit 1; }
done
git cat-file -p "$RELEASE:selfdrive/ui/ui" | head -c 20 | od -An -tx1 | grep -q "7f 45 4c 46 02 01 01 00" || { log "selfdrive/ui/ui is not a 64-bit ELF"; exit 1; }
git cat-file -p "$RELEASE:selfdrive/ui/ui" | head -c 20 | od -An -tx1 | tr -d ' \n' | grep -q "b700$" || { log "selfdrive/ui/ui is not aarch64"; exit 1; }
if git ls-tree -r --name-only "$RELEASE" | grep -q "^frogpilot/navigation_assist/tests/"; then log "tests leaked into release"; exit 1; fi

log "Files changed versus current $RELEASE_BRANCH:"
git diff --stat "$CURRENT" "$RELEASE" | tail -15

if [ "$DRY_RUN" = "--dry-run" ]; then
  log "Dry run: not pushing."
  exit 0
fi

log "Pushing $RELEASE to $REMOTE/$RELEASE_BRANCH (fast-forward only)"
git push "$REMOTE" "$RELEASE:refs/heads/$RELEASE_BRANCH"

PUSHED="$(git ls-remote "$REMOTE" "refs/heads/$RELEASE_BRANCH" | cut -f1)"
[ "$PUSHED" = "$RELEASE" ] || { log "GitHub reports $PUSHED, expected $RELEASE"; exit 1; }
log "Published. On the comma: Settings -> Software -> Update (car parked)."
log "Roll back: reinstall from installer.comma.ai/SkydiverRedMan/na2bk"
