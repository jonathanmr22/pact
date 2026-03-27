#!/usr/bin/env bash
# =============================================================================
# PACT SessionStart Hook — checks status.claude.com for active incidents
# that affect Claude Code or Claude API at major/critical severity.
#
# Only shows a warning when there's a real problem (major_outage,
# critical impact). Skips minor/degraded to avoid false positives.
# Fails silently on network errors — never blocks session start.
# =============================================================================

STATUS_URL="https://status.claude.com/api/v2/incidents/unresolved.json"

# Fetch with 4s timeout, fail silently
RESPONSE=$(curl -s --max-time 4 "$STATUS_URL" 2>/dev/null)
if [ -z "$RESPONSE" ]; then
  exit 0
fi

# Parse and filter — only major/critical incidents affecting Claude Code or API
python3 -c "
import json, sys
from datetime import datetime, timezone

try:
    data = json.loads(sys.argv[1])
except (json.JSONDecodeError, IndexError):
    sys.exit(0)

incidents = data.get('incidents', [])
if not incidents:
    sys.exit(0)

# Component IDs we care about
RELEVANT_COMPONENTS = {'Claude Code', 'Claude API (api.anthropic.com)', 'claude.ai'}
SEVERE_IMPACTS = {'major', 'critical'}
SEVERE_STATUSES = {'major_outage', 'partial_outage'}

warnings = []
for inc in incidents:
    impact = inc.get('impact', 'none')

    # Check if any affected component we care about is in a severe state
    latest_update = inc.get('incident_updates', [{}])[0] if inc.get('incident_updates') else {}
    affected = latest_update.get('affected_components', [])

    relevant_severe = False
    affected_names = []
    for comp in affected:
        if comp.get('name') in RELEVANT_COMPONENTS and comp.get('new_status') in SEVERE_STATUSES:
            relevant_severe = True
            affected_names.append(comp['name'])

    # Only warn on major/critical impact OR when our components are in severe state
    if impact not in SEVERE_IMPACTS and not relevant_severe:
        continue

    name = inc.get('name', 'Unknown incident')
    status = inc.get('status', 'unknown')
    started = inc.get('started_at', '')

    # Format start time
    time_str = ''
    if started:
        try:
            dt = datetime.fromisoformat(started.replace('Z', '+00:00'))
            time_str = f' (since {dt.strftime(\"%Y-%m-%d %H:%M\")} UTC)'
        except ValueError:
            pass

    # Get latest update body
    body = latest_update.get('body', '') if latest_update else ''
    body_line = f'  Latest: {body}' if body else ''

    warnings.append(f'[Status] WARNING: {name} [{status}]{time_str}')
    if body_line:
        warnings.append(body_line)
    if affected_names:
        warnings.append(f'  Affected: {', '.join(affected_names)}')

if warnings:
    print('[Status] Active incident on status.claude.com:')
    for w in warnings:
        print(w)
    print('[Status] Details: https://status.claude.com')
" "$RESPONSE" 2>/dev/null

exit 0
