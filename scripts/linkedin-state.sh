#!/usr/bin/env bash
# Read and write the LinkedIn announce ledger on the `linkedin-state` branch.
#
#   scripts/linkedin-state.sh fetch <file>             # empty file when the branch doesn't exist yet
#   scripts/linkedin-state.sh save  <file> <message>   # commit <file> as announced.json and push
#
# The ledger lives on its own orphan branch so the workflow never pushes to
# main (no deploy loop, no clash with branch protection). Needs GITHUB_TOKEN
# and GITHUB_REPOSITORY, which Actions provides.
set -euo pipefail

BRANCH=linkedin-state
FILE=announced.json
cmd=${1:?usage: fetch|save <file> [message]}
target=${2:?missing ledger path}
remote="https://x-access-token:${GITHUB_TOKEN:?}@github.com/${GITHUB_REPOSITORY:?}.git"
work="${RUNNER_TEMP:-/tmp}/linkedin-state-repo"

prepare() {
  rm -rf "$work"
  git init -q "$work"
  git -C "$work" config user.name "github-actions[bot]"
  git -C "$work" config user.email "41898282+github-actions[bot]@users.noreply.github.com"
  git -C "$work" remote add origin "$remote"
  if git -C "$work" fetch -q --depth 1 origin "$BRANCH" 2>/dev/null; then
    git -C "$work" checkout -q -B "$BRANCH" FETCH_HEAD
    return 0
  fi
  git -C "$work" checkout -q --orphan "$BRANCH"
  return 1
}

case "$cmd" in
  fetch)
    if prepare && [ -f "$work/$FILE" ]; then
      cp "$work/$FILE" "$target"
      echo "Ledger loaded from $BRANCH."
    else
      : > "$target"
      echo "No ledger on $BRANCH yet."
    fi
    ;;
  save)
    message=${3:-"chore(linkedin): update announce ledger"}
    for attempt in 1 2 3; do
      prepare || true
      cp "$target" "$work/$FILE"
      git -C "$work" add "$FILE"
      if git -C "$work" diff --cached --quiet; then
        echo "Ledger unchanged."
        exit 0
      fi
      git -C "$work" commit -q -m "$message"
      if git -C "$work" push -q origin "HEAD:$BRANCH"; then
        echo "Ledger saved to $BRANCH."
        exit 0
      fi
      echo "Push rejected (attempt $attempt), retrying." >&2
      sleep $((attempt * 5))
    done
    echo "::error::Could not push the ledger to $BRANCH. If a post just went out, record it there by hand or the next run will repeat it." >&2
    exit 1
    ;;
  *)
    echo "unknown command: $cmd" >&2
    exit 2
    ;;
esac
