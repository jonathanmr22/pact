#!/usr/bin/env bash
# =============================================================================
# PACT PreToolUse Hook — BLOCKS edits that violate project rules
#
# Runs BEFORE the agent writes to a file. Pattern-matches against the content
# being written. Exit 1 = blocked, exit 0 = allowed.
#
# CUSTOMIZE: Add your project's forbidden patterns below.
# Each rule should have a comment explaining WHY it's forbidden.
# =============================================================================

INPUT=$(cat)

# Extract file path from tool input JSON
FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

# Extract new content (works for both Edit and Write tools)
NEW_STRING=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input', {})
    print(ti.get('new_string', '') or ti.get('content', ''))
except:
    pass
" 2>/dev/null)

# ---- CUSTOMIZE: File extensions to check ----
# Only check source files (skip configs, docs, etc.)
# Example for Dart: \.dart$
# Example for TypeScript: \.(ts|tsx)$
# Example for Python: \.py$
if [[ ! "$FILE_PATH" =~ \.(dart|ts|tsx|py|js|jsx)$ ]]; then exit 0; fi

VIOLATIONS=""

# ============================================================================
# FORBIDDEN IMPORTS
# Add libraries your project has banned. Include WHY in the message.
# ============================================================================

# Example: Forbidden database library (replaced by ORM)
# if echo "$NEW_STRING" | grep -qi 'import.*hive'; then
#   VIOLATIONS="${VIOLATIONS}BLOCKED: Hive is forbidden. Use Drift (our ORM).\n"
# fi

# Example: Forbidden state management (standardized on one solution)
# if echo "$NEW_STRING" | grep -qi 'import.*getx\|import.*bloc'; then
#   VIOLATIONS="${VIOLATIONS}BLOCKED: Use Riverpod for state management.\n"
# fi

# ============================================================================
# FORBIDDEN FUNCTIONS
# Functions that should never appear in source code.
# ============================================================================

# Example: No print statements (use structured logger)
# if echo "$NEW_STRING" | grep -qE '^\s*(print|debugPrint)\('; then
#   VIOLATIONS="${VIOLATIONS}BLOCKED: Use AppLogger, not print(). Print statements violate app store guidelines.\n"
# fi

# Example: No console.log (use logger)
# if echo "$NEW_STRING" | grep -qE '^\s*console\.(log|warn|error)\('; then
#   VIOLATIONS="${VIOLATIONS}BLOCKED: Use Logger, not console.log().\n"
# fi

# ============================================================================
# SECURITY RULES
# Patterns that would create security vulnerabilities.
# ============================================================================

# No hardcoded secrets
if echo "$NEW_STRING" | grep -qiE '(api_key|secret_key|password|token)\s*=\s*["\x27][A-Za-z0-9+/=_-]{8,}'; then
  VIOLATIONS="${VIOLATIONS}BLOCKED: No hardcoded secrets. Use environment variables.\n"
fi

# No raw SQL with string interpolation (injection risk)
# if echo "$NEW_STRING" | grep -qE 'customSelect.*\$|customStatement.*\$|execute.*\$'; then
#   VIOLATIONS="${VIOLATIONS}BLOCKED: No raw SQL with string interpolation. Use parameterized queries.\n"
# fi

# ============================================================================
# READ-BEFORE-WRITE ENFORCEMENT
# Agent must read a file before editing it. Prevents edits based on guessing.
# Requires the post-read-tracker.sh hook to be active.
# ============================================================================

TRACK_FILE="${TEMP:-/tmp}/pact_read_files.txt"
NORM_PATH=$(echo "$FILE_PATH" | sed 's|\\|/|g' | tr '[:upper:]' '[:lower:]')
if [ -f "$FILE_PATH" ] && [ -f "$TRACK_FILE" ]; then
  if ! grep -qF "$NORM_PATH" "$TRACK_FILE" 2>/dev/null; then
    VIOLATIONS="${VIOLATIONS}BLOCKED: Read '$FILE_PATH' before editing. You haven't opened this file.\n"
  fi
fi

# ============================================================================
# VERDICT
# ============================================================================

if [ -n "$VIOLATIONS" ]; then
  echo -e "$VIOLATIONS" >&2
  exit 1
fi
exit 0
