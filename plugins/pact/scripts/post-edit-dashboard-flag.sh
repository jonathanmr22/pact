#!/usr/bin/env bash
# PostToolUse hook: when Edit/Write touches dashboard.html, set a session flag.
# When Edit/Write touches dashboard_build.yaml, clear the flag.
# A separate Stop hook reads the flag and nudges if it's still set at end of
# the response — that's the "wave-based" YAML-sync enforcement.
set -euo pipefail

FLAG_FILE="/tmp/pact-dashboard-html-edited-${CLAUDE_SESSION_ID:-default}"

# The hook receives the tool call as JSON on stdin
INPUT=$(cat)
TOOL=$(echo "$INPUT" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_name',''))" 2>/dev/null || echo "")
PATH_EDITED=$(echo "$INPUT" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null || echo "")

if [ -z "$PATH_EDITED" ]; then exit 0; fi

# Set flag when dashboard.html is edited
if echo "$PATH_EDITED" | grep -q "plans/dashboard/dashboard\.html$"; then
    touch "$FLAG_FILE"
    exit 0
fi

# Clear flag when dashboard_build.yaml is edited
if echo "$PATH_EDITED" | grep -q "plans/dashboard/trees/governance/streams/dashboard_build\.yaml$"; then
    rm -f "$FLAG_FILE" 2>/dev/null || true
    exit 0
fi
exit 0
