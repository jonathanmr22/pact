#!/usr/bin/env bash
# =============================================================================
# PACT Gemini BeforeTool Adapter
# Translates Gemini's stdin JSON format to PACT hook environment variables,
# then delegates to the corresponding PACT hook script.
#
# Gemini sends: {"toolName": "replace", "toolInput": {"file_path": "..."}}
# PACT expects: $CLAUDE_TOOL_NAME, $CLAUDE_FILE_PATH, $CLAUDE_COMMAND
# =============================================================================

PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('toolName',''))" 2>/dev/null)

case "$TOOL_NAME" in
  replace|write_file)
    FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
inp = d.get('toolInput', {})
print(inp.get('file_path', inp.get('filePath', '')))
" 2>/dev/null)
    export CLAUDE_TOOL_NAME="Edit"
    export CLAUDE_FILE_PATH="$FILE_PATH"
    export TOOL_INPUT="$INPUT"
    bash "${PROJECT_ROOT}/.claude/hooks/pre-edit-rules.sh"
    EDIT_EXIT=$?
    if [ $EDIT_EXIT -ne 0 ]; then exit $EDIT_EXIT; fi
    bash "${PROJECT_ROOT}/.claude/hooks/pre-edit-feature-flow.sh"
    ;;
  run_shell_command)
    COMMAND=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
inp = d.get('toolInput', {})
print(inp.get('command', ''))
" 2>/dev/null)
    export CLAUDE_TOOL_NAME="Bash"
    export CLAUDE_COMMAND="$COMMAND"
    bash "${PROJECT_ROOT}/.claude/hooks/pre-bash-guard.sh"
    ;;
  *)
    exit 0
    ;;
esac
