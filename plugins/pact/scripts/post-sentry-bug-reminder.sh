#!/usr/bin/env bash
# =============================================================================
# PACT PostToolUse Hook — fires after issue tracker tool calls (e.g. Sentry MCP)
#
# Writes a flag file so pre-edit-rules.sh can BLOCK source edits until a
# bugs/ file is created. Same pattern as read-before-write.
#
# WHY THIS EXISTS: Agents fetch bug reports, jump straight to fix code, and
# never create bug files. Rules say "create the bug file IMMEDIATELY" but
# rules get ignored. This hook makes it mechanical: you cannot edit source
# code after fetching an issue until you've documented the bug.
#
# CUSTOMIZE: Adjust the ISSUE_ID regex for your issue tracker format.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/pact-common.sh"

INPUT=$(cat)

TOOL_OUTPUT=$(echo "$INPUT" | $PACT_PYTHON -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('tool_result', {}).get('content', '') if isinstance(d.get('tool_result'), dict) else str(d.get('tool_result', '')))
" 2>/dev/null)

# Extract issue ID from output
# Matches patterns like: "Issue PROJ-123", "Issue ID: PROJ-123", "#123"
ISSUE_ID=$(echo "$TOOL_OUTPUT" | grep -oE 'Issue [A-Z]+-[A-Za-z0-9]+' | head -1 | sed 's/Issue //')
[ -z "$ISSUE_ID" ] && ISSUE_ID=$(echo "$TOOL_OUTPUT" | grep -oE '#[0-9]+' | head -1)

if [ -z "$ISSUE_ID" ]; then
  exit 0
fi

# Write the flag file
FLAG_FILE="${PACT_TEMP}/pact_issue_pending.txt"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "${ISSUE_ID} ${TIMESTAMP}" >> "$FLAG_FILE"

echo ""
echo "═══ BUG TRACKER: DOCUMENT BEFORE FIXING ═══"
echo "  Issue fetched: ${ISSUE_ID}"
echo ""
echo "  BEFORE editing source code, you MUST create:"
echo "    bugs/{system}/{system}-NNN.yaml"
echo ""
echo "  This is mechanically enforced — pre-edit-rules.sh"
echo "  will BLOCK edits until a bug file exists."
echo ""
echo "  Template: bugs/_INDEX.yaml"
echo "═════════════════════════════════════════════"

exit 0
