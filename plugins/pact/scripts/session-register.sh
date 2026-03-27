#!/usr/bin/env bash
# =============================================================================
# PACT SessionStart Hook — registers this session in .claude/sessions.yaml
# so parallel sessions can see each other's activity.
#
# Creates a unique session entry with start time. Old sessions (>24h) are
# pruned automatically. The file is committed alongside code changes via
# pre-bash-guard auto-staging.
# =============================================================================

PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
SESSION_FILE="${PROJECT_ROOT}/.claude/sessions.yaml"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
SESSION_ID="${TIMESTAMP}_$(head -c 2 /dev/urandom | od -An -tx1 | tr -d ' \n')"

# Store session ID in temp for pre-bash-guard to reference
echo "$SESSION_ID" > "${TEMP:-/tmp}/pact_session_id.txt"

# Create file if missing
if [ ! -f "$SESSION_FILE" ]; then
  mkdir -p "$(dirname "$SESSION_FILE")"
  cat > "$SESSION_FILE" << 'HEADER'
# Multi-Session Coordination
# Auto-maintained by PACT hooks. DO NOT edit manually.
sessions: []
HEADER
fi

# Prune sessions older than 24h and add this session
python3 -c "
import sys, re
from datetime import datetime, timezone, timedelta

session_file = sys.argv[1]
session_id = sys.argv[2]
timestamp = sys.argv[3]

with open(session_file, 'r') as f:
    content = f.read()

sessions = []
try:
    session_blocks = re.findall(
        r'- id: \"([^\"]+)\"\n\s+started: \"([^\"]+)\"\n\s+last_activity: \"([^\"]+)\"\n\s+last_commit_hash: ([^\n]+)\n\s+last_commit_msg: \"([^\"]*)\"\n\s+status: (\w+)',
        content
    )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    for sid, started, last_act, commit_hash, commit_msg, status in session_blocks:
        try:
            started_dt = datetime.fromisoformat(started.replace('Z', '+00:00'))
            if started_dt > cutoff:
                sessions.append({
                    'id': sid, 'started': started, 'last_activity': last_act,
                    'last_commit_hash': commit_hash, 'last_commit_msg': commit_msg,
                    'status': status,
                })
        except ValueError:
            pass
except Exception:
    pass

sessions.append({
    'id': session_id, 'started': timestamp, 'last_activity': timestamp,
    'last_commit_hash': 'null', 'last_commit_msg': '', 'status': 'active',
})

with open(session_file, 'w') as f:
    f.write('# Multi-Session Coordination\n')
    f.write('# Auto-maintained by PACT hooks. DO NOT edit manually.\n\n')
    f.write('sessions:\n')
    for s in sessions:
        f.write(f'  - id: \"{s[\"id\"]}\"\n')
        f.write(f'    started: \"{s[\"started\"]}\"\n')
        f.write(f'    last_activity: \"{s[\"last_activity\"]}\"\n')
        f.write(f'    last_commit_hash: {s[\"last_commit_hash\"]}\n')
        f.write(f'    last_commit_msg: \"{s[\"last_commit_msg\"]}\"\n')
        f.write(f'    status: {s[\"status\"]}\n')
" "$SESSION_FILE" "$SESSION_ID" "$TIMESTAMP" 2>/dev/null

ACTIVE=$(grep -c "status: active" "$SESSION_FILE" 2>/dev/null || echo 0)

echo "[Session] Registered: ${SESSION_ID}"
if [ "$ACTIVE" -gt 1 ]; then
  echo "[Session] WARNING: $ACTIVE active sessions detected. Check .claude/sessions.yaml"
fi

exit 0
