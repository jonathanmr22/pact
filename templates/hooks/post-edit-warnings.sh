#!/usr/bin/env bash
# =============================================================================
# PACT PostToolUse Hook — WARNS about patterns that need attention
# Non-blocking (exit 0 always). Agent sees warnings and can self-correct.
#
# Checks:
#   - File size > 800 lines
#   - Import count > 25
#   - Modal/bottom sheet without scroll wrapper
#   - Code deletion that removes comments (destroying documented intent)
#   - Workaround/hack language in new code
#   - Name-based matching instead of ID-based
#   - Entity ID string interpolation (double-prefix bug)
#   - Braceless control flow (language-specific)
#
# CUSTOMIZE: Uncomment or add project-specific warnings at the bottom.
# =============================================================================

INPUT=$(cat)

FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

if [[ ! "$FILE_PATH" =~ \.(dart|ts|tsx|js|jsx|py|rs|go|java|kt|swift|rb|cs)$ ]]; then exit 0; fi
if [ ! -f "$FILE_PATH" ]; then exit 0; fi
if [[ "$FILE_PATH" =~ /test/ ]]; then exit 0; fi

WARNINGS=""

# ============================================================================
# FILE SIZE
# ============================================================================
LINES=$(wc -l < "$FILE_PATH" 2>/dev/null | tr -d ' ')
if [ -n "$LINES" ] && [ "$LINES" -gt 800 ]; then
  WARNINGS="${WARNINGS}WARNING: $FILE_PATH is $LINES lines (>800). Consider extracting sub-modules.\n"
fi

# ============================================================================
# IMPORT COUNT
# ============================================================================
IMPORT_COUNT=$(grep -cE '^(import |from |require\(|use )' "$FILE_PATH" 2>/dev/null || echo "0")
if [ "$IMPORT_COUNT" -gt 25 ]; then
  WARNINGS="${WARNINGS}WARNING: $FILE_PATH has $IMPORT_COUNT imports (>25). Consider decomposing.\n"
fi

# ============================================================================
# MODAL WITHOUT SCROLL WRAPPER
# ============================================================================
if grep -qE 'showModalBottomSheet|showBottomSheet|BottomSheet\(' "$FILE_PATH" 2>/dev/null; then
  if ! grep -q 'SingleChildScrollView\|DraggableScrollableSheet\|ListView' "$FILE_PATH" 2>/dev/null; then
    WARNINGS="${WARNINGS}WARNING: Modal/bottom sheet in $FILE_PATH without scroll wrapper — body MUST scroll to prevent overflow.\n"
  fi
fi

# ============================================================================
# CODE DELETION WITH COMMENTS REMOVED
# Catches when the agent deletes code without understanding WHY it exists.
# ============================================================================
COMMENT_REMOVAL_WARN=$(python3 -c "
import sys, json

try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input', {})
    old = ti.get('old_string', '')
    new = ti.get('new_string', '')

    if not old:
        sys.exit(0)

    old_lines = old.strip().split('\n')
    new_lines = new.strip().split('\n')

    def is_comment_line(line):
        s = line.strip()
        return s.startswith('//') or s.startswith('#') or s.startswith('/*') or s.startswith('*') or s.startswith('*/') or s.startswith('\"\"\"') or s.startswith(\"'''\")

    old_comments = [l for l in old_lines if is_comment_line(l)]
    new_comments = [l for l in new_lines if is_comment_line(l)]

    removed = []
    for cl in old_comments:
        stripped = cl.strip()
        if stripped and not any(stripped == nl.strip() for nl in new_comments):
            removed.append(stripped)

    net_deleted = len(old_lines) - len(new_lines)

    if len(removed) >= 1 and net_deleted >= 3:
        samples = '; '.join(removed[:3])
        print(f'DELETED {net_deleted} lines including {len(removed)} comment(s): {samples}')
except Exception:
    pass
" <<< "$INPUT" 2>/dev/null)

if [ -n "$COMMENT_REMOVAL_WARN" ]; then
  WARNINGS="${WARNINGS}WARNING: You removed code with explanatory comments. Comments document WHY code exists. ${COMMENT_REMOVAL_WARN}. Before removing commented code, understand the intent behind it.\n"
fi

# ============================================================================
# WORKAROUND / HACK LANGUAGE IN NEW CODE
# Detects bespoke workarounds instead of proper research.
# ============================================================================
WORKAROUND_WARN=$(python3 -c "
import sys, json, re

try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input', {})
    new = ti.get('new_string', '') or ti.get('content', '')

    if not new:
        sys.exit(0)

    patterns = [
        r'(//|#).*\b(workaround|work-around|hack|kludge|bandaid|band-aid)\b',
        r'(//|#).*\b(doesn.t work|does not work|broken in|bug in|issue with)\b',
        r'(//|#).*\b(fallback|fall back)\s+(for|because|since|due)',
        r'(//|#).*\bTODO.*\b(fix|remove|revert).*\b(when|once|after)\b.*\b(update|upgrade|patch|release|version)\b',
        r'(//|#).*\b(supposed to|should but|expected to)\b',
    ]

    matches = []
    for line in new.split('\n'):
        stripped = line.strip()
        for pat in patterns:
            if re.search(pat, stripped, re.IGNORECASE):
                matches.append(stripped[:120])
                break

    if matches:
        print(f'{len(matches)} workaround comment(s): {matches[0]}')
except Exception:
    pass
" <<< "$INPUT" 2>/dev/null)

if [ -n "$WORKAROUND_WARN" ]; then
  WARNINGS="${WARNINGS}WARNING: WORKAROUND DETECTED — $WORKAROUND_WARN. STOP AND RESEARCH. Check knowledge/packages/{package}.yaml first. If not sufficient, search official docs. Save findings for future sessions. The correct response to unexpected behavior is research, not hacks.\n"
fi

# ============================================================================
# NAME-BASED MATCHING INSTEAD OF ID
# NEVER deduplicate or identify entities by display name. Names aren't unique.
# ============================================================================
if grep -qE '\.name\s*==\s*.*\.name|indexWhere.*\.name\s*==' "$FILE_PATH" 2>/dev/null; then
  NAME_DEDUP=$(grep -nE '\.name\s*==\s*.*\.name|indexWhere.*\.name\s*==' "$FILE_PATH" 2>/dev/null | head -3)
  if [ -n "$NAME_DEDUP" ]; then
    WARNINGS="${WARNINGS}WARNING: NAME-BASED MATCHING in $FILE_PATH — use IDs, not display names. Names are not unique.\n"
  fi
fi

# ============================================================================
# ENTITY ID STRING INTERPOLATION (double-prefix bug)
# Catches 'prefix_${entity.id}' where id already contains the prefix.
# ============================================================================
if grep -qP "'\w+_\\\$\{.*\.(id|entityId)" "$FILE_PATH" 2>/dev/null; then
  WARNINGS="${WARNINGS}WARNING: Entity ID string interpolation in $FILE_PATH — verify the ID isn't already prefixed (double-prefix bug).\n"
fi

# ============================================================================
# BRACELESS CONTROL FLOW (language-dependent)
# ============================================================================
if [[ "$FILE_PATH" =~ \.(dart|java|kt|swift|ts|tsx|js|jsx|cs)$ ]]; then
  BRACELESS=$(grep -nE '^\s*(if|else if|for|while)\s*\(.*\)\s*[^{;/]' "$FILE_PATH" 2>/dev/null | grep -v '//' | head -5)
  if [ -n "$BRACELESS" ]; then
    WARNINGS="${WARNINGS}WARNING: Possible braceless control flow in $FILE_PATH:\n$BRACELESS\n"
  fi
fi

# ============================================================================
# ASYNC SAFETY: await without mounted check (Dart/Flutter specific)
# Uncomment if using Flutter.
# ============================================================================
# if [[ "$FILE_PATH" =~ \.dart$ ]] && grep -qE 'await ' "$FILE_PATH" 2>/dev/null; then
#   MISSING=$(python3 -c "
# with open('$FILE_PATH', 'r', errors='replace') as f:
#     lines = f.read().split('\n')
# count = 0
# for i, line in enumerate(lines):
#     s = line.strip()
#     if 'setState(' in s or 'Navigator.' in s or 'context.push' in s:
#         prev = lines[max(0,i-5):i]
#         if any('await ' in l for l in prev) and not any('mounted' in l for l in prev + [lines[i]]):
#             count += 1
# print(count)
# " 2>/dev/null)
#   if [ "$MISSING" != "0" ] && [ -n "$MISSING" ]; then
#     WARNINGS="${WARNINGS}WARNING: $MISSING setState/Navigator after await without mounted check in $FILE_PATH\n"
#   fi
# fi

# ============================================================================
# PROJECT-SPECIFIC WARNINGS (uncomment and customize)
# ============================================================================

# ---- Sacred files that should never lose data ----
# if [[ "$FILE_PATH" =~ seed_data\.dart$ ]]; then
#   WARNINGS="${WARNINGS}WARNING: You are editing a seed data file — never delete seed entries.\n"
# fi

# ---- Hardcoded spacing/padding instead of design system constants ----
# HARDCODED_GAPS=$(grep -cE 'SizedBox\(height:\s*[0-9]' "$FILE_PATH" 2>/dev/null || echo 0)
# if [ "$HARDCODED_GAPS" -gt 3 ]; then
#   WARNINGS="${WARNINGS}WARNING: $HARDCODED_GAPS hardcoded gaps — use design system spacing constants.\n"
# fi

# ── Warning: async method without reentrancy guard ──
# The #1 race condition pattern: async method called by callbacks (GPS, timers,
# UI events) without a guard preventing concurrent execution. LLMs create this
# pattern constantly because they reason about the happy path, not interleavings.
if grep -qE 'Future.*async' "$FILE_PATH" 2>/dev/null; then
  UNGUARDED_ASYNC=$(python3 -c "
import re
with open('$FILE_PATH', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()
lines = content.split('\n')
count = 0
in_async = False
has_guard = False
has_await = False
for line in lines:
    s = line.strip()
    m = re.match(r'(static\s+)?Future.*\b(\w+)\s*\(.*\)\s*async\s*\{', s)
    if m:
        if in_async and has_await and not has_guard:
            count += 1
        in_async = True
        has_guard = False
        has_await = False
        continue
    if in_async:
        if 'await ' in s:
            has_await = True
        if re.search(r'if\s*\(\s*_\w*(ing|ting|ding|sing|ized|cessing)\b', s) and 'return' in s:
            has_guard = True
if in_async and has_await and not has_guard:
    count += 1
print(count)
" 2>/dev/null)
  UNGUARDED_ASYNC=${UNGUARDED_ASYNC:-0}
  if [ "$UNGUARDED_ASYNC" -gt 0 ] && [ "$UNGUARDED_ASYNC" != "0" ]; then
    WARNINGS="${WARNINGS}WARNING: $UNGUARDED_ASYNC async method(s) in $FILE_PATH with await but no reentrancy guard. If called by event callbacks, add: if (_processing) return; at the top.\n"
  fi
fi

if [ -n "$WARNINGS" ]; then
  echo -e "$WARNINGS" >&2
fi
exit 0
