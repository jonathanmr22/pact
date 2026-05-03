#!/usr/bin/env bash
# inject-timestamp.sh — UserPromptSubmit hook
#
# Injects the current local time into the agent's context as additionalContext
# on every user message. Replaces the failing pattern of asking the agent to
# call `date` / `Get-Date` itself every turn — agents skip that often, but a
# hook never forgets.
#
# DESIGN PROPERTIES:
#   - Cross-platform: powershell.exe on Windows (Git Bash / Cygwin / MSYS),
#     `date` on Linux/macOS
#   - Configurable timezone label via the PACT_TIMEZONE_LABEL env var
#     (default: empty — no label appended)
#   - Configurable date format via the PACT_TIME_FORMAT env var
#     (default: "yyyy-MM-dd h:mm tt" on Windows, "+%Y-%m-%d %-l:%M %p" on Unix)
#   - Silent on failure (never breaks the conversation)
#   - No Python, no YAML, no external deps — single shell script
#
# CONFIGURATION:
#   Set in your shell rc or in .claude/settings.json env section:
#     export PACT_TIMEZONE_LABEL="CST"          # appended to time
#     export PACT_TIME_FORMAT="yyyy-MM-dd h:mm tt"  # Windows format
#     export PACT_TIME_LOCATION_HINT="Minneapolis local"  # parenthetical
#
# Why a label override (not just `date +%Z`)? Some users want a stable label
# year-round even when the wall clock crosses DST boundaries (e.g. a "CST"
# user who doesn't want to switch to "CDT" half the year). Empty default
# means the hook stays silent on locality unless you opt in.

set -uo pipefail

# Drain stdin so the harness doesn't see a broken pipe — we don't need the
# prompt body, just the trigger.
cat >/dev/null 2>&1 || true

# Read configuration with sane defaults.
TZ_LABEL="${PACT_TIMEZONE_LABEL:-}"
LOCATION_HINT="${PACT_TIME_LOCATION_HINT:-}"

# Detect platform and fetch timestamp.
TS=""
if command -v powershell.exe >/dev/null 2>&1; then
    # Windows (Git Bash / MSYS / Cygwin) — read Windows system clock directly.
    # PowerShell respects the Windows locale and gives us the user's actual
    # wall-clock time, regardless of any TZ env var Git Bash might be ignoring.
    WIN_FORMAT="${PACT_TIME_FORMAT:-yyyy-MM-dd h:mm tt}"
    TS=$(powershell.exe -NoProfile -NoLogo -Command "Get-Date -Format '$WIN_FORMAT'" 2>/dev/null \
         | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
elif command -v date >/dev/null 2>&1; then
    # Linux / macOS — use date. Default format mirrors the PowerShell output
    # for visual consistency across platforms. GNU date supports %-l (no pad);
    # macOS BSD date does not — fall back to %l (space-padded) if needed.
    UNIX_FORMAT="${PACT_TIME_FORMAT:-+%Y-%m-%d %-l:%M %p}"
    TS=$(date "$UNIX_FORMAT" 2>/dev/null | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    if [ -z "$TS" ]; then
        # %-l unsupported (BSD date) — retry with %l and trim leading space
        TS=$(date "+%Y-%m-%d %l:%M %p" 2>/dev/null | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    fi
fi

# Bail silently if we couldn't get a time.
if [ -z "$TS" ]; then
    echo '{}'
    exit 0
fi

# Compose the final time string with optional label.
if [ -n "$TZ_LABEL" ]; then
    TIME_STR="[$TS $TZ_LABEL]"
else
    TIME_STR="[$TS]"
fi

# Compose the optional location hint suffix.
HINT_STR=""
if [ -n "$LOCATION_HINT" ]; then
    HINT_STR=" ($LOCATION_HINT)"
fi

# Emit additionalContext via JSON. The agent sees this as a SystemReminder at
# the top of the turn — no tool call required to know the time.
printf '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"Current time: %s%s. Use this for any user-facing timestamps you emit this turn — do not call shell commands to fetch time."}}' "$TIME_STR" "$HINT_STR"
