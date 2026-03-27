#!/usr/bin/env bash
# =============================================================================
# PACT SessionStart Hook — checks both Claude and Gemini status pages
# for active incidents affecting coding agents.
#
# Claude: status.claude.com/api/v2/incidents/unresolved.json (Statuspage)
# Gemini: status.cloud.google.com/incidents.json (Google Cloud)
#
# Only warns on major/critical incidents. Fails silently on network errors.
# =============================================================================

# ── Claude status check ─────────────────────────────────────────────────
CLAUDE_RESPONSE=$(curl -s --max-time 4 "https://status.claude.com/api/v2/incidents/unresolved.json" 2>/dev/null)

if [ -n "$CLAUDE_RESPONSE" ]; then
  python3 -c "
import json, sys
from datetime import datetime

try:
    data = json.loads(sys.argv[1])
except (json.JSONDecodeError, IndexError):
    sys.exit(0)

incidents = data.get('incidents', [])
if not incidents:
    sys.exit(0)

RELEVANT = {'Claude Code', 'Claude API (api.anthropic.com)', 'claude.ai'}
SEVERE_IMPACTS = {'major', 'critical'}
SEVERE_STATUSES = {'major_outage', 'partial_outage'}

for inc in incidents:
    impact = inc.get('impact', 'none')
    latest = inc.get('incident_updates', [{}])[0] if inc.get('incident_updates') else {}
    affected = latest.get('affected_components', [])

    relevant_severe = any(
        c.get('name') in RELEVANT and c.get('new_status') in SEVERE_STATUSES
        for c in affected
    )

    if impact not in SEVERE_IMPACTS and not relevant_severe:
        continue

    name = inc.get('name', 'Unknown')
    status = inc.get('status', 'unknown')
    started = inc.get('started_at', '')
    body = latest.get('body', '')

    time_str = ''
    if started:
        try:
            dt = datetime.fromisoformat(started.replace('Z', '+00:00'))
            time_str = f' (since {dt.strftime(\"%Y-%m-%d %H:%M\")} UTC)'
        except ValueError:
            pass

    print(f'[Status] CLAUDE DEGRADED: {name} [{status}]{time_str}')
    if body:
        print(f'  {body[:120]}')
    print(f'  https://status.claude.com')
" "$CLAUDE_RESPONSE" 2>/dev/null
fi

# ── Gemini / Google Cloud status check ──────────────────────────────────
GOOGLE_RESPONSE=$(curl -s --max-time 4 "https://status.cloud.google.com/incidents.json" 2>/dev/null)

if [ -n "$GOOGLE_RESPONSE" ]; then
  python3 -c "
import json, sys
from datetime import datetime, timezone, timedelta

try:
    data = json.loads(sys.argv[1])
except (json.JSONDecodeError, IndexError):
    sys.exit(0)

incidents = data.get('incidents', [])
if not incidents:
    sys.exit(0)

# Products we care about
GEMINI_PRODUCTS = {'Vertex Gemini API', 'Gemini Code Assist', 'Gemini Enterprise'}
SEVERE = {'medium', 'high'}
cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

for inc in incidents:
    # Skip resolved incidents
    if inc.get('status') == 'AVAILABLE':
        continue
    # Skip old incidents
    begin = inc.get('begin', '')
    if begin:
        try:
            dt = datetime.fromisoformat(begin)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < cutoff:
                continue
        except ValueError:
            pass

    severity = inc.get('severity', 'low')
    affected = {p.get('title') for p in inc.get('affected_products', [])}
    gemini_hit = affected & GEMINI_PRODUCTS

    if not gemini_hit:
        continue
    if severity not in SEVERE:
        continue

    name = inc.get('external_desc', 'Unknown incident')
    status = inc.get('status', 'unknown')
    locations = ', '.join(l.get('title', '') for l in inc.get('currently_affected_locations', [])[:3])

    print(f'[Status] GEMINI DEGRADED: {name} [{status}]')
    if locations:
        print(f'  Regions: {locations}')
    print(f'  Affected: {\", \".join(gemini_hit)}')
    print(f'  https://status.cloud.google.com/{inc.get(\"uri\", \"\")}')
" "$GOOGLE_RESPONSE" 2>/dev/null
fi

exit 0
