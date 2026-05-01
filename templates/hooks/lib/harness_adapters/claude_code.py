#!/usr/bin/env python3
"""Claude Code session-format adapter for the cognitive-redirect hook.

Reads Claude Code's session JSONL and returns the most recent assistant turn's
reasoning artifacts in a uniform shape. Other harnesses (Cline, Cursor) would
implement the same get_last_assistant_artifacts() interface against their own
session formats.

Claude Code session JSONL structure (verified 2026-04-30):
  Each line is a JSON record with a `type` field:
    - "user" — user prompt or tool result
    - "assistant" — model's response, may contain text + thinking + tool_use blocks
    - "system" — session metadata
    - "summary" — compaction artifact

  Assistant message structure:
    {
      "type": "assistant",
      "message": {
        "content": [
          {"type": "thinking", "text": "<extended thinking content>"},  # if enabled
          {"type": "text", "text": "<user-visible prose>"},
          {"type": "tool_use", "id": "...", "name": "...", "input": {...}}
        ]
      }
    }
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def find_session_file(session_id: str | None = None,
                      project_dir: str | None = None) -> Path | None:
    """Locate the Claude Code session JSONL for the current session.

    Strategy (in priority order):
      1. If $CLAUDE_SESSION_FILE is set, use it (future-proof).
      2. If session_id provided, search ~/.claude/projects/ for {session_id}.jsonl
         (top-level only — subagent sessions live deeper, we want the parent).
      3. Fall back to most recent top-level JSONL anywhere.

    NOTE: We deliberately AVOID the project-dir-to-slug heuristic because Claude
    Code's slug rules vary (capital C-- vs lowercase c--, with/without leading
    underscore, etc.). Searching by session_id is more robust.
    """
    # Strategy 1: env var (preferred if available)
    env_path = os.environ.get("CLAUDE_SESSION_FILE")
    if env_path and Path(env_path).exists():
        return Path(env_path)

    home = Path.home()
    projects_root = home / ".claude" / "projects"
    if not projects_root.exists():
        return None

    # Strategy 2: search for {session_id}.jsonl directly under any project dir
    # (NOT recursive into subagents/ — we want the top-level parent session).
    if session_id:
        for proj_dir in projects_root.iterdir():
            if not proj_dir.is_dir():
                continue
            candidate = proj_dir / f"{session_id}.jsonl"
            if candidate.exists():
                return candidate

    # Strategy 3: most recent TOP-LEVEL JSONL (skip subagents/ subdirs).
    # If project_dir is provided, prefer sessions in matching project dirs.
    proj_hint = project_dir or os.environ.get("CLAUDE_PROJECT_DIR", "")
    proj_basename = Path(proj_hint).name.lower() if proj_hint else ""

    candidates: list[Path] = []
    for proj_dir in projects_root.iterdir():
        if not proj_dir.is_dir():
            continue
        # Score: sessions in dirs whose name contains the project basename rank higher
        match_bonus = 1 if proj_basename and proj_basename in proj_dir.name.lower() else 0
        for jsonl in proj_dir.glob("*.jsonl"):  # top-level only, no subagents
            candidates.append((match_bonus, jsonl.stat().st_mtime, jsonl))

    if candidates:
        # Sort by (match_bonus desc, mtime desc)
        candidates.sort(key=lambda x: (-x[0], -x[1]))
        return candidates[0][2]

    return None


def get_last_assistant_artifacts(session_file: Path | None = None,
                                 session_id: str | None = None) -> dict[str, Any]:
    """Extract the most recent assistant turn's reasoning artifacts.

    Returns:
        {
          "thinking": "<extended thinking text or empty>",
          "text": "<assistant prose, joined across multiple text blocks>",
          "tool_uses": [{"name": str, "input": dict}, ...],
          "turn_index": int,
          "session_file": str,
        }

    Returns empty artifacts dict if no assistant turn found.
    """
    sf = session_file or find_session_file(session_id=session_id)
    if sf is None or not sf.exists():
        return {"thinking": "", "text": "", "tool_uses": [], "turn_index": -1, "session_file": ""}

    # Read all records first, then walk backwards collecting assistant records
    # until we hit a user message. Claude Code splits one assistant TURN across
    # multiple JSONL records (one per content block in some serializations), so
    # we need to combine all consecutive trailing assistant records into one turn.
    records: list[dict[str, Any]] = []
    try:
        with sf.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except (OSError, IOError):
        return {"thinking": "", "text": "", "tool_uses": [], "turn_index": -1, "session_file": str(sf)}

    if not records:
        return {"thinking": "", "text": "", "tool_uses": [], "turn_index": -1, "session_file": str(sf)}

    # Compute COLLAPSED assistant turn count — consecutive assistant records
    # are one turn (a single assistant response can span multiple JSONL records,
    # one per content block). This MUST match detect_self_correction.py's
    # _records_to_assistant_turns() output so fire-log turn indices line up
    # with the detector's lookups.
    turn_index = 0
    last_was_assistant = False
    for r in records:
        if r.get("type") == "assistant":
            if not last_was_assistant:
                turn_index += 1
            last_was_assistant = True
        elif r.get("type") == "user":
            last_was_assistant = False
        # other types don't reset the run
    # turn_index now equals the count of distinct collapsed assistant turns.
    # The CURRENT (most recent) assistant turn is index turn_index - 1 (0-based).
    turn_index = max(0, turn_index - 1)

    # Walk backwards, collect assistant records until we hit user/system or beginning
    assistant_records_in_turn: list[dict[str, Any]] = []
    for rec in reversed(records):
        rtype = rec.get("type")
        if rtype == "assistant":
            assistant_records_in_turn.append(rec)
        elif rtype in ("user",):
            # End of current assistant turn (going back in time)
            break
        # Skip system/summary/other — they don't break a turn

    if not assistant_records_in_turn:
        return {"thinking": "", "text": "", "tool_uses": [], "turn_index": turn_index, "session_file": str(sf)}

    # Records are in reverse chronological order — re-reverse so we read in real order
    assistant_records_in_turn.reverse()

    thinking_parts: list[str] = []
    text_parts: list[str] = []
    tool_uses: list[dict] = []

    for rec in assistant_records_in_turn:
        msg = rec.get("message", {})
        content = msg.get("content", [])
        if isinstance(content, str):
            text_parts.append(content)
            continue
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "thinking":
                t = block.get("text") or block.get("thinking") or ""
                if t:
                    thinking_parts.append(t)
            elif btype == "text":
                t = block.get("text", "")
                if t:
                    text_parts.append(t)
            elif btype == "tool_use":
                tool_uses.append({
                    "name": block.get("name", ""),
                    "input": block.get("input", {}),
                })

    return {
        "thinking": "\n".join(thinking_parts),
        "text": "\n".join(text_parts),
        "tool_uses": tool_uses,
        "turn_index": turn_index,
        "session_file": str(sf),
    }


def main():
    """CLI: print the last assistant artifacts as JSON."""
    session_id = sys.argv[1] if len(sys.argv) > 1 else None
    artifacts = get_last_assistant_artifacts(session_id=session_id)
    json.dump(artifacts, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
