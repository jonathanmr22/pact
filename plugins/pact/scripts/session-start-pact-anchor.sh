#!/usr/bin/env bash
# ============================================================================
# PACT Session Anchor (SessionStart)
# ============================================================================
# Origin: downstream consumer-project session 2026-05-11. The motivating
# observation: "Some sessions ignore task documentation, others don't."
# The strongest predictor identified during that session was
# WHETHER THE SESSION ANCHORS ON THE DASHBOARD AT MINUTE ZERO. Sessions
# that read HANDOFF + skim in_flight tasks before their first execution
# tend to keep documenting; sessions that dive straight into "fix this"
# stop writing claude_notes.
#
# This hook forces the anchor: surfaces top priorities from HANDOFF.yaml
# and a short list of currently in_flight dashboard tasks. The agent
# sees it as additional context on the first turn and tends to behave
# accordingly.
#
# Non-blocking; just injects context. Cheap (no LLM calls, just file
# reads + a tiny Python summarizer).
# ============================================================================

set -euo pipefail

# Everything's done inside one Python block so we don't fight bash heredoc
# escaping. The script's job is to emit ONE JSON line to stdout in the
# SessionStart hookSpecificOutput shape — Claude Code picks it up as
# additionalContext.
python - <<'PY'
import json, os
from pathlib import Path

root = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
handoff = root / "HANDOFF.yaml"
trees = root / "plans" / "dashboard" / "trees"

parts = ["PACT SESSION ANCHOR — read before your first execution."]
parts.append("")

# Top of HANDOFF.yaml — surface up to 25 non-blank, non-comment lines.
if handoff.is_file():
    try:
        kept = []
        for ln in handoff.read_text(encoding="utf-8", errors="replace").splitlines():
            if not ln.strip(): continue
            if ln.lstrip().startswith("#"): continue
            kept.append(ln)
            if len(kept) >= 25: break
        if kept:
            parts.append("HANDOFF.yaml (top non-blank lines):")
            parts.extend(["  " + l for l in kept])
            parts.append("")
    except Exception as e:
        parts.append(f"(HANDOFF.yaml unreadable: {e})")
else:
    parts.append("(HANDOFF.yaml missing — surface this to the user)")

# In-flight dashboard tasks — walk all stream YAMLs, gather names where
# status == in_flight.
in_flight = []
if trees.is_dir():
    try:
        import yaml
        have_yaml = True
    except ImportError:
        have_yaml = False
    for stream in trees.rglob("streams/*.yaml"):
        if have_yaml:
            try:
                data = yaml.safe_load(stream.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
            if not isinstance(data, dict): continue
            def walk(node):
                if not isinstance(node, dict): return
                name = node.get("name", "")
                if node.get("status") == "in_flight":
                    in_flight.append((stream.name, name[:90]))
                for c in (node.get("children") or []):
                    walk(c)
            root_node = data.get("node")
            if root_node: walk(root_node)
        else:
            # Fallback grep: less precise but works if PyYAML isn't installed.
            try:
                txt = stream.read_text(encoding="utf-8", errors="replace")
                for chunk in txt.split("- name:")[1:]:
                    head = chunk.split("\n", 1)[0].strip().strip('"').strip("'")
                    next_block = chunk.split("- name:", 1)[0]
                    if "status: in_flight" in next_block:
                        in_flight.append((stream.name, head[:90]))
            except Exception:
                continue

if in_flight:
    parts.append(f"In-flight dashboard tasks ({len(in_flight)}):")
    for sname, tname in in_flight[:15]:
        parts.append(f"  - [{sname}] {tname}")
    if len(in_flight) > 15:
        parts.append(f"  ... and {len(in_flight) - 15} more")
else:
    parts.append("(no in_flight dashboard tasks found)")

parts.append("")
parts.append("DISCIPLINE: when you ship work, update the corresponding")
parts.append("plans/dashboard/trees/**/streams/*.yaml task with status,")
parts.append("last_touched, and claude_notes. The post-commit hook nags")
parts.append("if commits land without a dashboard touch.")

msg = "\n".join(parts)
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": msg}}))
PY
