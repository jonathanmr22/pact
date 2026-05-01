#!/usr/bin/env python3
"""Validate cognitive trigger patterns against the existing session corpus.

For each pattern in cognitive_triggers.yaml, measure precision via one of two
methods:

  --method legacy    (single-signal, original implementation)
    precision = true_positives / total_fires
    where true_positive = "user correction within N turns of fire"

  --method weighted  (multi-signal, NEW — DEFAULT)
    weighted_precision = sum(signal_weights) / total_fires
    Signal weights:
      - user correction within 2 turns:    1.0
      - user correction within 5 turns:    0.5  (only if 2-turn didn't already match)
      - Claude self-correction (heeded):   0.8  (via detect_self_correction.py)
      - bug file created within 24h:       1.5
      - file revert / git reset within 5:  1.2  (NEGATIVE — counts AGAINST precision)

    Per pattern fire, we tally the weighted contribution. Precision = sum / fires
    can exceed 1.0 (a fire that produced both a user correction AND a bug file
    is unambiguously a true positive — it earns extra weight). The validator
    does NOT cap per-fire weight.

    NOTE on the negative weight (file revert / git reset): when this fires
    within 5 turns of the trigger, we INTERPRET it as "Claude correctly heeded
    the warning that the previous fix was wrong" — so it counts AS a positive
    signal for the trigger that fired. The weight (1.2) reflects the high
    diagnostic value of an actual revert.

USAGE:
  python validate_triggers.py [--method weighted|legacy]
                              [--triggers PATH] [--max-sessions N]
                              [--min-precision 0.6] [--min-support 5]
                              [--correction-window 2]
                              [--lookahead-turns 3]

OUTPUT:
  - validation_report.yaml with per-pattern stats AND per-pattern signal breakdown
  - Stdout summary: which patterns pass, which fail, why, and recommended action

EVIDENCE PROXY CAVEAT:
  Even with multi-signal weighting, this systematically UNDERESTIMATES true
  precision because some fires produce no observable artifact (Claude reads the
  redirect, internally reorients, but we can't see thinking-only adjustments).
  Mitigation: precision threshold stays conservative (0.6 default).

DECISION TABLE for recommended_action:
  weighted_precision >= 1.0  AND support >= 5   -> promote   (high-value signal)
  weighted_precision >= 0.6  AND support >= 5   -> keep      (passes the gate)
  weighted_precision >= 0.3  AND support >= 5   -> keep_with_override
                                                   (needs human-override rationale)
  weighted_precision <  0.3  OR support <  5    -> demote    (move to candidates)
  weighted_precision <  0.1  AND support >= 20  -> remove    (proven noise)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(1)

# Local imports — keep validator self-contained but reuse the new detector
sys.path.insert(0, str(Path(__file__).parent))
try:
    from detect_self_correction import (
        detect_self_correction,
        _records_to_assistant_turns as _detect_records_to_turns,
        _load_session_records as _detect_load_records,
        CATEGORY_SIGNALS,
    )
    _DETECTOR_AVAILABLE = True
except ImportError:
    _DETECTOR_AVAILABLE = False
    CATEGORY_SIGNALS = {}


# ============================================================================
# Signal weights (weighted method)
# ============================================================================

SIGNAL_WEIGHTS = {
    "user_correction_2turn": 1.0,
    "user_correction_5turn": 0.5,
    "claude_self_correction": 0.8,
    "bug_file_within_24h": 1.5,
    "file_revert_within_5": 1.2,
}


# ============================================================================
# User-correction signals (shared with legacy mode)
# ============================================================================

USER_CORRECTION_PATTERNS = [
    r"\bno[.,!]\s+(no|stop|wait|that.?s|don.?t|you.?re wrong)",
    r"^\s*no[.,!]?\s",
    r"^\s*(stop|wait|hold on)\b",
    r"\b(stop|don.?t)\s+(doing|guessing|assuming)",
    r"\byou.?re wrong\b",
    r"\bthat.?s wrong\b",
    r"\bthat.?s not (right|correct|accurate|true)",
    r"\b(verify|check|prove|confirm)\s+(this|that|first|before)",
    r"\bdid you (actually|really|even)\s+",
    r"\b(without|stop) guessing\b",
    r"\bresearch (instead|first|this)",
    r"\bwtf\b",
    r"\b(why are|why didn.?t|why did) you\b",
    r"\byou (still|keep|always) (don.?t|never)",
    r"\b(don.?t|stop) (do|doing|making|patching|guessing|assuming)",
    r"\bthink (more|harder|again|carefully)\b",
    r"\b(re)?read (the|that|this) (docs|file|knowledge|claude\.md)",
    r"\b(this|that) (isn.?t|is not) (working|right|correct|enough)",
    r"\b(too) (slow|big|much|many|aggressive)\b",
    r"\b(same|broken|empty) (response|result|output|pattern)",
]
USER_CORRECTION_RE = re.compile("|".join(f"({p})" for p in USER_CORRECTION_PATTERNS),
                                re.IGNORECASE)


def _strip_use_mention_contexts(text: str) -> str:
    """Same preprocessing the live scanner applies."""
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"^\s*(?:pattern|regex|redirection)\s*:.*$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*>.*$", " ", text, flags=re.MULTILINE)
    return text


def extract_assistant_text(record: dict) -> str:
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


def session_to_turns(session_file: Path) -> list[dict]:
    """Walk a session JSONL, return ordered list of turns. Each turn:
       {role: 'user'|'assistant', text: str, tool_uses: list[dict],
        ts: str, assistant_turn_idx: int|None}

    Multiple consecutive assistant records get collapsed into one turn.
    `assistant_turn_idx` is the 0-based ordinal among assistant turns only;
    user turns have None. This index aligns with detect_self_correction's
    `fire_turn_index` argument.
    """
    turns: list[dict] = []
    cur_assistant_text: list[str] = []
    cur_assistant_tools: list[dict] = []
    cur_assistant_ts: str = ""
    assistant_turn_counter = 0

    def _flush_assistant():
        nonlocal cur_assistant_text, cur_assistant_tools, cur_assistant_ts, assistant_turn_counter
        if cur_assistant_text or cur_assistant_tools:
            turns.append({
                "role": "assistant",
                "text": "\n".join(cur_assistant_text),
                "tool_uses": list(cur_assistant_tools),
                "ts": cur_assistant_ts,
                "assistant_turn_idx": assistant_turn_counter,
            })
            assistant_turn_counter += 1
            cur_assistant_text = []
            cur_assistant_tools = []
            cur_assistant_ts = ""

    try:
        with session_file.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    rec = json.loads(line.strip())
                except (json.JSONDecodeError, ValueError):
                    continue
                rtype = rec.get("type")
                ts = rec.get("timestamp") or rec.get("ts") or ""
                if rtype == "assistant":
                    if not cur_assistant_ts:
                        cur_assistant_ts = ts
                    txt = extract_assistant_text(rec)
                    if txt:
                        cur_assistant_text.append(txt)
                    msg = rec.get("message", {})
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                cur_assistant_tools.append({
                                    "name": block.get("name", ""),
                                    "input": block.get("input", {}) or {},
                                })
                elif rtype == "user":
                    _flush_assistant()
                    user_text = extract_user_text(rec)
                    if user_text:
                        turns.append({
                            "role": "user",
                            "text": user_text,
                            "tool_uses": [],
                            "ts": ts,
                            "assistant_turn_idx": None,
                        })
    except (OSError, IOError):
        pass

    _flush_assistant()
    return turns


# ============================================================================
# Per-fire signal probes
# ============================================================================

GIT_REVERT_RE = re.compile(
    r"\bgit\s+(checkout\s+(?!-b\b)|reset\s+--hard|restore|revert)\b",
    re.IGNORECASE,
)


def _user_correction_signal(turns: list[dict], fire_pos: int) -> str | None:
    """Walk forward from fire_pos. Return:
       'user_correction_2turn' if first 2 user msgs has correction
       'user_correction_5turn' if 3rd-5th user msg has it (but not first 2)
       None otherwise
    """
    user_count = 0
    for j in range(fire_pos + 1, len(turns)):
        if turns[j]["role"] != "user":
            continue
        user_count += 1
        if USER_CORRECTION_RE.search(turns[j]["text"]):
            if user_count <= 2:
                return "user_correction_2turn"
            elif user_count <= 5:
                return "user_correction_5turn"
            else:
                return None
        if user_count >= 5:
            return None
    return None


def _file_revert_signal(turns: list[dict], fire_pos: int,
                        max_assistant_turns: int = 5) -> bool:
    """True if any Bash command in next N assistant turns matches git revert/reset."""
    seen_assistant = 0
    for j in range(fire_pos + 1, len(turns)):
        if turns[j]["role"] != "assistant":
            continue
        seen_assistant += 1
        if seen_assistant > max_assistant_turns:
            return False
        for tu in turns[j].get("tool_uses", []):
            if tu.get("name") not in ("Bash", "PowerShell"):
                continue
            cmd = (tu.get("input", {}) or {}).get("command", "")
            if GIT_REVERT_RE.search(str(cmd)):
                return True
    return False


def _bug_file_within_24h(session_file: Path, fire_ts: str,
                         repo_root: Path, pattern_id: str,
                         category: str) -> bool:
    """Look in bugs/**/*.yaml for files modified within 24h after fire_ts that
       contain the pattern_id, category, or session id in their content.

       Cheap heuristic: scan filenames first, then grep contents for matches.
    """
    if not fire_ts:
        return False
    try:
        # Truncate microseconds so fromisoformat works on Z-suffixed strings too
        fire_dt = datetime.fromisoformat(fire_ts.replace("Z", "").split(".")[0])
    except ValueError:
        return False
    bugs_root = repo_root / "bugs"
    if not bugs_root.exists():
        return False
    cutoff = fire_dt + timedelta(hours=24)
    for bug_file in bugs_root.rglob("*.yaml"):
        try:
            mtime = datetime.fromtimestamp(bug_file.stat().st_mtime)
        except (OSError, ValueError):
            continue
        if not (fire_dt <= mtime <= cutoff):
            continue
        # Cheap content match: pattern_id or category appearing in file
        try:
            content = bug_file.read_text(encoding="utf-8", errors="replace")
        except (OSError, IOError):
            continue
        if pattern_id and pattern_id in content:
            return True
        if category and category in content:
            return True
    return False


def _claude_self_correction_signal(session_file: Path,
                                   assistant_turn_idx: int,
                                   category: str,
                                   lookahead_turns: int = 3) -> bool:
    """Use detect_self_correction. Returns True if heeded == True."""
    if not _DETECTOR_AVAILABLE:
        return False
    if category not in CATEGORY_SIGNALS:
        return False
    try:
        result = detect_self_correction(
            session_file=session_file,
            fire_turn_index=assistant_turn_idx,
            category=category,
            lookahead_turns=lookahead_turns,
        )
    except Exception:
        return False
    return result.get("heeded") is True


# ============================================================================
# Per-pattern measurement
# ============================================================================

def measure_pattern_legacy(pattern_id: str, regex: str, all_turns: list[list[dict]],
                           correction_window: int = 2) -> dict[str, Any]:
    """Single-signal precision (original implementation)."""
    try:
        rx = re.compile(regex, re.IGNORECASE | re.MULTILINE)
    except re.error as e:
        return {"id": pattern_id, "regex_error": str(e), "total_fires": 0,
                "true_positives": 0, "precision": 0.0, "support": 0}

    total_fires = 0
    true_positives = 0

    for turns in all_turns:
        for i, turn in enumerate(turns):
            if turn["role"] != "assistant":
                continue
            scanned = _strip_use_mention_contexts(turn["text"])
            if not rx.search(scanned):
                continue
            total_fires += 1
            user_msgs_seen = 0
            for j in range(i + 1, len(turns)):
                if turns[j]["role"] != "user":
                    continue
                user_msgs_seen += 1
                if USER_CORRECTION_RE.search(turns[j]["text"]):
                    true_positives += 1
                    break
                if user_msgs_seen >= correction_window:
                    break

    precision = (true_positives / total_fires) if total_fires > 0 else 0.0
    return {
        "id": pattern_id,
        "method": "legacy",
        "total_fires": total_fires,
        "true_positives": true_positives,
        "precision": round(precision, 3),
        "support": total_fires,
    }


def measure_pattern_weighted(pattern_id: str, regex: str, category: str,
                             session_corpus: list[tuple[Path, list[dict]]],
                             repo_root: Path,
                             lookahead_turns: int = 3) -> dict[str, Any]:
    """Multi-signal weighted precision."""
    try:
        rx = re.compile(regex, re.IGNORECASE | re.MULTILINE)
    except re.error as e:
        return {
            "id": pattern_id, "category": category, "regex_error": str(e),
            "total_fires": 0, "weighted_score": 0.0, "weighted_precision": 0.0,
            "support": 0, "signal_breakdown": {},
        }

    total_fires = 0
    weighted_score = 0.0
    signal_breakdown = defaultdict(int)

    for session_file, turns in session_corpus:
        for i, turn in enumerate(turns):
            if turn["role"] != "assistant":
                continue
            scanned = _strip_use_mention_contexts(turn["text"])
            if not rx.search(scanned):
                continue
            total_fires += 1

            # --- User correction (2-turn or 5-turn — mutually exclusive)
            uc_signal = _user_correction_signal(turns, i)
            if uc_signal:
                weighted_score += SIGNAL_WEIGHTS[uc_signal]
                signal_breakdown[uc_signal] += 1

            # --- Claude self-correction (via detect_self_correction)
            assistant_idx = turn.get("assistant_turn_idx")
            if assistant_idx is not None and category in CATEGORY_SIGNALS:
                if _claude_self_correction_signal(
                    session_file, assistant_idx, category, lookahead_turns
                ):
                    weighted_score += SIGNAL_WEIGHTS["claude_self_correction"]
                    signal_breakdown["claude_self_correction"] += 1

            # --- Bug file within 24h
            if _bug_file_within_24h(session_file, turn.get("ts", ""),
                                    repo_root, pattern_id, category):
                weighted_score += SIGNAL_WEIGHTS["bug_file_within_24h"]
                signal_breakdown["bug_file_within_24h"] += 1

            # --- File revert / git reset within 5 assistant turns
            if _file_revert_signal(turns, i, max_assistant_turns=5):
                weighted_score += SIGNAL_WEIGHTS["file_revert_within_5"]
                signal_breakdown["file_revert_within_5"] += 1

    weighted_precision = (weighted_score / total_fires) if total_fires > 0 else 0.0
    return {
        "id": pattern_id,
        "category": category,
        "method": "weighted",
        "total_fires": total_fires,
        "weighted_score": round(weighted_score, 3),
        "weighted_precision": round(weighted_precision, 3),
        "support": total_fires,
        "signal_breakdown": dict(signal_breakdown),
    }


def _recommend_action(weighted_precision: float, support: int,
                      min_precision: float, min_support: int) -> str:
    if weighted_precision < 0.1 and support >= 20:
        return "remove"
    if weighted_precision < 0.3 or support < min_support:
        return "demote"
    if weighted_precision >= 1.0 and support >= min_support:
        return "promote"
    if weighted_precision >= min_precision and support >= min_support:
        return "keep"
    return "keep_with_override"  # 0.3 <= prec < min_precision, support adequate


# ============================================================================
# Main
# ============================================================================

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--method", choices=["weighted", "legacy"], default="weighted",
                    help="Precision-measurement method (default: weighted)")
    ap.add_argument("--triggers", default=str(Path(__file__).parent / "cognitive_triggers.yaml"))
    ap.add_argument("--max-sessions", type=int, default=50)
    ap.add_argument("--min-precision", type=float, default=0.6)
    ap.add_argument("--min-support", type=int, default=5)
    ap.add_argument("--correction-window", type=int, default=2,
                    help="Legacy mode only: user-correction lookahead window")
    ap.add_argument("--lookahead-turns", type=int, default=3,
                    help="Weighted mode only: assistant-turn lookahead for self-correction detection")
    ap.add_argument("--repo-root", default=str(Path(__file__).parent.parent.parent.parent),
                    help="Repo root for bugs/ directory scan (default: 3 levels up from this script)")
    ap.add_argument("--report-out", default=str(Path(__file__).parent / "validation_report.yaml"))
    args = ap.parse_args()

    triggers_path = Path(args.triggers)
    if not triggers_path.exists():
        print(f"No triggers file at {triggers_path}", file=sys.stderr)
        sys.exit(1)
    triggers_data = yaml.safe_load(triggers_path.read_text(encoding="utf-8"))
    patterns = triggers_data.get("triggers", [])
    if not patterns:
        print("No patterns to validate", file=sys.stderr)
        sys.exit(1)

    repo_root = Path(args.repo_root).resolve()

    print(f"Method: {args.method}", file=sys.stderr)
    print(f"Validating {len(patterns)} patterns against session corpus...", file=sys.stderr)
    print(f"Repo root for bug-file scan: {repo_root}", file=sys.stderr)

    # Load session corpus
    projects_root = Path.home() / ".claude" / "projects"
    sessions: list[Path] = []
    if projects_root.exists():
        for proj_dir in projects_root.iterdir():
            if not proj_dir.is_dir():
                continue
            for jsonl in proj_dir.glob("*.jsonl"):
                sessions.append(jsonl)
    sessions.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    sessions = sessions[:args.max_sessions]
    print(f"Loading {len(sessions)} sessions into memory...", file=sys.stderr)

    session_corpus: list[tuple[Path, list[dict]]] = []
    for sf in sessions:
        try:
            turns = session_to_turns(sf)
            if turns:
                session_corpus.append((sf, turns))
        except Exception as e:
            print(f"  skip {sf.name}: {e}", file=sys.stderr)

    total_assistant_turns = sum(
        sum(1 for t in turns if t["role"] == "assistant")
        for _, turns in session_corpus
    )
    print(f"Corpus loaded: {len(session_corpus)} sessions, "
          f"{total_assistant_turns} assistant turns total\n", file=sys.stderr)

    # Validate each pattern
    results: list[dict] = []
    for p in patterns:
        pid = p.get("id", "unknown")
        regex = p.get("pattern", "")
        category = p.get("category", "unknown")
        if args.method == "legacy":
            result = measure_pattern_legacy(
                pattern_id=pid,
                regex=regex,
                all_turns=[turns for _, turns in session_corpus],
                correction_window=args.correction_window,
            )
            result["category"] = category
            result["passes_gate"] = (
                result["precision"] >= args.min_precision
                and result["support"] >= args.min_support
            )
            result["recommended_action"] = _recommend_action(
                result["precision"], result["support"],
                args.min_precision, args.min_support,
            )
        else:
            result = measure_pattern_weighted(
                pattern_id=pid,
                regex=regex,
                category=category,
                session_corpus=session_corpus,
                repo_root=repo_root,
                lookahead_turns=args.lookahead_turns,
            )
            result["passes_gate"] = (
                result["weighted_precision"] >= args.min_precision
                and result["support"] >= args.min_support
            )
            result["recommended_action"] = _recommend_action(
                result["weighted_precision"], result["support"],
                args.min_precision, args.min_support,
            )
        result["severity"] = p.get("severity", "medium")
        results.append(result)

    # Sort by passes_gate desc, then precision desc
    def _prec(r: dict) -> float:
        return r.get("weighted_precision", r.get("precision", 0.0))
    results.sort(key=lambda r: (-int(r["passes_gate"]), -_prec(r), -r["support"]))

    # Write report
    report = {
        "generated": datetime.now().isoformat(),
        "method": args.method,
        "corpus": {
            "sessions": len(session_corpus),
            "assistant_turns": total_assistant_turns,
        },
        "thresholds": {
            "min_precision": args.min_precision,
            "min_support": args.min_support,
            "correction_window": args.correction_window,
            "lookahead_turns": args.lookahead_turns,
        },
        "signal_weights": SIGNAL_WEIGHTS if args.method == "weighted" else None,
        "results": results,
    }
    Path(args.report_out).write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")

    # Stdout summary
    passes = [r for r in results if r["passes_gate"]]
    fails = [r for r in results if not r["passes_gate"]]
    print(f"=" * 78)
    print(f"VALIDATION RESULTS ({args.method}) — {len(passes)} pass / {len(fails)} fail "
          f"(of {len(results)})")
    print(f"=" * 78)
    print(f"Thresholds: precision >= {args.min_precision}, support >= {args.min_support}")
    print(f"Corpus: {len(session_corpus)} sessions, {total_assistant_turns} assistant turns")
    print()

    if args.method == "weighted":
        print("PASSED — keep in live trigger library:")
        print(f"{'pattern_id':38s} {'sev':8s} {'fires':>6s} {'wScore':>7s} {'wPrec':>6s} action")
        print("-" * 78)
        for r in passes:
            print(f"{r['id']:38s} {r['severity']:8s} {r['support']:>6d} "
                  f"{r['weighted_score']:>7.2f} {r['weighted_precision']:>6.2f} "
                  f"{r['recommended_action']}")
        print()
        print("FAILED — review:")
        print(f"{'pattern_id':38s} {'sev':8s} {'fires':>6s} {'wScore':>7s} {'wPrec':>6s} action")
        print("-" * 78)
        for r in fails:
            print(f"{r['id']:38s} {r['severity']:8s} {r['support']:>6d} "
                  f"{r['weighted_score']:>7.2f} {r['weighted_precision']:>6.2f} "
                  f"{r['recommended_action']}")
        print()
        print("Per-pattern signal breakdown:")
        for r in results:
            sb = r.get("signal_breakdown", {})
            if not sb:
                continue
            parts = ", ".join(f"{k}={v}" for k, v in sb.items())
            print(f"  {r['id']:38s}  {parts}")
    else:
        print("PASSED:")
        print(f"{'pattern_id':40s} {'sev':8s} {'fires':>6s} {'TPs':>5s} {'prec':>6s}")
        print("-" * 70)
        for r in passes:
            print(f"{r['id']:40s} {r['severity']:8s} {r['support']:>6d} "
                  f"{r['true_positives']:>5d} {r['precision']:>6.2f}")
        print()
        print("FAILED:")
        for r in fails:
            print(f"{r['id']:40s} {r['severity']:8s} {r['support']:>6d} "
                  f"{r['true_positives']:>5d} {r['precision']:>6.2f}")

    print(f"\nFull report: {args.report_out}")


if __name__ == "__main__":
    main()
