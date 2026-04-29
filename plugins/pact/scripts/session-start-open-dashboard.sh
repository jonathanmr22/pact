#!/usr/bin/env bash
# SessionStart hook: open the PACT Dashboard in the user's browser unless
# the user has disabled it via the dashboard's Settings toggle.
# Disable flag: .claude/memory/dashboard_autoopen_disabled  (file presence = OFF)
# Default behavior: ON (open dashboard).
# Also makes sure serve.py is running (idempotent — skips if port is bound).
set -euo pipefail

DISABLE_FLAG=".claude/memory/dashboard_autoopen_disabled"
DASHBOARD_URL="http://localhost:8800/dashboard.html"
DASHBOARD_DIR="plans/dashboard"
SERVE_SCRIPT="$DASHBOARD_DIR/serve.py"

# Honor the user's opt-out
if [ -f "$DISABLE_FLAG" ]; then exit 0; fi

# Skip if there's no dashboard scaffolding in this project
if [ ! -f "$SERVE_SCRIPT" ]; then exit 0; fi

# Start serve.py if port 8800 isn't already listening (Windows-safe check)
if command -v netstat >/dev/null 2>&1; then
    if ! netstat -ano 2>/dev/null | grep -q ":8800.*LISTENING"; then
        # Launch detached so the hook returns immediately
        ( cd "$DASHBOARD_DIR" && nohup python serve.py 8800 >/dev/null 2>&1 & ) >/dev/null 2>&1 &
        sleep 1
    fi
fi

# Open the dashboard in the user's default browser. Detached so the hook
# doesn't block the SessionStart pipeline.
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OS" == "Windows_NT" ]]; then
    cmd //c start "" "$DASHBOARD_URL" >/dev/null 2>&1 || true
elif [[ "$OSTYPE" == "darwin"* ]]; then
    open "$DASHBOARD_URL" >/dev/null 2>&1 || true
else
    xdg-open "$DASHBOARD_URL" >/dev/null 2>&1 || true
fi

# Emit a non-blocking SessionStart hookSpecificOutput note. This is delivered
# to Claude ONCE per session — it carries the dashboard's conventions so we
# don't have to repeat them in every copied prompt.
cat <<JSON
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "PACT Dashboard opened at ${DASHBOARD_URL}. (Toggle off in Dashboard Settings → Startup if unwanted.)\n\nDASHBOARD CONVENTIONS — pasted directives from the dashboard reference this once-per-session context:\nProject root:    \$CLAUDE_PROJECT_DIR\nLedger location: <project_root>/plans/dashboard/trees/{tree}/streams/{stream}.yaml\nTree index:      <project_root>/plans/dashboard/_index.yaml\nSYSTEM_MAP:      <project_root>/SYSTEM_MAP.yaml\n\nDirective grammar (prefix → meaning):\n  WORK ON:           pick this task up next (status todo or in_flight).\n  REVISIT:           re-evaluate this task (status done) — confirm still complete.\n  NEED DETAILS:      explain in depth before doing anything; surface known + unknown.\n  BUMP TASK VERSION: log current attempt as failed in YAML node's attempts list, increment version, reset status to in_flight.\n  UPDATE SYSTEM_MAP: re-verify a section/subsystem in SYSTEM_MAP.yaml against live codebase + bring it current.\n  USER NOTES on …:   notes user attached to that task in the dashboard. Read BEFORE acting; do not make user repeat anything in the inline notes. Mark UNREAD as 'status: read' in <project_root>/.claude/memory/dashboard_user_notes.yaml once acknowledged.\n  SWITCH PROJECT:    swap working context to a different project root.\n\nWhen acting on a directive: search YAML trees for the task name shown after the colon, do the work, mark task done, bump 'last_touched: YYYY-MM-DD'. Live polling refreshes the dashboard within 5s."
  }
}
JSON
