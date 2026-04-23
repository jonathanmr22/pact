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
# Extract session_id from hook input JSON (per-conversation, no shared state)
SESSION_ID=$(echo "$INPUT" | grep -o '"session_id"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*"session_id"[[:space:]]*:[[:space:]]*"//;s/"$//')
[ -z "$SESSION_ID" ] && SESSION_ID=$(cat "${TEMP:-${TMP:-/tmp}}/claude_session_id.txt" 2>/dev/null || echo "default")
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

# ── Auto-index knowledge files into vector memory (background, non-blocking) ──
# Detects writes to bug files, solutions, and research — indexes them immediately
# so vector search stays current without manual reindex.
if echo "$NORM_PATH" | grep -qE '\bugs/.*\.yaml$|knowledge/research/.*\.yaml$'; then
  MEMORY_SCRIPT="$SCRIPT_DIR/pact-memory.py"
  if [ ! -f "$MEMORY_SCRIPT" ]; then
    MEMORY_SCRIPT="$SCRIPT_DIR/../memory/pact-memory.py"
  fi
  if [ -f "$MEMORY_SCRIPT" ]; then
    PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." 2>/dev/null && pwd)"
    PROJECT_NAME="$(basename "$PROJECT_DIR")"
    # index-file does proper YAML field extraction in background — zero latency
    python "$MEMORY_SCRIPT" index-file "$PROJECT_DIR/$NORM_PATH" \
      --project "$PROJECT_NAME" > /dev/null 2>&1 &
  fi
fi

exit 0
