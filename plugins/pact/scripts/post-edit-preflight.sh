#!/usr/bin/env bash
# ============================================================================
# Preflight — architectural metacognitive checks
# ============================================================================
# PostToolUse hook that fires AFTER edits. Unlike post-edit-warnings.sh
# (syntax-level: missing braces, mounted checks), Preflight catches
# ARCHITECTURAL mistakes: wrong call site, missing platform config,
# unverified API assumptions, state changes without UI notification.
#
# Checks defined in preflight-checks.yaml (data-driven, expandable).
# Adding a new check = adding YAML. No script changes needed.
#
# Each check fires ONCE per session (session-scoped dedup prevents alert fatigue).
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/pact-common.sh"

INPUT=$(cat)

# Extract file_path from the hook input
FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

# Only check source files (customize extensions for your project)
if [[ ! "$FILE_PATH" =~ \.(dart|ts|tsx|js|jsx|py|rs|go|xml|yaml)$ ]]; then
  exit 0
fi

# Skip test/generated files
if [[ "$FILE_PATH" =~ /test/ ]] || [[ "$FILE_PATH" =~ \.(g|generated)\. ]]; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHECKS_FILE="$SCRIPT_DIR/preflight-checks.yaml"

if [ ! -f "$CHECKS_FILE" ]; then
  exit 0
fi

# Extract new_string from the JSON input (the content being written)
NEW_STRING=$($PACT_PYTHON -c "
import sys, json
try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input', {})
    ns = ti.get('new_string', '') or ti.get('content', '')
    print(ns)
except:
    pass
" <<< "$INPUT" 2>/dev/null)

# Session-scoped dedup: don't fire the same check twice per session
SESSION_ID="${CLAUDE_SESSION_ID:-default}"
STATE_FILE="${PACT_TEMP}/preflight_fired_${SESSION_ID}.json"

# Run checks (with session dedup)
WARNINGS=$($PACT_PYTHON -c "
import sys, re, json, os

try:
    import yaml
except ImportError:
    print('Preflight: PyYAML not installed (pip install pyyaml)', file=sys.stderr)
    sys.exit(0)

checks_file = sys.argv[1]
file_path = sys.argv[2]
state_file = sys.argv[3]
new_string = sys.stdin.read()

with open(checks_file, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

if not config or 'checks' not in config:
    sys.exit(0)

# Load session state (which checks already fired)
already_fired = set()
if os.path.exists(state_file):
    try:
        with open(state_file, 'r') as f:
            already_fired = set(json.load(f))
    except:
        pass

fired = []

for check in config['checks']:
    cid = check.get('id', 'unknown')

    # Skip if already fired this session
    if cid in already_fired:
        continue

    trigger = check.get('trigger', {})
    file_match = trigger.get('file_match', '')
    content_new = trigger.get('content_new', '')
    require_all = trigger.get('require_all', True)

    matches = []

    if file_match:
        matches.append(bool(re.search(file_match, file_path)))
    if content_new:
        matches.append(bool(re.search(content_new, new_string)))

    if not matches:
        continue

    if require_all:
        triggered = all(matches)
    else:
        triggered = any(matches)

    if triggered:
        fired.append(check)

if fired:
    # Save fired check IDs to session state
    new_fired = already_fired | {c.get('id', '?') for c in fired}
    try:
        with open(state_file, 'w') as f:
            json.dump(list(new_fired), f)
    except:
        pass

    for check in fired:
        severity = check.get('severity', 'think').upper()
        cid = check.get('id', 'unknown')
        msg = check.get('message', '').strip()
        root = check.get('root_pattern', '')
        print(f'Preflight [{cid}]: {msg}')
        if root:
            print(f'   Root pattern: {root}')
        print()
" "$CHECKS_FILE" "$FILE_PATH" "$STATE_FILE" <<< "$NEW_STRING" 2>/dev/null)

if [ -n "$WARNINGS" ]; then
  echo "$WARNINGS"
fi

exit 0
