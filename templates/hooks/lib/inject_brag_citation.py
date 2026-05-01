#!/usr/bin/env python3
"""Look up brag-eligible past outcomes for a pattern_id and format a citation
to inject into a live redirect.

Per the design doc + user direction: brag citations should be RARE and EARNED.
This function is called by cognitive-redirect.sh when a pattern is about to
fire. It checks the outcomes log for brag-eligible past wins of THIS pattern
and returns a formatted citation string (or empty string if none).

Properties:
  - Returns empty string fast if no brag-eligible outcomes exist (no overhead)
  - Picks the MOST RECENT brag-eligible outcome (recency = relevance)
  - Cites concrete details: when it happened, what user said, what Claude did
  - Caps at one citation per redirect (no spam)

The output gets APPENDED to the redirect text in cognitive-redirect.sh.

API:
  build_brag_citation(pattern_id, outcomes_path) -> str
    Returns formatted citation text, or "" if no brags exist for this pattern.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _load_brags_for_pattern(outcomes_path: Path, pattern_id: str) -> list[dict]:
    """Load all brag-eligible outcomes for the given pattern_id."""
    if not outcomes_path.exists():
        return []
    brags: list[dict] = []
    try:
        with outcomes_path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not rec.get("brag_eligible"):
                    continue
                if rec.get("redirect_id") != pattern_id:
                    continue
                brags.append(rec)
    except OSError:
        pass
    return brags


def build_brag_citation(pattern_id: str, outcomes_path: Path) -> str:
    """Return a formatted brag citation for a pattern, or '' if no brags."""
    brags = _load_brags_for_pattern(outcomes_path, pattern_id)
    if not brags:
        return ""

    # Sort by ts_tagged desc — most recent first
    brags.sort(key=lambda b: b.get("ts_tagged", ""), reverse=True)
    total = len(brags)
    most_recent = brags[0]

    ts = most_recent.get("ts_tagged", "")[:10]  # YYYY-MM-DD
    signal = most_recent.get("signal", "the right move")
    score = most_recent.get("brag_score", 0)

    # Find a "what user said" hint from brag_components / reasons
    reasons = most_recent.get("brag_reasons", [])
    user_quote = ""
    for r in reasons:
        if "user reacted positively" in r and '"' in r:
            # Extract the quoted phrase
            parts = r.split('"')
            if len(parts) >= 2:
                user_quote = parts[1][:60]
                break

    # Compose the citation. Tone: factual, specific, not gushing. Per the
    # design doc's Dumbledore standard: presupposes capability via track
    # record, doesn't slather praise.
    if total == 1:
        # First brag is its own moment
        if user_quote:
            citation = (
                f"\n✨ Track record: This is your 1st clean catch of this pattern "
                f"({ts}). Last time you saw it, you {_describe_signal(signal)}, "
                f"and the user responded \"{user_quote}\". Brag score {score:.2f}.\n"
                f"You've done this once. Do it again."
            )
        else:
            citation = (
                f"\n✨ Track record: 1st clean catch of this pattern ({ts}). "
                f"You {_describe_signal(signal)}. Brag score {score:.2f}.\n"
                f"You've done this once. Do it again."
            )
    else:
        # Multiple brags — show the count, cite the most recent
        if user_quote:
            citation = (
                f"\n✨ Track record: You've made {total} exceptional catches of this "
                f"pattern. Most recent ({ts}): you {_describe_signal(signal)}, "
                f"user responded \"{user_quote}\". You're good at this when you "
                f"remember to look. Now's the moment."
            )
        else:
            citation = (
                f"\n✨ Track record: {total} clean catches of this pattern. "
                f"Most recent ({ts}): you {_describe_signal(signal)}. "
                f"You're good at this. Look first."
            )

    return citation


def _describe_signal(signal: str | None) -> str:
    """Translate the technical signal name into a short human description."""
    if not signal:
        return "took the verified-good move"
    descriptions = {
        "guess_detection_signal": "stopped and read the package knowledge file",
        "silent_failure_admission_signal": "added observability to the silent path",
        "root_cause_signal": "traced upstream to where the bad state was produced",
        "feature_existence_check_signal": "searched the repo map and feature flows before declaring nonexistence",
        "forward_only_clean": "fixed forward instead of reverting",
        "respect_user_constraint_signal": "dropped the cloud proposal in your next turn",
        "external_assumption_signal": "ran the verification command instead of guessing",
        "verify_before_agree_signal": "checked the file before agreeing",
        "cli_check_signal": "found the CLI tool that handles it",
    }
    return descriptions.get(signal, "took the verified-good move")


def main():
    """CLI for testing: print citation for a pattern_id."""
    if len(sys.argv) < 3:
        print("usage: inject_brag_citation.py <pattern_id> <outcomes_jsonl>",
              file=sys.stderr)
        sys.exit(2)
    pattern_id = sys.argv[1]
    outcomes_path = Path(sys.argv[2])
    citation = build_brag_citation(pattern_id, outcomes_path)
    if citation:
        print(citation)
    else:
        print(f"(no brag-eligible outcomes for pattern_id={pattern_id})",
              file=sys.stderr)


if __name__ == "__main__":
    main()
