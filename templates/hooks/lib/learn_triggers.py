#!/usr/bin/env python3
"""Mine existing session JSONLs for trigger-pattern candidates.

Strategy:
  1. Walk all session files under ~/.claude/projects/ (skip subagent dirs).
  2. For each session, find USER messages whose content contains "correction
     language" — phrases that signal the user redirecting/correcting Claude.
  3. Extract the IMMEDIATELY-PRECEDING assistant turn's text + thinking.
  4. Frequency-count short phrases (n-grams) in that pre-correction language.
  5. Filter for phrases that:
       - appear in many distinct correction events (not a one-off quirk)
       - aren't generic English fillers
       - look like failure-mode signals (hedging, guessing, agreement, etc.)
  6. Output top candidates ranked by (event_count, severity_proxy) to
     trigger_candidates.yaml for human review.

This script does NOT auto-add patterns to cognitive_triggers.yaml — it produces
candidates that you (or future Claude) curate. Auto-promotion is a separate
concern (see #3 in the self-improvement plan).

Usage:
  python learn_triggers.py [--max-sessions N] [--min-event-count N]

Output: writes trigger_candidates.yaml in the same directory as the script.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Correction signals — phrases the USER says that indicate they're correcting
# or redirecting Claude. Tuned for high precision (we'd rather miss some
# corrections than mine noise).
# ─────────────────────────────────────────────────────────────────────────────
USER_CORRECTION_PATTERNS = [
    # Explicit "no" / "stop" — strongest signal
    r"\bno[.,!]\s+(no|stop|wait|that.?s|don.?t|you.?re wrong)",
    r"^\s*no[.,!]?\s",
    r"^\s*(stop|wait|hold on)\b",
    r"\b(stop|don.?t)\s+(doing|guessing|assuming)",
    # Direct correction
    r"\byou.?re wrong\b",
    r"\bthat.?s wrong\b",
    r"\bthat.?s not (right|correct|accurate|true)",
    r"\b(actually|but),?\s+(no|that.?s)",
    # Verification demands
    r"\b(verify|check|prove|confirm)\s+(this|that|first|before)",
    r"\bdid you (actually|really|even)\s+",
    r"\b(without|stop) guessing\b",
    r"\bresearch (instead|first|this)",
    # Frustration markers (high-precision)
    r"\bwtf\b",
    r"\b(why are|why didn.?t|why did) you\b",
    r"\byou (still|keep|always) (don.?t|never)",
    # Behavioral redirect
    r"\b(don.?t|stop) (do|doing|making|patching|guessing|assuming)",
    r"\bthink (more|harder|again|carefully)\b",
    r"\b(re)?read (the|that|this) (docs|file|knowledge|claude\.md)",
    # Quality call-outs
    r"\b(this|that) (isn.?t|is not) (working|right|correct|enough)",
    r"\b(too) (slow|big|much|many|aggressive)\b",
    r"\b(same|broken|empty) (response|result|output|pattern)",
]
USER_CORRECTION_RE = re.compile("|".join(f"({p})" for p in USER_CORRECTION_PATTERNS),
                                re.IGNORECASE)

# ─────────────────────────────────────────────────────────────────────────────
# Pre-correction phrase extraction — what Claude tends to say RIGHT BEFORE
# being corrected. We look for short phrases (2-5 words) that:
#   - Use first-person voice ("I", "my", "let me")
#   - Contain hedge/guess/agreement markers
#   - Are short enough to be a recognizable trigger
# ─────────────────────────────────────────────────────────────────────────────

# Generic stop words — phrases containing only these are noise
STOP_PHRASES = {
    "the", "a", "an", "is", "are", "was", "were", "of", "for", "in", "on",
    "at", "to", "from", "by", "with", "this", "that", "these", "those",
    "it", "its", "and", "or", "but", "as", "so", "if", "then", "be", "been",
}

# Phrase patterns we consider "candidate triggers" — must contain at least one
# of these signal words to be worth surfacing
SIGNAL_WORDS = {
    "should", "might", "probably", "likely", "could", "may",
    "let me", "i'll", "i will", "i can", "i think", "i believe",
    "i guess", "i assume", "i suspect", "presumably", "perhaps",
    "actually", "wait", "hmm", "looks like", "seems",
    "you're right", "good point", "i agree", "that's correct",
    "after the", "once the", "when the",
    "workaround", "hack", "patch", "tweak", "just", "simply",
    "easy", "quick", "small", "minor",
    "doesn't exist", "can't find", "don't see",
    "i can't", "cannot", "impossible",
    "should work", "should be", "should fit", "should handle",
    "let me try", "let me see", "let me test", "let me check",
    "going to", "i'll just", "i'll quickly",
}


def extract_phrases(text: str, ngram_range: tuple[int, int] = (2, 6)) -> list[str]:
    """Extract candidate phrases from text — n-grams that contain a signal word."""
    if not text:
        return []
    text_low = text.lower()
    # Tokenize: keep contractions as one word
    words = re.findall(r"[a-z]+(?:[''][a-z]+)?", text_low)
    phrases: list[str] = []
    n_min, n_max = ngram_range
    for n in range(n_min, n_max + 1):
        for i in range(len(words) - n + 1):
            ng = " ".join(words[i:i + n])
            # Must contain a signal word/phrase
            has_signal = any(sig in ng for sig in SIGNAL_WORDS)
            # Must not be ALL stop words
            non_stop = [w for w in words[i:i + n] if w not in STOP_PHRASES]
            if has_signal and len(non_stop) >= 2:
                phrases.append(ng)
    return phrases


# ─────────────────────────────────────────────────────────────────────────────
# Session walker
# ─────────────────────────────────────────────────────────────────────────────

def walk_sessions(projects_root: Path, max_sessions: int | None = None) -> list[Path]:
    """Find session JSONL files (top-level only, skip subagents)."""
    sessions: list[Path] = []
    for proj_dir in projects_root.iterdir():
        if not proj_dir.is_dir():
            continue
        for jsonl in proj_dir.glob("*.jsonl"):  # top-level only
            sessions.append(jsonl)
    sessions.sort(key=lambda p: p.stat().st_mtime, reverse=True)  # newest first
    if max_sessions:
        sessions = sessions[:max_sessions]
    return sessions


def extract_assistant_text(record: dict) -> str:
    """Pull text + thinking from an assistant record."""
    msg = record.get("message", {})
    content = msg.get("content", [])
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype in ("text", "thinking"):
            t = block.get("text") or block.get("thinking") or ""
            if t:
                parts.append(t)
    return "\n".join(parts)


def extract_user_text(record: dict) -> str:
    """Pull user message text."""
    msg = record.get("message", {})
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def mine_session(session_file: Path) -> tuple[list[tuple[str, str]], int, int]:
    """Mine one session. Returns:
       - list of (correction_excerpt, prior_assistant_text) pairs
       - total user messages
       - total correction events found
    """
    pairs: list[tuple[str, str]] = []
    last_assistant_buffer: list[str] = []
    total_user = 0
    total_corrections = 0

    try:
        with session_file.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    rec = json.loads(line.strip())
                except (json.JSONDecodeError, ValueError):
                    continue

                rtype = rec.get("type")
                if rtype == "assistant":
                    txt = extract_assistant_text(rec)
                    if txt:
                        last_assistant_buffer.append(txt)
                elif rtype == "user":
                    total_user += 1
                    user_text = extract_user_text(rec)
                    if not user_text:
                        # Tool result, not a real user message
                        continue
                    m = USER_CORRECTION_RE.search(user_text)
                    if m and last_assistant_buffer:
                        total_corrections += 1
                        excerpt = user_text[max(0, m.start() - 30):m.end() + 60]
                        prior = "\n".join(last_assistant_buffer[-5:])  # last 5 chunks
                        pairs.append((excerpt, prior))
                    last_assistant_buffer = []  # reset for next turn
    except (OSError, IOError):
        pass

    return pairs, total_user, total_corrections


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-sessions", type=int, default=None,
                    help="Cap number of sessions analyzed (default: all)")
    ap.add_argument("--min-event-count", type=int, default=3,
                    help="Phrase must appear in at least N distinct correction events to surface (default: 3)")
    ap.add_argument("--top-n", type=int, default=50,
                    help="How many candidates to surface (default: 50)")
    ap.add_argument("--output", type=str, default=None,
                    help="Output YAML path (default: trigger_candidates.yaml next to this script)")
    args = ap.parse_args()

    projects_root = Path.home() / ".claude" / "projects"
    if not projects_root.exists():
        print(f"No projects directory at {projects_root}", file=sys.stderr)
        sys.exit(1)

    sessions = walk_sessions(projects_root, max_sessions=args.max_sessions)
    print(f"Analyzing {len(sessions)} sessions...", file=sys.stderr)

    # phrase → set of session_files where it appeared in a pre-correction context
    phrase_sessions: defaultdict[str, set[str]] = defaultdict(set)
    # phrase → count of distinct correction events
    phrase_events: Counter[str] = Counter()
    # phrase → sample correction excerpts (for human review)
    phrase_samples: defaultdict[str, list[str]] = defaultdict(list)

    total_sessions_analyzed = 0
    total_correction_events = 0
    total_user_messages = 0

    for sf in sessions:
        try:
            pairs, n_user, n_correct = mine_session(sf)
        except Exception as e:
            print(f"  skip {sf.name}: {type(e).__name__}", file=sys.stderr)
            continue
        total_sessions_analyzed += 1
        total_user_messages += n_user
        total_correction_events += n_correct

        for excerpt, prior_text in pairs:
            phrases_in_prior = set(extract_phrases(prior_text))
            for phrase in phrases_in_prior:
                phrase_sessions[phrase].add(str(sf))
                phrase_events[phrase] += 1
                if len(phrase_samples[phrase]) < 3:
                    phrase_samples[phrase].append(excerpt[:200])

    print(f"\nAnalyzed {total_sessions_analyzed} sessions, {total_user_messages} user messages,",
          file=sys.stderr)
    print(f"found {total_correction_events} correction events.", file=sys.stderr)

    # Filter: must appear in min-event-count or more events
    candidates = [
        (phrase, count, len(phrase_sessions[phrase]))
        for phrase, count in phrase_events.items()
        if count >= args.min_event_count
    ]
    # Rank by (event_count desc, distinct_session_count desc)
    candidates.sort(key=lambda x: (-x[1], -x[2]))
    candidates = candidates[:args.top_n]

    # Output
    out_path = Path(args.output) if args.output else (
        Path(__file__).parent / "trigger_candidates.yaml"
    )

    out_lines = [
        "# Auto-generated trigger candidates from session mining.",
        f"# Generated: {datetime.now().isoformat()}",
        f"# Sessions analyzed: {total_sessions_analyzed}",
        f"# Correction events found: {total_correction_events}",
        f"# Min event count threshold: {args.min_event_count}",
        "#",
        "# Each candidate shows: event_count (times this phrase appeared in a turn",
        "# that was followed by user correction), distinct_sessions (how many",
        "# different sessions exhibited this), and 1-3 sample correction excerpts.",
        "#",
        "# REVIEW WORKFLOW: Read the samples. If the phrase looks like a real",
        "# failure-mode trigger, copy it into cognitive_triggers.yaml as a regex",
        "# pattern with appropriate severity. Delete from this file once promoted.",
        "",
        "candidates:",
    ]
    for phrase, count, n_sessions in candidates:
        out_lines.append(f"  - phrase: {json.dumps(phrase)}")
        out_lines.append(f"    event_count: {count}")
        out_lines.append(f"    distinct_sessions: {n_sessions}")
        out_lines.append(f"    samples:")
        for s in phrase_samples[phrase][:3]:
            out_lines.append(f"      - {json.dumps(s)}")
        out_lines.append("")

    out_path.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"\nWrote {len(candidates)} candidates to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
