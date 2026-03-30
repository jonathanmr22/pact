#!/usr/bin/env bash
# =============================================================================
# PACT PostToolUse Hook — Logs file edit timestamps for cross-session awareness.
# =============================================================================

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

if [ -z "$FILE_PATH" ]; then exit 0; fi

NORM_PATH=$(echo "$FILE_PATH" | sed 's|\\\\|/|g; s|\\|/|g; s|//|/|g')

# ── PACT Dashboard event (all file types) ──
SESSION_ID_FILE="${TEMP:-${TMP:-/tmp}}/claude_session_id.txt"
SESSION_ID=$(cat "$SESSION_ID_FILE" 2>/dev/null || echo "default")
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/pact-event-logger.sh" ]; then
  bash "$SCRIPT_DIR/pact-event-logger.sh" "edit" "{\"file\":\"$NORM_PATH\"}" "$SESSION_ID" 2>/dev/null &
fi

LOG_FILE=".claude/memory/file_edit_log.yaml"
if [ ! -f "$LOG_FILE" ]; then
  mkdir -p "$(dirname "$LOG_FILE")"
  echo "# File edit timestamps — auto-populated by PACT" > "$LOG_FILE"
  echo "edits:" >> "$LOG_FILE"
fi

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
NORM_PATH=$(echo "$FILE_PATH" | sed 's|\\|/|g')
echo "  - file: \"$NORM_PATH\"" >> "$LOG_FILE"
echo "    at: \"$TIMESTAMP\"" >> "$LOG_FILE"
exit 0
