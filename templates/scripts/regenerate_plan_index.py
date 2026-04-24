#!/usr/bin/env python3
"""Regenerate plans/_PLAN_INDEX.yaml from plan file headers.

Mirrors the manual skills/_SKILL_INDEX.yaml pattern. Run anytime a new plan
is added or a plan's status changes:

    python scripts/regenerate_plan_index.py

Reads the YAML or markdown frontmatter of every file under plans/ (except
FOLDER.yaml and _PLAN_INDEX.yaml itself), groups by status, and emits a
sorted, status-grouped index.

Plan file format expected:
    ---
    name: Some Plan
    description: |
      Multi-line description...
    status: active        # one of: active | partial | delayed | complete
    ---
"""
import os
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
PLANS_DIR = PROJECT_DIR / "plans"
INDEX_FILE = PLANS_DIR / "_PLAN_INDEX.yaml"
SKIP = {"FOLDER.yaml", "_PLAN_INDEX.yaml"}


def extract_meta(path: Path):
    """Return (status, description) parsed from the file's first ~3KB."""
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:3000]
    except Exception:
        return ("unreadable", "")

    status = "unknown"
    if m := re.search(r"^status:\s*(\S+)", head, re.MULTILINE):
        status = m.group(1).lower().strip(',"')
    elif re.search(r"COMPLETE\b|SHIPPED\b", head, re.IGNORECASE):
        status = "complete"
    elif re.search(r"in[_ ]flight|ACTIVE|in flight", head, re.IGNORECASE):
        status = "active"

    desc = ""
    for pat in (
        r"^description:\s*[>|]?\s*(.+?)(?=\n[a-z_]+:|\n---|\Z)",
        r"^purpose:\s*[>|]?\s*(.+?)(?=\n[a-z_]+:|\n---|\Z)",
        r"^# (.+?)$",
        r"^name:\s*(.+?)$",
    ):
        if m := re.search(pat, head, re.MULTILINE | re.DOTALL):
            desc = " ".join(m.group(1).split())[:140]
            break
    return (status, desc.strip().rstrip("."))


def main():
    if not PLANS_DIR.exists():
        print(f"FATAL: {PLANS_DIR} does not exist. Create it first.", file=sys.stderr)
        sys.exit(2)

    files = sorted(p for p in PLANS_DIR.iterdir() if p.is_file() and p.name not in SKIP)
    entries = [(p.name, *extract_meta(p)) for p in files]

    out_lines = [
        "# Plans Index - quickly find which plan covers a topic and its current status.",
        "# Mirrors skills/_SKILL_INDEX.yaml.",
        "# Regenerate via: python scripts/regenerate_plan_index.py",
        "# Status vocabulary (per FOLDER.yaml): active, partial, delayed, complete.",
        "",
        "plans:",
    ]
    for status in ["active", "partial", "delayed", "complete", "unknown"]:
        matching = sorted([e for e in entries if e[1] == status])
        if not matching:
            continue
        out_lines.append(f"\n  # === {status.upper()} ({len(matching)}) ===")
        for name, _, desc in matching:
            ext = name.rsplit(".", 1)[-1]
            out_lines.append(f"  - file: plans/{name}")
            out_lines.append(f"    status: {status}")
            out_lines.append(f"    format: {ext}")
            if desc:
                esc = desc.replace('"', "'").replace("\n", " ")[:120]
                out_lines.append(f'    desc: "{esc}"')

    INDEX_FILE.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(entries)} entries to {INDEX_FILE}")


if __name__ == "__main__":
    main()
