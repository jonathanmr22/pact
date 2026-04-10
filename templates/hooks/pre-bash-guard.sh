#!/usr/bin/env bash
# =============================================================================
# PACT PreToolUse Hook (Bash) — BLOCKS dangerous shell commands
#
# Exit 1 = blocked, exit 0 = allowed.
#
# Covers:
#   - Git safety (no force push main, no --no-verify, no reset --hard)
#   - Destructive file operations (rm -rf on project dirs)
#   - Multi-session safety (blocks commit if local behind remote)
#   - Bug tracker enforcement on fix commits
#   - Staleness warnings on commit (non-blocking)
#
# CUSTOMIZE: Uncomment project-specific rules at the bottom.
# =============================================================================

INPUT=$(cat)

COMMAND=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('tool_input', {}).get('command', ''))
" 2>/dev/null)

VIOLATIONS=""

# ============================================================================
# GIT SAFETY
# ============================================================================

# No --no-verify on git commands (never skip hooks)
if echo "$COMMAND" | grep -qE 'git.*--no-verify'; then
  VIOLATIONS="${VIOLATIONS}BLOCKED: --no-verify flag on git command — never skip hooks.\n"
fi

# No git push --force to main/master
if echo "$COMMAND" | grep -qE 'git push.*--force.*(main|master)|git push.*-f.*(main|master)'; then
  VIOLATIONS="${VIOLATIONS}BLOCKED: Force push to main/master — this is destructive.\n"
fi

# No git reset --hard
if echo "$COMMAND" | grep -qE 'git reset --hard'; then
  VIOLATIONS="${VIOLATIONS}BLOCKED: git reset --hard — this is destructive and discards work.\n"
fi

# No git branch -D (force delete) — use -d (safe delete)
if echo "$COMMAND" | grep -qE 'git branch -D '; then
  VIOLATIONS="${VIOLATIONS}BLOCKED: git branch -D (force delete) — use -d (safe delete) unless user explicitly requests force.\n"
fi

# No bulk discard of changes
if echo "$COMMAND" | grep -qE 'git checkout \.|git checkout -- |git restore \.|git restore --staged \.'; then
  VIOLATIONS="${VIOLATIONS}BLOCKED: Bulk discard of all changes — this erases work from other sessions.\n"
fi
if echo "$COMMAND" | grep -qE 'git clean\s+-[a-zA-Z]*f'; then
  VIOLATIONS="${VIOLATIONS}BLOCKED: git clean -f — deletes untracked files, may erase other sessions' work.\n"
fi

# Block git checkout <branch> with uncommitted changes
if echo "$COMMAND" | grep -qE '^git checkout [^-]' && ! echo "$COMMAND" | grep -qE '^git checkout -b '; then
  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    VIOLATIONS="${VIOLATIONS}BLOCKED: git checkout <branch> with uncommitted changes — commit or stash first.\n"
  fi
fi

# ============================================================================
# LLM DELEGATION ENFORCEMENT (Growth+ tier)
# If using pact-delegate for multi-model delegation, block direct API calls
# to LLM providers. All model calls MUST go through pact-delegate for proper
# routing, cost tracking, system prompts, and delegation logging.
# ============================================================================
LLM_ENDPOINTS="openrouter\.ai/api/v1/chat|api\.anthropic\.com/v1/messages|generativelanguage\.googleapis\.com|api\.openai\.com/v1/chat"
if echo "$COMMAND" | grep -qE "$LLM_ENDPOINTS"; then
  if ! echo "$COMMAND" | grep -q 'pact-delegate'; then
    VIOLATIONS="${VIOLATIONS}BLOCKED: Direct LLM API call detected — use pact-delegate instead.\n  pact-delegate routes to the correct model, applies system prompts, tracks cost, and logs delegation.\n  Usage: pact-delegate <task_type> \"<prompt>\" [--context-file <path>]\n  Task types: research, code, classify, plan, document, seed_data\n"
  fi
fi
# Also catch Python scripts that construct LLM API calls
if echo "$COMMAND" | grep -qE "python.*(-c|\.py)" && echo "$COMMAND" | grep -qE "$LLM_ENDPOINTS"; then
  if ! echo "$COMMAND" | grep -q 'pact-delegate'; then
    VIOLATIONS="${VIOLATIONS}BLOCKED: Python script with direct LLM API call — use pact-delegate instead.\n  Never construct ad-hoc scripts that call LLM providers. pact-delegate exists for this.\n"
  fi
fi

# ============================================================================
# DESTRUCTIVE FILE OPERATIONS
# ============================================================================

# No rm -rf on project directories
if echo "$COMMAND" | grep -qE 'rm -rf\s+(lib|src|test|assets|\.claude|app|packages)'; then
  VIOLATIONS="${VIOLATIONS}BLOCKED: rm -rf on project directory — this is destructive.\n"
fi

# ============================================================================
# RELEASE BUILD SAFETY (uncomment for your framework)
# ============================================================================

# ---- Flutter: release without obfuscation ----
# if echo "$COMMAND" | grep -qE 'flutter build (apk|appbundle|ipa).*--release'; then
#   if ! echo "$COMMAND" | grep -q '\-\-obfuscate'; then
#     VIOLATIONS="${VIOLATIONS}BLOCKED: Release build without --obfuscate --split-debug-info.\n"
#   fi
# fi

# ============================================================================
# PROJECT-SPECIFIC RULES (uncomment and customize)
# ============================================================================

# ---- Block destructive commands targeting specific devices ----
# if echo "$COMMAND" | grep -qE 'YOUR_DEVICE_ID'; then
#   if echo "$COMMAND" | grep -qiE 'pm clear|pm uninstall|wipe|factory.*reset'; then
#     VIOLATIONS="${VIOLATIONS}BLOCKED: Destructive command targets physical device.\n"
#   fi
# fi

if [ -n "$VIOLATIONS" ]; then
  echo -e "$VIOLATIONS" >&2
  exit 1
fi

# ============================================================================
# WORKTREE ISOLATION: merge/push to main branch requires user approval
# With worktree isolation, commits on session branches are free (low-stakes
# checkpoints). The gate is on merging/pushing to the main branch — landing
# work on the shared branch requires explicit user approval.
# To enable: set PACT_WORKTREE_ISOLATION=1 in your environment or
# pact-config.json { "worktree_isolation": true }
# ============================================================================
PACT_WORKTREE_ENABLED=false
PACT_CONFIG="$HOME/.claude/pact-config.json"
if [ -n "$PACT_WORKTREE_ISOLATION" ] && [ "$PACT_WORKTREE_ISOLATION" = "1" ]; then
  PACT_WORKTREE_ENABLED=true
elif [ -f "$PACT_CONFIG" ]; then
  if python3 -c "import json; exit(0 if json.load(open('$PACT_CONFIG')).get('worktree_isolation') else 1)" 2>/dev/null; then
    PACT_WORKTREE_ENABLED=true
  fi
fi

if [ "$PACT_WORKTREE_ENABLED" = true ]; then
  CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
  DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
  [ -z "$DEFAULT_BRANCH" ] && DEFAULT_BRANCH="main"

  # Block: git merge into default branch without approval
  if echo "$COMMAND" | grep -qE '^git merge' && [ "$CURRENT_BRANCH" = "$DEFAULT_BRANCH" ]; then
    APPROVAL_FILE="${TEMP:-/tmp}/pact_merge_approved.lock"
    if [ -f "$APPROVAL_FILE" ]; then
      APPROVAL_AGE=$(( $(date +%s) - $(cat "$APPROVAL_FILE" 2>/dev/null || echo 0) ))
      if [ "$APPROVAL_AGE" -lt 120 ]; then
        rm -f "$APPROVAL_FILE"
      else
        rm -f "$APPROVAL_FILE"
        echo "" >&2
        echo "═══ BLOCKED: MERGE APPROVAL EXPIRED ═══" >&2
        echo "  Ask the user again, then: date +%s > \"\${TEMP:-/tmp}/pact_merge_approved.lock\"" >&2
        echo "═════════════════════════════════════════" >&2
        exit 1
      fi
    else
      echo "" >&2
      echo "═══ BLOCKED: MERGE TO ${DEFAULT_BRANCH} REQUIRES USER APPROVAL ═══" >&2
      echo "  Merges to ${DEFAULT_BRANCH} are gated — ask the user before merging." >&2
      echo "  When approved, run:" >&2
      echo "    date +%s > \"\${TEMP:-/tmp}/pact_merge_approved.lock\"" >&2
      echo "  Then re-run the merge." >&2
      echo "═══════════════════════════════════════════════════════════════════" >&2
      exit 1
    fi
  fi

  # Block: git push from default branch without approval
  if echo "$COMMAND" | grep -qE '^git push' && [ "$CURRENT_BRANCH" = "$DEFAULT_BRANCH" ]; then
    APPROVAL_FILE="${TEMP:-/tmp}/pact_merge_approved.lock"
    if [ -f "$APPROVAL_FILE" ]; then
      APPROVAL_AGE=$(( $(date +%s) - $(cat "$APPROVAL_FILE" 2>/dev/null || echo 0) ))
      if [ "$APPROVAL_AGE" -lt 120 ]; then
        rm -f "$APPROVAL_FILE"
      else
        rm -f "$APPROVAL_FILE"
        echo "" >&2
        echo "═══ BLOCKED: PUSH APPROVAL EXPIRED ═══" >&2
        echo "  Ask the user again, then: date +%s > \"\${TEMP:-/tmp}/pact_merge_approved.lock\"" >&2
        echo "═════════════════════════════════════════" >&2
        exit 1
      fi
    else
      echo "" >&2
      echo "═══ BLOCKED: PUSH TO ${DEFAULT_BRANCH} REQUIRES USER APPROVAL ═══" >&2
      echo "  Pushes to ${DEFAULT_BRANCH} are gated — ask the user before pushing." >&2
      echo "  When approved, run:" >&2
      echo "    date +%s > \"\${TEMP:-/tmp}/pact_merge_approved.lock\"" >&2
      echo "  Then re-run the push." >&2
      echo "═══════════════════════════════════════════════════════════════════" >&2
      exit 1
    fi
  fi
fi

# ============================================================================
# MULTI-SESSION SAFETY: check remote before commit or push (BLOCKING)
# If another session pushed while we were working, our local branch is behind.
# ============================================================================
if echo "$COMMAND" | grep -qE '^git (commit|push)'; then
  git fetch origin --quiet 2>/dev/null

  CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
  if [ -n "$CURRENT_BRANCH" ]; then
    BEHIND=$(git rev-list HEAD..origin/"$CURRENT_BRANCH" --count 2>/dev/null)
    if [ -n "$BEHIND" ] && [ "$BEHIND" -gt 0 ]; then
      echo "" >&2
      echo "═══ BLOCKED: LOCAL BRANCH IS $BEHIND COMMIT(S) BEHIND REMOTE ═══" >&2
      echo "  Another session pushed changes — pull first to incorporate" >&2
      echo "  their work alongside yours. This keeps everyone's progress intact." >&2
      echo "" >&2
      echo "  TO UNBLOCK:" >&2
      echo "    1. Run: git pull" >&2
      echo "    2. If conflicts arise, resolve them and ask the user" >&2
      echo "    3. Re-run your commit" >&2
      echo "" >&2
      echo "  Recent remote commits you're missing:" >&2
      git log --oneline HEAD..origin/"$CURRENT_BRANCH" 2>/dev/null | head -5 | sed 's/^/    /' >&2
      echo "═════════════════════════════════════════════════════════════" >&2
      exit 1
    fi
  fi
fi

# ============================================================================
# SESSION TRACKING: update sessions.yaml on commit
# ============================================================================
if echo "$COMMAND" | grep -qE '^git commit'; then
  PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
  SESSION_FILE="${PROJECT_ROOT}/.claude/sessions.yaml"
  COMMIT_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # Extract session_id from hook input JSON (per-conversation, no shared state)
  MY_SESSION_ID=$(echo "$INPUT" | grep -o '"session_id"[[:space:]]*:[[:space:]]*"[^"]*"' \
    | head -1 | sed 's/.*"session_id"[[:space:]]*:[[:space:]]*"//;s/"$//')
  [ -z "$MY_SESSION_ID" ] && MY_SESSION_ID=$(cat "${TEMP:-/tmp}/pact_session_id.txt" 2>/dev/null)

  if [ -f "$SESSION_FILE" ] && [ -n "$MY_SESSION_ID" ]; then
    if [ -n "$MY_SESSION_ID" ]; then
      LAST_HASH=$(git log -1 --format=%h 2>/dev/null || echo "unknown")
      COMMIT_MSG=$(echo "$COMMAND" | sed -n 's/.*-m[[:space:]]*"\([^"]*\).*/\1/p' | head -c 60)
      [ -z "$COMMIT_MSG" ] && COMMIT_MSG=$(echo "$COMMAND" | sed -n "s/.*-m[[:space:]]*'\([^']*\).*/\1/p" | head -c 60)
      [ -z "$COMMIT_MSG" ] && COMMIT_MSG="(in progress)"

      python3 -c "
import sys, re

session_file = sys.argv[1]
session_id = sys.argv[2]
timestamp = sys.argv[3]
commit_msg = sys.argv[4]
last_hash = sys.argv[5]

with open(session_file, 'r') as f:
    content = f.read()

esc_id = re.escape(session_id)

content = re.sub(
    r'(- id: \"' + esc_id + r'\".*?\n\s+started: \"[^\"]+\"\n\s+last_activity: )\"[^\"]+\"',
    r'\g<1>\"' + timestamp + '\"',
    content, flags=re.DOTALL
)
content = re.sub(
    r'(- id: \"' + esc_id + r'\".*?last_commit_hash: )\S+',
    r'\g<1>' + last_hash,
    content, flags=re.DOTALL
)
safe_msg = commit_msg.replace('\"', '').replace('\\\\', '')[:60]
content = re.sub(
    r'(- id: \"' + esc_id + r'\".*?last_commit_msg: )\"[^\"]*\"',
    r'\g<1>\"' + safe_msg + '\"',
    content, flags=re.DOTALL
)
content = re.sub(
    r'(- id: \"' + esc_id + r'\".*?status: )\w+',
    r'\g<1>committing',
    content, flags=re.DOTALL
)

with open(session_file, 'w') as f:
    f.write(content)
" "$SESSION_FILE" "$MY_SESSION_ID" "$COMMIT_TIMESTAMP" "$COMMIT_MSG" "$LAST_HASH" 2>/dev/null

      git add "$SESSION_FILE" 2>/dev/null
    fi
  fi
fi

# ============================================================================
# STALENESS WARNINGS on commit (non-blocking)
# ============================================================================
if echo "$COMMAND" | grep -qE '^git commit'; then
  WARNINGS=""
  PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
  EDIT_LOG="${PROJECT_ROOT}/.claude/memory/file_edit_log.yaml"

  # Check: is PENDING_WORK.yaml stale?
  PENDING_WORK="${PROJECT_ROOT}/.claude/memory/PENDING_WORK.yaml"
  if [ -f "$PENDING_WORK" ]; then
    PW_AGE=$(( ($(date +%s) - $(stat -c %Y "$PENDING_WORK" 2>/dev/null || stat -f %m "$PENDING_WORK" 2>/dev/null || echo 0)) / 3600 ))
    if [ "$PW_AGE" -gt 1 ]; then
      WARNINGS="${WARNINGS}  - PENDING_WORK.yaml last updated ${PW_AGE}h ago — update with this session's progress\n"
    fi
  fi

  if [ -f "$EDIT_LOG" ]; then
    TODAY=$(date +%Y-%m-%d)

    if grep -qE "services?/.*$TODAY" "$EDIT_LOG" 2>/dev/null; then
      WARNINGS="${WARNINGS}  - Service file edited → is SYSTEM_MAP.yaml wiring current?\n"
    fi
    if grep -qE "screens?/.*$TODAY" "$EDIT_LOG" 2>/dev/null; then
      WARNINGS="${WARNINGS}  - Screen file edited → is SYSTEM_MAP.yaml screens list current?\n"
    fi
    if grep -qE "(tables?|models?|schema)/.*$TODAY" "$EDIT_LOG" 2>/dev/null; then
      WARNINGS="${WARNINGS}  - Database/model file edited → is SYSTEM_MAP.yaml tables list current?\n"
    fi
    if grep -qE "(providers?|store)/.*$TODAY" "$EDIT_LOG" 2>/dev/null; then
      WARNINGS="${WARNINGS}  - State management file edited → is any reference doc current?\n"
    fi

    # Knowledge system files edited?
    if grep -qE "(research/|bugs/|packages/).*$TODAY" "$EDIT_LOG" 2>/dev/null; then
      WARNINGS="${WARNINGS}  - Knowledge system file edited → is KNOWLEDGE_DIRECTORY.yaml current?\n"
    fi
  fi

  # SYSTEM_MAP freshness
  SMAP="${PROJECT_ROOT}/SYSTEM_MAP.yaml"
  if [ -f "$SMAP" ]; then
    SMAP_DATE=$(grep "Last verified:" "$SMAP" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}')
    if [ -n "$SMAP_DATE" ]; then
      SMAP_AGE=$(( ($(date +%s) - $(date -d "$SMAP_DATE" +%s 2>/dev/null || echo 0)) / 86400 ))
      if [ "$SMAP_AGE" -gt 3 ]; then
        WARNINGS="${WARNINGS}  - SYSTEM_MAP.yaml last verified ${SMAP_AGE} days ago\n"
      fi
    fi
  fi

  if [ -n "$WARNINGS" ]; then
    echo "" >&2
    echo "═══ KNOWLEDGE SYNC (keep the system sharp for future sessions) ═══" >&2
    echo -e "$WARNINGS" >&2
    echo "These are reminders, not blocks." >&2
    echo "════════════════════════════════════════════════════════════════════" >&2
  fi

  # ── Knowledge Directory pairing enforcement (BLOCKING) ──
  # When knowledge system files are staged, KNOWLEDGE_DIRECTORY.yaml must
  # also be staged so the tag index stays in sync.
  STAGED=$(git diff --cached --name-only 2>/dev/null)
  NEEDS_KDIR=false

  # Only require KDIR update for NEW knowledge files (not edits to existing ones).
  # New files have status 'A' in git diff --cached --name-status.
  STAGED_STATUS=$(git diff --cached --name-status 2>/dev/null)

  # New research files? (exclude the index file itself)
  if echo "$STAGED_STATUS" | grep -E '^A.*docs/reference/research/.*\.yaml' | grep -qv '_RESEARCH.yaml'; then
    NEEDS_KDIR=true
  fi
  # New bug solutions? (new entries detected by added SOL- lines)
  if echo "$STAGED" | grep -q '_SOLUTIONS.yaml'; then
    if git diff --cached _SOLUTIONS.yaml 2>/dev/null | grep -q '^\+.*id: SOL-'; then
      NEEDS_KDIR=true
    fi
  fi
  # New package knowledge files? (exclude the format spec)
  if echo "$STAGED_STATUS" | grep -E '^A.*docs/reference/packages/.*\.yaml' | grep -qv '_PACKAGE_KNOWLEDGE'; then
    NEEDS_KDIR=true
  fi
  # New feature flow files?
  if echo "$STAGED_STATUS" | grep -qE '^A.*docs/feature_flows/.*\.yaml'; then
    NEEDS_KDIR=true
  fi

  if [ "$NEEDS_KDIR" = true ]; then
    if ! echo "$STAGED" | grep -q "KNOWLEDGE_DIRECTORY.yaml"; then
      echo "" >&2
      echo "═══ BLOCKED: KNOWLEDGE DIRECTORY UPDATE REQUIRED ═══" >&2
      echo "  Knowledge system file staged but KNOWLEDGE_DIRECTORY.yaml is NOT staged." >&2
      echo "  Add new tags/file entries to docs/reference/KNOWLEDGE_DIRECTORY.yaml." >&2
      echo "" >&2
      echo "  WHY: The Knowledge Directory is your searchability superpower." >&2
      echo "  Updating it means future sessions find your work instantly" >&2
      echo "  instead of opening files one by one." >&2
      echo "" >&2
      echo "  TO UNBLOCK:" >&2
      echo "    1. Update docs/reference/KNOWLEDGE_DIRECTORY.yaml tags section" >&2
      echo "    2. git add docs/reference/KNOWLEDGE_DIRECTORY.yaml" >&2
      echo "    3. Re-run the commit" >&2
      echo "══════════════════════════════════════════════════" >&2
      exit 1
    fi
  fi

  # ── Bug tracker enforcement on fix commits (BLOCKING) ──
  if echo "$COMMAND" | grep -qiE 'fix|bug|resolve|patch|repair|hotfix'; then
    BUG_TOUCHED=false

    if git diff --cached --name-only 2>/dev/null | grep -q '.claude/bugs/'; then
      BUG_TOUCHED=true
    fi
    if [ -f "$EDIT_LOG" ] && grep -q "bugs/.*$TODAY" "$EDIT_LOG" 2>/dev/null; then
      BUG_TOUCHED=true
    fi

    if [ "$BUG_TOUCHED" = false ]; then
      echo "" >&2
      echo "═══ BLOCKED: BUG TRACKER REQUIRED ═══" >&2
      echo "  This commit contains fix/bug keywords but no .claude/bugs/ file" >&2
      echo "  is staged." >&2
      echo "" >&2
      echo "  WHY: Your debugging knowledge is valuable. 5 minutes of documentation" >&2
      echo "  gives the next session a 3-hour head start. That's compound leverage." >&2
      echo "" >&2
      echo "  TO UNBLOCK:" >&2
      echo "    1. Create .claude/bugs/{system}/{system}-NNN.yaml" >&2
      echo "    2. Fill in: root_cause, attempts[], resolution" >&2
      echo "    3. git add .claude/bugs/" >&2
      echo "    4. Re-run the commit" >&2
      echo "═══════════════════════════════════════" >&2
      exit 1
    fi
  fi

  # ── Governance pairing: schema files → SYSTEM_MAP.yaml (BLOCKING) ──
  # Uncomment and customize the file patterns for your project.
  # STAGED=$(git diff --cached --name-only 2>/dev/null)
  # if echo "$STAGED" | grep -qE "(schema|migration|model).*\.(dart|ts|py|rs)"; then
  #   if ! echo "$STAGED" | grep -q "SYSTEM_MAP.yaml"; then
  #     echo "BLOCKED: Schema/model file staged but SYSTEM_MAP.yaml is NOT staged." >&2
  #     echo "  Update the architecture map, then: git add SYSTEM_MAP.yaml" >&2
  #     exit 1
  #   fi
  # fi
fi

exit 0
