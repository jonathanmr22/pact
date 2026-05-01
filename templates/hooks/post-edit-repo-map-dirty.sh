#!/usr/bin/env bash
# PostToolUse hook: real-time repo-map rebuild after every tracked-file edit.
#
# Design:
#   1. Touches the `repo_map_dirty` flag (consumed by builder loop).
#   2. If no builder is already running, spawns one in the background.
#   3. The builder loops while the dirty flag exists — so a flurry of edits
#      collapses into a single tail rebuild that captures the final state.
#   4. Builds are cached (~1s on 1284 files). The dashboard polls the JSON,
#      so the user sees the new state within ~1-3s of any edit.
#
# Tracked dirs match scripts/repo_map.py INCLUDE_DIRS: lib/, scripts/,
# supabase/functions/. Generated files (*.g.dart etc.) are excluded.
#
# Why this pattern: if we naïvely ran the build inline, every Edit/Write
# tool call would block for ~1s. If we naïvely backgrounded one build per
# edit, 10 rapid edits would queue 10 builds. The loop-while-dirty pattern
# guarantees: at most one builder running, and it always sees the latest
# state before exiting.
set -euo pipefail

INPUT=$(cat)
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
SCRIPT="$ROOT/scripts/repo_map.py"
DIRTY="$ROOT/.claude/memory/repo_map_dirty"
LOCK="$ROOT/.claude/memory/repo_map_build.lock"

FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
    | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Normalize path separators for matching.
NORM=$(echo "$FILE_PATH" | sed 's|\\|/|g')

# Only fire on source files in tracked dirs with tracked extensions.
case "$NORM" in
    */lib/*.dart|*/scripts/*.py|*/supabase/functions/*.ts|*/supabase/functions/*.tsx|*/supabase/functions/*.js|*/feature_flows/*.yaml)
        case "$NORM" in
            *.g.dart|*.freezed.dart|*.mocks.dart|*.gr.dart) exit 0 ;;
        esac
        ;;
    *)
        exit 0
        ;;
esac

# Skip if the build script doesn't exist (fresh clone, mid-migration).
if [ ! -f "$SCRIPT" ]; then
    exit 0
fi

mkdir -p "$ROOT/.claude/memory" 2>/dev/null || true

# 1. Mark dirty so any running builder loop sees the new state.
touch "$DIRTY"

# 2. If a builder is already running, it'll consume the dirty flag — no need
#    to spawn another. We check both the lock file's existence AND that the
#    PID it names is still alive (stale lockfiles from crashes are cleaned
#    up by spawning fresh).
if [ -f "$LOCK" ]; then
    PID=$(cat "$LOCK" 2>/dev/null || true)
    if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
        # Live builder; it'll see the dirty flag on its next iteration.
        exit 0
    fi
    # Stale lock — clean up before spawning.
    rm -f "$LOCK" 2>/dev/null || true
fi

# 3. Spawn a builder loop in the background. It consumes the dirty flag,
#    runs the build, and re-checks the flag; if another edit landed during
#    the build, it loops. Detached so this hook returns immediately.
(
    # Record our PID so the next hook invocation can detect us.
    echo $BASHPID > "$LOCK"
    trap 'rm -f "$LOCK" 2>/dev/null || true' EXIT

    while [ -f "$DIRTY" ]; do
        # Consume the dirty flag BEFORE the build so edits arriving during
        # the build re-set it and trigger another iteration.
        rm -f "$DIRTY" 2>/dev/null || true

        # Run the cached build. Timeout caps any single iteration.
        timeout 60 python "$SCRIPT" build --quiet </dev/null >/dev/null 2>&1 || true
    done
) </dev/null >/dev/null 2>&1 &
disown

exit 0
