#!/usr/bin/env bash
# cognitive-redirect.sh — PostToolUse hook
#
# Reads the most recent assistant turn's reasoning artifacts (extended thinking
# block + pre-tool narration), pattern-matches against the trigger library, and
# emits a SystemReminder via additionalContext when a high-severity match fires.
#
# This is the "thought-level hook" — it watches what the model just SAID and
# injects a redirection before the model's NEXT thought, when the model is in
# a recognizable failure pattern (hedging, workaround language, repeated
# iteration, agreement without verification, etc.).
#
# DESIGN PROPERTIES:
#   - Model-agnostic (works for Claude, would work for GPT/Gemini/local with
#     a different harness adapter)
#   - Per-session dedup (don't fire same category twice within cooldown window)
#   - Telemetry to .claude/memory/cognitive_redirect_log.jsonl for tuning
#   - Silent on failure (never breaks the conversation)

set -uo pipefail  # NOT -e: we tolerate failures gracefully

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Convert Git Bash paths (/c/...) to Windows paths (C:/...) so the Python heredoc
# below can resolve them. Python on Windows treats /c/Users/... as a relative
# path and prepends C:\, breaking module loads.
to_win_path() {
    local p="$1"
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -w "$p" 2>/dev/null | sed 's|\\|/|g' || echo "$p"
    else
        # Fallback: drive-letter conversion for Git Bash style
        echo "$p" | sed -E 's|^/([a-zA-Z])/|\U\1:/|'
    fi
}

PROJECT_DIR=$(to_win_path "$PROJECT_DIR")
HOOKS_DIR="$PROJECT_DIR/.claude/hooks"
LIB_DIR="$HOOKS_DIR/lib"
MEMORY_DIR="$PROJECT_DIR/.claude/memory"
TRIGGERS_FILE="$LIB_DIR/cognitive_triggers.yaml"
ADAPTER="$LIB_DIR/harness_adapters/claude_code.py"
SCANNER="$LIB_DIR/scan_triggers.py"
LOG_FILE="$MEMORY_DIR/cognitive_redirect_log.jsonl"
DEDUP_FILE="$MEMORY_DIR/cognitive_redirect_dedup.json"

# Bail silently if any required component missing (don't break the session)
[ ! -f "$TRIGGERS_FILE" ] && exit 0
[ ! -f "$ADAPTER" ] && exit 0
[ ! -f "$SCANNER" ] && exit 0
mkdir -p "$MEMORY_DIR" 2>/dev/null

# Read the hook's stdin to get session_id (Claude Code passes JSON)
HOOK_INPUT=$(cat 2>/dev/null || echo '{}')
SESSION_ID=$(echo "$HOOK_INPUT" | python3 -c "import json,sys; d=json.load(sys.stdin) if sys.stdin.isatty()==False else {}; print(d.get('session_id',''))" 2>/dev/null || echo "")

# Use Python for everything (regex + YAML + JSON + dedup) — easier than bash
PYTHONIOENCODING=utf-8 python3 - "$ADAPTER" "$SCANNER" "$TRIGGERS_FILE" "$LOG_FILE" "$DEDUP_FILE" "$SESSION_ID" <<'PYEOF'
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ADAPTER, SCANNER, TRIGGERS, LOG, DEDUP, SESSION_ID = sys.argv[1:7]

def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    # Must register in sys.modules BEFORE exec_module, otherwise @dataclass
    # decorators fail with AttributeError because the module isn't visible
    # to dataclasses' internal sys.modules lookup.
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        sys.modules.pop(name, None)
        return None

adapter = load_module(ADAPTER, "claude_code_adapter")
scanner = load_module(SCANNER, "scan_triggers")
if not adapter or not scanner:
    sys.exit(0)

# 1. Get the latest assistant artifacts
artifacts = adapter.get_last_assistant_artifacts(session_id=SESSION_ID or None)
text_to_scan = (artifacts.get("thinking", "") + "\n" + artifacts.get("text", "")).strip()
if not text_to_scan:
    sys.exit(0)

# 2. Scan for triggers
triggers_data = scanner.load_triggers(TRIGGERS)
matches = scanner.scan(text_to_scan, triggers_data=triggers_data)
severity_actions = triggers_data.get("severity_actions", {})
injectable = scanner.filter_by_severity_action(matches, severity_actions)

# 3. Per-session dedup — don't fire same category twice within cooldown
now = time.time()
dedup_data = {}
try:
    if Path(DEDUP).exists():
        dedup_data = json.loads(Path(DEDUP).read_text(encoding="utf-8") or "{}")
except Exception:
    dedup_data = {}

session_dedup = dedup_data.get(SESSION_ID or "default", {})
dedup_windows = triggers_data.get("dedup_window_seconds", {})
default_window = dedup_windows.get("default", 300)

filtered = []
for m in injectable:
    last_fired = session_dedup.get(m.category, 0)
    window = dedup_windows.get(m.category, default_window)
    if (now - last_fired) >= window:
        filtered.append(m)
        session_dedup[m.category] = now

# 4. Always log all matches to telemetry (even ones we don't inject due to dedup)
try:
    with open(LOG, "a", encoding="utf-8") as f:
        for m in matches:
            f.write(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "session": SESSION_ID,
                "turn_index": artifacts.get("turn_index", -1),
                "match_id": m.id,
                "category": m.category,
                "severity": m.severity,
                "matched_text": m.matched_text,
                "injected": m in filtered,
            }) + "\n")
except Exception:
    pass

# 5. Persist dedup state
try:
    dedup_data[SESSION_ID or "default"] = session_dedup
    Path(DEDUP).write_text(json.dumps(dedup_data), encoding="utf-8")
except Exception:
    pass

# 6. Emit hookSpecificOutput if any match passed filtering
#    Pick the highest-severity match (already sorted by scan() ranking)
if filtered:
    top = filtered[0]
    # Build base redirect text
    body = (
        f"{top.redirection}\n\n"
        f"(triggered by: \"{top.matched_text}\" — category={top.category}, severity={top.severity})"
    )
    # Try to append a brag citation if THIS pattern has prior brag-eligible
    # successes. Brag citations are RARE and EARNED — only ~10-15% of heeded
    # outcomes earn the brag_eligible flag. When one exists for the firing
    # pattern, it's worth surfacing. Per the design: presupposed capability
    # via track record is more behaviorally effective than abstract praise.
    try:
        brag_path = Path(LOG).parent / "cognitive_redirect_outcomes.jsonl"
        if brag_path.exists():
            brag_module = load_module(
                str(Path(SCANNER).parent / "inject_brag_citation.py"),
                "inject_brag_citation",
            )
            if brag_module:
                brag_text = brag_module.build_brag_citation(top.id, brag_path)
                if brag_text:
                    body += brag_text
    except Exception:
        pass  # never let brag injection break a redirect

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": body,
        }
    }
    json.dump(out, sys.stdout)
    sys.stdout.write("\n")

sys.exit(0)
PYEOF

exit 0
