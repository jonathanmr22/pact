#!/usr/bin/env bash
# Stop hook: fires at the end of Claude's response. If dashboard.html was
# edited this session but dashboard_build.yaml was NOT (flag file still
# exists), inject a strong reminder so the NEXT user turn surfaces the
# missed YAML sync. Wave-based enforcement.
set -euo pipefail

FLAG_FILE="/tmp/pact-dashboard-html-edited-${CLAUDE_SESSION_ID:-default}"

if [ ! -f "$FLAG_FILE" ]; then exit 0; fi

# Flag set = dashboard.html was edited but YAML never followed. Block stop
# with a hookSpecificOutput that becomes a system-reminder on the next turn.
cat <<'JSON'
{
  "decision": "block",
  "reason": "WAVE-END YAML SYNC MISSING: You edited plans/dashboard/dashboard.html in this wave but did NOT update plans/dashboard/trees/governance/streams/dashboard_build.yaml to log the work. Before declaring the wave done, write the YAML now: add a new initiative entry (or new tasks under an existing one) for everything you shipped, with status: done and last_touched: today. The dashboard's XP system + your audit trail both depend on this. Then re-emit your final message."
}
JSON
