#!/usr/bin/env bash
# Roll na2 back to an earlier release WITHOUT rewriting history, so the comma's
# normal Settings -> Software -> Update installs it.
#
# It makes a new commit on top of the current na2 whose files are exactly those of
# the target release (default: the na2bk backup taken before Navigation Assist).
#
# Usage (Git Bash, repo root):
#   tools/na2/rollback.sh                 # back to na2bk
#   tools/na2/rollback.sh <commit-or-ref> # back to any earlier na2 release
#   tools/na2/rollback.sh <ref> --dry-run
set -euo pipefail

TARGET="${1:-refs/remotes/origin/na2bk}"
DRY_RUN="${2:-}"
REMOTE="${REMOTE:-origin}"
RELEASE_BRANCH="${RELEASE_BRANCH:-na2}"

git fetch "$REMOTE" "+refs/heads/$RELEASE_BRANCH:refs/remotes/$REMOTE/$RELEASE_BRANCH" "+refs/heads/na2bk:refs/remotes/$REMOTE/na2bk"
CURRENT="$(git rev-parse "refs/remotes/$REMOTE/$RELEASE_BRANCH")"
TARGET_SHA="$(git rev-parse "$TARGET^{commit}")"
git cat-file -e "$TARGET_SHA:prebuilt" || { echo "$TARGET is not a prebuilt release"; exit 1; }

COMMIT="$(git commit-tree "$TARGET_SHA^{tree}" -p "$CURRENT" -m "Roll back $RELEASE_BRANCH to $(git rev-parse --short "$TARGET_SHA")

Files are identical to $TARGET_SHA. History is kept; this is a normal fast-forward.")"
echo "Rollback commit $COMMIT (files of $TARGET_SHA on top of $CURRENT)"
git diff --stat "$CURRENT" "$COMMIT" | tail -5

if [ "$DRY_RUN" = "--dry-run" ]; then
  echo "Dry run: not pushing."
  exit 0
fi

git push "$REMOTE" "$COMMIT:refs/heads/$RELEASE_BRANCH"
echo "Pushed. On the comma: Settings -> Software -> Update."
