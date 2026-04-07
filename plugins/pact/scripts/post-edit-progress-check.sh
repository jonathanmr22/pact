#!/usr/bin/env bash
# =============================================================================
# PACT PostToolUse Hook — Progress Breadcrumb Staleness Check
# =============================================================================
#
# WHAT: Warns the agent when PENDING_WORK.yaml hasn't been updated in a while.
# WHY:  During long operations (bulk inserts, multi-file refactors, seeding),
#       agents get deep into execution and stop documenting where they are.
#       The next session opens PENDING_WORK.yaml and finds stale information —
#       either repeating work or missing where the previous session stopped.
#       This hook catches that drift mechanically.
#
# HOW:  Counts edits since last PENDING_WORK.yaml update using file_edit_log.yaml.
#       If the count exceeds the threshold, emits a non-blocking warning.
#
# TRIGGER: PostToolUse on Edit|Write (fires after every file edit)
# ACTION:  WARNS (non-blocking, exit 0 always)
#
# THRESHOLD: 30 edits without a PENDING_WORK update triggers the warning.
#            Adjust STALE_THRESHOLD below for your project's pace.
# =============================================================================

STALE_THRESHOLD=30

INPUT=$(cat)

FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

if [ -z "$FILE_PATH" ]; then exit 0; fi

# If the file being edited IS PENDING_WORK.yaml, clear the counter and exit
NORM_PATH=$(echo "$FILE_PATH" | sed 's|\\|/|g')
if echo "$NORM_PATH" | grep -q "PENDING_WORK"; then
  # Reset the counter by touching a marker file
  MARKER="${TEMP:-${TMP:-/tmp}}/pact_pending_work_last_update.txt"
  date +%s > "$MARKER"
  exit 0
fi

# Only check on source code edits (not config, not docs — those are fine)
if [[ ! "$NORM_PATH" =~ \.(dart|ts|tsx|js|jsx|py|rs|go|java|kt|swift|rb|cs|sql|yaml|json)$ ]]; then
  exit 0
fi

# Count edits since last PENDING_WORK update
LOG_FILE=".claude/memory/file_edit_log.yaml"
if [ ! -f "$LOG_FILE" ]; then exit 0; fi

# Find the line number of the last PENDING_WORK edit in the log
LAST_PW_LINE=$(grep -n "PENDING_WORK" "$LOG_FILE" | tail -1 | cut -d: -f1)

if [ -z "$LAST_PW_LINE" ]; then
  # PENDING_WORK has never been in the edit log — count all edits
  EDITS_SINCE=$(grep -c "^  - file:" "$LOG_FILE" 2>/dev/null || echo "0")
else
  # Count edit entries after the last PENDING_WORK line
  TOTAL_LINES=$(wc -l < "$LOG_FILE" | tr -d ' ')
  REMAINING=$((TOTAL_LINES - LAST_PW_LINE))
  EDITS_SINCE=$(tail -n "$REMAINING" "$LOG_FILE" | grep -c "^  - file:" 2>/dev/null || echo "0")
fi

if [ "$EDITS_SINCE" -ge "$STALE_THRESHOLD" ]; then
  echo "BREADCRUMB CHECK: You've made $EDITS_SINCE edits since last updating PENDING_WORK.yaml."
  echo ""
  echo "If a future session opened PENDING_WORK.yaml right now, would they know:"
  echo "  - What you're currently doing?"
  echo "  - What's complete vs in-progress?"
  echo "  - Where to pick up if this session ends?"
  echo ""
  echo "Update .claude/memory/PENDING_WORK.yaml before continuing."
  echo "This warning repeats every $STALE_THRESHOLD edits until you update it."
fi

# Also check time-based staleness via marker file
MARKER="${TEMP:-${TMP:-/tmp}}/pact_pending_work_last_update.txt"
if [ -f "$MARKER" ]; then
  LAST_UPDATE=$(cat "$MARKER")
  NOW=$(date +%s)
  ELAPSED=$(( NOW - LAST_UPDATE ))
  # 20 minutes = 1200 seconds
  if [ "$ELAPSED" -gt 1200 ]; then
    MINUTES=$(( ELAPSED / 60 ))
    echo ""
    echo "TIME CHECK: ${MINUTES} minutes since last PENDING_WORK update."
    echo "Long operations need periodic breadcrumbs — update your progress now."
  fi
else
  # No marker exists — create one on first run
  date +%s > "$MARKER"
fi

exit 0
