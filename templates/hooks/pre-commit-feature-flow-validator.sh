#!/usr/bin/env bash
# PreToolUse Bash hook: run the feature_flow schema validator before any git commit.
#
# Phase 2 (active as of 2026-04-29): BLOCKING on errors. Promoted from
# warn-only after the system_map_decomposition Phase 2 audit landed all
# 38 flows clean (0 errors). Warnings are surfaced but do NOT block.
#
# See plans/system_map_decomposition_plan.yaml § phase_3.5 for the
# promotion rationale.
set -euo pipefail

INPUT=$(cat)
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Extract the bash command from the input JSON
COMMAND=$(echo "$INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' \
    | head -1 | sed 's/.*"command"[[:space:]]*:[[:space:]]*"//;s/"$//')

# Only fire on `git commit` (not `git diff`, `git log`, etc.)
case "$COMMAND" in
    *"git commit"*) ;;
    *) exit 0 ;;
esac

# Skip if validator script doesn't exist yet (fresh clone, mid-migration, etc.)
if [ ! -f "$ROOT/scripts/verify_feature_flow_schema.py" ]; then
    exit 0
fi
if [ ! -f "$ROOT/plans/dashboard/data/repo_map.json" ]; then
    # Validator depends on repo_map.json; skip silently if not yet generated.
    exit 0
fi

# Run the validator. --summary keeps output short; we capture it both for the
# success advisory (warnings only) and the blocking error path. Exit code 1
# from the validator means there are errors and we must block.
VALIDATOR_OUTPUT=$(cd "$ROOT" && python scripts/verify_feature_flow_schema.py --summary 2>&1)
VALIDATOR_RC=$?

# Count errors and warnings from the summary line
ERRORS=$(echo "$VALIDATOR_OUTPUT" | grep -oE 'errors:\s+[0-9]+' | head -1 | grep -oE '[0-9]+' || echo 0)
WARNINGS=$(echo "$VALIDATOR_OUTPUT" | grep -oE 'warnings:\s+[0-9]+' | head -1 | grep -oE '[0-9]+' || echo 0)

# If both are zero, exit silently — clean commit.
if [ "${ERRORS:-0}" = "0" ] && [ "${WARNINGS:-0}" = "0" ]; then
    exit 0
fi

# BLOCKING path: errors found. Output goes to stderr so Claude Code surfaces it
# to the user; exit code 2 stops the commit.
if [ "${ERRORS:-0}" != "0" ] || [ "$VALIDATOR_RC" != "0" ]; then
    cat >&2 <<EOM
Feature flow validator (Phase 2 — BLOCKING): ${ERRORS} error(s), ${WARNINGS} warning(s).

The commit is BLOCKED because at least one feature_flow YAML's intent layer no
longer matches the structural truth in plans/dashboard/data/repo_map.json.

Run for full output:
    python scripts/verify_feature_flow_schema.py | head -80

Common fixes:
  - missing_purpose: add 'purpose: "..."' at the top level
  - participating_files_path_not_in_repo: rebuild repo_map (python scripts/repo_map.py build) OR remove the stale path from the flow
  - declared_dep_unknown_target: target flow renamed/deleted — fix the name OR add it to RECOGNIZED_SUBSYSTEM_STUBS
  - declared_dep_via_symbol_not_found: rename the symbol OR add the implementing file to the target flow's participating_files
EOM
    exit 2
fi

# Warnings-only path: surface as advisory but allow the commit.
cat <<JSON
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "Feature flow validator: 0 errors, ${WARNINGS} warning(s) found across feature_flows/. Commit allowed (warnings are advisory). Review with: python scripts/verify_feature_flow_schema.py | head -80."
  }
}
JSON
