#!/usr/bin/env bash
# skill-injector.sh — UserPromptSubmit hook
#
# Scans the user's incoming message against skills/_SKILL_INDEX.yaml triggers.
# When a skill's trigger phrase appears in the user prompt, injects an
# additionalContext block that:
#   1. Names the matched skill
#   2. Quotes the matched trigger phrase
#   3. Surfaces the skill's one_liner
#   4. Tells Claude to read the full skill file BEFORE starting work
#
# WHY: Skills are useless if Claude never realizes they apply. The skill
# index has perfect trigger metadata but it's only consulted manually. This
# hook makes skill discovery automatic at the moment of need.
#
# DESIGN PROPERTIES:
#   - Substring match (case-insensitive) on each trigger phrase against the
#     full user prompt — same matching strategy as feature-complexity-check
#   - Per-session dedup: don't re-inject the same skill within a 30-min
#     window (Claude was told once already; reminding every turn is noise)
#   - Multiple skills can match a single prompt — all surfaced in one block
#   - Telemetry to .claude/memory/skill_injector_log.jsonl for tuning
#   - Silent on failure (never breaks the conversation)
#
# COMPANION HOOK: skill-followup.sh fires PostToolUse Bash, catching when
# Claude runs a skill's main script but skips its mandatory follow-up step.
# Together they cover before-work awareness + after-action enforcement.

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
SKILL_INDEX="$PROJECT_DIR/skills/_SKILL_INDEX.yaml"
MEMORY_DIR="$PROJECT_DIR/.claude/memory"
LOG_FILE="$MEMORY_DIR/skill_injector_log.jsonl"
DEDUP_FILE="$MEMORY_DIR/skill_injector_dedup.json"

[ ! -f "$SKILL_INDEX" ] && exit 0
mkdir -p "$MEMORY_DIR" 2>/dev/null

# Read hook stdin into env var so the heredoc'd Python can read it back.
HOOK_INPUT=$(cat 2>/dev/null || echo '{}')
export HOOK_INPUT_JSON="$HOOK_INPUT"
export SKILL_INDEX_PATH="$SKILL_INDEX"
export SKILL_LOG_PATH="$LOG_FILE"
export SKILL_DEDUP_PATH="$DEDUP_FILE"

PYTHONIOENCODING=utf-8 python3 <<'PYEOF'
import json
import os
import re
import sys
import time
from pathlib import Path

INDEX_PATH = os.environ.get("SKILL_INDEX_PATH", "")
LOG_PATH = os.environ.get("SKILL_LOG_PATH", "")
DEDUP_PATH = os.environ.get("SKILL_DEDUP_PATH", "")
DEDUP_WINDOW_SEC = 1800  # 30 min — don't re-inject same skill repeatedly

def emit_empty():
    print("{}")
    sys.exit(0)

# Parse hook input
try:
    hook_input = json.loads(os.environ.get("HOOK_INPUT_JSON", "{}"))
except Exception:
    emit_empty()

session_id = hook_input.get("session_id", "default") or "default"
user_prompt = hook_input.get("prompt", "") or hook_input.get("user_message", "") or ""

if not user_prompt or not isinstance(user_prompt, str):
    emit_empty()

prompt_lower = user_prompt.lower()

# Parse skills/_SKILL_INDEX.yaml — try PyYAML, fall back to manual parser
def load_skills(path):
    try:
        import yaml  # type: ignore
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("skills", []) or []
    except Exception:
        # Fallback parser — handles the index's known structure
        skills = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            return []
        # Split into per-skill blocks at "  - name:" lines
        blocks = re.split(r"\n  - name:\s*", text)
        for block in blocks[1:]:
            entry = {}
            entry["name"] = block.split("\n", 1)[0].strip()
            file_m = re.search(r"\n    file:\s*(\S+)", block)
            if file_m:
                entry["file"] = file_m.group(1).strip()
            one_m = re.search(r'\n    one_liner:\s*"?([^"\n]+)"?', block)
            if one_m:
                entry["one_liner"] = one_m.group(1).strip().rstrip('"')
            # Triggers can be inline list ["a", "b"] OR multi-line block
            inline_m = re.search(r"\n    triggers:\s*\[(.*?)\]", block, re.DOTALL)
            triggers = []
            if inline_m:
                triggers = re.findall(r'"([^"]+)"', inline_m.group(1))
            else:
                multi_m = re.search(r"\n    triggers:\n((?:      - .+\n?)+)", block)
                if multi_m:
                    for line in multi_m.group(1).strip().splitlines():
                        v = line.strip().lstrip("-").strip().strip('"')
                        if v:
                            triggers.append(v)
            entry["triggers"] = triggers
            if entry.get("name") and entry.get("triggers"):
                skills.append(entry)
        return skills

skills = load_skills(INDEX_PATH)
if not skills:
    emit_empty()

# Match
matches = []
for skill in skills:
    name = skill.get("name", "")
    triggers = skill.get("triggers", []) or []
    file_path = skill.get("file", f"skills/{name}.yaml")
    one_liner = skill.get("one_liner", "")
    matched_trigger = None
    for trigger in triggers:
        if not isinstance(trigger, str) or not trigger:
            continue
        if trigger.lower() in prompt_lower:
            matched_trigger = trigger
            break
    if matched_trigger:
        matches.append({
            "name": name,
            "file": file_path,
            "one_liner": one_liner,
            "matched_trigger": matched_trigger,
        })

if not matches:
    emit_empty()

# Per-session dedup
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
    last = session_dedup.get(m["name"], 0)
    if (now - last) >= DEDUP_WINDOW_SEC:
        fresh.append(m)
        session_dedup[m["name"]] = now

# Telemetry (always, even when deduped)
try:
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        for m in matches:
            f.write(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "session": session_id,
                "skill": m["name"],
                "matched_trigger": m["matched_trigger"],
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

# Build the additionalContext block
lines = ["[SKILL TRIGGERS MATCHED] One or more reusable workflows apply to this request:"]
lines.append("")
for m in fresh:
    lines.append(f"  - {m['name']}  ({m['file']})")
    lines.append(f"      matched trigger: \"{m['matched_trigger']}\"")
    if m["one_liner"]:
        lines.append(f"      one-liner: {m['one_liner']}")
    lines.append("")
lines.append("REQUIRED ACTION: Read the matched skill file(s) BEFORE starting this work.")
lines.append("Skills encode mandatory steps that prior sessions discovered the hard way —")
lines.append("skipping them is how known failure modes get re-shipped. If a skill's procedure")
lines.append("includes a 'MANDATORY' or 'critique' step, you MUST run it before declaring done.")
lines.append("")
lines.append("If you've already read this skill earlier in this session and you're confident")
lines.append("of the procedure, briefly acknowledge it and proceed.")

output = {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": "\n".join(lines),
    }
}
print(json.dumps(output))
PYEOF
