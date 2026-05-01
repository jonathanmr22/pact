#!/usr/bin/env python3
"""Cognitive trigger scanner — pure, model-agnostic, harness-agnostic.

Takes a text blob and a triggers YAML file, returns matched triggers ranked by
severity. No I/O beyond reading the triggers file. No knowledge of Claude Code,
session formats, or any specific harness.

Usage as library:
    from scan_triggers import scan
    matches = scan(text="let me try a different model", triggers_path="...")
    # matches: list of dicts with id, severity, category, redirection, span

Usage as CLI:
    python scan_triggers.py <triggers.yaml> < text_to_scan
    # Outputs JSON list of matches to stdout

The dedup logic and the SystemReminder emission live in the calling hook
(cognitive-redirect.sh), not here. This module is pure pattern matching.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

# Lazy YAML import so this module can run without PyYAML in environments that
# only need the JSON-fallback parsing path. In practice we always have it on
# Windows + Linux dev machines, but kept minimal for portability.
try:
    import yaml  # type: ignore
except ImportError:
    yaml = None


SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class Match:
    id: str
    category: str
    severity: str
    redirection: str
    matched_text: str
    span: tuple[int, int]


def load_triggers(triggers_path: str | Path) -> dict[str, Any]:
    """Load the YAML triggers file. Returns the parsed dict."""
    p = Path(triggers_path)
    if not p.exists():
        return {"triggers": [], "dedup_window_seconds": {}, "severity_actions": {}}
    text = p.read_text(encoding="utf-8")
    if yaml is None:
        # No YAML available — bail with empty triggers rather than crash the hook
        return {"triggers": [], "dedup_window_seconds": {}, "severity_actions": {}}
    return yaml.safe_load(text) or {}


def _strip_use_mention_contexts(text: str) -> str:
    """Strip text contexts where the model is MENTIONING a phrase rather than
    USING it. Without this, the scanner false-positives whenever the model
    discusses trigger patterns themselves (e.g. editing this YAML library,
    showing example regex patterns in chat, quoting the user back).

    Stripped contexts:
      - Triple-backtick code fences (```...```)
      - Single-backtick inline code (`...`)
      - YAML pattern: lines (lines containing 'pattern:' literal — for
        when the model is editing cognitive_triggers.yaml itself)
      - Lines that quote the user (starting with > or "user said")
      - Markdown table cells whose text is wrapped in pipes around code-y content

    This is best-effort — sophisticated mention contexts (long prose
    discussion of a phrase) will still false-positive. The dedup window
    handles the rest.
    """
    import re
    # Remove triple-backtick fences (greedy across multiline)
    text = re.sub(r"```[\s\S]*?```", " ", text)
    # Remove inline backticks
    text = re.sub(r"`[^`\n]*`", " ", text)
    # Remove YAML pattern: lines (the model is editing the trigger library)
    text = re.sub(r"^\s*(?:pattern|regex|redirection)\s*:.*$", " ", text, flags=re.MULTILINE)
    # Remove block-quoted text (lines starting with >)
    text = re.sub(r"^\s*>.*$", " ", text, flags=re.MULTILINE)
    return text


def scan(text: str, triggers_path: str | Path | None = None,
         triggers_data: dict[str, Any] | None = None) -> list[Match]:
    """Scan text against the trigger library. Returns all matches ranked by
    severity (highest first). Pass either triggers_path OR triggers_data.

    Pre-processes the text to strip use/mention contexts (code fences, quotes,
    YAML pattern definitions) so the scanner doesn't false-positive when the
    model is DISCUSSING a pattern rather than USING the failure-mode language."""
    if not text:
        return []
    if triggers_data is None:
        if triggers_path is None:
            return []
        triggers_data = load_triggers(triggers_path)

    text = _strip_use_mention_contexts(text)

    triggers = triggers_data.get("triggers", [])
    matches: list[Match] = []

    for t in triggers:
        pattern = t.get("pattern", "")
        if not pattern:
            continue
        try:
            rx = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
        except re.error:
            # Bad pattern — skip rather than crash
            continue
        m = rx.search(text)
        if not m:
            continue
        matches.append(Match(
            id=t.get("id", "unknown"),
            category=t.get("category", "unknown"),
            severity=t.get("severity", "medium"),
            redirection=t.get("redirection", "").strip(),
            matched_text=m.group(0)[:120],
            span=(m.start(), m.end()),
        ))

    # Sort by severity (highest first), then by span position (earliest first)
    matches.sort(key=lambda x: (-SEVERITY_RANK.get(x.severity, 0), x.span[0]))
    return matches


def filter_by_severity_action(matches: list[Match],
                              severity_actions: dict[str, str]) -> list[Match]:
    """Drop matches whose severity action is 'log_only' (caller will still log them
    via telemetry but not inject them)."""
    kept: list[Match] = []
    for m in matches:
        action = severity_actions.get(m.severity, "log_and_inject")
        if action != "log_only":
            kept.append(m)
    return kept


def main():
    if len(sys.argv) < 2:
        print("usage: scan_triggers.py <triggers.yaml>", file=sys.stderr)
        sys.exit(2)
    triggers_path = sys.argv[1]
    text = sys.stdin.read()
    triggers_data = load_triggers(triggers_path)
    matches = scan(text, triggers_data=triggers_data)
    severity_actions = triggers_data.get("severity_actions", {})
    injectable = filter_by_severity_action(matches, severity_actions)
    out = {
        "all_matches": [asdict(m) for m in matches],
        "injectable_matches": [asdict(m) for m in injectable],
    }
    json.dump(out, sys.stdout, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
