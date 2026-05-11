#!/usr/bin/env bash
# ============================================================================
# Post-Commit Dashboard-Sync Check (PostToolUse, Bash matcher)
# ============================================================================
# Origin: downstream consumer-project session 2026-05-11. The motivating
# observation: "There's no hook that says 'you just committed a code
# change, did you update the corresponding dashboard YAML task?' That's
# pure self-discipline, which fluctuates." This is that hook.
#
# Fires after any Bash tool invocation. Inspects:
#   1. Did the command include "git commit" (vs other git ops)?
#   2. Did the most recent commit touch any plans/dashboard/trees/**/streams/*.yaml?
# If commit happened AND no dashboard YAML was in it, surface a soft
# reminder so the agent's next turn picks up the discipline gap.
#
# Non-blocking — purely advisory via additionalContext.
# ============================================================================

set -euo pipefail

INPUT=$(cat)

# Parse the bash command + (best-effort) the result. The PostToolUse JSON shape is:
#   {"tool_name": "Bash", "tool_input": {"command": "..."}, "tool_response": {...}}
COMMAND=$(printf '%s' "$INPUT" | python -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('tool_input', {}).get('command', ''))
except Exception:
    print('')
" 2>/dev/null)

# Only fire for actual git-commit operations.
echo "$COMMAND" | grep -qE 'git[[:space:]]+(.*[[:space:]]+)?commit([[:space:]]|$)' || exit 0

# Skip if --amend without a new file set (less common; user knows what they're doing).
# Also skip if the command is `git -c ... commit ...` — still want to fire then.

cd "${CLAUDE_PROJECT_DIR:-$(pwd)}" 2>/dev/null || exit 0

# Best-effort: examine the very latest commit on the current branch.
# If we can't, exit silently (no false positives).
LATEST_FILES=$(git diff --name-only HEAD~1..HEAD 2>/dev/null || echo "")
if [ -z "$LATEST_FILES" ]; then exit 0; fi

# Did the commit touch any dashboard stream YAML?
if printf '%s\n' "$LATEST_FILES" | grep -qE '^plans/dashboard/trees/.*/streams/.*\.yaml$'; then
    # Touched — discipline preserved. Stay silent.
    exit 0
fi

# Did the commit touch any "real work" file types? If it's a pure
# documentation/dashboard commit, no reminder is useful.
WORK_FILES=$(printf '%s\n' "$LATEST_FILES" | grep -E '\.(dart|py|ts|tsx|js|jsx|sh|ps1|sql|yaml|yml|md)$' | grep -vE '^plans/dashboard/trees/' | head -20)
if [ -z "$WORK_FILES" ]; then exit 0; fi

# Soft reminder via additionalContext.
LATEST_HASH=$(git log -1 --format=%h 2>/dev/null || echo "???")
LATEST_MSG=$(git log -1 --format=%s 2>/dev/null | head -c 120)
FILE_COUNT=$(printf '%s\n' "$LATEST_FILES" | wc -l | tr -d ' ')

python - <<PY
import json
msg = """POST-COMMIT DISCIPLINE CHECK — commit $LATEST_HASH landed without touching
any plans/dashboard/trees/**/streams/*.yaml. Subject: '$LATEST_MSG'.
Files changed: $FILE_COUNT.

If this commit corresponds to an open dashboard task, update its YAML:
  - status (in_flight -> done, or new -> in_flight)
  - last_touched: 2026-05-11
  - claude_notes: |  (heavy, compaction-resilient)
  - references.commits: [add $LATEST_HASH]

If the commit is a pure refactor with no tracked task, that's fine —
just be aware that future sessions won't see this work tracked unless
you add it to the relevant stream.
"""
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg.strip()}}))
PY
