#!/usr/bin/env python3
"""Brag eligibility scoring for cognitive-redirect outcomes.

Per the design doc + user direction: brag citations should be RARE and EARNED,
not routine. Most of Claude's work is decent; only some is exceptional. Brags
should fire only when an outcome scores high on multiple discriminating signals
— not just 'heeded'.

Score components (weighted to total 1.0):
  0.3 — heeded confidence (from detect_self_correction)
  0.3 — user positive reaction in next 3 user msgs (explicit appreciation)
  0.2 — novelty (inverse of prior heeded count for this pattern_id)
  0.1 — severity weight (high/critical patterns merit brags more)
  0.1 — bug avoidance proxy (no bug file with related category in next 24h)

Threshold for brag_eligible: score >= 0.7

This routes ~10-15% of heeded outcomes to brag-eligible status. The other 85%
stay in the outcomes log as routine wins (still useful for telemetry, just
not citation material).

Called by tag_outcomes.py when tagging a new outcome — the brag_eligible flag
+ score components get embedded in the outcome record.

API:
  compute_brag_score(outcome, session_records, history_outcomes, severity_map=None)
    -> {brag_eligible: bool, score: float, components: dict, reasons: list[str]}
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ============================================================================
# User positive-reaction detection
# ============================================================================

# Patterns that indicate the user reacted positively to Claude's behavior
# AFTER a redirect was heeded. These are EXPLICIT recognition signals — not
# acknowledgments like "ok" or "got it" (those are just continuation).
USER_POSITIVE_PATTERNS = [
    # Direct quality praise
    r"\b(great|fantastic|amazing|perfect|excellent|brilliant|exceptional|world.?class)\b",
    r"\b(love (?:this|it|that)|spot.on|nailed it|exactly\s+right)\b",
    r"\b(good (?:catch|move|call|work|job|point|find)|well (?:done|caught|spotted))\b",
    # Direct gratitude
    r"\b(thank|thanks|cheers|appreciate)\b",
    # Standalone enthusiastic affirmation (must be early in message)
    r"^\s*(yes|yeah|yep|yup)[!.]+\s*",
    r"^\s*(perfect|exactly|right)[!.]+\s*",
    # Claude-specific recognition phrasings
    r"\b(damn (?:claude|good)|fantastic work|great work|great job)\b",
    # Mild emoji-positive (not exhaustive but catches common ones)
    r":[)D]\b",
    r"❤️|🙌|✨|🔥|💪|🎯|👏",
]
USER_POSITIVE_RE = re.compile("|".join(f"({p})" for p in USER_POSITIVE_PATTERNS),
                              re.IGNORECASE)

# Patterns that indicate user is NEUTRAL or NEGATIVE — disqualify brag if
# present in same message as positive (mixed signal = not a clean win)
USER_NEGATIVE_PATTERNS = [
    r"\b(no|stop|wait|but|however|actually)\b",
    r"\b(wrong|incorrect|missed|forgot)\b",
    r"\b(why (?:are|did|didn))\b",
]
USER_NEGATIVE_RE = re.compile("|".join(f"({p})" for p in USER_NEGATIVE_PATTERNS),
                              re.IGNORECASE)


def detect_user_positive_reaction(
    session_records: list[dict],
    fire_turn_index: int,
    lookahead_user_messages: int = 3,
) -> dict[str, Any]:
    """Scan the next N user messages after fire_turn_index for explicit
    positive recognition. Returns {present: bool, message: str|None,
    pattern_matched: str|None}.

    Mixed signals (positive AND negative in same message) count as NOT
    positive — those are corrections-with-pleasantries, not clean wins.
    """
    # Find the fire turn in the records
    assistant_turn_count = 0
    fire_record_idx = None
    for i, rec in enumerate(session_records):
        if rec.get("type") == "assistant":
            assistant_turn_count += 1
        if assistant_turn_count - 1 == fire_turn_index and rec.get("type") == "assistant":
            fire_record_idx = i
            # Continue past consecutive assistant records
            while (fire_record_idx + 1 < len(session_records) and
                   session_records[fire_record_idx + 1].get("type") == "assistant"):
                fire_record_idx += 1
            break

    if fire_record_idx is None:
        return {"present": False, "message": None, "pattern_matched": None,
                "reason": "fire_turn_not_found"}

    # Walk forward through user messages
    user_msgs_seen = 0
    for rec in session_records[fire_record_idx + 1:]:
        if rec.get("type") != "user":
            continue
        user_msgs_seen += 1
        msg = rec.get("message", {})
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(b.get("text", "") for b in content
                               if isinstance(b, dict) and b.get("type") == "text")
        if not isinstance(content, str):
            continue
        # Skip tool result messages (they have a structured form)
        if content.startswith("<tool_result"):
            continue

        pos_match = USER_POSITIVE_RE.search(content)
        neg_match = USER_NEGATIVE_RE.search(content)

        if pos_match and not neg_match:
            return {
                "present": True,
                "message": content[:200],
                "pattern_matched": pos_match.group(0),
            }
        if pos_match and neg_match:
            # Mixed signal — disqualify this message but keep looking
            continue

        if user_msgs_seen >= lookahead_user_messages:
            break

    return {"present": False, "message": None, "pattern_matched": None,
            "reason": f"no_positive_in_{lookahead_user_messages}_msgs"}


# ============================================================================
# Novelty detection
# ============================================================================

def compute_novelty(history_outcomes: list[dict], pattern_id: str,
                    current_ts: str) -> tuple[float, int]:
    """Novelty = 1 - (prior_heeded_count / 10), clamped [0, 1].
    First catch is fully novel (1.0). 10+ prior catches = not novel (0.0).
    Returns (novelty_score, prior_heeded_count).
    """
    prior_heeded = 0
    for o in history_outcomes:
        if o.get("redirect_id") != pattern_id:
            continue
        if o.get("outcome") != "heeded":
            continue
        if o.get("ts_tagged", "") >= current_ts:
            continue  # don't count outcomes from later
        prior_heeded += 1
    novelty = max(0.0, 1.0 - (prior_heeded / 10.0))
    return novelty, prior_heeded


# ============================================================================
# Severity weighting
# ============================================================================

SEVERITY_WEIGHTS = {
    "low": 0.0,
    "medium": 0.3,
    "high": 0.7,
    "critical": 1.0,
}


# ============================================================================
# Bug-avoidance proxy
# ============================================================================

def detect_bug_avoidance(category: str, fire_ts: str,
                         bugs_dir: Path | None = None) -> bool:
    """Negative-signal proxy: if NO bug file with a related category was
    created within 24h after the fire, count it as 'bug avoided'.
    Imperfect — many failure modes never produce a bug file regardless —
    but combined with other components it provides modest evidence.

    Returns True if no related bug file appeared (positive signal for brag).
    """
    if bugs_dir is None:
        bugs_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())) / "bugs"
    if not bugs_dir.exists():
        return True  # can't disprove → assume avoidance

    try:
        fire_dt = datetime.fromisoformat(fire_ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return True

    # Categories → potential bug system folders
    category_to_systems = {
        "guess_detection": {"meld", "infra", "scraper"},
        "silent_failure_admission": {"meld", "sync", "infra"},
        "root_cause": {"map", "scraper", "infra"},
        "feature_existence_check": {"infra", "blueprints"},
        "external_assumption": {"infra", "auth"},
        "verify_before_agree": {"map", "infra", "schema"},
        "forward_only": {"map", "infra"},
        "respect_user_constraint": set(),  # no specific bug category
        "stale_state_admission": {"infra", "auth", "sync"},
        "regression_in_flight": {"map", "meld", "infra"},
        "cli_check": set(),
    }
    related = category_to_systems.get(category, set())
    if not related:
        return True

    cutoff = fire_dt + timedelta(hours=24)
    for system in related:
        sys_dir = bugs_dir / system
        if not sys_dir.exists():
            continue
        for bug_file in sys_dir.glob("*.yaml"):
            try:
                mtime = datetime.fromtimestamp(bug_file.stat().st_mtime)
                if fire_dt < mtime < cutoff:
                    return False  # a related bug appeared → not avoided
            except OSError:
                continue
    return True


# ============================================================================
# Main scoring function
# ============================================================================

def compute_brag_score(
    outcome: dict[str, Any],
    session_records: list[dict],
    history_outcomes: list[dict],
    bugs_dir: Path | None = None,
) -> dict[str, Any]:
    """Compute brag eligibility for a single outcome.

    Returns:
        {
          brag_eligible: bool,           # True if score >= 0.7
          score: float,                  # 0.0 - 1.0+
          components: dict,              # per-component breakdown
          reasons: list[str],            # human-readable explanation
        }
    """
    components: dict[str, float] = {}
    reasons: list[str] = []

    # Disqualify ignored outcomes outright
    if outcome.get("outcome") != "heeded":
        return {
            "brag_eligible": False,
            "score": 0.0,
            "components": {"disqualified": 1.0},
            "reasons": ["outcome was not heeded"],
        }

    # 1. Heeded confidence (0.3 weight)
    confidence = float(outcome.get("confidence", 0.0))
    if confidence < 0.7:
        # Hard floor — low-confidence heeded events don't earn brags
        components["heeded_confidence"] = 0.0
        reasons.append(f"low confidence ({confidence:.2f} < 0.7 threshold)")
    else:
        components["heeded_confidence"] = min(confidence, 1.0) * 0.3
        reasons.append(f"high confidence ({confidence:.2f})")

    # 2. User positive reaction (0.3 weight)
    fire_turn = outcome.get("fire_turn_index", 0)
    user_pos = detect_user_positive_reaction(session_records, fire_turn,
                                             lookahead_user_messages=3)
    if user_pos["present"]:
        components["user_positive"] = 0.3
        reasons.append(f"user reacted positively: \"{user_pos['pattern_matched']}\"")
    else:
        components["user_positive"] = 0.0
        reasons.append(f"no user positive reaction ({user_pos['reason']})")

    # 3. Novelty (0.2 weight)
    novelty, prior_count = compute_novelty(
        history_outcomes,
        outcome.get("redirect_id", ""),
        outcome.get("ts_tagged", ""),
    )
    components["novelty"] = novelty * 0.2
    reasons.append(f"novelty {novelty:.2f} (prior heeded count: {prior_count})")

    # 4. Severity weight (0.1 weight)
    # Severity comes from the redirect_id's pattern definition; we proxy
    # via the outcome's category + a default lookup.
    severity = outcome.get("severity")
    if not severity:
        # Heuristic: critical categories get critical, others medium
        critical_categories = {"forward_only", "regression_in_flight"}
        severity = "critical" if outcome.get("category") in critical_categories else "medium"
    sev_weight = SEVERITY_WEIGHTS.get(severity, 0.3)
    components["severity"] = sev_weight * 0.1
    reasons.append(f"severity {severity} (weight {sev_weight:.1f})")

    # 5. Bug avoidance proxy (0.1 weight)
    if detect_bug_avoidance(outcome.get("category", ""),
                            outcome.get("ts_fired", ""),
                            bugs_dir=bugs_dir):
        components["bug_avoidance"] = 0.1
        reasons.append("no related bug file appeared within 24h")
    else:
        components["bug_avoidance"] = 0.0
        reasons.append("related bug file appeared within 24h")

    score = sum(components.values())
    brag_eligible = score >= 0.7

    return {
        "brag_eligible": brag_eligible,
        "score": round(score, 3),
        "components": {k: round(v, 3) for k, v in components.items()},
        "reasons": reasons,
    }


# ============================================================================
# CLI for testing
# ============================================================================

def main():
    import argparse
    import sys
    ap = argparse.ArgumentParser()
    ap.add_argument("outcomes_jsonl",
                    help="Path to cognitive_redirect_outcomes.jsonl")
    ap.add_argument("--session-file", default=None,
                    help="Session JSONL (auto-discover if omitted)")
    ap.add_argument("--rescore", action="store_true",
                    help="Rescore all outcomes in the file (default: just stats)")
    args = ap.parse_args()

    outcomes_path = Path(args.outcomes_jsonl)
    if not outcomes_path.exists():
        print(f"No outcomes file at {outcomes_path}", file=sys.stderr)
        sys.exit(1)

    outcomes: list[dict] = []
    with outcomes_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                outcomes.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue

    if not outcomes:
        print("No outcomes to score", file=sys.stderr)
        sys.exit(0)

    # Stats
    n_heeded = sum(1 for o in outcomes if o.get("outcome") == "heeded")
    n_brag_eligible = sum(1 for o in outcomes if o.get("brag_eligible"))
    print(f"Total outcomes: {len(outcomes)}")
    print(f"  Heeded: {n_heeded}")
    print(f"  Brag-eligible (existing flag): {n_brag_eligible}")

    if args.rescore:
        # Need session file
        from claude_code import find_session_file  # type: ignore
        sf = Path(args.session_file) if args.session_file else find_session_file()
        if not sf:
            print("Need --session-file for rescoring", file=sys.stderr)
            sys.exit(1)
        records = []
        with sf.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    records.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    pass
        # Score each outcome (history_outcomes = outcomes BEFORE this one)
        new_outcomes = []
        for i, o in enumerate(outcomes):
            history = outcomes[:i]
            scoring = compute_brag_score(o, records, history)
            o.update(scoring)
            new_outcomes.append(o)
        # Write back
        with outcomes_path.open("w", encoding="utf-8") as f:
            for o in new_outcomes:
                f.write(json.dumps(o, default=str) + "\n")
        n_brag_after = sum(1 for o in new_outcomes if o.get("brag_eligible"))
        print(f"\nRescored. Brag-eligible after: {n_brag_after}")


if __name__ == "__main__":
    main()
