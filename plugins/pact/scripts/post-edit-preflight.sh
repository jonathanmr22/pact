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
# Each check:
#   trigger  — file path + content patterns
#   severity — "think" (metacognitive prompt) or "warn" (likely mistake)
#   message  — a QUESTION that engages reasoning, not a rule to comply with
#   root_pattern + learned_from — the class of mistake and the incident
# ============================================================================

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
NEW_STRING=$(python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input', {})
    # Edit tool has new_string, Write tool has content
    ns = ti.get('new_string', '') or ti.get('content', '')
    print(ns)
except:
    pass
" <<< "$INPUT" 2>/dev/null)

# Run checks
WARNINGS=$(python3 -c "
import sys, re, yaml

checks_file = sys.argv[1]
file_path = sys.argv[2]
new_string = sys.stdin.read()

with open(checks_file, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

if not config or 'checks' not in config:
    sys.exit(0)

fired = []

for check in config['checks']:
    trigger = check.get('trigger', {})
    file_match = trigger.get('file_match', '')
    content_new = trigger.get('content_new', '')
    require_all = trigger.get('require_all', True)

    matches = []

    # Test file path pattern
    if file_match:
        if re.search(file_match, file_path):
            matches.append(True)
        else:
            matches.append(False)

    # Test new content pattern
    if content_new:
        if re.search(content_new, new_string):
            matches.append(True)
        else:
            matches.append(False)

    # Skip if no patterns defined
    if not matches:
        continue

    # Evaluate: require_all means AND, else OR
    if require_all:
        triggered = all(matches)
    else:
        triggered = any(matches)

    if triggered:
        fired.append(check)

if fired:
    for check in fired:
        severity = check.get('severity', 'think').upper()
        cid = check.get('id', 'unknown')
        msg = check.get('message', '').strip()
        root = check.get('root_pattern', '')
        icon = 'THINK:' if severity == 'THINK' else 'WARN:'
        print(f'Preflight [{cid}]: {msg}')
        if root:
            print(f'   Root pattern: {root}')
        print()
" "$CHECKS_FILE" "$FILE_PATH" <<< "$NEW_STRING" 2>/dev/null)

if [ -n "$WARNINGS" ]; then
  echo "$WARNINGS"
fi

exit 0
