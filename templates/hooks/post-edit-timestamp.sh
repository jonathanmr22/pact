#!/usr/bin/env bash
# =============================================================================
# PACT PostToolUse Hook — Logs file edit timestamps
#
# Creates a running log of which files were modified and when.
# Invaluable for cross-session awareness: the next session reads this file
# to know what changed recently, preventing stale assumptions.
# =============================================================================

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

if [ -z "$FILE_PATH" ]; then exit 0; fi

# ---- CUSTOMIZE: Path to your edit log ----
LOG_FILE=".claude/memory/file_edit_log.yaml"

if [ ! -f "$LOG_FILE" ]; then
  echo "# File edit timestamps — auto-populated by PACT hook" > "$LOG_FILE"
  echo "edits:" >> "$LOG_FILE"
fi

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
NORM_PATH=$(echo "$FILE_PATH" | sed 's|\\|/|g')
echo "  - file: \"$NORM_PATH\"" >> "$LOG_FILE"
echo "    at: \"$TIMESTAMP\"" >> "$LOG_FILE"

exit 0
