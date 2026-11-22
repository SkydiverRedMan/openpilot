#!/usr/bin/env bash
# Quick na2 release ON THE COMMA for na2-src changes that need no compiling (Python, JavaScript, HTML, CSS, images,
# sounds, JSON). Takes the current na2 release, swaps in only the files that changed in na2-src since the source that
# release was built from, and packs it like build_on_device.sh does. Minutes instead of a 15-40 minute rebuild, and
# openpilot keeps running (no reboot).
#
# Refuses, and tells you to run build_on_device.sh instead, when anything changed that is compiled or generated:
# C/C++/Qt, Cython, cereal schema, params, SConscripts, panda, opendbc, third_party, tinygrad, model files.
#
# First used 2026-11-18 by hand (the paramotor-wheel change on top of release beef7bf -> 33e5b3f); this script is that
# procedure. Then on the PC: tools/na2/publish_from_pc.sh <comma-ip>
set -euo pipefail

REPO="${REPO:-https://github.com/SkydiverRedMan/openpilot.git}"
SOURCE_BRANCH="${SOURCE_BRANCH:-na2-src}"
RELEASE_BRANCH="${RELEASE_BRANCH:-na2}"
WORK="${WORK:-/data/na2_build}"
QUICK="$WORK/quick"

log() { echo "[na2-quick] $*"; }

[ "$(cat /data/params/d/IsOnroad 2>/dev/null)" != "1" ] || { log "Car is onroad. Park first."; exit 1; }

rm -rf "$QUICK"
mkdir -p "$WORK"
log "Fetching $RELEASE_BRANCH and $SOURCE_BRANCH"
git clone -q --filter=blob:none --no-checkout --no-tags --branch "$RELEASE_BRANCH" "$REPO" "$QUICK"
cd "$QUICK"
git fetch -q origin "$SOURCE_BRANCH"

BASE="$(git rev-parse HEAD)"
NEW_SOURCE="$(git rev-parse FETCH_HEAD)"
OLD_SOURCE="$(git rev-parse --verify -q "$BASE^2")" || { log "$RELEASE_BRANCH has no source parent; use build_on_device.sh"; exit 1; }
git merge-base --is-ancestor "$OLD_SOURCE" "$NEW_SOURCE" || { log "$SOURCE_BRANCH doesn't continue from the source of $RELEASE_BRANCH; use build_on_device.sh"; exit 1; }
[ "$OLD_SOURCE" != "$NEW_SOURCE" ] || { log "Nothing new in $SOURCE_BRANCH since $RELEASE_BRANCH was built"; exit 1; }
log "Release $BASE (source $OLD_SOURCE) + $SOURCE_BRANCH $NEW_SOURCE"

COMPILED='\.(c|cc|cpp|h|hpp|pyx|pxd|capnp|qrc|ts|dbc|onnx|pkl|so|a|o)$|(^|/)SCons(cript|truct)$|^(cereal|panda|opendbc|third_party|tinygrad_repo|msgq_repo|rednose_repo|body)/|^common/params|^selfdrive/ui/|^frogpilot/ui/'
CHANGES="$(git diff --name-status --no-renames "$OLD_SOURCE" "$NEW_SOURCE")"
BLOCKED="$(echo "$CHANGES" | cut -f2 | grep -E "$COMPILED" || true)"
if [ -n "$BLOCKED" ]; then
  log "These changes need compiling; run build_on_device.sh instead:"
  echo "$BLOCKED"
  exit 1
fi

# Which changed files belong in a release: the same rule prepare_release.py uses
git show "$NEW_SOURCE:release/prepare_release.py" > "$WORK/quick_prepare_release.py"
SHIPPED="$(echo "$CHANGES" | cut -f2 | python3 -c '
import importlib.util, sys
spec = importlib.util.spec_from_file_location("prepare_release", sys.argv[1])
pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr)
for line in sys.stdin:
  path = line.strip()
  if path and (pr.is_runtime_file(path) or path in pr.KEEP_FILES):
    print(path)
' "$WORK/quick_prepare_release.py")"

# Build the new tree by rewriting only the folders on the changed paths (git mktree). The clone is blobless and the
# comma's git (2.25) has no way to stop lazy fetches, so anything that touches every file (read-tree, write-tree)
# fetches thousands of files one by one and runs out of file handles (found 2026-11-22).
EDITS="$WORK/quick_edits"
: > "$EDITS"
while IFS=$'\t' read -r status path; do
  [ -n "$path" ] || continue
  if ! echo "$SHIPPED" | grep -qxF "$path"; then
    log "  skip (not shipped): $path"
    continue
  fi
  if [ "$status" = "D" ]; then
    printf 'D\t-\t%s\n' "$path" >> "$EDITS"
    log "  remove: $path"
    continue
  fi
  # The release must still hold the file exactly as the old source had it, or the release was changed some other way
  OLD_BLOB="$(git rev-parse -q --verify "$OLD_SOURCE:$path" 2>/dev/null || true)"
  if [ -n "$OLD_BLOB" ] && [ "$(git rev-parse -q --verify "$BASE:$path" 2>/dev/null || true)" != "$OLD_BLOB" ]; then
    log "$path in $RELEASE_BRANCH differs from its source; use build_on_device.sh"
    exit 1
  fi
  MODE="$(git ls-tree "$NEW_SOURCE" -- "$path" | cut -d' ' -f1)"
  [ "$MODE" != "120000" ] || { log "$path is a symlink; use build_on_device.sh"; exit 1; }
  printf '%s\t%s\t%s\n' "$MODE" "$(git rev-parse "$NEW_SOURCE:$path")" "$path" >> "$EDITS"
  log "  update: $path"
done <<< "$CHANGES"

TREE="$(python3 - "$(git rev-parse "$BASE^{tree}")" "$EDITS" <<'PYEOF'
import subprocess, sys

def git(*args, data=None):
  return subprocess.run(["git", *args], input=data, check=True, stdout=subprocess.PIPE, text=True).stdout

def read_tree(sha):
  entries = {}
  if sha:
    for line in git("ls-tree", sha).splitlines():
      meta, name = line.split("\t", 1)
      mode, kind, obj = meta.split(" ")
      entries[name] = (mode, kind, obj)
  return entries

def apply(tree_sha, edits):
  """edits: {relative path: (mode, sha) or None to delete}. Returns the new tree's sha, or None when empty."""
  entries = read_tree(tree_sha)
  sub = {}
  for path, change in edits.items():
    head, _, rest = path.partition("/")
    if rest:
      sub.setdefault(head, {})[rest] = change
    elif change is None:
      entries.pop(head, None)
    else:
      entries[head] = (change[0], "blob", change[1])
  for name, changes in sub.items():
    current = entries.get(name)
    new = apply(current[2] if current and current[1] == "tree" else None, changes)
    if new is None:
      entries.pop(name, None)
    else:
      entries[name] = ("040000", "tree", new)
  if not entries:
    return None
  lines = "".join(f"{mode} {kind} {obj}\t{name}\n" for name, (mode, kind, obj) in entries.items())
  return git("mktree", "--missing", data=lines).strip()

edits = {}
for line in open(sys.argv[2]):
  mode, sha, path = line.rstrip("\n").split("\t", 2)
  edits[path] = None if mode == "D" else (mode, sha)
print(apply(sys.argv[1], edits))
PYEOF
)"

[ "$TREE" != "$(git rev-parse "$BASE^{tree}")" ] || { log "No shipped file changed; nothing to release"; exit 1; }

MESSAGE="Add $SOURCE_BRANCH $(git rev-parse --short "$NEW_SOURCE") to $RELEASE_BRANCH without recompiling

Quick release by tools/na2/quick_release_on_device.sh on $(hostname) at $(date -u +%Y-%m-%dT%H:%M:%SZ): only files that
need no compiling changed; every compiled file is the same as in $(git rev-parse --short "$BASE").
Parents: previous $RELEASE_BRANCH release, and the $SOURCE_BRANCH source commit it now matches."
RELEASE_SHA="$(git -c user.name="${GIT_NAME:-SkydiverRedMan}" -c user.email="${GIT_EMAIL:-110471467+SkydiverRedMan@users.noreply.github.com}" \
  commit-tree "$TREE" -p "$BASE" -p "$NEW_SOURCE" -m "$MESSAGE")"
git update-ref refs/heads/release "$RELEASE_SHA"

log "Files changed versus $RELEASE_BRANCH:"
git diff --stat "$BASE" "$RELEASE_SHA" | tail -15

git bundle create "$WORK/release.bundle" release "^$BASE" "^$NEW_SOURCE" 2>/dev/null
echo "$RELEASE_SHA" > "$WORK/RELEASE_SHA"
log "Done. Release commit $RELEASE_SHA. On the PC run: tools/na2/publish_from_pc.sh <comma-ip>"
