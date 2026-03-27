#!/usr/bin/env bash
# =============================================================================
# PACT Cooperative Agent — delegate a task from one agent to another
#
# Usage (from the primary agent's Bash/shell tool):
#   bash .gemini/delegate-to-gemini.sh "research the API for X"
#   bash .gemini/delegate-to-gemini.sh --edit "refactor this service"
#   bash .gemini/delegate-to-gemini.sh --research "what does package Y's API look like"
#
# Modes:
#   (default)    — read-only research, no file edits (safe)
#   --edit       — full tool access, can edit files
#   --research   — explicit read-only, web search enabled
#
# Output: Gemini's response is printed to stdout for the calling agent to read.
# File changes: visible via git diff after the call.
# =============================================================================

set -euo pipefail

MODE="plan"
YOLO_FLAG=""
PROMPT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --edit)
      MODE="auto_edit"
      YOLO_FLAG="--yolo"
      shift
      ;;
    --research)
      MODE="plan"
      shift
      ;;
    *)
      PROMPT="$1"
      shift
      ;;
  esac
done

if [ -z "$PROMPT" ]; then
  echo "ERROR: No prompt provided."
  echo "Usage: delegate-to-gemini.sh [--edit|--research] \"task description\""
  exit 1
fi

PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")

FULL_PROMPT="You are Gemini, working cooperatively with another AI agent on this project.
The other agent has delegated this specific task to you. Complete it and report back.

IMPORTANT:
- Read GEMINI.md for project context
- Read the project's instruction file (CLAUDE.md or equivalent) for rules
- Do NOT redo work the other agent has already done
- Be concise in your response — the other agent will read your output
- If you edit files, explain what you changed and why

TASK: ${PROMPT}"

cd "$PROJECT_ROOT"

if [ "$MODE" = "auto_edit" ]; then
  gemini --prompt "$FULL_PROMPT" $YOLO_FLAG 2>/dev/null
else
  gemini --prompt "$FULL_PROMPT" 2>/dev/null
fi

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
  echo "WARNING: Gemini exited with code $EXIT_CODE"
fi

exit 0
