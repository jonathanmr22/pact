#!/usr/bin/env bash
# auto-compact-counter.sh
#
# Counts user prompts per Claude Code session and inserts a system message
# every N prompts (default 350) telling the agent to run /compact. Prevents
# the conversation from running into context limits without warning.
#
# Wire in .claude/settings.json under hooks.UserPromptSubmit (matcher: ".*").
# Counter is keyed by parent process ID, so each session has its own count.

COUNTER_FILE="${TEMP:-/tmp}/claude_msg_count_${PPID}"

# Read current count
if [ -f "$COUNTER_FILE" ]; then
    COUNT=$(cat "$COUNTER_FILE")
else
    COUNT=0
fi

# Increment
COUNT=$((COUNT + 1))
echo "$COUNT" > "$COUNTER_FILE"

THRESHOLD=350

# Check threshold
if [ "$COUNT" -ge "$THRESHOLD" ]; then
    # Reset counter so the message doesn't repeat every prompt
    echo "0" > "$COUNTER_FILE"
    # Tell the agent to compact
    echo -n "{\"systemMessage\":\"MESSAGE COUNT HIT $THRESHOLD. Run /compact now. Focus on: current task context, recent code changes, architectural decisions, and any unresolved bugs. Discard verbose tool outputs and old exploration.\"}"
else
    echo -n '{}'
fi
