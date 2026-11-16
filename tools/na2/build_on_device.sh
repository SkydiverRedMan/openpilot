#!/usr/bin/env bash
# Build a complete prebuilt na2 release ON THE COMMA, from the na2-src source branch.
#
# This is the same process FrogPilot uses for its own releases
# (.github/workflows/compile_frogpilot.yaml): full scons build of one source commit,
# then release/prepare_release.py. Nothing is installed or pushed here; the result
# is a local git commit that tools/na2/publish_from_pc.sh fetches and pushes.
#
# Run from the PC (car parked, comma on Wi-Fi):
#   ssh comma@<comma-ip> "cat > /data/na2_build.sh" < tools/na2/build_on_device.sh
#   ssh comma@<comma-ip> "setsid nohup bash /data/na2_build.sh > /data/na2_build.log 2>&1 < /dev/null &"
#   ssh comma@<comma-ip> "tail -f /data/na2_build.log"     # watch; safe to disconnect
#
# openpilot is stopped while compiling and restarted afterwards, even on failure.
set -euo pipefail

REPO="${REPO:-https://github.com/SkydiverRedMan/openpilot.git}"
SOURCE_BRANCH="${SOURCE_BRANCH:-na2-src}"
RELEASE_BRANCH="${RELEASE_BRANCH:-na2}"
WORK="${WORK:-/data/na2_build}"
UPSTREAM_SOURCE_BASE="${UPSTREAM_SOURCE_BASE:-8d70565038dfa6f355f7140f61520b04cec138be}"  # FrogPilot October 31st, 2026 source

log() { echo "[na2-build] $*"; }

if [ "$(cat /data/params/d/IsOnroad 2>/dev/null || echo 0)" = "1" ]; then
  log "Car is onroad. Park and turn the car off before building."
  exit 1
fi

set +u
source /etc/profile
set -u

log "Preparing $WORK"
rm -rf "$WORK"
mkdir -p "$WORK"

log "Cloning $SOURCE_BRANCH"
git clone --filter=blob:none --no-tags --branch "$SOURCE_BRANCH" "$REPO" "$WORK/build"
SOURCE_SHA="$(git -C "$WORK/build" rev-parse HEAD)"
git -C "$WORK/build" fetch --filter=blob:none --no-tags origin "+refs/heads/$RELEASE_BRANCH:refs/remotes/origin/$RELEASE_BRANCH"
BASE_SHA="$(git -C "$WORK/build" rev-parse "refs/remotes/origin/$RELEASE_BRANCH")"
log "Source $SOURCE_SHA, current $RELEASE_BRANCH $BASE_SHA"

log "Stopping openpilot for the build"
sudo systemctl stop comma
trap 'log "Starting openpilot"; sudo systemctl start comma' EXIT

export WORK
export BUILD='source /etc/profile
cd /data/openpilot
export PYTHONPATH=/data/openpilot
scons -j"$(nproc)" --minimal --ccflags=-g0 --cache-disable'

log "Compiling (15-40 minutes)"
sudo -E unshare --mount \
  sh -c 'mount --bind "$WORK/build" /data/openpilot && exec setpriv --reuid="$SUDO_UID" --regid="$SUDO_GID" --init-groups bash -e -c "$BUILD"'

log "Preparing release tree"
mkdir "$WORK/release"
mv "$WORK/build/.git" "$WORK/release/.git"
export PREPARE='source /etc/profile
python3 "$WORK/build/release/prepare_release.py" "$WORK/build" "$WORK/release"'
sudo -E unshare --mount \
  sh -c 'mount --bind "$WORK/release" /data/openpilot && exec setpriv --reuid="$SUDO_UID" --regid="$SUDO_GID" --init-groups bash -e -c "$PREPARE"'

cd "$WORK/release"

# Panda firmware: when the panda source is unchanged from FrogPilot's source, keep the exact
# firmware already on na2 so the update does not reflash the panda.
if git cat-file -e "$UPSTREAM_SOURCE_BASE^{commit}" 2>/dev/null && git diff --quiet "$UPSTREAM_SOURCE_BASE" "$SOURCE_SHA" -- panda; then
  log "Panda source unchanged; keeping na2's panda firmware"
  git checkout "$BASE_SHA" -- panda/board/obj
else
  log "Panda source changed (or base unknown); using freshly built panda firmware"
fi

git add --all --force
TREE="$(git write-tree)"
MESSAGE="Compile na2 from $SOURCE_BRANCH $(git rev-parse --short "$SOURCE_SHA")

Prebuilt by tools/na2/build_on_device.sh on $(hostname) at $(date -u +%Y-%m-%dT%H:%M:%SZ).
Parents: previous $RELEASE_BRANCH release, and the $SOURCE_BRANCH source commit it was built from."
RELEASE_SHA="$(git -c user.name="${GIT_NAME:-SkydiverRedMan}" -c user.email="${GIT_EMAIL:-SkydiverRedMan@users.noreply.github.com}" \
  commit-tree "$TREE" -p "$BASE_SHA" -p "$SOURCE_SHA" -m "$MESSAGE")"
git update-ref refs/heads/release "$RELEASE_SHA"

log "Checks"
test -f prebuilt
test -x selfdrive/ui/ui
test -f common/params_pyx.so
grep -q "NavigationAssist" common/params_pyx.so
grep -q "navigationAssist" selfdrive/ui/ui
git diff --quiet "$BASE_SHA" "$RELEASE_SHA" -- panda/board/obj || log "NOTE: panda firmware differs from current $RELEASE_BRANCH"

echo "$RELEASE_SHA" > "$WORK/RELEASE_SHA"

# The clone is partial (blob:none), which cannot serve a git fetch reliably, so hand the
# release to the PC as a bundle holding only what is new relative to both parents.
git bundle create "$WORK/release.bundle" release "^$BASE_SHA" "^$SOURCE_SHA"
log "Done. Release commit $RELEASE_SHA is in $WORK/release (branch 'release')."
log "On the PC run: tools/na2/publish_from_pc.sh <comma-ip>"
