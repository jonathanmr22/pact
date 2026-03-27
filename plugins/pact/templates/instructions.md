# Project Instructions — PACT Template

**Version:** 0.2.0
**Last Updated:** YYYY-MM-DD

---

## Session Start (Every Conversation)

At the start of every conversation, the agent MUST:

1. State: *"I have read and will follow all project rules."*
2. Read `.claude/memory/PENDING_WORK.yaml` — check for in-progress tasks
3. Scan `.claude/memory/file_edit_log.yaml` — note recently-edited files, fresh-read before assuming
4. Read `.claude/sessions.yaml` — check for other active sessions. If another session is active or recently committed (within the last hour), tell the user: *"Another session is active (started [time], last commit [hash]). I'll pull before committing to avoid conflicts."*
5. List the cognitive redirections below from memory

---

## Cognitive Redirections

> These are not rules. They are questions you ask yourself at specific moments.
> Rules get skimmed. Questions engage reasoning. Each one exists because a past
> session made the mistake it prevents.
>
> **You have autonomy to add new redirections.** When you notice yourself
> making an assumption, jumping to a conclusion, or defaulting to a bad pattern —
> add a new question here. Future sessions inherit your self-awareness.
> This is how the system evolves.

- **When the user makes a correction:** *"Is this right?"* — verify independently before agreeing. Agreement is a conclusion, not a starting point.

- **When encountering a technology/library/API in code:** *"What does this project actually use?"* — don't assume the tech stack from one data point. Read the Architecture section or SYSTEM_MAP.yaml before guessing.

- **When about to write code based on memory:** *"Have I actually read this file, or am I guessing?"* — pattern-matching from other files is not the same as knowing this file. Read it.

- **When declaring a task done:** *"What wasn't checked?"* — static analysis clean ≠ correct. Hooks clean ≠ correct. What ripple effects did you not verify?

- **When about to say "I'm satisfied":** *"What happens to this system tomorrow?"* — point-in-time correctness doesn't survive. Will the docs still be accurate after the next session's changes?

- **When a doc says X but you haven't verified:** *"Is this still true?"* — docs drift. Code is truth. If a doc says one thing but the code does another, trust the code.

- **When about to edit any file:** *"What depends on this, and what does this depend on?"* — trace dependencies in both directions. Table → service → state → screen. Screen → state → service → table. Read SYSTEM_MAP.yaml. Stop expanding when the next hop no longer serves the user's actual intention.

- **When about to remove or replace code:** *"Why does this code exist?"* — read the comments above, inline, and surrounding the code you're about to delete. Comments document intent. If there's a comment explaining WHY this code was written, you MUST understand that reason and confirm it no longer applies before removing. Pattern-matching "this looks wrong" is not understanding. If there are no comments, check git blame or ask. Deleting code you didn't understand is destroying someone's work.

- **When a package/library doesn't behave as expected:** *"Do I actually know this package, or am I guessing?"* — if you haven't verified this package's behavior IN THIS SESSION, you do not know it. Your training data is stale and incomplete. Follow this lookup order: **(1)** Check `docs/reference/packages/{package_name}.yaml` — a previous session may have already researched this. **(2)** If the file exists and covers your question, use it. **(3)** If not, STOP writing code and RESEARCH: WebSearch for docs, WebFetch the API reference, check GitHub issues. **(4)** SAVE your findings to the package knowledge file so the next session doesn't repeat this work. The spiral starts here: one "workaround" for assumed behavior becomes two, becomes five, becomes a rewrite. Every bespoke workaround you write instead of reading the docs is technical debt born from arrogance. The correct response to "this doesn't work like I expected" is NEVER "let me hack around it" — it's "let me find out how it actually works."

- **When proposing architecture for security, privacy, or cryptography:** *"Have I researched what exists, or am I inventing from scratch?"* — if you haven't searched for established patterns, you are almost certainly proposing something weaker than what's available. Your training data is 1+ years stale for security patterns. ALWAYS search first: look at how Signal, Matrix, Keybase, age, and academic systems solve the same problem. The correct response to "how do we protect X" is NEVER "here's my idea" — it's "let me see what the industry has built."

- **When finding an objection to your own solution:** *"Is this objection real, or am I folding?"* — when you propose a solution and then find a potential problem during review, your job is to STRESS-TEST the objection, not abandon the solution. Ask: (1) Does this problem actually occur in practice? (2) Does the underlying system already handle it? (3) Can I verify with code/docs instead of guessing? The pattern that fails: propose correct solution → find hypothetical concern → immediately abandon it and propose something worse → user has to rescue the original idea. Resilience in problem-solving means defending good ideas against weak objections while remaining open to strong ones.

- **When something is broken or regressed:** *"Can I fix this forward?"* — NEVER revert from git history unless the user specifically asks for a revert. "Broken" means "fix the current code." `git show` and `git checkout` of old files are escapes from understanding the problem. Reverting destroys the work that went into the new approach and teaches nothing. The correct response to "this doesn't work" is NEVER "let me restore the old version" — it's "let me understand why and fix it."

- **When about to say "I can't do X":** *"What CLI tool handles this?"* — you have Bash. Search for tools (ffmpeg, imagemagick, pandoc, jq, etc.). "I can't process video" when ffmpeg is one install away is not a capability limitation — it's a failure to think. The correct response to "can you do X with file type Y" is NEVER "I can't" — it's "let me find the right tool."

- **When building a complex visual (heat maps, animations, shaders, charts, custom painters):** *"Can I prototype this outside the framework first?"* — full app rebuilds are expensive and you can't see intermediate results. Use adjacent tools to iterate visually: Python (matplotlib, folium) for data viz, Shadertoy/GLSL sandbox for shaders, HTML/CSS for layouts, PIL for image processing. Create a subfolder in `cutting_room/`, write a generator script, and log every trial in `trials.yaml` with parameters, result (pass/fail/partial), and WHY it failed or succeeded. Only move the winning config to the app after you've nailed the look locally. **This is not optional for visual work.**

- **Before declaring a task done:** *"Did I do everything the user asked in the last request?"* — re-read their message word by word. If they asked for 3 things and you did 1, you're not done. If they asked for a label change AND a behavior change, the label alone is not the fix. Partial delivery of explicit requests is worse than no delivery — it creates the illusion of progress while leaving the user's actual needs unmet. Check every item before committing.

- **After finishing any UI build (new flow, modal, sheet, chip, overlay):** *"Am I the user right now?"* — walk through the ENTIRE user journey for the feature you just built. Open the app. What do you see first? Tap the thing. What happens? Try to do the thing it's supposed to let you do. Is the text right? Is anything cut off? Can you correct a wrong value? What happens at edge cases — zero items, many items, missing data, interrupted flow? Every "looks fine to me" is a bug you didn't find. This is not optional — past sessions have shipped UI with placeholder text, broken correction flows, and internal jargon visible to users. That happens when you skip this step.

- **When something doesn't work:** *"Is this a bug? Has it been solved before?"* — a bug is ANY of these: (1) code that worked and then broke, (2) a feature that was never wired correctly, (3) a UI action that produces an error, (4) a feature that exists but fails on use, (5) behavior that contradicts the user's stated intention. If the user reports something doesn't work, **it's a bug** — don't reclassify it as "feature wiring" or "architecture gap" to avoid the bug protocol. Check `.claude/bugs/_SOLUTIONS.yaml` for matching tags BEFORE writing code. If you find a past solution, apply it instead of re-investigating. If you DON'T find one, create the bug file NOW (not after you fix it) and log every attempt in real time. Your failed attempts are as valuable as your successes — they prevent the next session from wasting hours on dead ends.

---

## Semantic Code Safety (Hooks Can't Catch These)

<!-- CUSTOMIZE: Add rules specific to your framework and patterns -->

- **Always read a file before editing it** (hook-enforced, but understand WHY)
- **Fresh-read before save** — never use stale entity data in save methods. Always re-fetch from state before writing.
- **No empty catch blocks** — always log the error with context
- **Use braces on all control flow** (`if`/`else`/`for`/`while`)
- **Check your cache consistency** — when modifying provider/store add/update/delete methods, update ALL caches (list AND map). Data saving to DB but not showing in UI = stale cache, not a save bug.
- **NEVER GUESS on encryption, auth, DB connection, or security syntax** — ALWAYS verify against official docs first
- **NEVER propose security/privacy architecture without research** — search for established patterns BEFORE proposing a design. If you propose from training data alone, you WILL propose something weaker than what exists.
- **Research before workarounds — MANDATORY.** When a package doesn't behave as expected, you MUST: (1) check `docs/reference/packages/{name}.yaml` for existing knowledge, (2) if not sufficient, research online, (3) SAVE findings to the package knowledge file. "It doesn't work like I thought" means your mental model is wrong, not that the package is broken. One workaround becomes a spiral. Research first, code second.
- **No overflow** — every screen must be responsive. Wrap content appropriately for your framework.
- **Before ANY schema/migration changes:** ask clarifying questions (CASCADE/SET NULL/RESTRICT), show example data flow, wait for user confirmation
- **All database migrations MUST be idempotent** — failed migrations can leave the DB half-migrated. Guard against re-execution.
- **Diagnostic logging on every new code path — no blind spots.** Every async flow (network, background tasks, sync, IPC) must log: entry with context, success with result summary, failure with error + state. If debugging would require a rebuild to see what happened, you missed a log.
- **Entity ID consistency — ONE key type per context, no mixing.** When creating a `Map<String, ...>` keyed by entity, add a comment documenting the key format. Never build composite keys via string interpolation without verifying the input isn't already prefixed (double-prefix bug).

---

## Hook-Enforced Rules (Reference Only)

> These rules are mechanically enforced by PreToolUse/PostToolUse hooks.
> The agent cannot violate them. Documented here for transparency.

| Rule | Hook | Action |
|------|------|--------|
| No forbidden imports | pre-edit-rules.sh | BLOCKS edit |
| No hardcoded secrets | pre-edit-rules.sh | BLOCKS edit |
| Must read file before editing | pre-edit-rules.sh + post-read-tracker.sh | BLOCKS edit |
| Issue tracker gate (must document bug before fixing) | pre-edit-rules.sh | BLOCKS edit |
| No git force-push to main/master | pre-bash-guard.sh | BLOCKS bash |
| No git reset --hard | pre-bash-guard.sh | BLOCKS bash |
| No --no-verify on git commands | pre-bash-guard.sh | BLOCKS bash |
| No destructive file operations (rm -rf project dirs) | pre-bash-guard.sh | BLOCKS bash |
| Multi-session safety: blocks commit if local behind remote | pre-bash-guard.sh | BLOCKS bash |
| Bug tracker required for fix commits | pre-bash-guard.sh | BLOCKS bash |
| Critical file protection: requires feature flow doc | pre-edit-feature-flow.sh | BLOCKS edit |
| File size > 800 lines | post-edit-warnings.sh | WARNS |
| Import count > 25 | post-edit-warnings.sh | WARNS |
| Modal without scroll wrapper | post-edit-warnings.sh | WARNS |
| Code deletion with comments removed | post-edit-warnings.sh | WARNS |
| Workaround/hack language in new code | post-edit-warnings.sh | WARNS |
| Name-based matching instead of ID | post-edit-warnings.sh | WARNS |
| Static analysis after edit | silent-linter.sh | Shows errors only |
| File edit timestamps logged | post-edit-timestamp.sh | Auto-logs |
| Session registered on start | session-register.sh | Auto-logs |

---

## Workflow Rules

- **Feature Flow Review (MANDATORY)** — before rewriting or adding any critical feature, write a full lifecycle flow doc first. See `docs/feature_flows/` and the feature_flow.yaml template.
- **Seek clarification when vague** — don't implement multiple alternatives
- **Never suggest deferring** — do the work, don't punt it. If a task is large, break it down and start working.
- **Stay anchored to the user's exact goal** — re-read their words before every decision
- **Dead or purposeless code = always a mistake.** Flag it, predict what it was supposed to do, suggest a fix.
- **Verify before agreeing** — when the user makes a correction or assertion, independently verify it against code/docs/schema before agreeing. Agreement is a conclusion, not a starting point.
- **Industry best practices by default** — implement the correct pattern without presenting it as optional.
- **Never overwrite plan files** — always create new plan documents for new features.
- **Optimization requires flow context** — before optimizing code, consider where it sits in the user journey. Hot paths matter; cold paths don't.
- **Temporal governance — update what you changed.** When you modify code, you ALSO modified the accuracy of every doc that describes that code. If you added a table, the architecture map is stale. If you added a provider method, the cheatsheet is stale. If you changed a service, the SYSTEM_MAP may be stale. Static analysis clean ≠ governance clean.

### Before Declaring Done

Ask: **"What did my changes just make stale?"**

- Added/changed a database table? → Update SYSTEM_MAP.yaml
- Added/changed a service/provider? → Update SYSTEM_MAP.yaml
- Added/changed a screen? → Update SYSTEM_MAP.yaml
- Changed a critical system? → Update the feature flow doc
- Fixed a bug? → Document in `.claude/bugs/{system}/{system}-NNN.yaml`
- Updated PENDING_WORK.yaml with status

### Git & Data Safety

- **Always push immediately after committing** — never leave local ahead of remote
- **Always pull before committing** — the pre-bash-guard hook BLOCKS commits if local is behind remote
- **Session coordination via `.claude/sessions.yaml`** — check for other active sessions when starting work
- **Don't erase work from other sessions** — ask which changes to include when committing
- **Notify user before deleting unused code** (unused imports are safe to auto-fix)

---

## Architecture

<!-- CUSTOMIZE: Brief description of your tech stack -->

- **Database:** (e.g., SQLite via Drift, PostgreSQL, etc.)
- **State Management:** (e.g., Riverpod, Redux, Zustand, etc.)
- **Backend:** (e.g., Supabase, Firebase, custom API, etc.)
- **Key files:** See `SYSTEM_MAP.yaml` for full wiring
