#!/usr/bin/env bash
# ============================================================================
# PACT Event Logger
# ============================================================================
# Appends structured JSON events to .claude/pact-events.jsonl.
# Called by other hooks to record PACT activity for the visualizer.
#
# Usage (from other hooks):
#   bash .claude/hooks/pact-event-logger.sh <type> <json_fields>
#
# Examples:
#   bash .claude/hooks/pact-event-logger.sh preflight '{"check":"startup_ordering","file":"main.dart","severity":"think"}'
#   bash .claude/hooks/pact-event-logger.sh edit '{"file":"main.dart","lines":15}'
#   bash .claude/hooks/pact-event-logger.sh hook_block '{"hook":"pre-edit-rules","reason":"no print()"}'
#   bash .claude/hooks/pact-event-logger.sh session_start '{"model":"opus-4-6","redirections_recited":true}'
#   bash .claude/hooks/pact-event-logger.sh flow_read '{"flow":"auth_flow.yaml"}'
#   bash .claude/hooks/pact-event-logger.sh governance '{"action":"updated","file":"feature_flows/auth_flow.yaml"}'
# ============================================================================

EVENT_TYPE="${1:-unknown}"
JSON_FIELDS="$2"
if [ -z "$JSON_FIELDS" ]; then JSON_FIELDS="{}"; fi
SESSION_ID="${3:-default}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Detect project folder name (two levels up from .claude/hooks/)
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_NAME="$(basename "$PROJECT_DIR")"

# Write to CENTRAL user-level JSONL (multi-project support)
# Also write to project-local copy for offline/backup
CENTRAL_LOG="$HOME/.claude/pact-events.jsonl"
LOCAL_LOG="$SCRIPT_DIR/../pact-events.jsonl"

# Merge timestamp + type + session + project + fields into one JSON line
# Use 'python' not 'python3' — on Windows, python3 is a broken Store stub
EVENT_LINE=$(python -c "
import json, sys
try:
    fields = json.loads(sys.argv[1])
except:
    fields = {}
event = {'ts': sys.argv[2], 'type': sys.argv[3], 'sid': sys.argv[4], 'project': sys.argv[5]}
event.update(fields)
print(json.dumps(event))
" "$JSON_FIELDS" "$TIMESTAMP" "$EVENT_TYPE" "$SESSION_ID" "$PROJECT_NAME" 2>/dev/null)

if [ -z "$EVENT_LINE" ]; then
  EVENT_LINE="{\"ts\":\"$TIMESTAMP\",\"type\":\"$EVENT_TYPE\",\"sid\":\"$SESSION_ID\",\"project\":\"$PROJECT_NAME\"}"
fi

# Write to both central and local
echo "$EVENT_LINE" >> "$CENTRAL_LOG" 2>/dev/null
echo "$EVENT_LINE" >> "$LOCAL_LOG" 2>/dev/null
