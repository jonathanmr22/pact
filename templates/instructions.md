# Project Instructions — PACT Template

**Version:** 0.1.0
**Last Updated:** YYYY-MM-DD

---

## Session Start (Every Conversation)

At the start of every conversation, the agent MUST:

1. State: *"I have read and will follow all project rules."*
2. Read `.claude/memory/PENDING_WORK.yaml` — check for in-progress tasks
3. Scan `.claude/memory/file_edit_log.yaml` — note recently-edited files
4. List the cognitive redirections below from memory

---

## Cognitive Redirections

> These are not rules. They are questions you ask yourself at specific moments.
> Rules get skimmed. Questions engage reasoning.
>
> **You have autonomy to add new redirections.** When you notice yourself
> making an assumption or falling into a pattern, add a new question here.
> Future sessions inherit your self-awareness.

- **When about to edit any file:** *"What depends on this, and what does this depend on?"* — trace dependencies in both directions. Read SYSTEM_MAP.yaml.

- **When declaring a task done:** *"What did my changes just make stale?"* — code correctness is necessary but not sufficient. Did you update the architecture map? The docs? The tests?

- **When a package/library doesn't behave as expected:** *"Do I actually know this package, or am I guessing?"* — if you haven't verified this package's behavior IN THIS SESSION, you do not know it. Check `docs/reference/packages/{name}.yaml` first. If insufficient, research online and SAVE findings.

- **When the user makes a correction:** *"Is this right?"* — verify independently before agreeing. Agreement is a conclusion, not a starting point.

- **When about to remove or replace code:** *"Why does this code exist?"* — read the comments above the code. If there's a comment explaining WHY, understand that reason and confirm it no longer applies before removing.

- **When finding an objection to your own solution:** *"Is this objection real, or am I folding?"* — stress-test the objection before abandoning a good solution. Ask: does this problem actually occur in practice?

---

## Semantic Code Safety (Hooks Can't Catch These)

<!-- CUSTOMIZE: Add rules specific to your framework and patterns -->

- **Always read a file before editing it** (hook-enforced, but understand WHY)
- **Fresh-read before save** — never use stale entity data in save methods
- **No empty catch blocks** — always log the error
- **Use braces on all control flow** (`if`/`else`/`for`/`while`)
- **Check your cache consistency** — when modifying provider add/update/delete methods, update ALL caches (list AND map)

---

## Hook-Enforced Rules (Reference Only)

> These rules are mechanically enforced by PreToolUse/PostToolUse hooks.
> The agent cannot violate them. Documented here for transparency.

| Rule | Hook | Action |
|------|------|--------|
| No forbidden imports | pre-edit-rules.sh | BLOCKS edit |
| No hardcoded secrets | pre-edit-rules.sh | BLOCKS edit |
| Must read file before editing | pre-edit-rules.sh + post-read-tracker.sh | BLOCKS edit |
| File size > 800 lines | post-edit-warnings.sh | WARNS |
| Import count > 25 | post-edit-warnings.sh | WARNS |
| Static analysis after edit | silent-linter.sh | Shows errors only |
| File edit timestamps logged | post-edit-timestamp.sh | Auto-logs |

---

## Workflow Rules

- **Seek clarification when vague** — don't implement multiple alternatives
- **Read SYSTEM_MAP.yaml before editing feature code** — know the full data flow
- **Write a feature flow doc before rewriting critical systems** — see `docs/feature_flows/`
- **Research packages before writing workarounds** — check `docs/reference/packages/`
- **After code changes, verify with analyzer before declaring done**
- **Update PENDING_WORK.yaml** with what was done and what's pending

### Before Declaring Done

Ask: **"What did my changes just make stale?"**

- Added/changed a database table? → Update SYSTEM_MAP.yaml
- Added/changed a service/provider? → Update SYSTEM_MAP.yaml
- Added/changed a screen? → Update SYSTEM_MAP.yaml
- Changed a critical system? → Update the feature flow doc
- Updated PENDING_WORK.yaml with status

---

## Architecture

<!-- CUSTOMIZE: Brief description of your tech stack -->

- **Database:** (e.g., SQLite via Drift, PostgreSQL, etc.)
- **State Management:** (e.g., Riverpod, Redux, Zustand, etc.)
- **Backend:** (e.g., Supabase, Firebase, custom API, etc.)
- **Key files:** See `SYSTEM_MAP.yaml` for full wiring
