#!/usr/bin/env bash
# PACT TodoWrite enforcement hook.
#
# Block Edit/Write/Bash after N substantive tool calls if TodoWrite hasn't
# been called recently. Same governance-lock pattern as the CLAUDE.md gate.
#
# Why: the harness emits "TodoWrite hasn't been used recently" reminders on
# its own schedule, but those are easy to ignore. Blocking the next Edit
# until TodoWrite is called forces acknowledgement of task state and keeps
# multi-step work visible to the user.
#
# Routing (configure in .claude/settings.json):
#   PreToolUse  matcher = Edit|Write|Bash|NotebookEdit  -> arg = check
#   PostToolUse matcher = TodoWrite                      -> arg = reset
#   PostToolUse matcher = Edit|Write|Bash|NotebookEdit   -> arg = increment
#
# Threshold tuning: 12 is the default. Lower it (e.g. 8) for projects with
# strict task-tracking discipline; raise it (e.g. 20) if it's getting noisy.

set -e

MODE="${1:-check}"
THRESHOLD=12   # substantive tool calls allowed between TodoWrite updates

PROJ_KEY=$(pwd | md5sum | cut -c1-12)
COUNTER_FILE="${TEMP:-/tmp}/pact_todowrite_counter_${PROJ_KEY}"

if [ "$MODE" = "reset" ]; then
  echo "0" > "$COUNTER_FILE"
  echo '{}'
  exit 0
fi

COUNT=0
[ -f "$COUNTER_FILE" ] && COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)

if [ "$MODE" = "increment" ]; then
  COUNT=$((COUNT + 1))
  echo "$COUNT" > "$COUNTER_FILE"
  echo '{}'
  exit 0
fi

if [ "$COUNT" -ge "$THRESHOLD" ]; then
  cat >/dev/null
  cat <<EOF
{"continue":false,"stopReason":"BLOCKED: You have made $COUNT substantive tool calls without updating your TodoWrite list. Call TodoWrite now to reflect current task state (mark completed items, add discovered work, update in-progress status). Threshold = $THRESHOLD."}
EOF
  exit 0
fi

echo '{}'
