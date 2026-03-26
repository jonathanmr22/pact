#!/usr/bin/env bash
# =============================================================================
# PACT PostToolUse Hook — WARNS about patterns that need attention
#
# Runs AFTER the agent edits a file. Non-blocking (exit 0 always).
# Surfaces code smells and potential issues for the agent to address.
#
# CUSTOMIZE: Add your project's warning patterns below.
# =============================================================================

INPUT=$(cat)

FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

# Only check source files
if [[ ! "$FILE_PATH" =~ \.(dart|ts|tsx|py|js|jsx)$ ]]; then exit 0; fi
if [ ! -f "$FILE_PATH" ]; then exit 0; fi

WARNINGS=""

# ============================================================================
# FILE SIZE WARNING
# Large files should be decomposed into focused modules.
# ============================================================================

LINES=$(wc -l < "$FILE_PATH")
if [ "$LINES" -gt 800 ]; then
  WARNINGS="${WARNINGS}WARNING: $FILE_PATH is $LINES lines. Consider extracting sub-modules.\n"
fi

# ============================================================================
# IMPORT COUNT WARNING
# Too many imports = file is doing too much.
# ============================================================================

IMPORT_COUNT=$(grep -c '^import ' "$FILE_PATH" 2>/dev/null || echo "0")
if [ "$IMPORT_COUNT" -gt 25 ]; then
  WARNINGS="${WARNINGS}WARNING: $FILE_PATH has $IMPORT_COUNT imports. Consider decomposing.\n"
fi

# ============================================================================
# LANGUAGE-SPECIFIC WARNINGS
# Uncomment and customize for your stack.
# ============================================================================

# ---- Dart/Flutter ----
# Mounted check after await (prevents setState on disposed widget)
# if grep -n 'await ' "$FILE_PATH" 2>/dev/null | while read -r line; do
#   LINENUM=$(echo "$line" | cut -d: -f1)
#   NEXT=$(sed -n "$((LINENUM+1))p" "$FILE_PATH")
#   if echo "$NEXT" | grep -qE '(setState|Navigator)' && ! echo "$NEXT" | grep -q 'mounted'; then
#     echo "WARNING: Line $LINENUM — await followed by setState/Navigator without mounted check"
#   fi
# done | grep -q 'WARNING'; then
#   WARNINGS="${WARNINGS}Check mounted guards after await calls.\n"
# fi

# ---- TypeScript/JavaScript ----
# Empty catch blocks
# if grep -qE 'catch\s*\([^)]*\)\s*\{\s*\}' "$FILE_PATH"; then
#   WARNINGS="${WARNINGS}WARNING: Empty catch block detected. Log the error.\n"
# fi

# ---- Python ----
# Bare except
# if grep -qE '^\s*except\s*:' "$FILE_PATH"; then
#   WARNINGS="${WARNINGS}WARNING: Bare 'except:' detected. Catch specific exceptions.\n"
# fi

# ============================================================================
# CODE DELETION WITH COMMENTS REMOVED
# If the agent removed a comment, it may have deleted code it didn't understand.
# ============================================================================

# This is checked by diffing — only works if you have the pre-edit content.
# Uncomment if your hook receives the old content:
# if echo "$INPUT" | python3 -c "
# import sys, json
# d = json.load(sys.stdin)
# old = d.get('tool_input', {}).get('old_string', '')
# new = d.get('tool_input', {}).get('new_string', '')
# if '//' in old and '//' not in new and len(new) < len(old):
#     print('WARN')
# " 2>/dev/null | grep -q 'WARN'; then
#   WARNINGS="${WARNINGS}WARNING: Comments were removed along with code. Was the comment's intent preserved?\n"
# fi

# ============================================================================
# OUTPUT
# ============================================================================

if [ -n "$WARNINGS" ]; then
  echo -e "$WARNINGS" >&2
fi
exit 0
