#!/usr/bin/env python3
"""Outcome-tagging worker for the cognitive-redirect system.

Reads recent un-tagged fires from cognitive_redirect_log.jsonl, calls
detect_self_correction() for each, and appends outcome records to
cognitive_redirect_outcomes.jsonl.

This is the second loop of the cognitive-redirect system (per the design doc):
  Loop 1: Detection — cognitive-redirect.sh fires redirects, logs to fire log
  Loop 2: Outcome  — this script reads pending fires, classifies them, logs outcomes
  Loop 3: Recognition — future redirects cite past success outcomes (brag log)

Loops 1 and 3 happen at fire-time. Loop 2 (this script) runs as a separate
PostToolUse hook so outcome detection has time to observe Claude's next
moves before tagging (we wait until lookahead_turns have elapsed).

USAGE:
  python tag_outcomes.py [--session-id SID] [--lookahead 3]
                         [--log PATH] [--outcomes PATH] [--max-pending 20]

DESIGN:
  - "Pending" = a fire entry in the log whose fire_turn_index is at least
    `lookahead_turns` turns behind the current assistant turn count, AND has
    no corresponding outcome record yet.
  - Outcome records use the fire's req_id as a join key — same id appears in
    fire log + outcome log, easy to correlate.
  - We don't modify the fire log (append-only, immutable). The outcomes log
    IS the source-of-truth for "tagged or not."
  - Fires from prior sessions get skipped — we only tag the current session
    so the lookahead math is consistent.
  - If detect_self_correction returns heeded=None (insufficient data), we
    skip and try again on the NEXT hook fire. Outcome only gets written
    when we have a definitive heeded=True or heeded=False.

OUTPUT FORMAT (cognitive_redirect_outcomes.jsonl, one JSON per line):
  {
    "fire_id": "<req_id from fire log>",
    "session": "<session_id>",
    "ts_fired": "<original fire timestamp>",
    "ts_tagged": "<this script's tag timestamp>",
    "category": "<trigger category>",
    "redirect_id": "<trigger pattern id>",
    "fire_turn_index": <assistant turn # where fire occurred>,
    "tag_turn_index": <assistant turn # at tag time>,
    "outcome": "heeded" | "ignored",
    "signal": "<signal name from detect_self_correction>",
    "confidence": <float 0-1>,
    "evidence": [<list of evidence strings>]
  }
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Find sibling modules
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "harness_adapters"))

try:
    import claude_code as adapter
    from detect_self_correction import detect_self_correction, _records_to_assistant_turns, _load_session_records
    from brag_scoring import compute_brag_score
    _DEPS_AVAILABLE = True
except ImportError as e:
    _DEPS_AVAILABLE = False
    _IMPORT_ERROR = str(e)


def _read_fire_log(log_path: Path) -> list[dict]:
    """Read all fire records from cognitive_redirect_log.jsonl."""
    if not log_path.exists():
        return []
    fires: list[dict] = []
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    fires.append(rec)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return fires


def _read_existing_outcomes(outcomes_path: Path) -> set[str]:
    """Return set of fire_ids that already have outcomes recorded."""
    if not outcomes_path.exists():
        return set()
    tagged: set[str] = set()
    try:
        with outcomes_path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    fire_id = rec.get("fire_id")
                    if fire_id:
                        tagged.add(fire_id)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return tagged


def _append_outcome(outcomes_path: Path, outcome: dict) -> None:
    """Append one outcome record. Failures silent (caller never blocked)."""
    try:
        outcomes_path.parent.mkdir(parents=True, exist_ok=True)
        with outcomes_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(outcome, default=str) + "\n")
    except OSError:
        pass


def find_pending_fires(
    fire_log_path: Path,
    outcomes_path: Path,
    session_id: str,
    current_turn_index: int,
    lookahead_turns: int = 3,
) -> list[dict]:
    """Return fires that are ready to be tagged: same-session, sufficient
    lookahead has elapsed, not yet tagged.
    """
    all_fires = _read_fire_log(fire_log_path)
    already_tagged = _read_existing_outcomes(outcomes_path)

    pending: list[dict] = []
    for f in all_fires:
        # Must be from this session
        if f.get("session") != session_id:
            continue
        # Must have a fire_id (req_id field in the existing log schema)
        fire_id = f.get("req_id")
        if not fire_id:
            continue
        # Skip if already tagged
        if fire_id in already_tagged:
            continue
        # Must have sufficient lookahead — fire must be at least
        # lookahead_turns behind the current turn
        fire_turn = f.get("turn_index")
        if fire_turn is None:
            continue
        if (current_turn_index - fire_turn) < lookahead_turns:
            continue
        # Must have a category (only category-aware patterns can be detected)
        if not f.get("category"):
            continue
        pending.append(f)

    return pending


def tag_one_fire(fire: dict, session_file: Path, lookahead_turns: int,
                  session_records: list[dict] | None = None,
                  history_outcomes: list[dict] | None = None) -> dict | None:
    """Tag a single fire by calling detect_self_correction + compute_brag_score.
    Returns the outcome record (caller appends it) or None if insufficient data.

    For brag scoring, pass session_records (full session JSONL) and
    history_outcomes (outcomes already in the log, for novelty detection).
    If omitted, brag scoring is skipped (brag_eligible=False, score=0).
    """
    fire_turn = fire.get("turn_index")
    category = fire.get("category")
    if fire_turn is None or not category:
        return None

    result = detect_self_correction(
        session_file=session_file,
        fire_turn_index=fire_turn,
        category=category,
        lookahead_turns=lookahead_turns,
    )

    heeded = result.get("heeded")
    if heeded is None:
        # Insufficient data — try again on next hook fire when more turns elapsed
        return None

    outcome = {
        "fire_id": fire.get("req_id"),
        "session": fire.get("session"),
        "ts_fired": fire.get("ts"),
        "ts_tagged": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "category": category,
        "redirect_id": fire.get("match_id") or fire.get("redirect_id"),
        "severity": fire.get("severity"),
        "fire_turn_index": fire_turn,
        "tag_turn_index": fire_turn + lookahead_turns,
        "outcome": "heeded" if heeded else "ignored",
        "signal": result.get("signal"),
        "confidence": result.get("confidence", 0.0),
        "evidence": result.get("evidence", []),
    }

    # Compute brag eligibility if we have the data
    if session_records is not None and history_outcomes is not None:
        brag = compute_brag_score(outcome, session_records, history_outcomes)
        outcome["brag_eligible"] = brag["brag_eligible"]
        outcome["brag_score"] = brag["score"]
        outcome["brag_components"] = brag["components"]
        outcome["brag_reasons"] = brag["reasons"]
    else:
        outcome["brag_eligible"] = False
        outcome["brag_score"] = 0.0

    return outcome


def run(
    session_id: str | None = None,
    fire_log_path: Path | None = None,
    outcomes_path: Path | None = None,
    lookahead_turns: int = 3,
    max_pending: int = 20,
) -> dict[str, int]:
    """Main entry. Returns {tagged: int, skipped_no_data: int, errors: int}."""
    if not _DEPS_AVAILABLE:
        return {"tagged": 0, "skipped_no_data": 0, "errors": 1, "error": _IMPORT_ERROR}

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    fire_log_path = fire_log_path or Path(project_dir) / ".claude" / "memory" / "cognitive_redirect_log.jsonl"
    outcomes_path = outcomes_path or Path(project_dir) / ".claude" / "memory" / "cognitive_redirect_outcomes.jsonl"

    # Find session file
    session_file = adapter.find_session_file(session_id=session_id)
    if not session_file or not session_file.exists():
        return {"tagged": 0, "skipped_no_data": 0, "errors": 1, "error": "session not found"}

    # Load session and compute current assistant turn count
    records = _load_session_records(session_file)
    turns = _records_to_assistant_turns(records)
    current_turn_index = len(turns) - 1  # 0-based

    if not session_id:
        # Try to recover session id from the path filename
        session_id = session_file.stem

    # Find pending fires
    pending = find_pending_fires(
        fire_log_path=fire_log_path,
        outcomes_path=outcomes_path,
        session_id=session_id,
        current_turn_index=current_turn_index,
        lookahead_turns=lookahead_turns,
    )
    pending = pending[:max_pending]  # cap per-run to keep hook fast

    # Load all existing outcomes once for novelty detection
    history_outcomes: list[dict] = []
    if outcomes_path.exists():
        try:
            with outcomes_path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        history_outcomes.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

    tagged = 0
    brag_eligible_count = 0
    skipped_no_data = 0
    for fire in pending:
        outcome = tag_one_fire(
            fire, session_file, lookahead_turns,
            session_records=records,
            history_outcomes=history_outcomes,
        )
        if outcome is None:
            skipped_no_data += 1
            continue
        _append_outcome(outcomes_path, outcome)
        history_outcomes.append(outcome)  # so subsequent novelty calcs see it
        tagged += 1
        if outcome.get("brag_eligible"):
            brag_eligible_count += 1

    return {
        "tagged": tagged,
        "brag_eligible": brag_eligible_count,
        "skipped_no_data": skipped_no_data,
        "errors": 0,
        "current_turn": current_turn_index,
        "pending_count": len(pending),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-id", default=None,
                    help="Session id (defaults to most recent)")
    ap.add_argument("--lookahead", type=int, default=3,
                    help="Turns to wait before tagging (default: 3)")
    ap.add_argument("--log", type=str, default=None,
                    help="Path to cognitive_redirect_log.jsonl")
    ap.add_argument("--outcomes", type=str, default=None,
                    help="Path to cognitive_redirect_outcomes.jsonl")
    ap.add_argument("--max-pending", type=int, default=20,
                    help="Max fires to tag per run (keeps hook fast)")
    args = ap.parse_args()

    result = run(
        session_id=args.session_id,
        fire_log_path=Path(args.log) if args.log else None,
        outcomes_path=Path(args.outcomes) if args.outcomes else None,
        lookahead_turns=args.lookahead,
        max_pending=args.max_pending,
    )
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
