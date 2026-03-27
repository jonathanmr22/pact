#!/usr/bin/env bash
# =============================================================================
# PACT Gemini AfterTool Adapter
# Translates Gemini's stdin JSON format to PACT hook environment variables,
# then delegates to the corresponding PACT PostToolUse hooks.
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
    bash "${PROJECT_ROOT}/.claude/hooks/post-edit-warnings.sh"
    bash "${PROJECT_ROOT}/.claude/hooks/post-edit-timestamp.sh"
    ;;
  read_file|read_many_files)
    FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
inp = d.get('toolInput', {})
print(inp.get('file_path', inp.get('filePath', '')))
" 2>/dev/null)
    export CLAUDE_TOOL_NAME="Read"
    export CLAUDE_FILE_PATH="$FILE_PATH"
    bash "${PROJECT_ROOT}/.claude/hooks/post-read-tracker.sh"
    ;;
  *)
    exit 0
    ;;
esac
