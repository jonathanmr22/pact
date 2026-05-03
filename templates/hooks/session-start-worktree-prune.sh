#!/usr/bin/env bash
# session-start-worktree-prune.sh — auto-remove stale clean worktrees on SessionStart.
#
# Conservative auto-prune: removes ONLY worktrees that are
#   (a) NOT the currently-starting session,
#   (b) at-or-behind the main branch (no commits ahead),
#   (c) clean (no uncommitted changes).
#
# Worktrees with unique commits OR dirty state are left alone — those need
# the human-in-the-loop scripts/worktree_cleanup.sh script.
#
# WHY THIS EXISTS: SessionEnd / Stop hooks don't fire reliably (force-quit,
# crash, terminal close, IDE reload, context-compaction reboots), so worktrees
# accumulate over time. Without this, dozens can pile up between manual
# cleanups. Field report 2026-05-03: a single PACT-using project had 37
# stale worktrees accumulated.
#
# Designed to be cheap (~50ms per worktree) and silent (logs to stderr only,
# never to model context).
#
# Repository: https://github.com/jonathanmr22/pact

set -euo pipefail

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
MY_SESSION="${CLAUDE_SESSION_ID:-}"

cd "$PROJECT_ROOT"

# Determine main branch — defaults to master, fall back to main
MAIN_BRANCH="master"
if ! git show-ref --verify --quiet "refs/heads/$MAIN_BRANCH"; then
  if git show-ref --verify --quiet "refs/heads/main"; then
    MAIN_BRANCH="main"
  fi
fi

# Quick exit if there are no worktrees beyond the main checkout
total=$(git worktree list 2>/dev/null | wc -l | tr -d ' ')
if [[ "$total" -le 1 ]]; then
  exit 0
fi

removed=0
kept_ahead=0
kept_dirty=0
kept_active=0

while IFS= read -r line; do
  path=$(awk '{print $1}' <<< "$line")
  if [[ "$path" == "$PROJECT_ROOT" ]]; then
    continue
  fi
  name=$(basename "$path")

  # Never touch the active session
  if [[ -n "$MY_SESSION" && "$name" == "$MY_SESSION" ]]; then
    kept_active=$((kept_active + 1))
    continue
  fi

  branch="session/$name"

  # Skip if branch has unique commits ahead of the main branch
  ahead=$(git rev-list --count "${MAIN_BRANCH}..${branch}" 2>/dev/null || echo 0)
  if [[ "$ahead" -gt 0 ]]; then
    kept_ahead=$((kept_ahead + 1))
    continue
  fi

  # Skip if working tree is dirty (let the human deal via worktree_cleanup.sh --force)
  dirty=$(git -C "$path" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$dirty" -gt 0 ]]; then
    kept_dirty=$((kept_dirty + 1))
    continue
  fi

  # Safe to remove: clean, behind main, not active session
  if git worktree remove "$path" 2>/dev/null; then
    git branch -D "$branch" >/dev/null 2>&1 || true
    removed=$((removed + 1))
  fi
done < <(git worktree list 2>/dev/null)

git worktree prune 2>/dev/null || true

# Log to stderr — visible in --debug only, never in model context
if [[ "$removed" -gt 0 ]]; then
  echo "[session-start-worktree-prune] removed $removed stale worktree(s); kept active=$kept_active ahead=$kept_ahead dirty=$kept_dirty" >&2
fi

exit 0
