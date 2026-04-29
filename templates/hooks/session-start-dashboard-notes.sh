#!/usr/bin/env bash
# SessionStart hook: surface unread dashboard user-notes from
# .claude/memory/dashboard_user_notes.yaml without disrupting active work.
# The sentinel file dashboard_notes_unread is touched by serve.py whenever a
# new note is added; we count notes with `status: unread` and emit a short
# JSON additionalContext block. Non-blocking.
set -euo pipefail

NOTES_FILE=".claude/memory/dashboard_user_notes.yaml"
SENTINEL=".claude/memory/dashboard_notes_unread"

# Quick exit if neither file exists
if [ ! -f "$NOTES_FILE" ] && [ ! -f "$SENTINEL" ]; then
    exit 0
fi

# Count unread notes (status: unread lines after a `notes:` list).
UNREAD=0
if [ -f "$NOTES_FILE" ]; then
    UNREAD=$(grep -c "status: unread" "$NOTES_FILE" 2>/dev/null || echo 0)
fi

if [ "$UNREAD" -eq 0 ]; then
    # Stale sentinel; clear it
    rm -f "$SENTINEL" 2>/dev/null || true
    exit 0
fi

# Pull the most recent unread note's task name + first 60 chars for the summary
LATEST_TASK=$(grep -B 2 "status: unread" "$NOTES_FILE" 2>/dev/null \
    | grep "task:" | tail -1 | sed -E 's/.*task: "([^"]*)".*/\1/' | head -c 60)
LATEST_NOTE=$(grep -B 1 "status: unread" "$NOTES_FILE" 2>/dev/null \
    | grep "note:" | tail -1 | sed -E 's/.*note: "([^"]*)".*/\1/' | head -c 100)

# Emit a JSON hookSpecificOutput block — non-blocking, just informational
cat <<JSON
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "DASHBOARD NOTES: ${UNREAD} unread user note(s) on dashboard tasks. Latest: \"${LATEST_TASK}\" — ${LATEST_NOTE}. Full file at .claude/memory/dashboard_user_notes.yaml. Don't interrupt your current task to read them; surface them when you're at a natural break or when the user asks. Mark each as 'read' (set status: read in the YAML) once you've acknowledged it."
  }
}
JSON
