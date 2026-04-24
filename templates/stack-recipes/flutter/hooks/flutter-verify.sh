#!/usr/bin/env bash
# flutter-verify.sh — run flutter analyze after .dart edits
#
# PostToolUse hook for Flutter projects. Fires after Edit/Write tool calls
# that touch .dart files. Surfaces analyzer errors immediately so the agent
# sees them before moving on.
#
# Wire in .claude/settings.json under hooks.PostToolUse:
#   {
#     "matcher": "Edit|Write",
#     "hooks": [
#       { "type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/flutter-verify.sh" }
#     ]
#   }
#
# Output goes to stderr so the agent sees it. Exit 0 always — this is a
# WARN hook, not a BLOCK hook. If you want to block on analyzer errors,
# wrap this in a pre-bash-guard rule that requires `flutter analyze` clean
# before commits.

set -u

INPUT=$(cat)

FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

# Only run if the edited file is .dart
if ! echo "$FILE_PATH" | grep -qE '\.dart$'; then
  echo '{}'
  exit 0
fi

# Skip generated files (.g.dart, .freezed.dart, etc.)
if echo "$FILE_PATH" | grep -qE '\.(g|freezed|chopper|swagger|gr)\.dart$'; then
  echo '{}'
  exit 0
fi

# Find project root (directory containing pubspec.yaml)
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
while [ "$PROJECT_ROOT" != "/" ] && [ ! -f "$PROJECT_ROOT/pubspec.yaml" ]; do
  PROJECT_ROOT=$(dirname "$PROJECT_ROOT")
done

if [ ! -f "$PROJECT_ROOT/pubspec.yaml" ]; then
  echo '{}'
  exit 0
fi

# Run flutter analyze on the lib/ directory (or the edited file's directory)
# Limit output to errors+warnings (skip info-level lints)
ANALYZE_OUTPUT=$(cd "$PROJECT_ROOT" && flutter analyze --no-fatal-warnings --no-fatal-infos lib/ 2>&1 | grep -E '^\s*(error|warning)' | head -20)

if [ -n "$ANALYZE_OUTPUT" ]; then
  echo "" >&2
  echo "── flutter analyze ──" >&2
  echo "$ANALYZE_OUTPUT" >&2
  echo "" >&2
fi

echo '{}'
exit 0
