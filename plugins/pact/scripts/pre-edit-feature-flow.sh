#!/usr/bin/env bash
# =============================================================================
# PACT PreToolUse Hook — BLOCKS edits to critical system files without a
# feature flow document. Forces writing a lifecycle flow before touching
# security, auth, encryption, database core, or other high-risk code.
#
# Exit 1 = blocked, exit 0 = allowed.
#
# CUSTOMIZE: Edit CRITICAL_PATTERNS and get_flow_category() for your project.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/pact-common.sh"

INPUT=$(cat)

FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

# Only check source files
if [[ ! "$FILE_PATH" =~ \.(dart|ts|tsx|js|jsx|py|rs|go|java|kt|swift|rb|cs)$ ]]; then
  exit 0
fi

# Skip test files
if [[ "$FILE_PATH" =~ /test/ ]]; then
  exit 0
fi

NORM_PATH=$(echo "$FILE_PATH" | sed 's|\\|/|g')

# ============================================================================
# CRITICAL FILE PATTERNS
# These are files where a narrow change can topple the whole structure.
# CUSTOMIZE: Add your project's critical file patterns here.
# ============================================================================
CRITICAL_PATTERNS=(
  # Encryption / Security
  "encryption_service"
  "encryption_provider"
  "crypto_service"
  # Auth
  "auth_service"
  "auth_provider"
  "auth_gate"
  # Backup / Restore
  "backup_service"
  "backup_provider"
  "restore_service"
  # Sync
  "sync_service"
  "sync_provider"
  # App initialization
  "app_startup"
  "app_init"
  # Database core
  # "database.dart"
  # "db_service"
)

# ============================================================================
# MAP PATTERNS TO FLOW DOC CATEGORIES
# Returns the expected flow doc filename for a critical file.
# ============================================================================
get_flow_category() {
  local path="$1"
  if [[ "$path" =~ encrypt|crypto ]]; then
    echo "encryption"
  elif [[ "$path" =~ auth ]]; then
    echo "auth"
  elif [[ "$path" =~ backup|restore ]]; then
    echo "backup"
  elif [[ "$path" =~ sync ]]; then
    echo "sync"
  elif [[ "$path" =~ app_startup|app_init ]]; then
    echo "app_initialization"
  elif [[ "$path" =~ database|db_service ]]; then
    echo "database"
  else
    echo ""
  fi
}

# Check if this file matches any critical pattern
IS_CRITICAL=false
for pattern in "${CRITICAL_PATTERNS[@]}"; do
  if [[ "$NORM_PATH" =~ $pattern ]]; then
    IS_CRITICAL=true
    break
  fi
done

if [ "$IS_CRITICAL" = false ]; then
  exit 0
fi

CATEGORY=$(get_flow_category "$NORM_PATH")

if [ -z "$CATEGORY" ]; then
  exit 0
fi

# Look for a flow doc matching this category
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
FLOW_DIR="docs/feature_flows"

FOUND_FLOW=false
for ext in yaml md; do
  if [ -f "${PROJECT_ROOT}/${FLOW_DIR}/${CATEGORY}_flow.${ext}" ]; then
    FOUND_FLOW=true
    break
  fi
done

if [ "$FOUND_FLOW" = false ]; then
  cat >&2 <<EOF
BLOCKED: You are editing a CRITICAL system file (${CATEGORY}) without a Feature Flow document.

Before modifying this file, you MUST:
1. Create docs/feature_flows/${CATEGORY}_flow.yaml with the full lifecycle state machine
2. Cover ALL states: fresh_install, normal_open, background, force_close_reopen, error_paths
3. Include: invariants, assumes, lost/persisted, danger flags, gotchas
4. Present the flow verbally to the user and get confirmation
5. Only THEN edit this file

See the feature_flow.yaml template for the YAML format.
EOF
  exit 1
fi

exit 0
