#!/usr/bin/env bash
# =============================================================================
# PACT PostToolUse Hook (Read) — Tracks which files the agent has opened.
# Enables the "must read before edit" rule in pre-edit-rules.sh.
# =============================================================================

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

if [ -z "$FILE_PATH" ]; then exit 0; fi

TRACK_FILE="${TEMP:-/tmp}/pact_read_files.txt"
NORM_PATH=$(echo "$FILE_PATH" | sed 's|\\|/|g' | tr '[:upper:]' '[:lower:]')
echo "$NORM_PATH" >> "$TRACK_FILE"
exit 0
