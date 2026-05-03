#!/usr/bin/env bash
# scripts/worktree_cleanup.sh — remove stale PACT session worktrees.
#
# What's "stale": a session/<id> worktree whose branch tip is at-or-behind
# master AND (clean OR --force flag passed). Worktrees with unique commits
# beyond master are NEVER removed — those represent uncommitted session work
# that hasn't been merged in.
#
# Usage:
#   scripts/worktree_cleanup.sh              # dry-run, lists what would be removed
#   scripts/worktree_cleanup.sh --apply      # actually remove clean stale worktrees
#   scripts/worktree_cleanup.sh --apply --force  # also force-remove dirty stale ones
#
# This is the manual deep-clean. The SessionStart hook
# (session-start-worktree-prune.sh) runs a lighter version automatically on
# every session start.
#
# WHY THIS EXISTS: SessionEnd / Stop hooks don't fire reliably (force-quit,
# crash, terminal close, IDE reload, context-compaction reboots), so worktrees
# accumulate over time. PACT's git-worktree-per-session model is great for
# isolation but needs cleanup hygiene to avoid pile-up.
#
# Repository: https://github.com/jonathanmr22/pact

set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

# Determine main branch — defaults to master, fall back to main if master doesn't exist
MAIN_BRANCH="master"
if ! git show-ref --verify --quiet "refs/heads/$MAIN_BRANCH"; then
  if git show-ref --verify --quiet "refs/heads/main"; then
    MAIN_BRANCH="main"
  fi
fi

APPLY=false
FORCE=false
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=true ;;
    --force) FORCE=true ;;
    -h|--help)
      grep '^# ' "$0" | sed 's/^# \?//'
      exit 0
      ;;
  esac
done

# Guard: never touch the currently-active session's worktree if we can identify it.
MY_SESSION="${CLAUDE_SESSION_ID:-}"

# Counters
clean_stale=0
dirty_stale=0
ahead_keep=0
my_session_keep=0
removed=0

while IFS= read -r line; do
  # Parse `git worktree list` lines: <path> <sha> [<branch>]
  path=$(awk '{print $1}' <<< "$line")

  # Skip the main checkout — only operate on session worktrees
  if [[ "$path" == "$PROJECT_ROOT" ]]; then
    continue
  fi

  name=$(basename "$path")

  # Skip the active session
  if [[ -n "$MY_SESSION" && "$name" == "$MY_SESSION" ]]; then
    echo "  KEEP (active session): $name"
    my_session_keep=$((my_session_keep + 1))
    continue
  fi

  branch="session/$name"

  # Does this branch have commits ahead of the main branch?
  ahead=$(git rev-list --count "${MAIN_BRANCH}..${branch}" 2>/dev/null || echo 0)
  if [[ "$ahead" -gt 0 ]]; then
    echo "  KEEP (ahead $ahead commits): $name"
    ahead_keep=$((ahead_keep + 1))
    continue
  fi

  # Is the worktree dirty?
  dirty=$(git -C "$path" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$dirty" -gt 0 ]]; then
    if [[ "$FORCE" == true ]]; then
      echo "  REMOVE (dirty/$dirty files, --force): $name"
      dirty_stale=$((dirty_stale + 1))
      if [[ "$APPLY" == true ]]; then
        git worktree remove --force "$path" 2>/dev/null || echo "    (remove failed)"
        git branch -D "$branch" >/dev/null 2>&1 || true
        removed=$((removed + 1))
      fi
    else
      echo "  SKIP (dirty/$dirty files, no --force): $name"
    fi
    continue
  fi

  # Clean + at-or-behind main = safe to remove
  echo "  REMOVE (clean, behind ${MAIN_BRANCH}): $name"
  clean_stale=$((clean_stale + 1))
  if [[ "$APPLY" == true ]]; then
    git worktree remove "$path" 2>/dev/null || git worktree remove --force "$path" 2>/dev/null || echo "    (remove failed)"
    git branch -D "$branch" >/dev/null 2>&1 || true
    removed=$((removed + 1))
  fi
done < <(git worktree list)

if [[ "$APPLY" == true ]]; then
  git worktree prune
fi

echo ""
echo "=== Summary ==="
echo "  active session kept:    $my_session_keep"
echo "  ahead-of-${MAIN_BRANCH} kept:   $ahead_keep"
echo "  clean stale:            $clean_stale"
echo "  dirty stale:            $dirty_stale"
if [[ "$APPLY" == true ]]; then
  echo "  REMOVED THIS RUN:       $removed"
else
  echo ""
  echo "  (dry-run; pass --apply to remove)"
  if [[ "$dirty_stale" -gt 0 ]]; then
    echo "  (dirty stale worktrees skipped; pass --apply --force to include)"
    echo "  IMPORTANT: audit the dirty diffs first — sometimes 'dirty' state is"
    echo "  actually a regression of changes already merged into ${MAIN_BRANCH}, not unique work."
  fi
fi
