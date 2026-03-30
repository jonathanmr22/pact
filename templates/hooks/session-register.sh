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

PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
SESSION_FILE="${PROJECT_ROOT}/.claude/sessions.yaml"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
SESSION_ID="${TIMESTAMP}_$(head -c 2 /dev/urandom | od -An -tx1 | tr -d ' \n')"

# Detect which agent is running
if [ -n "$GEMINI_API_KEY" ] || [ -n "$GEMINI_PROJECT_DIR" ] || [ -n "$GOOGLE_GENAI_USE_VERTEXAI" ]; then
  AGENT_MODEL="gemini"
elif [ -n "$CLAUDE_CODE_VERSION" ] || [ -n "$CLAUDE_PROJECT_DIR" ]; then
  AGENT_MODEL="claude"
else
  PARENT=$(ps -o comm= -p $PPID 2>/dev/null || echo "unknown")
  if echo "$PARENT" | grep -qi "gemini"; then
    AGENT_MODEL="gemini"
  else
    AGENT_MODEL="claude"
  fi
fi

# Store session ID and model in temp for pre-bash-guard to reference
echo "$SESSION_ID" > "${TEMP:-/tmp}/pact_session_id.txt"
echo "$AGENT_MODEL" > "${TEMP:-/tmp}/pact_agent_model.txt"

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
python3 -c "
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
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    for sid, started, last_act, commit_hash, commit_msg, model, status in session_blocks:
        try:
            started_dt = datetime.fromisoformat(started.replace('Z', '+00:00'))
            if started_dt > cutoff:
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

# ── Emit PACT session_start event (if event logger exists) ──
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/pact-event-logger.sh" ]; then
  bash "$SCRIPT_DIR/pact-event-logger.sh" "session_start" "{\"model\":\"$AGENT_MODEL\"}" "$SESSION_ID" 2>/dev/null &
fi

# ── PACT Dashboard check ──
PACT_CONFIG="$HOME/.claude/pact-config.json"
PACT_PREF="ask"
if [ -f "$PACT_CONFIG" ]; then
  PACT_PREF=$(python -c "import json; print(json.load(open('$PACT_CONFIG')).get('dashboard','ask'))" 2>/dev/null || echo "ask")
fi

PACT_RUNNING=false
if curl -s --max-time 1 http://127.0.0.1:7246/ > /dev/null 2>&1; then
  PACT_RUNNING=true
fi

echo "[Session] Registered: ${SESSION_ID} (${AGENT_MODEL})"
if [ "$ACTIVE" -gt 1 ]; then
  echo "[Session] WARNING: $ACTIVE active sessions detected. Check .claude/sessions.yaml"
fi

if [ "$PACT_PREF" = "off" ]; then
  :
elif [ "$PACT_RUNNING" = "true" ]; then
  echo "[PACT] Dashboard active at http://127.0.0.1:7246"
elif [ "$PACT_PREF" = "auto" ]; then
  python "$SCRIPT_DIR/../dashboard/pact-server.py" > /dev/null 2>&1 &
  echo "[PACT] Dashboard auto-started at http://127.0.0.1:7246"
else
  echo "[PACT] Dashboard is not running. User preference is 'ask'. Ask the user if they'd like to activate it. To start: python .claude/hooks/pact-server.py &"
fi

SCORECARD="$HOME/.claude/pact-scorecard.md"
if [ -f "$SCORECARD" ]; then
  echo "[PACT] Task scorecard available — read ~/.claude/pact-scorecard.md for user feedback on past tasks."
fi

# ── PACT Memory (vector recall) ──
MEMORY_DB="$HOME/.claude/pact-memory.db"
if [ -f "$MEMORY_DB" ]; then
  DOC_COUNT=$(python -c "
import sqlite3, os
db = sqlite3.connect(os.path.expanduser('~/.claude/pact-memory.db'))
print(db.execute('SELECT COUNT(*) FROM pact_docs').fetchone()[0])
db.close()
" 2>/dev/null || echo 0)
  echo "[PACT] Vector memory active — $DOC_COUNT documents indexed. Use /pact-recall to search."
fi

# ── PACT Feedback milestones (Day 2, Week 2) ──
python -c "
import json, os, sys
from datetime import datetime, timedelta

config_path = os.path.expanduser('~/.claude/pact-config.json')
if not os.path.exists(config_path):
    sys.exit(0)

with open(config_path, 'r') as f:
    config = json.load(f)

today = datetime.now().strftime('%Y-%m-%d')

# Set first_used if not set
if 'first_used' not in config:
    config['first_used'] = today
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    sys.exit(0)

first = datetime.strptime(config['first_used'], '%Y-%m-%d')
now = datetime.now()
days = (now - first).days

# Day 2 milestone
if days >= 2 and not config.get('feedback_day2_done'):
    print('[PACT Feedback] You have been using PACT for 2 days. Ask the user: \"PACT has a milestone feedback feature — would you like me to generate a feedback report about your experience so far? It contains zero identifying information — no project names, no tech stack, no code. Just aggregate PACT usage and what helped or didn\\'t. It stays local unless you choose to share it.\"')

# Week 2 milestone
elif days >= 14 and not config.get('feedback_week2_done'):
    print('[PACT Feedback] You have been using PACT for 2 weeks. Ask the user: \"It has been two weeks with PACT. Would you like me to generate a feedback report? It captures what subsystems you used, what helped, and what caused friction. No project names, no tech stack, no identifying details — fully anonymous if you choose to share.\"')
" 2>/dev/null

exit 0
