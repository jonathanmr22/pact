#!/usr/bin/env bash
# session-start-worktree-prune.sh — DETECT stale session worktrees + REPORT.
#
# This hook does NOT remove anything. It scans worktrees and emits an
# additionalContext block telling Claude what's stale, so Claude can
# analyze, propose a specific cleanup plan, and ask the user for approval
# BEFORE anything is destroyed.
#
# Why detection-only: an earlier draft auto-removed clean+behind-master
# worktrees on every session start. That is too aggressive — even "clean
# and behind master" worktrees may represent a session a user is
# intentionally keeping around (e.g. for reference, in-progress mental
# context, or restore-on-demand). Removal must be a deliberate user choice,
# not a silent SessionStart side effect.
#
# So this hook:
#   1. Counts stale worktrees by category (clean+behind / dirty+behind /
#      ahead / active-session)
#   2. Outputs an additionalContext SystemReminder if any stale ones exist
#   3. Tells Claude to propose a cleanup plan + wait for user approval
#
# Cleanup itself happens via scripts/worktree_cleanup.sh (--apply [--force]),
# which Claude runs only after explicit user authorization.
#
# Designed to be cheap (~50ms per worktree) and silent on no-stale-found.
#
# Repository: https://github.com/jonathanmr22/pact

set -euo pipefail

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
MY_SESSION="${CLAUDE_SESSION_ID:-}"

cd "$PROJECT_ROOT"

# Quick exit if there are no worktrees beyond the main checkout
total=$(git worktree list 2>/dev/null | wc -l | tr -d ' ')
if [[ "$total" -le 1 ]]; then
  exit 0
fi

# Determine main branch — defaults to master, fall back to main
MAIN_BRANCH="master"
if ! git show-ref --verify --quiet "refs/heads/$MAIN_BRANCH"; then
  if git show-ref --verify --quiet "refs/heads/main"; then
    MAIN_BRANCH="main"
  fi
fi

clean_stale=0
dirty_stale=0
ahead=0
active=0
oldest_clean_age_days=0
sample_clean=""
sample_dirty=""

while IFS= read -r line; do
  path=$(awk '{print $1}' <<< "$line")
  if [[ "$path" == "$PROJECT_ROOT" ]]; then
    continue
  fi
  name=$(basename "$path")

  if [[ -n "$MY_SESSION" && "$name" == "$MY_SESSION" ]]; then
    active=$((active + 1))
    continue
  fi

  branch="session/$name"
  unique_commits=$(git rev-list --count "${MAIN_BRANCH}..${branch}" 2>/dev/null || echo 0)
  if [[ "$unique_commits" -gt 0 ]]; then
    ahead=$((ahead + 1))
    continue
  fi

  dirty=$(git -C "$path" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  # Worktree mtime as proxy for "last session activity"
  if [[ -d "$path" ]]; then
    age_days=$(( ( $(date +%s) - $(stat -c %Y "$path" 2>/dev/null || echo 0) ) / 86400 ))
  else
    age_days=0
  fi

  if [[ "$dirty" -gt 0 ]]; then
    dirty_stale=$((dirty_stale + 1))
    if [[ -z "$sample_dirty" ]]; then
      sample_dirty="${name:0:8}… (dirty/${dirty} files, age ${age_days}d)"
    fi
  else
    clean_stale=$((clean_stale + 1))
    if [[ "$age_days" -gt "$oldest_clean_age_days" ]]; then
      oldest_clean_age_days="$age_days"
    fi
    if [[ -z "$sample_clean" ]]; then
      sample_clean="${name:0:8}… (clean, age ${age_days}d)"
    fi
  fi
done < <(git worktree list 2>/dev/null)

# Silent exit if nothing stale
if [[ "$clean_stale" -eq 0 && "$dirty_stale" -eq 0 ]]; then
  exit 0
fi

# Build the report. Keep it concise — counts + samples + instruction.
ctx="WORKTREE PILE-UP DETECTED at session start. ${clean_stale} clean+behind-master worktree(s) and ${dirty_stale} dirty worktree(s) from prior sessions are present (active session and ahead-of-master worktrees excluded from these counts). Oldest clean stale: ${oldest_clean_age_days} day(s)."
if [[ -n "$sample_clean" ]]; then
  ctx="${ctx} Sample clean: ${sample_clean}."
fi
if [[ -n "$sample_dirty" ]]; then
  ctx="${ctx} Sample dirty: ${sample_dirty}."
fi
ctx="${ctx} ACTION REQUIRED: do NOT auto-remove. Surface this to the user, propose a specific plan (which categories to remove, what to verify on dirty worktrees first), and wait for explicit approval. If approved, the cleanup tool is: scripts/worktree_cleanup.sh (use --apply for clean stale; --apply --force for dirty stale ONLY after auditing the diffs are not unique work — sometimes 'dirty' state is a regression of values already scrubbed in master). Use scripts/worktree_cleanup.sh (no flags) to dry-run a full classification first."

# Emit JSON for the harness
printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":%s}}' \
  "$(printf '%s' "$ctx" | python -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"

exit 0
