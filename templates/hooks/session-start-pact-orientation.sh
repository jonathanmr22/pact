#!/usr/bin/env bash
# session-start-pact-orientation.sh — teach the agent what PACT is on fresh installs.
#
# WHY: PACT compounds value over time but doesn't bootstrap value. A new
# install gets all the code (hooks, skills, knowledge dirs) but the agent
# has no reason to look at any of it unless something tells it to. This
# hook is that something.
#
# WHAT IT DOES: detects "fresh install" state and injects an orientation
# block teaching the agent (a) what PACT is in two sentences, (b) where
# the key files live, (c) the core cognitive redirections that always
# apply, (d) the session-start protocol.
#
# WHEN IT FIRES: only when the project looks fresh — empty knowledge dirs,
# empty bugs, empty feature_flows, no skills beyond template, AND the
# orientation count is below threshold (5 sessions). After ~5 fresh
# sessions or once any of those dirs gets populated, the hook goes silent.
#
# SAFE TO RE-FIRE: if the agent populates things and the project ages,
# the hook stops on its own. If you want to force-fire it again (e.g.
# bringing on a new teammate), delete .claude/.pact-orientation-count.
#
# Repository: https://github.com/jonathanmr22/pact

set -euo pipefail

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
COUNT_FILE="$PROJECT_ROOT/.claude/.pact-orientation-count"
ORIENTATION_LIMIT=5

# ─── 1. Determine if we should fire ──────────────────────────────────────
COUNT=0
if [[ -f "$COUNT_FILE" ]]; then
  COUNT=$(cat "$COUNT_FILE" 2>/dev/null || echo 0)
fi

# Hard cap: stop after ORIENTATION_LIMIT firings regardless of state
if [[ "$COUNT" -ge "$ORIENTATION_LIMIT" ]]; then
  exit 0
fi

# Soft signals of "still fresh" — if any of these is empty, the project
# hasn't accumulated PACT artifacts yet
is_dir_empty_of_real_content() {
  local dir="$1"
  [[ ! -d "$dir" ]] && return 0
  # Empty if it contains only template/index files (filenames starting with _)
  local non_meta_count
  non_meta_count=$(find "$dir" -maxdepth 1 -type f ! -name "_*" ! -name ".*" 2>/dev/null | wc -l | tr -d ' ')
  [[ "$non_meta_count" -eq 0 ]]
}

FRESH_INDICATORS=0
is_dir_empty_of_real_content "$PROJECT_ROOT/feature_flows" && FRESH_INDICATORS=$((FRESH_INDICATORS + 1))
is_dir_empty_of_real_content "$PROJECT_ROOT/knowledge/research" && FRESH_INDICATORS=$((FRESH_INDICATORS + 1))
is_dir_empty_of_real_content "$PROJECT_ROOT/knowledge/packages" && FRESH_INDICATORS=$((FRESH_INDICATORS + 1))

# Also count empty bugs/ directory (no <system>/ subdirs with actual bug files)
BUGS_EMPTY=true
if [[ -d "$PROJECT_ROOT/bugs" ]]; then
  if find "$PROJECT_ROOT/bugs" -mindepth 2 -name "*.yaml" -not -name "_*" 2>/dev/null | grep -q .; then
    BUGS_EMPTY=false
  fi
fi
[[ "$BUGS_EMPTY" == "true" ]] && FRESH_INDICATORS=$((FRESH_INDICATORS + 1))

# If 0 of 4 indicators say "fresh", the project has accumulated PACT artifacts;
# stop firing even if count is below limit
if [[ "$FRESH_INDICATORS" -eq 0 ]]; then
  echo "$ORIENTATION_LIMIT" > "$COUNT_FILE"
  exit 0
fi

# ─── 2. Increment the count ──────────────────────────────────────────────
mkdir -p "$(dirname "$COUNT_FILE")"
NEW_COUNT=$((COUNT + 1))
echo "$NEW_COUNT" > "$COUNT_FILE"

# ─── 3. Emit the orientation block ───────────────────────────────────────
SESSIONS_LEFT=$((ORIENTATION_LIMIT - NEW_COUNT))

cat <<JSON
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "PACT ORIENTATION (session ${NEW_COUNT}/${ORIENTATION_LIMIT}; this hook will go silent after ${ORIENTATION_LIMIT} sessions or once the project has accumulated real PACT artifacts).\n\nPACT is a governance methodology for AI-assisted software work. It is NOT a workflow you follow rigidly — it is a set of mechanical hooks + structured knowledge files that compound your project's understanding across sessions.\n\nWHERE THINGS LIVE IN THIS PROJECT:\n  CLAUDE.md                              — Read every session. Cognitive redirections, hook-blocked rules, project philosophy.\n  HANDOFF.yaml                           — Entry pointer. Top priorities + last session's summary. Read at session start.\n  plans/dashboard/trees/{tree}/streams/  — Active task ledger (single source of truth for current AND historical work).\n  feature_flows/*.yaml                   — Lifecycle docs for critical systems. Read before editing files claimed in participating_files.\n  knowledge/packages/{name}.yaml         — Verified package APIs. Read BEFORE writing code that uses a package.\n  knowledge/KNOWLEDGE_DIRECTORY.yaml     — Tag index across all knowledge systems. Read before researching.\n  bugs/{system}/{system}-NNN.yaml        — Bug investigations + resolutions. Check bugs/_SOLUTIONS.yaml first when something is broken.\n  skills/_SKILL_INDEX.yaml + skills/*.yaml — Proven multi-step workflows. Scan triggers before starting any non-trivial task.\n  scripts/SCRIPT_CATALOG.yaml            — Index of every script with deps, lessons, reusable patterns.\n  .claude/hooks/                         — Mechanical enforcement (PreToolUse / PostToolUse / SessionStart). The agent cannot bypass these.\n\nCORE COGNITIVE REDIRECTIONS (full list in CLAUDE.md):\n  - Verify before agreeing — when the user makes a correction, check it independently\n  - Fresh-read before edit — never edit a file based on memory of an earlier read\n  - Three-hop dependency trace — what depends on this and what does this depend on, in both directions\n  - Bug-file FIRST — when investigating something broken, create the bugs/{system}/{system}-NNN.yaml file BEFORE starting fixes\n  - Package-knowledge first — before writing code with a package, check knowledge/packages/{name}.yaml\n\nSESSION-START PROTOCOL:\n  1. State 'I have read and will follow all <project> rules.'\n  2. Read HANDOFF.yaml for entry pointer\n  3. Scan .claude/memory/file_edit_log.yaml for recent edits\n  4. Check .claude/sessions.yaml for other active sessions\n\nFIRST-SESSION HOMEWORK (do these once per project, not per session):\n  - Customize CLAUDE.md's Project Philosophy section (core beliefs, decision filters, what this project is NOT)\n  - Add 1-2 critical-system feature_flows/*.yaml docs as you start touching those systems\n  - Add 1-2 knowledge/packages/{name}.yaml entries for the libraries you actually use\n\n${SESSIONS_LEFT} more orientation injections will fire before this hook goes silent. Use them to absorb the structure; after that, it's invisible governance running in the background."
  }
}
JSON

exit 0
