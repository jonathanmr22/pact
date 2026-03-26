#!/usr/bin/env bash
# =============================================================================
# PACT PostToolUse Hook — WARNS about patterns that need attention
# Non-blocking (exit 0 always). Agent sees warnings and can self-correct.
# =============================================================================

INPUT=$(cat)

FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

if [[ ! "$FILE_PATH" =~ \.(dart|ts|tsx|js|jsx|py|rs|go|java|kt|swift|rb|cs)$ ]]; then exit 0; fi
if [ ! -f "$FILE_PATH" ]; then exit 0; fi

WARNINGS=""

# File size
LINES=$(wc -l < "$FILE_PATH")
if [ "$LINES" -gt 800 ]; then
  WARNINGS="${WARNINGS}WARNING: $FILE_PATH is $LINES lines. Consider extracting sub-modules.\n"
fi

# Import count
IMPORT_COUNT=$(grep -cE '^(import |from |require\(|use )' "$FILE_PATH" 2>/dev/null || echo "0")
if [ "$IMPORT_COUNT" -gt 25 ]; then
  WARNINGS="${WARNINGS}WARNING: $FILE_PATH has $IMPORT_COUNT imports. Consider decomposing.\n"
fi

if [ -n "$WARNINGS" ]; then
  echo -e "$WARNINGS" >&2
fi
exit 0
