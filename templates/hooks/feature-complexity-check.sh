#!/usr/bin/env bash
# feature-complexity-check.sh — UserPromptSubmit hook
#
# Scans the user's incoming message for "new feature" trigger phrases. When
# a trigger fires, injects an additionalContext block instructing the agent
# to self-classify complexity (Low/Moderate/High) and score training-data
# confidence (1-10) BEFORE responding. At Moderate+, the agent offers to
# run online research first.
#
# This is a NEW CATEGORY of trigger — all existing cognitive_triggers.yaml
# entries fire PostToolUse on agent output. This hook fires on USER input,
# before the agent responds. It's the first pre-response cognitive redirect
# in PACT.
#
# DESIGN PROPERTIES:
#   - Reuses scan_triggers.py for pattern matching (DRY with PostToolUse hooks)
#   - Per-session dedup (don't fire same category twice within window)
#   - Telemetry to .claude/memory/feature_check_log.jsonl for tuning
#   - Silent on failure (never breaks the conversation)

set -uo pipefail  # NOT -e: tolerate failures gracefully

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Convert Git Bash paths (/c/...) to Windows paths (C:/...) for Python on
# Windows. No-op on Linux/macOS where paths already work.
to_native_path() {
    local p="$1"
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -w "$p" 2>/dev/null | sed 's|\\|/|g' || echo "$p"
    elif [[ "$p" =~ ^/[a-zA-Z]/ ]]; then
        # Git Bash drive-letter conversion fallback
        echo "$p" | sed -E 's|^/([a-zA-Z])/|\U\1:/|'
    else
        echo "$p"
    fi
}

PROJECT_DIR=$(to_native_path "$PROJECT_DIR")
LIB_DIR="$PROJECT_DIR/.claude/hooks/lib"
MEMORY_DIR="$PROJECT_DIR/.claude/memory"
TRIGGERS_FILE="$LIB_DIR/feature_request_triggers.yaml"
SCANNER="$LIB_DIR/scan_triggers.py"
LOG_FILE="$MEMORY_DIR/feature_check_log.jsonl"
DEDUP_FILE="$MEMORY_DIR/feature_check_dedup.json"

[ ! -f "$TRIGGERS_FILE" ] && exit 0
[ ! -f "$SCANNER" ] && exit 0
mkdir -p "$MEMORY_DIR" 2>/dev/null

# Read hook stdin (Claude Code passes JSON with session_id + prompt) into env
# var so the heredoc'd Python can read it back. Quoted heredoc keeps shell
# from expanding the JSON's $-signs.
HOOK_INPUT=$(cat 2>/dev/null || echo '{}')
export HOOK_INPUT_JSON="$HOOK_INPUT"

PYTHONIOENCODING=utf-8 python3 - "$SCANNER" "$TRIGGERS_FILE" "$LOG_FILE" "$DEDUP_FILE" <<'PYEOF'
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

SCANNER, TRIGGERS, LOG, DEDUP = sys.argv[1:5]

def load_module(path, name):
    """Load a Python module from a file path. Registers in sys.modules
    BEFORE exec_module so @dataclass decorators don't fail with the
    'NoneType has no __dict__' bug from dynamically-loaded modules."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        sys.modules.pop(name, None)
        return None

scanner = load_module(SCANNER, "scan_triggers")
if not scanner:
    print("{}")
    sys.exit(0)

# Get the user's prompt from the env-passed hook input
hook_input_raw = os.environ.get("HOOK_INPUT_JSON", "{}")
try:
    hook_input = json.loads(hook_input_raw)
except Exception:
    hook_input = {}

session_id = hook_input.get("session_id", "")
user_prompt = hook_input.get("prompt", "") or hook_input.get("user_message", "") or ""

if not user_prompt or not isinstance(user_prompt, str):
    print("{}")
    sys.exit(0)

# Scan
triggers_data = scanner.load_triggers(TRIGGERS)
matches = scanner.scan(user_prompt, triggers_data=triggers_data)
severity_actions = triggers_data.get("severity_actions", {})
injectable = scanner.filter_by_severity_action(matches, severity_actions)

if not injectable:
    print("{}")
    sys.exit(0)

# Per-session dedup
now = time.time()
dedup_data = {}
try:
    if Path(DEDUP).exists():
        dedup_data = json.loads(Path(DEDUP).read_text(encoding="utf-8") or "{}")
except Exception:
    dedup_data = {}

session_key = session_id or "default"
session_dedup = dedup_data.get(session_key, {})
dedup_windows = triggers_data.get("dedup_window_seconds", {})
default_window = dedup_windows.get("default", 120)

fired = None
for m in injectable:
    window = dedup_windows.get(m.category, default_window)
    last_fired = session_dedup.get(m.category, 0)
    if (now - last_fired) >= window:
        fired = m
        session_dedup[m.category] = now
        break

# Telemetry log (always, even when deduped)
try:
    with open(LOG, "a", encoding="utf-8") as f:
        for m in matches:
            f.write(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "session": session_id,
                "match_id": m.id,
                "category": m.category,
                "severity": m.severity,
                "matched_text": m.matched_text,
                "injected": fired is not None and m.id == fired.id,
            }) + "\n")
except Exception:
    pass

# Persist dedup
try:
    dedup_data[session_key] = session_dedup
    Path(DEDUP).write_text(json.dumps(dedup_data), encoding="utf-8")
except Exception:
    pass

if fired is None:
    print("{}")
    sys.exit(0)

# Emit additionalContext
output = {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": fired.redirection,
    }
}
print(json.dumps(output))
PYEOF
