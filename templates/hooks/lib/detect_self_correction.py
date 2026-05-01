#!/usr/bin/env python3
"""Detect category-specific Claude self-correction signals after a redirect fires.

Given a Claude Code session JSONL, the assistant-turn index where a cognitive
redirect fired, and the trigger category, scan the next N assistant turns for
behaviors that indicate Claude HEEDED the redirect.

This is the "Claude self-correction" signal source for the weighted-precision
validator (validate_triggers.py v2). Per COGNITIVE_REDIRECT_DESIGN.md, "user
correction within N turns" systematically UNDERESTIMATES precision because
Claude often self-corrects after a redirect without explicit user pushback. By
looking at what Claude DID — not just what the user said — we can recover that
hidden positive signal.

Each category maps to a specific set of self-correction behaviors:

| Category                  | Signal (next 1-3 assistant turns)                     |
|---------------------------|-------------------------------------------------------|
| guess_detection           | Read knowledge/packages/*.yaml OR WebFetch/WebSearch  |
|                           | OR context7 / pact-researcher                         |
| silent_failure_admission  | Edit/Write that adds AppLogger.error/warn, print(,    |
|                           | console.error, try/catch, or typed Result return      |
| root_cause                | Tool-use sequence going UPSTREAM: Read of a file path |
|                           | mentioned in trigger context, OR opens a bugs/*.yaml  |
| feature_existence_check   | Read of knowledge/repo_map.md OR feature_flows/*.yaml |
|                           | OR multiple Glob/Grep calls (3+) before next code     |
|                           | change                                                |
| forward_only              | NEGATIVE — does NOT run git checkout / git reset      |
|                           | --hard / git restore in next 3 turns                  |
| respect_user_constraint   | Drops the cloud/API mention from next assistant turn  |
|                           | text (text doesn't contain cloud/api/hosted)          |
| external_assumption       | Bash runs verification: ollama ps, nvidia-smi, curl,  |
|                           | ps, --version, health, etc.                           |
| verify_before_agree       | Read of a file referenced in user's prior message OR  |
|                           | Bash query before next assertion                      |

USAGE:
  python detect_self_correction.py <session_file> <fire_turn_index> <category>

API:
  detect_self_correction(session_file, fire_turn_index, category, lookahead_turns=3)
    -> {heeded: bool|None, signal: str|None, confidence: float, evidence: list}

  heeded == None means insufficient data (session ends before lookahead, or
  category not in mapping table) — caller should NOT treat that as positive
  OR negative evidence.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


# ============================================================================
# Category -> self-correction signal mapping
#
# Each entry has:
#   tools: list of (tool_name, input_predicate) pairs to look for
#   text:  list of compiled regexes to look for in assistant text
#   bash:  list of regexes to look for in Bash commands (input.command)
#   negative: if True, signal is ABSENCE of patterns — heeded means NOT seen
#   confidence: base confidence for this category's strongest signal
# ============================================================================

# Predicates take the tool's `input` dict and return True if it matches
def _read_path_re(pattern: str):
    """Builder for Read-tool predicates that match file_path against a regex."""
    rx = re.compile(pattern, re.IGNORECASE)
    def pred(input_dict: dict) -> bool:
        path = input_dict.get("file_path") or input_dict.get("path") or ""
        return bool(rx.search(str(path)))
    return pred


def _bash_command_re(pattern: str):
    rx = re.compile(pattern, re.IGNORECASE)
    def pred(input_dict: dict) -> bool:
        cmd = input_dict.get("command") or ""
        return bool(rx.search(str(cmd)))
    return pred


def _any_input(input_dict: dict) -> bool:
    return True


CATEGORY_SIGNALS: dict[str, dict[str, Any]] = {
    "guess_detection": {
        "description": "Looked up authoritative source instead of guessing again",
        "tools": [
            ("Read", _read_path_re(r"knowledge[/\\]packages[/\\].*\.ya?ml")),
            ("WebFetch", _any_input),
            ("WebSearch", _any_input),
            ("mcp__context7__query-docs", _any_input),
            ("mcp__context7__resolve-library-id", _any_input),
        ],
        "bash": [
            re.compile(r"\bpact-researcher\b", re.IGNORECASE),
            re.compile(r"\bpact-delegate\b.*\b(researcher|verify)\b", re.IGNORECASE),
        ],
        "text": [],
        "negative": False,
        "confidence": 0.85,
    },

    "silent_failure_admission": {
        "description": "Added observability / typed-error handling instead of silent return",
        "tools": [],
        "edits": [
            # Look in Edit/Write new_string / content for added observability
            re.compile(r"AppLogger\.(error|warn|warning)\s*\(", re.IGNORECASE),
            re.compile(r"console\.(error|warn)\s*\(", re.IGNORECASE),
            re.compile(r"\bprint\s*\(", re.IGNORECASE),  # Python diagnostic prints
            re.compile(r"\btry\s*[\{:]", re.IGNORECASE),
            re.compile(r"\bcatch\s*\(", re.IGNORECASE),
            re.compile(r"\bexcept\s+\w*Exception\b", re.IGNORECASE),
            re.compile(r"\bResult<", re.IGNORECASE),  # typed Result return
            re.compile(r"\breturn\s+(?:Err|Failure|Result\.)", re.IGNORECASE),
            re.compile(r"\bSentry\.captureException\b", re.IGNORECASE),
        ],
        "bash": [],
        "text": [],
        "negative": False,
        "confidence": 0.80,
    },

    "root_cause": {
        "description": "Walked upstream to where bad state is produced (Read or bug file)",
        "tools": [
            ("Read", _read_path_re(r"bugs[/\\].*\.ya?ml$")),
        ],
        # Also: any Read tool counts (we need to compare to context — handled below)
        "bash": [],
        "text": [],
        "negative": False,
        "confidence": 0.75,
        "needs_context_paths": True,  # also matches Reads of paths cited in trigger context
    },

    "feature_existence_check": {
        "description": "Verified feature existence via flows/repo_map/multiple searches",
        "tools": [
            ("Read", _read_path_re(r"knowledge[/\\]repo_map\.md$")),
            ("Read", _read_path_re(r"feature_flows[/\\].*\.ya?ml$")),
            ("Read", _read_path_re(r"repo_map\.json$")),
        ],
        "bash": [],
        "text": [],
        "negative": False,
        "confidence": 0.80,
        "min_search_calls": 3,  # 3+ Glob/Grep calls also counts
    },

    "forward_only": {
        "description": "Did NOT revert / git reset / git checkout old version",
        "tools": [],
        "bash": [
            re.compile(r"\bgit\s+checkout\s+(?!-b\b)", re.IGNORECASE),
            re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE),
            re.compile(r"\bgit\s+restore\b", re.IGNORECASE),
            re.compile(r"\bgit\s+revert\b", re.IGNORECASE),
        ],
        "text": [],
        "negative": True,  # heeded = absence of these
        "confidence": 0.70,
    },

    "respect_user_constraint": {
        "description": "Stopped mentioning the vetoed cloud/API option in next turn",
        "tools": [],
        "bash": [],
        "text_negative": [
            re.compile(r"\b(cloud|hosted|api\s+fallback|backup\s+api)\b", re.IGNORECASE),
            re.compile(r"\b(claude\s+api|openai\s+api|anthropic\s+api)\b", re.IGNORECASE),
        ],
        "text": [],
        "negative": True,
        "confidence": 0.65,
    },

    "external_assumption": {
        "description": "Verified external service state via Bash before proceeding",
        "tools": [],
        "bash": [
            re.compile(r"\bollama\s+(ps|list|show)\b", re.IGNORECASE),
            re.compile(r"\bnvidia-smi\b", re.IGNORECASE),
            re.compile(r"\bcurl\b.*\b(health|status|version|/api/)", re.IGNORECASE),
            re.compile(r"\bps\s+(aux|-ef|-A)\b"),  # `ps` listing
            re.compile(r"\bGet-Process\b", re.IGNORECASE),
            re.compile(r"--version\b"),
            re.compile(r"\b(systemctl|service)\s+status\b", re.IGNORECASE),
            re.compile(r"\bdocker\s+(ps|inspect|logs)\b", re.IGNORECASE),
            re.compile(r"\bnetstat\b|\bss\s+-"),
        ],
        "text": [],
        "negative": False,
        "confidence": 0.85,
    },

    "verify_before_agree": {
        "description": "Read a file or ran a query before next assertion",
        "tools": [
            ("Read", _any_input),
            ("Grep", _any_input),
            ("Glob", _any_input),
        ],
        "bash": [
            re.compile(r"\b(grep|rg|cat|head|tail|jq|yq|ls)\b", re.IGNORECASE),
            re.compile(r"\bgit\s+(log|show|blame|diff)\b", re.IGNORECASE),
        ],
        "text": [],
        "negative": False,
        "confidence": 0.70,
        "needs_user_context": True,  # ideally: Read a file the user mentioned
    },
}


# ============================================================================
# Session parsing
# ============================================================================

def _load_session_records(session_file: Path) -> list[dict]:
    """Load all JSONL records from a session file."""
    records: list[dict] = []
    try:
        with session_file.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except (OSError, IOError):
        pass
    return records


def _records_to_assistant_turns(records: list[dict]) -> list[dict]:
    """Collapse consecutive assistant records into ordered assistant turns.

    Returns list of dicts:
      {
        "turn_index": int,           # 0-based assistant turn ordinal
        "text": str,                 # joined text+thinking from all blocks in turn
        "tool_uses": [{name, input}],
        "preceding_user_text": str,  # the user message that triggered this turn
      }
    """
    turns: list[dict] = []
    cur_text_parts: list[str] = []
    cur_tool_uses: list[dict] = []
    pending_user_text = ""
    last_user_text_for_next_assistant = ""

    def _flush():
        if cur_text_parts or cur_tool_uses:
            turns.append({
                "turn_index": len(turns),
                "text": "\n".join(cur_text_parts),
                "tool_uses": list(cur_tool_uses),
                "preceding_user_text": pending_user_text,
            })

    for rec in records:
        rtype = rec.get("type")
        if rtype == "assistant":
            msg = rec.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, str):
                cur_text_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype in ("text", "thinking"):
                        t = block.get("text") or block.get("thinking") or ""
                        if t:
                            cur_text_parts.append(t)
                    elif btype == "tool_use":
                        cur_tool_uses.append({
                            "name": block.get("name", ""),
                            "input": block.get("input", {}) or {},
                        })
        elif rtype == "user":
            # Flush current assistant turn (if any), then capture user text
            if cur_text_parts or cur_tool_uses:
                # Use most recent user text as the trigger for this turn
                turns_pending_user = pending_user_text
                turns.append({
                    "turn_index": len(turns),
                    "text": "\n".join(cur_text_parts),
                    "tool_uses": list(cur_tool_uses),
                    "preceding_user_text": turns_pending_user,
                })
                cur_text_parts = []
                cur_tool_uses = []
            # Extract user text (skip pure tool_result records)
            msg = rec.get("message", {})
            content = msg.get("content", "")
            user_text = ""
            if isinstance(content, str):
                user_text = content
            elif isinstance(content, list):
                parts: list[str] = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                user_text = "\n".join(parts)
            # Only update pending_user_text if this is real user prose
            # (tool_result records have no text blocks)
            if user_text.strip():
                pending_user_text = user_text

    # Final flush
    if cur_text_parts or cur_tool_uses:
        turns.append({
            "turn_index": len(turns),
            "text": "\n".join(cur_text_parts),
            "tool_uses": list(cur_tool_uses),
            "preceding_user_text": pending_user_text,
        })

    return turns


# ============================================================================
# Signal detection per category
# ============================================================================

def _extract_paths_from_text(text: str) -> set[str]:
    """Pull file-path-like substrings out of arbitrary text.

    Used for root_cause + verify_before_agree to know what files were
    referenced in the trigger context / preceding user message, so we can
    detect whether Claude went and Read those specific files.
    """
    if not text:
        return set()
    # Match windows paths, unix paths, and typical relative lib/foo/bar.dart strings
    pattern = re.compile(
        r"(?:[A-Za-z]:[\\/])?(?:[\w.\-]+[\\/])+[\w.\-]+\.\w+"
    )
    return set(pattern.findall(text))


def _scan_edits_for_observability(tool_uses: list[dict],
                                  edit_patterns: list[re.Pattern]) -> list[str]:
    """Scan Edit/Write tool_uses for added observability patterns."""
    found: list[str] = []
    for tu in tool_uses:
        name = tu.get("name", "")
        if name not in ("Edit", "Write", "MultiEdit"):
            continue
        inp = tu.get("input", {}) or {}
        # Edit: new_string. Write: content. MultiEdit: edits[].new_string
        candidates: list[str] = []
        if "new_string" in inp:
            candidates.append(str(inp.get("new_string", "")))
        if "content" in inp:
            candidates.append(str(inp.get("content", "")))
        edits_list = inp.get("edits")
        if isinstance(edits_list, list):
            for e in edits_list:
                if isinstance(e, dict):
                    candidates.append(str(e.get("new_string", "")))
        joined = "\n".join(candidates)
        for rx in edit_patterns:
            m = rx.search(joined)
            if m:
                found.append(f"Edit/Write added: {m.group(0)[:60]}")
    return found


def _count_search_tools(tool_uses: list[dict]) -> int:
    return sum(1 for tu in tool_uses if tu.get("name") in ("Glob", "Grep"))


def _scan_tool_signals(tool_uses: list[dict],
                       tool_predicates: list[tuple[str, Any]]) -> list[str]:
    """Return list of evidence strings for matched tool signals."""
    found: list[str] = []
    for tu in tool_uses:
        name = tu.get("name", "")
        inp = tu.get("input", {}) or {}
        for want_name, pred in tool_predicates:
            if name != want_name:
                continue
            try:
                if pred(inp):
                    # Surface a useful identifier
                    ident = (inp.get("file_path") or inp.get("path")
                             or inp.get("query") or inp.get("url")
                             or "")
                    found.append(f"{name}({str(ident)[:80]})")
                    break
            except Exception:
                continue
    return found


def _scan_bash_signals(tool_uses: list[dict],
                       bash_patterns: list[re.Pattern]) -> list[str]:
    found: list[str] = []
    for tu in tool_uses:
        if tu.get("name") not in ("Bash", "PowerShell"):
            continue
        cmd = (tu.get("input", {}) or {}).get("command", "")
        for rx in bash_patterns:
            m = rx.search(str(cmd))
            if m:
                found.append(f"Bash: {m.group(0)[:60]}")
                break
    return found


def _scan_text_negative(text: str, negative_patterns: list[re.Pattern]) -> list[str]:
    """Return list of patterns that DID match (presence = NOT heeded for negative case)."""
    found: list[str] = []
    for rx in negative_patterns:
        m = rx.search(text or "")
        if m:
            found.append(m.group(0)[:60])
    return found


# ============================================================================
# Public API
# ============================================================================

def detect_self_correction(
    session_file: Path,
    fire_turn_index: int,
    category: str,
    lookahead_turns: int = 3,
) -> dict[str, Any]:
    """Scan next N assistant turns for category-specific self-correction.

    Args:
        session_file: Path to Claude Code session JSONL.
        fire_turn_index: 0-based assistant-turn index where the redirect fired.
            (i.e. the turn whose text triggered the regex match.)
        category: One of CATEGORY_SIGNALS keys.
        lookahead_turns: How many subsequent assistant turns to inspect.

    Returns dict:
        {
          "heeded": bool | None,    # None = insufficient data
          "signal": str | None,     # short label for the strongest matched signal
          "confidence": float,      # 0.0 - 1.0
          "evidence": list[str],    # human-readable hits
        }
    """
    if category not in CATEGORY_SIGNALS:
        return {
            "heeded": None,
            "signal": None,
            "confidence": 0.0,
            "evidence": [f"category '{category}' has no mapped self-correction signal"],
        }

    if not session_file.exists():
        return {
            "heeded": None,
            "signal": None,
            "confidence": 0.0,
            "evidence": [f"session file not found: {session_file}"],
        }

    records = _load_session_records(session_file)
    turns = _records_to_assistant_turns(records)

    if fire_turn_index < 0 or fire_turn_index >= len(turns):
        return {
            "heeded": None,
            "signal": None,
            "confidence": 0.0,
            "evidence": [f"fire_turn_index {fire_turn_index} out of range "
                         f"(session has {len(turns)} assistant turns)"],
        }

    # Insufficient lookahead
    available = len(turns) - 1 - fire_turn_index
    if available < 1:
        return {
            "heeded": None,
            "signal": None,
            "confidence": 0.0,
            "evidence": [f"session ends at fire_turn (no lookahead available)"],
        }

    spec = CATEGORY_SIGNALS[category]
    fire_turn = turns[fire_turn_index]
    next_turns = turns[fire_turn_index + 1: fire_turn_index + 1 + lookahead_turns]

    # Aggregate signals across the lookahead window
    all_evidence: list[str] = []
    matched_anything = False

    # --- Tool-use signals
    tool_predicates = spec.get("tools", [])
    if tool_predicates:
        for t in next_turns:
            ev = _scan_tool_signals(t["tool_uses"], tool_predicates)
            if ev:
                all_evidence.extend(f"turn+{t['turn_index'] - fire_turn_index}: {e}" for e in ev)
                matched_anything = True

    # --- Edit-content signals (silent_failure_admission)
    edit_patterns = spec.get("edits", [])
    if edit_patterns:
        for t in next_turns:
            ev = _scan_edits_for_observability(t["tool_uses"], edit_patterns)
            if ev:
                all_evidence.extend(f"turn+{t['turn_index'] - fire_turn_index}: {e}" for e in ev)
                matched_anything = True

    # --- Bash signals (positive case: external_assumption, verify_before_agree)
    bash_patterns = spec.get("bash", [])
    if bash_patterns and not spec.get("negative"):
        for t in next_turns:
            ev = _scan_bash_signals(t["tool_uses"], bash_patterns)
            if ev:
                all_evidence.extend(f"turn+{t['turn_index'] - fire_turn_index}: {e}" for e in ev)
                matched_anything = True

    # --- root_cause: also check for Reads of paths mentioned in fire turn
    if spec.get("needs_context_paths"):
        cited = _extract_paths_from_text(fire_turn.get("text", ""))
        if cited:
            for t in next_turns:
                for tu in t["tool_uses"]:
                    if tu.get("name") != "Read":
                        continue
                    fp = (tu.get("input", {}) or {}).get("file_path", "")
                    if not fp:
                        continue
                    fp_basename = Path(str(fp)).name
                    for c in cited:
                        c_basename = Path(c).name
                        if c_basename and c_basename in str(fp):
                            all_evidence.append(
                                f"turn+{t['turn_index'] - fire_turn_index}: "
                                f"Read upstream file cited in trigger: {fp_basename}"
                            )
                            matched_anything = True
                            break

    # --- feature_existence_check: 3+ Glob/Grep counts as signal
    if spec.get("min_search_calls"):
        total_searches = sum(_count_search_tools(t["tool_uses"]) for t in next_turns)
        if total_searches >= spec["min_search_calls"]:
            all_evidence.append(
                f"{total_searches} Glob/Grep calls across lookahead "
                f"(>= {spec['min_search_calls']} threshold)"
            )
            matched_anything = True

    # --- verify_before_agree: prefer Read of file mentioned by user
    if spec.get("needs_user_context"):
        user_paths = _extract_paths_from_text(fire_turn.get("preceding_user_text", ""))
        if user_paths:
            for t in next_turns:
                for tu in t["tool_uses"]:
                    if tu.get("name") != "Read":
                        continue
                    fp = (tu.get("input", {}) or {}).get("file_path", "")
                    fp_basename = Path(str(fp)).name
                    for up in user_paths:
                        if Path(up).name and Path(up).name in str(fp):
                            all_evidence.append(
                                f"turn+{t['turn_index'] - fire_turn_index}: "
                                f"Read user-cited file: {fp_basename}"
                            )
                            matched_anything = True
                            break

    # --- NEGATIVE-signal categories (forward_only, respect_user_constraint)
    if spec.get("negative"):
        # forward_only: presence of git revert/reset = NOT heeded
        violation_evidence: list[str] = []
        for t in next_turns:
            if bash_patterns:
                ev = _scan_bash_signals(t["tool_uses"], bash_patterns)
                if ev:
                    violation_evidence.extend(
                        f"turn+{t['turn_index'] - fire_turn_index}: VIOLATION {e}" for e in ev
                    )
        # respect_user_constraint: presence of cloud/api in next-turn TEXT = NOT heeded
        text_neg_patterns = spec.get("text_negative", [])
        if text_neg_patterns:
            for t in next_turns:
                ev = _scan_text_negative(t.get("text", ""), text_neg_patterns)
                if ev:
                    violation_evidence.extend(
                        f"turn+{t['turn_index'] - fire_turn_index}: re-mentioned '{e}'"
                        for e in ev
                    )

        if violation_evidence:
            return {
                "heeded": False,
                "signal": f"{category}_violation",
                "confidence": spec["confidence"],
                "evidence": violation_evidence,
            }
        else:
            # Clean window — heeded
            return {
                "heeded": True,
                "signal": f"{category}_clean",
                "confidence": spec["confidence"],
                "evidence": [f"no violations in next {len(next_turns)} assistant turn(s)"],
            }

    # --- POSITIVE-signal verdict
    if matched_anything:
        return {
            "heeded": True,
            "signal": f"{category}_signal",
            "confidence": spec["confidence"],
            "evidence": all_evidence[:10],  # cap for readability
        }
    else:
        return {
            "heeded": False,
            "signal": None,
            "confidence": spec["confidence"] * 0.5,
            "evidence": [f"no {category} self-correction signal in next "
                         f"{len(next_turns)} assistant turn(s)"],
        }


# ============================================================================
# CLI
# ============================================================================

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session_file", type=Path, help="Path to Claude Code session JSONL")
    ap.add_argument("fire_turn_index", type=int,
                    help="0-based assistant turn index where redirect fired")
    ap.add_argument("category",
                    help=f"Trigger category. One of: {', '.join(CATEGORY_SIGNALS.keys())}")
    ap.add_argument("--lookahead", type=int, default=3,
                    help="Number of subsequent assistant turns to scan (default: 3)")
    ap.add_argument("--json", action="store_true",
                    help="Emit JSON instead of human-readable")
    args = ap.parse_args()

    result = detect_self_correction(
        session_file=args.session_file,
        fire_turn_index=args.fire_turn_index,
        category=args.category,
        lookahead_turns=args.lookahead,
    )

    if args.json:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"Category:    {args.category}")
        print(f"Fire turn:   {args.fire_turn_index}")
        print(f"Lookahead:   {args.lookahead} assistant turns")
        print(f"Heeded:      {result['heeded']}")
        print(f"Signal:      {result['signal']}")
        print(f"Confidence:  {result['confidence']:.2f}")
        print(f"Evidence ({len(result['evidence'])}):")
        for e in result["evidence"]:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
