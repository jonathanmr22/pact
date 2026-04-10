#!/usr/bin/env bash
# =============================================================================
# PACT PostToolUse Hook — Checkpoint Telemetry Audit
# =============================================================================
# Detects when a checkpoint SHOULD have been used based on session state,
# and logs a checkpoint_expected event to pact-events.jsonl.
#
# This is observability only — no blocking, no warnings to the agent.
# The dashboard correlates checkpoint_expected events against actual
# checkpoint output to measure checkpoint adoption over time.
#
# Currently covers:
#   - bug_fix: A Sentry/issue-tracker fetch happened this session,
#     then a source file was edited → bug_fix checkpoint expected.
#
# Adding new checkpoint detectors: add a function, call it from main.
# Keep false-positive rate near zero — if unsure, don't emit.
# =============================================================================

INPUT=$(cat)

# Extract file_path from hook input
FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

# Only audit source file edits
if [[ ! "$FILE_PATH" =~ \.(dart|ts|tsx|js|jsx|py|rs|go|swift|kt)$ ]]; then
  exit 0
fi

# Skip test/generated files
if [[ "$FILE_PATH" =~ /test/ ]] || [[ "$FILE_PATH" =~ \.(g|generated)\. ]]; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Session ID for dedup
SESSION_ID=$(echo "$INPUT" | grep -o '"session_id"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*"session_id"[[:space:]]*:[[:space:]]*"//;s/"$//')
[ -z "$SESSION_ID" ] && SESSION_ID=$(cat "${TEMP:-${TMP:-/tmp}}/claude_session_id.txt" 2>/dev/null || echo "default")

# Dedup: only emit each checkpoint type once per session
DEDUP_FILE="${TEMP:-${TMP:-/tmp}}/pact_checkpoint_audit_${SESSION_ID}.json"

already_emitted() {
  local check_type="$1"
  if [ -f "$DEDUP_FILE" ]; then
    grep -q "\"$check_type\"" "$DEDUP_FILE" 2>/dev/null && return 0
  fi
  return 1
}

record_emitted() {
  local check_type="$1"
  if [ ! -f "$DEDUP_FILE" ]; then
    echo "[\"$check_type\"]" > "$DEDUP_FILE"
  else
    # Append to JSON array
    python -c "
import json, sys
try:
    with open(sys.argv[1], 'r') as f:
        arr = json.load(f)
except:
    arr = []
arr.append(sys.argv[2])
with open(sys.argv[1], 'w') as f:
    json.dump(arr, f)
" "$DEDUP_FILE" "$check_type" 2>/dev/null
  fi
}

emit_event() {
  local check_type="$1"
  local file="$2"
  if [ -f "$SCRIPT_DIR/pact-event-logger.sh" ]; then
    bash "$SCRIPT_DIR/pact-event-logger.sh" "checkpoint_expected" \
      "{\"checkpoint_type\":\"$check_type\",\"file\":\"$file\"}" \
      "$SESSION_ID" 2>/dev/null &
  fi
}

# ---------------------------------------------------------------------------
# Detector: bug_fix
# Condition: issue tracker flag file exists (written by post-sentry-bug-reminder.sh)
# Meaning: an issue was fetched this session, so source edits are bug-fix work
# ---------------------------------------------------------------------------
check_bug_fix() {
  local flag_file="${TEMP:-${TMP:-/tmp}}/pact_issue_pending.txt"
  if [ -f "$flag_file" ]; then
    if ! already_emitted "bug_fix"; then
      emit_event "bug_fix" "$FILE_PATH"
      record_emitted "bug_fix"
    fi
  fi
}

# ---------------------------------------------------------------------------
# Main — run all detectors silently
# ---------------------------------------------------------------------------
check_bug_fix

exit 0
