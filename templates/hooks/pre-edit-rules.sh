#!/usr/bin/env bash
# =============================================================================
# PACT PreToolUse Hook — BLOCKS edits that violate project rules
#
# Exit 1 = blocked, exit 0 = allowed.
#
# Ships with sensible defaults (hardcoded secrets, read-before-write, issue
# tracker gate). Customize by adding patterns for your project.
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

# ============================================================================
# ISSUE TRACKER GATE — must document bug before fixing it
# If an issue was fetched (post-sentry-bug-reminder.sh wrote a flag),
# BLOCK source file edits until a bugs/ file has been created.
# ============================================================================
ISSUE_FLAG="${TEMP:-${TMP:-/tmp}}/pact_issue_pending.txt"
if [ -f "$ISSUE_FLAG" ] && [ -s "$ISSUE_FLAG" ]; then
  # Only gate source file edits — bug files, docs, tests are always allowed
  if echo "$FILE_PATH" | grep -qiE '[/\\](lib|src|app|packages)[/\\]'; then
    BUG_FILED=false
    TRACK_FILE="${TEMP:-${TMP:-/tmp}}/pact_read_files.txt"
    if [ -f "$TRACK_FILE" ] && grep -qiE '\bugs/.*\.yaml' "$TRACK_FILE" 2>/dev/null; then
      BUG_FILED=true
    fi
    PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
    EDIT_LOG="${PROJECT_ROOT}/.claude/memory/file_edit_log.yaml"
    TODAY=$(date -u +"%Y-%m-%d")
    if [ -f "$EDIT_LOG" ] && grep -qE "bugs/.*${TODAY}" "$EDIT_LOG" 2>/dev/null; then
      BUG_FILED=true
    fi
    if [ "$BUG_FILED" = false ]; then
      PENDING=$(cat "$ISSUE_FLAG" | awk '{print $1}' | tr '\n' ', ' | sed 's/,$//')
      echo "BLOCKED: You fetched issue(s) [${PENDING}] but have NOT created a bug file yet." >&2
      echo "  Create bugs/{system}/{system}-NNN.yaml BEFORE editing source code." >&2
      echo "  Template: bugs/_INDEX.yaml" >&2
      exit 1
    fi
  fi
fi

# ============================================================================
# POWERSHELL ENCODING GATE — block non-ASCII bytes in .ps1 files
# ============================================================================
# `powershell -File` rejects/mis-parses files with UTF-8 multi-byte characters
# when no BOM is present (em-dash, en-dash, smart quotes, ellipsis, etc.).
# Has caused multiple wrapper-script failures in production. Force ASCII-only
# in .ps1. Cross-platform: only fires when the edited file ends in .ps1, so
# Linux/macOS-only projects are unaffected.
if echo "$FILE_PATH" | grep -qiE '\.ps1$' && [ -n "$NEW_STRING" ]; then
  PS1_CHECK=$(python3 -c "
import sys
content = sys.stdin.read()
offenders = []
for lineno, line in enumerate(content.split('\n'), 1):
    bad = [(i, c) for i, c in enumerate(line) if ord(c) > 127]
    if bad:
        offenders.append((lineno, line, bad[:3]))
        if len(offenders) >= 3:
            break
if offenders:
    print('BLOCKED')
    for lineno, line, bad in offenders:
        chars = ', '.join(f\"{repr(c)} at col {i+1}\" for i, c in bad)
        print(f'  line {lineno}: {chars}')
        print(f'    > {line[:120]}')
" <<< "$NEW_STRING" 2>/dev/null)
  if [ -n "$PS1_CHECK" ] && echo "$PS1_CHECK" | head -1 | grep -q '^BLOCKED'; then
    echo "BLOCKED: Non-ASCII bytes in .ps1 file." >&2
    echo "  PowerShell -File loader chokes on UTF-8 multi-byte chars without a BOM." >&2
    echo "  Common offenders: em-dash (use - or --), en-dash (use -), smart quotes, ellipsis (use ...)" >&2
    echo "  Fix: replace with ASCII equivalents before saving." >&2
    echo "$PS1_CHECK" | tail -n +2 | sed 's/^/  /' >&2
    exit 1
  fi
fi

# ============================================================================
# SCRIPT CATALOG GATE (Growth+ tier)
# Must read SCRIPT_CATALOG.yaml before creating or editing scripts.
# Prevents reinventing solutions that already exist in the script library.
# ============================================================================
if echo "$FILE_PATH" | grep -qiE 'scripts/.*\.(py|sh|ts|js)$'; then
  TRACK_FILE="${TEMP:-${TMP:-/tmp}}/pact_read_files.txt"
  CATALOG_READ=false
  if [ -f "$TRACK_FILE" ]; then
    if grep -qi 'script_catalog.yaml' "$TRACK_FILE" 2>/dev/null; then
      CATALOG_READ=true
    fi
  fi
  if [ "$CATALOG_READ" = false ]; then
    echo "BLOCKED: Read scripts/SCRIPT_CATALOG.yaml before creating or editing scripts." >&2
    echo "  The catalog indexes existing scripts with tags, reusable patterns, and lessons." >&2
    echo "  A solution to your problem may already exist — check before writing new code." >&2
    exit 1
  fi
fi

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
# ============================================================================
TRACK_FILE="${TEMP:-${TMP:-/tmp}}/pact_read_files.txt"
NORM_PATH=$(echo "$FILE_PATH" | sed 's|\\|/|g' | tr '[:upper:]' '[:lower:]')
if [ -f "$FILE_PATH" ] && [ -f "$TRACK_FILE" ]; then
  if ! grep -qF "$NORM_PATH" "$TRACK_FILE" 2>/dev/null; then
    VIOLATIONS="${VIOLATIONS}BLOCKED: Read '$FILE_PATH' before editing. You haven't opened this file.\n"
  fi
elif [ -f "$FILE_PATH" ] && [ ! -f "$TRACK_FILE" ]; then
  VIOLATIONS="${VIOLATIONS}BLOCKED: Read '$FILE_PATH' before editing. You haven't opened this file.\n"
fi

# ============================================================================
# No empty catch blocks
# ============================================================================
if echo "$NEW_STRING" | grep -qE 'catch\s*\(\s*_?\s*\)\s*\{\s*\}|catch\s*\(\s*e\s*\)\s*\{\s*\}'; then
  VIOLATIONS="${VIOLATIONS}BLOCKED: No empty catch blocks. Log the error.\n"
fi

# ============================================================================
# No raw SQL with string interpolation
# ============================================================================
if echo "$NEW_STRING" | grep -qE '(execute|rawQuery|customSelect|customStatement)\('; then
  if echo "$NEW_STRING" | grep -qE '\$[a-zA-Z_]|\$\{'; then
    VIOLATIONS="${VIOLATIONS}BLOCKED: No raw SQL with string interpolation. Use parameterized queries.\n"
  fi
fi

# ============================================================================
# AUTO-MEMORY BLOCK — prevent Claude from creating memory files
# The auto-memory system prompt tells Claude to create files in
# ~/.claude/projects/.../memory/. This conflicts with PACT's governance
# model where all knowledge routes to CLAUDE.md, knowledge/, or
# inline MEMORY.md entries. Only MEMORY.md itself is writable.
# ============================================================================
if echo "$FILE_PATH" | grep -qiE '\.claude[/\\]projects[/\\].*[/\\]memory[/\\]'; then
  BASENAME=$(basename "$FILE_PATH")
  if [[ "$BASENAME" != "MEMORY.md" ]]; then
    echo "BLOCKED: Do not create auto-memory files. Add feedback/rules to CLAUDE.md or as inline entries in MEMORY.md." >&2
    exit 1
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

# ---- Forbidden logging ----
# if echo "$NEW_STRING" | grep -qE '(^|[^a-zA-Z])print\(|debugPrint\(|console\.log\('; then
#   VIOLATIONS="${VIOLATIONS}BLOCKED: Use the structured logger, not print/console.log.\n"
# fi

# ---- No hardcoded project refs ----
# if echo "$NEW_STRING" | grep -qE 'YOUR_PROJECT_REF_HERE'; then
#   VIOLATIONS="${VIOLATIONS}BLOCKED: Hardcoded project ref — use environment variables.\n"
# fi

# ---- No manual styling on themed widgets ----
# if echo "$NEW_STRING" | grep -qE '\.styleFrom\('; then
#   VIOLATIONS="${VIOLATIONS}BLOCKED: Manual .styleFrom() — use the theme system.\n"
# fi

# ---- No arbitrary colors outside palette ----
# if echo "$NEW_STRING" | grep -qE 'Color\(0x[0-9A-Fa-f]'; then
#   VIOLATIONS="${VIOLATIONS}BLOCKED: Arbitrary Color() — use the design system palette.\n"
# fi

# ---- No raw dialogs/snackbars — use wrapper ----
# if echo "$NEW_STRING" | grep -qE 'AlertDialog\(|showDialog\(|SnackBar\('; then
#   VIOLATIONS="${VIOLATIONS}BLOCKED: Raw dialog/snackbar — use the project wrapper.\n"
# fi

# ============================================================================
# VERDICT
# ============================================================================
if [ -n "$VIOLATIONS" ]; then
  echo -e "$VIOLATIONS" >&2
  exit 1
fi
exit 0
