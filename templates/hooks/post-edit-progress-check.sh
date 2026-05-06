#!/usr/bin/env bash
# =============================================================================
# PACT PostToolUse Hook — Progress Breadcrumb Staleness Check
# =============================================================================
#
# WHAT: Warns the agent when HANDOFF.yaml or dashboard stream YAMLs haven't
#       been touched in a while during a long operation.
# WHY:  During long operations (bulk inserts, multi-file refactors, seeding),
#       agents get deep into execution and stop documenting where they are.
#       The next session opens HANDOFF.yaml, follows it into the dashboard
#       streams, and finds stale information — either repeating work or
#       missing where the previous session stopped. This hook catches that
#       drift mechanically.
#
# HOW:  Counts source-code edits since last HANDOFF.yaml or dashboard stream
#       update via file_edit_log.yaml. If the count exceeds the threshold,
#       emits a non-blocking warning.
#
# TRIGGER: PostToolUse on Edit|Write (fires after every file edit)
# ACTION:  WARNS (non-blocking, exit 0 always)
#
# THRESHOLD: 30 source edits without a progress breadcrumb triggers the
#            warning. Adjust STALE_THRESHOLD below for your project's pace.
# =============================================================================

STALE_THRESHOLD=30

INPUT=$(cat)

FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

if [ -z "$FILE_PATH" ]; then exit 0; fi

# Pattern matching governance-update files: HANDOFF.yaml or any
# plans/dashboard/trees/*/streams/*.yaml entry.
NORM_PATH=$(echo "$FILE_PATH" | sed 's|\\|/|g')
if echo "$NORM_PATH" | grep -qE 'HANDOFF\.yaml$|plans/dashboard/trees/[^/]+/streams/[^/]+\.yaml$'; then
  # Reset the counter by touching a marker file
  MARKER="${TEMP:-${TMP:-/tmp}}/pact_progress_breadcrumb_last_update.txt"
  date +%s > "$MARKER"
  exit 0
fi

# Only check on source code edits (not config, not docs — those are fine)
if [[ ! "$NORM_PATH" =~ \.(dart|ts|tsx|js|jsx|py|rs|go|java|kt|swift|rb|cs|sql)$ ]]; then
  exit 0
fi

# Count edits since last governance-update entry in the log
LOG_FILE=".claude/memory/file_edit_log.yaml"
if [ ! -f "$LOG_FILE" ]; then exit 0; fi

LAST_BREADCRUMB_LINE=$(grep -nE 'HANDOFF\.yaml|plans/dashboard/trees/[^/]+/streams/' "$LOG_FILE" | tail -1 | cut -d: -f1)

if [ -z "$LAST_BREADCRUMB_LINE" ]; then
  # No breadcrumb has ever been logged — count all source edits
  EDITS_SINCE=$(grep -c "^  - file:" "$LOG_FILE" 2>/dev/null || echo "0")
else
  TOTAL_LINES=$(wc -l < "$LOG_FILE" | tr -d ' ')
  REMAINING=$((TOTAL_LINES - LAST_BREADCRUMB_LINE))
  EDITS_SINCE=$(tail -n "$REMAINING" "$LOG_FILE" | grep -c "^  - file:" 2>/dev/null || echo "0")
fi

if [ "$EDITS_SINCE" -ge "$STALE_THRESHOLD" ]; then
  echo "BREADCRUMB CHECK: You've made $EDITS_SINCE source edits since last updating HANDOFF.yaml or any dashboard stream."
  echo ""
  echo "If a future session opened HANDOFF.yaml right now, would they know:"
  echo "  - What you're currently doing?"
  echo "  - What's complete vs in-progress?"
  echo "  - Where to pick up if this session ends?"
  echo ""
  echo "Update HANDOFF.yaml or the relevant plans/dashboard/trees/.../streams/*.yaml before continuing."
  echo "This warning repeats every $STALE_THRESHOLD edits until you update it."
fi

# Time-based staleness via marker file
MARKER="${TEMP:-${TMP:-/tmp}}/pact_progress_breadcrumb_last_update.txt"
if [ -f "$MARKER" ]; then
  LAST_UPDATE=$(cat "$MARKER")
  NOW=$(date +%s)
  ELAPSED=$(( NOW - LAST_UPDATE ))
  # 20 minutes = 1200 seconds
  if [ "$ELAPSED" -gt 1200 ]; then
    MINUTES=$(( ELAPSED / 60 ))
    echo ""
    echo "TIME CHECK: ${MINUTES} minutes since last progress breadcrumb."
    echo "Long operations need periodic breadcrumbs — update HANDOFF.yaml or the relevant dashboard stream now."
  fi
else
  # No marker exists — create one on first run
  date +%s > "$MARKER"
fi

exit 0
