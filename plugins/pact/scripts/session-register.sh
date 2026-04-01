#!/usr/bin/env bash
# =============================================================================
# PACT SessionStart Hook — registers this session in .claude/sessions.yaml
# so parallel sessions can see each other's activity.
#
# Detects which agent is running (Claude, Gemini, or unknown) via env vars.
# Creates a unique session entry with start time and model identity.
# Old sessions (>24h) are pruned automatically. The file is committed
# alongside code changes via pre-bash-guard auto-staging.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/pact-common.sh"

PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
SESSION_FILE="${PROJECT_ROOT}/.claude/sessions.yaml"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
SESSION_ID="${TIMESTAMP}_$(pact_random_hex 2)"

# Detect which agent is running
if [ -n "$GEMINI_API_KEY" ] || [ -n "$GEMINI_PROJECT_DIR" ] || [ -n "$GOOGLE_GENAI_USE_VERTEXAI" ]; then
  AGENT_MODEL="gemini"
elif [ -n "$CLAUDE_CODE_VERSION" ] || [ -n "$CLAUDE_PROJECT_DIR" ]; then
  AGENT_MODEL="claude"
else
  PARENT=$(pact_parent_name)
  if echo "$PARENT" | grep -qi "gemini"; then
    AGENT_MODEL="gemini"
  else
    AGENT_MODEL="claude"
  fi
fi

# Store session ID and model in temp for pre-bash-guard to reference
echo "$SESSION_ID" > "${PACT_TEMP}/pact_session_id.txt"
echo "$AGENT_MODEL" > "${PACT_TEMP}/pact_agent_model.txt"

# Create file if missing
if [ ! -f "$SESSION_FILE" ]; then
  mkdir -p "$(dirname "$SESSION_FILE")"
  cat > "$SESSION_FILE" << 'HEADER'
# Multi-Agent Session Coordination
# Auto-maintained by PACT hooks. DO NOT edit manually.
sessions: []
HEADER
fi

# Prune sessions older than 24h and add this session
[ -z "$PACT_PYTHON" ] && { echo "[Session] WARNING: Python not found — session tracking degraded"; exit 0; }
$PACT_PYTHON -c "
import sys, re
from datetime import datetime, timezone, timedelta

session_file = sys.argv[1]
session_id = sys.argv[2]
timestamp = sys.argv[3]
agent_model = sys.argv[4]

with open(session_file, 'r') as f:
    content = f.read()

sessions = []
try:
    session_blocks = re.findall(
        r'- id: \"([^\"]+)\"\n\s+started: \"([^\"]+)\"\n\s+last_activity: \"([^\"]+)\"\n\s+last_commit_hash: ([^\n]+)\n\s+last_commit_msg: \"([^\"]*)\"\n\s+(?:model: (\w+)\n\s+)?status: (\w+)',
        content
    )
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    ghost_cutoff = now - timedelta(hours=2)
    for sid, started, last_act, commit_hash, commit_msg, model, status in session_blocks:
        try:
            started_dt = datetime.fromisoformat(started.replace('Z', '+00:00'))
            last_act_dt = datetime.fromisoformat(last_act.replace('Z', '+00:00'))
            # Prune sessions older than 24h
            if started_dt < cutoff:
                continue
            # Prune ghost sessions: still "active" but no activity for 2h
            if status == 'active' and last_act_dt < ghost_cutoff:
                continue
            sessions.append({
                'id': sid, 'started': started, 'last_activity': last_act,
                'last_commit_hash': commit_hash, 'last_commit_msg': commit_msg,
                'model': model or 'claude', 'status': status,
            })
        except ValueError:
            pass
except Exception:
    pass

sessions.append({
    'id': session_id, 'started': timestamp, 'last_activity': timestamp,
    'last_commit_hash': 'null', 'last_commit_msg': '',
    'model': agent_model, 'status': 'active',
})

with open(session_file, 'w') as f:
    f.write('# Multi-Agent Session Coordination\n')
    f.write('# Auto-maintained by PACT hooks. DO NOT edit manually.\n\n')
    f.write('sessions:\n')
    for s in sessions:
        f.write(f'  - id: \"{s[\"id\"]}\"\n')
        f.write(f'    started: \"{s[\"started\"]}\"\n')
        f.write(f'    last_activity: \"{s[\"last_activity\"]}\"\n')
        f.write(f'    last_commit_hash: {s[\"last_commit_hash\"]}\n')
        f.write(f'    last_commit_msg: \"{s[\"last_commit_msg\"]}\"\n')
        f.write(f'    model: {s[\"model\"]}\n')
        f.write(f'    status: {s[\"status\"]}\n')
" "$SESSION_FILE" "$SESSION_ID" "$TIMESTAMP" "$AGENT_MODEL" 2>/dev/null

ACTIVE=$(grep -c "status: active" "$SESSION_FILE" 2>/dev/null || echo 0)

echo "[Session] Registered: ${SESSION_ID} (${AGENT_MODEL})"
if [ "$ACTIVE" -gt 1 ]; then
  echo "[Session] WARNING: $ACTIVE active sessions detected. Check .claude/sessions.yaml"
fi

exit 0
