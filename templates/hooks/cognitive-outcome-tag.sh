#!/usr/bin/env bash
# cognitive-outcome-tag.sh — PostToolUse hook
#
# Reads recent un-tagged fires from cognitive_redirect_log.jsonl, calls
# detect_self_correction for each, and writes outcome records to
# cognitive_redirect_outcomes.jsonl.
#
# This is loop 2 of the cognitive-redirect system (per COGNITIVE_REDIRECT_DESIGN.md):
#   Loop 1 (cognitive-redirect.sh)  — fires redirects when patterns match
#   Loop 2 (this hook)              — tags outcomes after lookahead window elapsed
#   Loop 3 (future brag injection)  — cites past success outcomes in new fires
#
# DESIGN PROPERTIES:
#   - Independent of redirect-emit hook (separation of concerns)
#   - Bounded work per fire (max 20 pending tagged per run)
#   - Silent on failure (never breaks the conversation)
#   - Idempotent (won't re-tag a fire that's already in the outcomes log)

set -uo pipefail  # NOT -e: tolerate failures gracefully

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Convert Git Bash paths (/c/...) to Windows paths so Python can resolve them.
to_win_path() {
    local p="$1"
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -w "$p" 2>/dev/null | sed 's|\\|/|g' || echo "$p"
    else
        echo "$p" | sed -E 's|^/([a-zA-Z])/|\U\1:/|'
    fi
}

PROJECT_DIR=$(to_win_path "$PROJECT_DIR")
HOOKS_DIR="$PROJECT_DIR/.claude/hooks"
LIB_DIR="$HOOKS_DIR/lib"
WORKER="$LIB_DIR/tag_outcomes.py"
MEMORY_DIR="$PROJECT_DIR/.claude/memory"
LOG_FILE="$MEMORY_DIR/cognitive_redirect_log.jsonl"
OUTCOMES_FILE="$MEMORY_DIR/cognitive_redirect_outcomes.jsonl"

# Bail silently if any required component missing
[ ! -f "$WORKER" ] && exit 0
mkdir -p "$MEMORY_DIR" 2>/dev/null

# If there are no fires logged yet, nothing to tag — exit fast
if [ ! -f "$LOG_FILE" ]; then
    exit 0
fi
if [ ! -s "$LOG_FILE" ]; then
    exit 0
fi

# Read hook stdin to get session_id (Claude Code passes JSON)
HOOK_INPUT=$(cat 2>/dev/null || echo '{}')
SESSION_ID=$(echo "$HOOK_INPUT" | python3 -c "import json,sys; d=json.load(sys.stdin) if not sys.stdin.isatty() else {}; print(d.get('session_id',''))" 2>/dev/null || echo "")

# Run the tagger
PYTHONIOENCODING=utf-8 python3 "$WORKER" \
    --session-id "$SESSION_ID" \
    --log "$LOG_FILE" \
    --outcomes "$OUTCOMES_FILE" \
    --lookahead 3 \
    --max-pending 20 \
    >/dev/null 2>&1

# This hook never emits hookSpecificOutput — outcome tagging is silent
# (it just appends to a log). The brag-citation feature (loop 3) will read
# the outcomes log and inject visible context — but that's a different hook.

exit 0
