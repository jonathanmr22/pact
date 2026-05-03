#!/usr/bin/env bash
# skill-followup.sh — PostToolUse Bash hook
#
# After a Bash command runs, scans the command against
# skills/_FOLLOWUP_TRIGGERS.yaml. Each entry whose `when_command_matches`
# regex matches gets its `require` block injected as additionalContext
# on the next turn.
#
# WHY: Skills define mandatory steps but nothing in PACT enforces the
# transition from step N to step N+1. This hook is that enforcement layer
# for steps that follow an automatable trigger command.
#
# COMPANION HOOK: skill-injector.sh (UserPromptSubmit) covers the BEFORE
# layer — surfacing matched skills at turn start so Claude knows the
# procedure exists. This hook is the AFTER layer — reminding mid-procedure.
#
# DESIGN PROPERTIES:
#   - Multiple triggers can match a single command — all fire (composable)
#   - Per-session, per-followup dedup with 10-min window (short enough that
#     iteration loops still fire, long enough to avoid spam)
#   - Telemetry to .claude/memory/skill_followup_log.jsonl
#   - Silent on failure (never breaks the session)

set -uo pipefail  # NOT -e: tolerate failures gracefully

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

to_win_path() {
    local p="$1"
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -w "$p" 2>/dev/null | sed 's|\\|/|g' || echo "$p"
    else
        echo "$p" | sed -E 's|^/([a-zA-Z])/|\U\1:/|'
    fi
}

PROJECT_DIR=$(to_win_path "$PROJECT_DIR")
TRIGGERS="$PROJECT_DIR/skills/_FOLLOWUP_TRIGGERS.yaml"
MEMORY_DIR="$PROJECT_DIR/.claude/memory"
LOG_FILE="$MEMORY_DIR/skill_followup_log.jsonl"
DEDUP_FILE="$MEMORY_DIR/skill_followup_dedup.json"

[ ! -f "$TRIGGERS" ] && exit 0
mkdir -p "$MEMORY_DIR" 2>/dev/null

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')
export HOOK_INPUT_JSON="$HOOK_INPUT"
export TRIGGERS_PATH="$TRIGGERS"
export FOLLOWUP_LOG_PATH="$LOG_FILE"
export FOLLOWUP_DEDUP_PATH="$DEDUP_FILE"

PYTHONIOENCODING=utf-8 python3 <<'PYEOF'
import json
import os
import re
import sys
import time
from pathlib import Path

TRIGGERS_PATH = os.environ.get("TRIGGERS_PATH", "")
LOG_PATH = os.environ.get("FOLLOWUP_LOG_PATH", "")
DEDUP_PATH = os.environ.get("FOLLOWUP_DEDUP_PATH", "")
DEDUP_WINDOW_SEC = 600  # 10 min

def emit_empty():
    print("{}")
    sys.exit(0)

# Parse PostToolUse hook input
try:
    hook_input = json.loads(os.environ.get("HOOK_INPUT_JSON", "{}"))
except Exception:
    emit_empty()

session_id = hook_input.get("session_id", "default") or "default"
tool_name = hook_input.get("tool_name", "")
if tool_name and tool_name != "Bash":
    emit_empty()

tool_input = hook_input.get("tool_input", {}) or {}
command = tool_input.get("command", "") or ""
if not command or not isinstance(command, str):
    emit_empty()

# Load triggers — try PyYAML, fall back to manual parser
def load_triggers(path):
    try:
        import yaml  # type: ignore
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("followups", []) or []
    except Exception:
        # Fallback parser for the known structure
        followups = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            return []
        # Split into per-followup blocks at "  - skill:" lines
        blocks = re.split(r"\n  - skill:\s*", text)
        for block in blocks[1:]:
            entry = {}
            entry["skill"] = block.split("\n", 1)[0].strip()
            for field in ("name", "when_command_matches", "severity"):
                m = re.search(rf"\n    {field}:\s*'?\"?(.*?)\"?'?\s*\n", block)
                if m:
                    entry[field] = m.group(1).strip()
            # require: | block
            req_m = re.search(r"\n    require:\s*\|\s*\n((?:      .*\n?)+)", block)
            if req_m:
                lines = [ln[6:] if ln.startswith("      ") else ln
                         for ln in req_m.group(1).splitlines()]
                entry["require"] = "\n".join(lines).rstrip()
            if entry.get("name") and entry.get("when_command_matches") and entry.get("require"):
                followups.append(entry)
        return followups

followups = load_triggers(TRIGGERS_PATH)
if not followups:
    emit_empty()

# Match
matches = []
for fu in followups:
    pattern = fu.get("when_command_matches", "")
    if not pattern:
        continue
    try:
        if re.search(pattern, command):
            matches.append(fu)
    except re.error:
        continue

if not matches:
    emit_empty()

# Per-session, per-followup dedup
now = time.time()
dedup = {}
try:
    if Path(DEDUP_PATH).exists():
        dedup = json.loads(Path(DEDUP_PATH).read_text(encoding="utf-8") or "{}")
except Exception:
    dedup = {}

session_dedup = dedup.get(session_id, {})
fresh = []
for m in matches:
    key = m["name"]
    last = session_dedup.get(key, 0)
    if (now - last) >= DEDUP_WINDOW_SEC:
        fresh.append(m)
        session_dedup[key] = now

# Telemetry
try:
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        for m in matches:
            f.write(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "session": session_id,
                "skill": m.get("skill", ""),
                "followup": m.get("name", ""),
                "command_head": command[:120],
                "injected": any(fm["name"] == m["name"] for fm in fresh),
            }) + "\n")
except Exception:
    pass

# Persist dedup
try:
    dedup[session_id] = session_dedup
    Path(DEDUP_PATH).write_text(json.dumps(dedup), encoding="utf-8")
except Exception:
    pass

if not fresh:
    emit_empty()

# Build additionalContext — concat all matched followup blocks
parts = ["[SKILL FOLLOWUP TRIGGERED] One or more mandatory steps follow your last Bash call:"]
parts.append("")
for m in fresh:
    severity = m.get("severity", "warn").upper()
    parts.append(f"---  ({severity})  skill: {m.get('skill', '?')}  followup: {m.get('name', '?')}  ---")
    parts.append(m.get("require", "").rstrip())
    parts.append("")

output = {
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": "\n".join(parts),
    }
}
print(json.dumps(output))
PYEOF
