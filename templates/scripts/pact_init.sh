#!/usr/bin/env bash
# pact_init.sh — interactive PACT scaffolder for a new project.
#
# What it does:
#   1. Asks a handful of questions about your project (name, stack, scale)
#   2. Generates a customized CLAUDE.md from the template
#   3. Scaffolds the directory structure PACT expects
#   4. Copies starter index files (KNOWLEDGE_DIRECTORY, SKILL_INDEX, etc.)
#   5. Drops in a working .claude/settings.json with sensible default hooks
#   6. Prints what to do next
#
# Run from your project root. The script works out where PACT is installed
# from its own location (templates/scripts/pact_init.sh).
#
# Idempotent: skips files that already exist; you can re-run safely.
#
# Repository: https://github.com/jonathanmr22/pact

set -euo pipefail

# ─── Locate PACT install + target project ────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACT_HOME="$(cd "$SCRIPT_DIR/../.." && pwd)"
TARGET_DIR="$(pwd)"

if [[ ! -d "$PACT_HOME/templates" ]]; then
  echo "ERROR: pact_init.sh expected to find PACT templates at $PACT_HOME/templates" >&2
  echo "       Make sure you're running this from a PACT install: <pact>/templates/scripts/pact_init.sh" >&2
  exit 1
fi

# ─── ANSI colors (best-effort) ───────────────────────────────────────────
if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; CYAN=$'\033[36m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; RESET=$'\033[0m'
else
  BOLD=""; DIM=""; CYAN=""; GREEN=""; YELLOW=""; RED=""; RESET=""
fi

banner() {
  echo ""
  echo "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${RESET}"
  echo "${BOLD}${CYAN}  $1${RESET}"
  echo "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${RESET}"
}
ask() { read -rp "${BOLD}?${RESET} $1 " "${2}"; }
ask_yn() {
  local prompt="$1" default="${2:-y}" reply
  local hint="[Y/n]"; [[ "$default" == "n" ]] && hint="[y/N]"
  read -rp "${BOLD}?${RESET} $prompt $hint " reply
  reply="${reply:-$default}"
  [[ "${reply,,}" =~ ^y ]]
}
note() { echo "${DIM}  $1${RESET}"; }
ok()   { echo "${GREEN}  ✓${RESET} $1"; }
warn() { echo "${YELLOW}  !${RESET} $1"; }
skip() { echo "${DIM}  · skipped: $1${RESET}"; }

# ─── 0. Sanity checks ────────────────────────────────────────────────────
banner "PACT init — scaffolding your project"
echo ""
echo "PACT install:  $PACT_HOME"
echo "Target:        $TARGET_DIR"
echo ""

if [[ "$PACT_HOME" == "$TARGET_DIR" ]]; then
  echo "${RED}ERROR:${RESET} target directory IS the PACT install. cd into your own project first." >&2
  exit 1
fi

if ! git -C "$TARGET_DIR" rev-parse --is-inside-work-tree &>/dev/null; then
  warn "this directory is not a git repo"
  if ask_yn "Initialize git here?" "y"; then
    git -C "$TARGET_DIR" init >/dev/null
    ok "git initialized"
  else
    note "PACT works without git but several hooks (worktree isolation, commit gates) will be no-ops"
  fi
fi

# ─── 1. Project questions ────────────────────────────────────────────────
banner "Project questions"
echo ""

DEFAULT_NAME="$(basename "$TARGET_DIR")"
ask "Project name?  [$DEFAULT_NAME]" PROJECT_NAME
PROJECT_NAME="${PROJECT_NAME:-$DEFAULT_NAME}"

echo ""
echo "Primary languages / frameworks (choose all that apply, comma-separated):"
echo "  1) Python"
echo "  2) JavaScript / TypeScript / Node"
echo "  3) Dart / Flutter"
echo "  4) Go"
echo "  5) Rust"
echo "  6) Java / Kotlin"
echo "  7) Other (you'll fill in)"
ask "Numbers?  [1]" LANG_CHOICE
LANG_CHOICE="${LANG_CHOICE:-1}"

LANGS=()
[[ "$LANG_CHOICE" == *1* ]] && LANGS+=("Python")
[[ "$LANG_CHOICE" == *2* ]] && LANGS+=("JavaScript/TypeScript/Node")
[[ "$LANG_CHOICE" == *3* ]] && LANGS+=("Dart/Flutter")
[[ "$LANG_CHOICE" == *4* ]] && LANGS+=("Go")
[[ "$LANG_CHOICE" == *5* ]] && LANGS+=("Rust")
[[ "$LANG_CHOICE" == *6* ]] && LANGS+=("Java/Kotlin")
[[ "$LANG_CHOICE" == *7* ]] && LANGS+=("(fill in your stack)")
LANG_LIST="$(IFS=", "; echo "${LANGS[*]}")"

echo ""
echo "Backend / database setup:"
echo "  1) Supabase (Postgres + Edge Functions)"
echo "  2) Firebase"
echo "  3) Custom REST API + database"
echo "  4) Database only, no backend service"
echo "  5) None — local-only or static"
ask "Number?  [5]" BACKEND_CHOICE
BACKEND_CHOICE="${BACKEND_CHOICE:-5}"
case "$BACKEND_CHOICE" in
  1) BACKEND="Supabase (Postgres + Edge Functions)";;
  2) BACKEND="Firebase";;
  3) BACKEND="Custom REST API + database";;
  4) BACKEND="Database only, no backend service";;
  5) BACKEND="None — local-only or static";;
  *) BACKEND="(fill in your backend)";;
esac

echo ""
HAS_MOBILE="No"
if ask_yn "Mobile app?" "n"; then HAS_MOBILE="Yes"; fi

echo ""
WORKTREE_ISOLATION="true"
if ! ask_yn "Use worktree isolation (recommended — keeps multiple Claude sessions from stepping on each other)?" "y"; then
  WORKTREE_ISOLATION="false"
fi

echo ""
note "Got it. Generating files..."

# ─── 2. Generate CLAUDE.md from template ─────────────────────────────────
banner "Generating CLAUDE.md"

CLAUDE_MD="$TARGET_DIR/CLAUDE.md"
TODAY="$(date +%Y-%m-%d)"

if [[ -f "$CLAUDE_MD" ]]; then
  warn "CLAUDE.md already exists at $CLAUDE_MD"
  if ask_yn "Overwrite?" "n"; then
    OVERWRITE_CLAUDE_MD=true
  else
    OVERWRITE_CLAUDE_MD=false
  fi
else
  OVERWRITE_CLAUDE_MD=true
fi

if [[ "$OVERWRITE_CLAUDE_MD" == "true" ]]; then
  python - <<PYEOF
import re
from pathlib import Path

src = Path(r"$PACT_HOME/templates/CLAUDE.md.template").read_text(encoding="utf-8")
out = src.replace("{PROJECT_NAME}", "$PROJECT_NAME").replace("{DATE}", "$TODAY")

# Fill in the Architecture section with the user's answers
arch_block = """- **Languages:** $LANG_LIST
- **Backend:** $BACKEND
- **Mobile app:** $HAS_MOBILE
- **Worktree isolation:** $WORKTREE_ISOLATION
- **Key files:** See \`feature_flows/*.yaml\` for the lifecycle docs of critical systems and their participating files."""

# Replace the example Architecture block
out = re.sub(
    r'- \*\*Database:\*\* \(e\.g\.,.*?\n- \*\*State Management:\*\*.*?\n- \*\*Backend:\*\*.*?\n- \*\*Key files:\*\*.*?\n',
    arch_block + "\n",
    out, flags=re.S
)

Path(r"$CLAUDE_MD").write_text(out, encoding="utf-8")
PYEOF
  ok "CLAUDE.md generated with $PROJECT_NAME's stack baked in"
else
  skip "CLAUDE.md (kept existing)"
fi

# ─── 3. Scaffold directories ─────────────────────────────────────────────
banner "Scaffolding directory structure"

mkdir -p "$TARGET_DIR/.claude/memory"
mkdir -p "$TARGET_DIR/.claude/hooks"
mkdir -p "$TARGET_DIR/knowledge/packages"
mkdir -p "$TARGET_DIR/knowledge/research"
mkdir -p "$TARGET_DIR/bugs"
mkdir -p "$TARGET_DIR/feature_flows"
mkdir -p "$TARGET_DIR/plans/dashboard/trees"
mkdir -p "$TARGET_DIR/plans/dashboard/data"
mkdir -p "$TARGET_DIR/skills"
mkdir -p "$TARGET_DIR/scripts"
ok ".claude/{memory,hooks}/"
ok "knowledge/{packages,research}/"
ok "bugs/"
ok "feature_flows/"
ok "plans/dashboard/{trees,data}/"
ok "skills/"
ok "scripts/"

# ─── 4. Copy starter index files (skip if already present) ───────────────
banner "Copying starter index files"

copy_if_missing() {
  local src="$1" dst="$2"
  if [[ -f "$dst" ]]; then
    skip "$(basename "$dst")"
    return
  fi
  if [[ ! -f "$src" ]]; then
    warn "source not found: $src"
    return
  fi
  cp "$src" "$dst"
  ok "$(basename "$dst")"
}

copy_if_missing "$PACT_HOME/templates/HANDOFF.yaml"               "$TARGET_DIR/HANDOFF.yaml"
copy_if_missing "$PACT_HOME/templates/knowledge_directory.yaml"   "$TARGET_DIR/knowledge/KNOWLEDGE_DIRECTORY.yaml"
copy_if_missing "$PACT_HOME/templates/skills/_SKILL_INDEX.yaml"   "$TARGET_DIR/skills/_SKILL_INDEX.yaml"
copy_if_missing "$PACT_HOME/templates/skills/_SKILL_TEMPLATE.yaml" "$TARGET_DIR/skills/_SKILL_TEMPLATE.yaml"
copy_if_missing "$PACT_HOME/templates/bugs/_INDEX.yaml"           "$TARGET_DIR/bugs/_INDEX.yaml"
copy_if_missing "$PACT_HOME/templates/bugs/_SOLUTIONS.yaml"       "$TARGET_DIR/bugs/_SOLUTIONS.yaml"
copy_if_missing "$PACT_HOME/templates/script_catalog.yaml"        "$TARGET_DIR/scripts/SCRIPT_CATALOG.yaml"
copy_if_missing "$PACT_HOME/templates/scripts/RUN_LOG.yaml"       "$TARGET_DIR/scripts/RUN_LOG.yaml"
copy_if_missing "$PACT_HOME/templates/feature_flow.yaml"          "$TARGET_DIR/feature_flows/_TEMPLATE.yaml"
copy_if_missing "$PACT_HOME/templates/pact-context.yaml"          "$TARGET_DIR/.claude/pact-context.yaml"
copy_if_missing "$PACT_HOME/templates/capability_baseline.yaml"   "$TARGET_DIR/knowledge/PACT_BASELINE.yaml"
copy_if_missing "$PACT_HOME/templates/pact-gitignore"             "$TARGET_DIR/.claude/.gitignore"

# ─── 5. Copy hooks ───────────────────────────────────────────────────────
banner "Copying default hooks"

if [[ -d "$PACT_HOME/templates/hooks" ]]; then
  for hook in "$PACT_HOME/templates/hooks"/*.sh "$PACT_HOME/templates/hooks"/*.py; do
    [[ -f "$hook" ]] || continue
    name="$(basename "$hook")"
    dst="$TARGET_DIR/.claude/hooks/$name"
    if [[ -f "$dst" ]]; then
      skip "$name"
    else
      cp "$hook" "$dst"
      chmod +x "$dst" 2>/dev/null || true
      ok "$name"
    fi
  done
  if [[ -d "$PACT_HOME/templates/hooks/lib" ]]; then
    cp -rn "$PACT_HOME/templates/hooks/lib" "$TARGET_DIR/.claude/hooks/" 2>/dev/null || true
    ok "hooks/lib/"
  fi
fi

# ─── 6. settings.json — minimal working version ──────────────────────────
banner "Generating .claude/settings.json"

SETTINGS="$TARGET_DIR/.claude/settings.json"
if [[ -f "$SETTINGS" ]]; then
  warn "settings.json already exists"
  skip "settings.json (kept existing — merge in PACT hooks manually if needed)"
else
  cat > "$SETTINGS" <<'JSON'
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/session-register.sh", "timeout": 5, "statusMessage": "Registering session..." },
          { "type": "command", "command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/session-start-pact-orientation.sh", "timeout": 5, "statusMessage": "Checking PACT orientation status..." }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          { "type": "command", "command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/inject-timestamp.sh", "timeout": 3, "statusMessage": "Injecting current local time..." }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          { "type": "command", "command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/pre-edit-rules.sh", "timeout": 5, "statusMessage": "Checking edit rules..." }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/pre-bash-guard.sh", "timeout": 5, "statusMessage": "Checking bash guard..." }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          { "type": "command", "command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/post-edit-timestamp.sh", "timeout": 3, "statusMessage": "Logging edit timestamp..." }
        ]
      },
      {
        "matcher": "Read",
        "hooks": [
          { "type": "command", "command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/post-read-tracker.sh", "timeout": 3, "statusMessage": "Tracking read..." }
        ]
      }
    ]
  }
}
JSON
  ok "settings.json (with default hook wiring)"
fi

# ─── 7. Drop a marker so the orientation hook knows we just initialized ──
echo "0" > "$TARGET_DIR/.claude/.pact-orientation-count"

# ─── 8. Summary + next steps ─────────────────────────────────────────────
banner "Done"
echo ""
echo "${GREEN}Your project is now PACT-scaffolded.${RESET}"
echo ""
echo "${BOLD}What's where:${RESET}"
echo "  CLAUDE.md                — project rules + cognitive redirections (read every session)"
echo "  HANDOFF.yaml             — entry pointer; surfaces top priorities + last-session summary"
echo "  knowledge/               — verified facts (packages/, research/, KNOWLEDGE_DIRECTORY.yaml)"
echo "  bugs/                    — bug investigations + reusable solutions"
echo "  skills/                  — proven multi-step workflows"
echo "  feature_flows/           — lifecycle docs for critical systems"
echo "  plans/                   — implementation plans + dashboard"
echo "  scripts/                 — project scripts + SCRIPT_CATALOG.yaml index"
echo "  .claude/hooks/           — mechanical enforcement layer"
echo "  .claude/settings.json    — wires the hooks into Claude Code"
echo ""
echo "${BOLD}Next steps:${RESET}"
echo "  1. Open this project in Claude Code. The session-start orientation hook"
echo "     will guide the agent through PACT's structure for the first ~5 sessions."
echo "  2. Customize CLAUDE.md — fill in Project Philosophy + project-specific rules."
echo "  3. Write your first feature_flows/{system}_flow.yaml when you start work on a critical system."
echo "  4. Read QUICKSTART.md in the PACT repo for the full day-one walkthrough."
echo ""
echo "${DIM}Re-run pact_init.sh anytime — it skips existing files.${RESET}"
echo ""
