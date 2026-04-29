#!/usr/bin/env bash
# ============================================================================
# PACT Dashboard Documentation Hook (PostToolUse)
# ============================================================================
# Fires after Edit/Write on:
#   - plans/dashboard/dashboard.html  (the implementation)
#   - plans/dashboard/trees/**/*.yaml (the data)
#
# Purpose: keep dashboard_build.yaml in sync with the work being done. The
# user repeatedly noticed I add tasks but never mark them done as they ship.
# This hook surfaces a soft reminder to update task statuses + add new tasks
# for any in-flight work you discovered while editing.
#
# Non-blocking — just emits a reminder via stdout (which the agent sees as
# additional context on the next prompt).
# ============================================================================

INPUT=$(cat)

FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

# Only fire on the dashboard's HTML or its data files
case "$FILE_PATH" in
  *plans/dashboard/dashboard.html|*plans\\dashboard\\dashboard.html) ;;
  *plans/dashboard/trees/*.yaml|*plans\\dashboard\\trees\\*.yaml) ;;
  *) exit 0 ;;
esac

# Skip if the edit is itself to dashboard_build.yaml (the documentation file)
case "$FILE_PATH" in
  *dashboard_build.yaml) exit 0 ;;
esac

LEDGER="plans/dashboard/trees/governance/streams/dashboard_build.yaml"

cat <<EOF
DASHBOARD-DOC REMINDER: You just edited $FILE_PATH.
Before moving to the next task, update $LEDGER:
  • Mark any tasks you just completed as status: done
  • Add new tasks for any in-flight work or follow-ups you discovered
  • Update last_touched on the parent feature
This keeps the dashboard's own tracking honest. Don't batch — the user keeps
catching this and it erodes trust.
EOF

exit 0
