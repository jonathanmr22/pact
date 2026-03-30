#!/usr/bin/env bash
# Logs user prompts as PACT events so they show as cards in the dashboard.
# Called by UserPromptSubmit hook.

INPUT=$(cat)

# Extract the user's message (first 200 chars for the card)
MESSAGE=$(echo "$INPUT" | python -c "
import sys, json, re
try:
    d = json.load(sys.stdin)
    msg = d.get('prompt', d.get('message', d.get('content', '')))
    if isinstance(msg, list):
        msg = ' '.join(str(m.get('text','') if isinstance(m,dict) else m) for m in msg)
    msg = str(msg)
    # Strip IDE context tags
    msg = re.sub(r'<ide_[^>]*>.*?</ide_[^>]*>\s*', '', msg, flags=re.DOTALL)
    msg = re.sub(r'<system-reminder>.*?</system-reminder>\s*', '', msg, flags=re.DOTALL)
    msg = msg.strip()
    print(msg[:200])
except:
    print('')
" 2>/dev/null)

if [ -z "$MESSAGE" ]; then
  exit 0
fi

# Read session ID
SESSION_ID_FILE="${TEMP:-${TMP:-/tmp}}/claude_session_id.txt"
SESSION_ID=$(cat "$SESSION_ID_FILE" 2>/dev/null || echo "default")

# Escape for JSON
ESCAPED=$(echo "$MESSAGE" | python -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))" 2>/dev/null)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
bash "$SCRIPT_DIR/pact-event-logger.sh" "prompt" "{\"message\":$ESCAPED}" "$SESSION_ID" 2>/dev/null &

exit 0
