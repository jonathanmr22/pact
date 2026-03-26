#!/usr/bin/env bash
# =============================================================================
# PACT PreToolUse Hook — BLOCKS edits that violate project rules
#
# Exit 1 = blocked, exit 0 = allowed.
#
# This hook ships with sensible defaults (hardcoded secrets, read-before-write).
# Customize by adding patterns to your project's .claude/hooks/pre-edit-rules.sh
# or by editing this file after installation.
# =============================================================================

INPUT=$(cat)

FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

NEW_STRING=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input', {})
    print(ti.get('new_string', '') or ti.get('content', ''))
except:
    pass
" 2>/dev/null)

# Skip non-source files (configs, docs, etc.)
if [[ ! "$FILE_PATH" =~ \.(dart|ts|tsx|js|jsx|py|rs|go|java|kt|swift|rb|cs)$ ]]; then
  exit 0
fi

VIOLATIONS=""

# ============================================================================
# SECURITY: No hardcoded secrets
# ============================================================================
if echo "$NEW_STRING" | grep -qiE '(api_key|secret_key|password|auth_token)\s*=\s*["\x27][A-Za-z0-9+/=_-]{8,}'; then
  VIOLATIONS="${VIOLATIONS}BLOCKED: No hardcoded secrets. Use environment variables.\n"
fi

# ============================================================================
# READ-BEFORE-WRITE: Agent must read a file before editing it
# Requires post-read-tracker.sh to be active.
# ============================================================================
TRACK_FILE="${TEMP:-/tmp}/pact_read_files.txt"
NORM_PATH=$(echo "$FILE_PATH" | sed 's|\\|/|g' | tr '[:upper:]' '[:lower:]')
if [ -f "$FILE_PATH" ] && [ -f "$TRACK_FILE" ]; then
  if ! grep -qF "$NORM_PATH" "$TRACK_FILE" 2>/dev/null; then
    VIOLATIONS="${VIOLATIONS}BLOCKED: Read '$FILE_PATH' before editing. You haven't opened this file.\n"
  fi
fi

# ============================================================================
# PROJECT-SPECIFIC RULES
# Uncomment and customize. Each rule should explain WHY it's forbidden.
# ============================================================================

# ---- Forbidden imports ----
# if echo "$NEW_STRING" | grep -qi 'import.*hive'; then
#   VIOLATIONS="${VIOLATIONS}BLOCKED: Hive is forbidden. Use Drift.\n"
# fi

# ---- Forbidden functions ----
# if echo "$NEW_STRING" | grep -qE '^\s*(print|debugPrint)\('; then
#   VIOLATIONS="${VIOLATIONS}BLOCKED: Use AppLogger, not print().\n"
# fi

# ---- No raw SQL with interpolation ----
# if echo "$NEW_STRING" | grep -qE 'execute.*\$|rawQuery.*\$'; then
#   VIOLATIONS="${VIOLATIONS}BLOCKED: No raw SQL with string interpolation. Use parameterized queries.\n"
# fi

# ---- No empty catch blocks ----
# if echo "$NEW_STRING" | grep -qE 'catch\s*\([^)]*\)\s*\{\s*\}'; then
#   VIOLATIONS="${VIOLATIONS}BLOCKED: No empty catch blocks. Log the error.\n"
# fi

# ============================================================================
# VERDICT
# ============================================================================
if [ -n "$VIOLATIONS" ]; then
  echo -e "$VIOLATIONS" >&2
  exit 1
fi
exit 0
