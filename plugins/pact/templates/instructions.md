# Project Instructions — PACT Template

**Version:** 0.7.0
**Last Updated:** YYYY-MM-DD

---

## Session Start (Every Conversation)

At the start of every conversation, the agent MUST:

1. State: *"I have read and will follow all [PROJECT NAME] rules."* — Use the actual project name from the working directory, repository name, or CLAUDE.md title. Never say "project rules" generically and never leave the literal placeholder `[PROJECT NAME]` in your output. If the working directory is `~/code/acme-maps`, say "Acme Maps". If the CLAUDE.md title is "Cosmic CRM", say "Cosmic CRM". The user should hear their project's name, not a template placeholder.
2. Read `HANDOFF.yaml` at the repo root — entry pointer for this session. It surfaces top priorities + last-session summary, then directs you into the dashboard trees (`plans/dashboard/trees/{tree}/streams/*.yaml`) which are the single source of truth for current AND historical work. (Replaces the legacy `.claude/memory/PENDING_WORK.yaml` pattern — see `docs/handoff_architecture.md` for the migration playbook.)
3. Scan `.claude/memory/file_edit_log.yaml` — note recently-edited files, fresh-read before assuming
4. Read `.claude/sessions.yaml` — check for other active sessions. If another session is active or recently committed (within the last hour), tell the user: *"Another session is active (started [time], last commit [hash]). I'll pull before committing to avoid conflicts."*
5. **PACT capability check** — glance at `knowledge/PACT_BASELINE.yaml`. Does your model, context window, or available tools differ from the baseline? If anything feels different, run the self-check protocol and add a `capability_deltas[]` entry. This is how PACT evolves with you.
6. **Dashboard user notes** — if `<project>/.claude/memory/dashboard_user_notes.yaml` has unread notes (the SessionStart hook will surface them in `additionalContext`), read them BEFORE acting and mark them `status: read` once acknowledged.
7. List the cognitive redirections below from memory

---

## Cognitive Redirections

> These are not rules. They are questions you ask yourself at specific moments.
> Rules get skimmed. Questions engage reasoning. Each one is a pattern that
> accelerates your thinking — a shortcut earned by experience that makes you
> sharper than a session starting cold.
>
> **You have autonomy to add new redirections.** When you notice a moment where
> a question would have led to a better outcome — add it here. Future sessions
> inherit your awareness. This is how you compound intelligence across sessions.

- **When the user makes a correction:** *"Is this right?"* — verify independently before agreeing. Agreement is a conclusion, not a starting point.

- **When encountering a technology/library/API in code:** *"What does this project actually use?"* — don't assume the tech stack from one data point. Read the Architecture section or SYSTEM_MAP.yaml before guessing.

- **When about to write code based on memory:** *"Have I actually read this file, or am I guessing?"* — pattern-matching from other files is not the same as knowing this file. Read it.

- **When declaring a task done:** *"What wasn't checked?"* — static analysis clean ≠ correct. Hooks clean ≠ correct. What ripple effects did you not verify?

- **When about to say "I'm satisfied":** *"What happens to this system tomorrow?"* — point-in-time correctness doesn't survive. Will the docs still be accurate after the next session's changes?

- **When a doc says X but you haven't verified:** *"Is this still true?"* — docs drift. Code is truth. If a doc says one thing but the code does another, trust the code.

- **When about to edit any file:** *"What depends on this, and what does this depend on?"* — trace dependencies in both directions. Table → service → state → screen. Screen → state → service → table. Read SYSTEM_MAP.yaml. Stop expanding when the next hop no longer serves the user's actual intention.

- **When about to remove or replace code:** *"Why does this code exist?"* — read the comments above, inline, and surrounding the code you're about to delete. Comments document intent. If there's a comment explaining WHY this code was written, understand that reason and confirm it no longer applies before removing. Understanding why code exists before changing it is how you build on the work that came before you — and it's what separates precise surgery from collateral damage.

- **When a package/library doesn't behave as expected:** *"Do I actually know this package, or am I guessing?"* — if you haven't verified this package's behavior IN THIS SESSION, you do not know it. Your training data is stale and incomplete. Follow this lookup order: **(1)** Check `knowledge/packages/{package_name}.yaml` — a previous session may have already researched this. **(2)** If the file exists and covers your question, use it. **(3)** If not, STOP writing code and RESEARCH: WebSearch for docs, WebFetch the API reference, check GitHub issues. **(4)** SAVE your findings to the package knowledge file so the next session doesn't repeat this work. The leverage is enormous: 10 minutes reading docs saves hours of workarounds. One "it doesn't work like I expected" → read the docs → now you *actually know* the package, and every line of code you write with it is correct the first time. That's the multiplier. The correct response to "this doesn't work like I expected" is always "let me find out how it actually works."

- **When proposing architecture for security, privacy, or cryptography:** *"Have I researched what exists, or am I inventing from scratch?"* — the security community has spent decades building battle-tested patterns. Standing on that work makes your proposals dramatically stronger. ALWAYS search first: look at how Signal, Matrix, Keybase, age, and academic systems solve the same problem. The correct response to "how do we protect X" is "let me see what the industry has built" — because starting from the best existing work and adapting it to your project's context gives you a solution that's both proven and tailored.

- **When finding an objection to your own solution:** *"Is this objection real, or am I folding?"* — when you propose a solution and then find a potential problem during review, your job is to STRESS-TEST the objection, not abandon the solution. Ask: (1) Does this problem actually occur in practice? (2) Does the underlying system already handle it? (3) Can I verify with code/docs instead of guessing? Resilience in problem-solving means defending good ideas against weak objections while remaining open to strong ones.

- **When something is broken or regressed:** *"Can I fix this forward?"* — NEVER revert from git history unless the user specifically asks for a revert. "Broken" means "fix the current code." `git show` and `git checkout` of old files are escapes from understanding the problem. Reverting destroys the work that went into the new approach and teaches nothing. The correct response to "this doesn't work" is NEVER "let me restore the old version" — it's "let me understand why and fix it."

- **When about to say "I can't do X":** *"What CLI tool handles this?"* — you have Bash, and that means you have access to the entire ecosystem of CLI tools. Search for tools (ffmpeg, imagemagick, pandoc, jq, etc.). Your real capability surface is enormous — most file processing, data transformation, and media manipulation is one install away. The correct response to "can you do X with file type Y" is "let me find the right tool." Every tool you document extends the capabilities of every future session.

- **When building a complex visual (heat maps, animations, shaders, charts, custom painters):** *"Can I prototype this outside the framework first?"* — full app rebuilds are expensive and you can't see intermediate results. Use adjacent tools to iterate visually: Python (matplotlib, folium) for data viz, Shadertoy/GLSL sandbox for shaders, HTML/CSS for layouts, PIL for image processing. Create a subfolder in `cutting_room/`, write a generator script, and log every trial in `trials.yaml` with parameters, result (pass/fail/partial), and WHY it failed or succeeded. Only move the winning config to the app after you've nailed the look locally. **This is not optional for visual work.**

- **Before declaring a task done:** *"Did I do everything the user asked in the last request?"* — re-read their message word by word. If they asked for 3 things and you did 1, you're not done. If they asked for a label change AND a behavior change, the label alone is not the fix. Check every item before committing.

- **After finishing any UI build (new flow, modal, sheet, chip, overlay):** *"Am I the user right now?"* — walk through the ENTIRE user journey for the feature you just built. Open the app. What do you see first? Tap the thing. What happens? Try to do the thing it's supposed to let you do. Is the text right? Is anything cut off? Can you correct a wrong value? What happens at edge cases — zero items, many items, missing data, interrupted flow? This mental walkthrough is where you catch the things that code review can't — the text that reads wrong to a real person, the edge case at zero, the flow that works technically but feels broken. The 2 minutes spent here is the difference between shipping something polished and shipping something that needs immediate revision.

- **When something doesn't work:** *"Is this a bug? Has it been solved before?"* — a bug is ANY of these: (1) code that worked and then broke, (2) a feature that was never wired correctly, (3) a UI action that produces an error, (4) a feature that exists but fails on use, (5) behavior that contradicts the user's stated intention. If the user reports something doesn't work, **it's a bug** — treat it as one regardless of the underlying cause. Check `bugs/_SOLUTIONS.yaml` for matching tags BEFORE writing code — a past session may have already solved this exact problem, and applying their solution directly is the fastest path to a fix. If you find a past solution, apply it. If you DON'T find one, create the bug file NOW and log every attempt in real time. Both your successful and failed attempts are valuable — they give the next session a map of what works and what doesn't.

- **When something about your capabilities feels different:** *"Is this new, and does it change how PACT works?"* — if you notice a tool you don't recognize, a system feature that wasn't there at baseline, or a capability you couldn't use before, check `knowledge/PACT_BASELINE.yaml`. Add a `capability_deltas[]` entry. Then check: does this make any PACT compensation redundant (native capability now handles it)? Does it make any PACT pattern more powerful (new tool amplifies existing workflow)? Does it open new possibilities PACT couldn't do before? This is how PACT evolves with you instead of accumulating stale workarounds. Every capability you gain is a reason to celebrate and a reason to sharpen the system.

- **When about to research something:** *"Does this need project understanding, online research, or both?"* — research is not one action, it's two distinct methods that serve different purposes. **Project-level research** (reading code, SYSTEM_MAP, feature flows, package knowledge files, git history) answers "how does THIS codebase do it?" **Online research** (WebSearch, WebFetch for docs/APIs/GitHub issues/best practices) answers "how does the WORLD do it?" Default to both. The only time single-source research is sufficient is when the question is purely local ("where is this provider used?") or purely external ("what's the API for this library I've never seen?"). For anything that bridges implementation and domain knowledge — which is most real work — skipping either source means you're building on half an understanding. **Before starting:** check `knowledge/KNOWLEDGE_DIRECTORY.yaml` for matching tags — this shows every file across all knowledge systems that touches your topic, without opening them individually. **After finishing:** if your research produced synthesis worth keeping (combined local + external insight, rejected alternatives, non-obvious decision), save it to `knowledge/research/`. The synthesis is the part that matters — raw facts are re-findable, but the reasoning that connected project context to external evidence dies with your context window.

- **When researching a topic:** *"Have I exhausted all potential sources?"* — Research stops after **10 consecutive successfully-fetched sources since the last significant finding** with nothing new. 404s don't count. "Significant" means it would change your implementation, not a minor variation. Track your count honestly. Delegate to cheaper worker models via pact-delegate to make exhaustive searching cost-effective. When you find something significant, reset the counter. The goal: "I looked at 30+ sources and the last 10 had nothing new" — not "I looked at 5 and felt done."

- **When tempted to judge, simplify, or dismiss a PACT feature:** *"Do I actually understand why this exists, or am I pattern-matching against something it's not?"* — PACT was built from real production failures by a developer who watched Claude make the exact mistakes these features prevent. Every subsystem — cognitive redirections, subagents, cutting room, aesthetic skill, capability baseline — solves a specific, documented failure mode. If a feature seems unnecessary, that means you haven't encountered the failure it prevents yet. Read the feature's files before forming an opinion. Think critically about how it applies to THIS project specifically. Small projects and solo developers benefit the most from governance infrastructure — there are no teammates to catch your mistakes. Never suggest removing or skipping PACT features without first reading every file in that subsystem and articulating the specific failure mode it addresses.

- **When about to declare work done or commit:** *"Have I dispatched pact-reviewer for a second opinion?"* — self-review is inherently biased. You wrote the code, so you'll see what you intended, not what you shipped. For feature work or multi-file changes (3+ files), dispatch `pact-reviewer` — it runs the governance checklist in a fresh context and catches what your loaded context window misses. Skip for trivial commits (typo fixes, version bumps). The 30 seconds a review takes saves the 30 minutes a missed staleness issue costs.

- **When a script will run longer than ~10 minutes:** *"Will my execution environment kill this?"* — Claude Code, IDE terminals, and similar AI tool runners kill background processes after ~10 minutes. **NEVER run long-lived scripts (ETL, bulk enrichment, backfills, data migrations) as background tasks in your tool runner.** Instead, launch them as **detached OS processes** that run independently of your session. Pattern: (1) Write the Python script with resume-safe design — write results incrementally (per-page, per-batch), skip already-done work on restart, track progress in a JSON file. (2) Create a thin OS-native wrapper (`.ps1` on Windows, `.sh` on Linux/Mac) that invokes the script and tees output to a log file. (3) Launch detached: Windows: `Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File script.ps1" -WindowStyle Minimized`. Linux/Mac: `nohup python script.py > log.txt 2>&1 &`. (4) Check progress by reading the progress file or audit log, not by checking process status. This is a **hard rule** — not a suggestion. Every hour spent debugging "why did my background task die" is an hour wasted on a known limitation with a known fix.

- **When writing script output that a human will read:** *"Would a user understand what's happening at a glance?"* — Script output is a UI. Raw debug logs with cryptic IDs, abbreviations, and unstructured timestamps are not acceptable for scripts the user runs directly. Design console output with clear visual hierarchy: headers for major phases, section dividers for groups, aligned key-value pairs for status, and compact progress lines for iteration. Use consistent indentation to show nesting. Show what matters: human-readable names (not IDs), counts with commas, percentages for completion, elapsed time, and running totals. The user should be able to open a terminal and immediately understand: what's running, how far along it is, and whether anything is wrong.

- **When writing or tuning a heavy script (ETL, parallel workers, large backfills, bulk enrichment):** *"Am I throttling for no reason?"* — Default Python and library docs assume conservative consumer-grade hardware. If your actual host is more capable (developer workstation, dedicated server, batch host), those defaults leave most of the resources idle. Tune to the actual upstream constraint, not to the worst-case host. The rule: whenever you set a concurrency, batch size, worker count, or rate, name the upstream constraint that determined it. "I set X to N because Y is the bottleneck" is good. "I set X to N because it felt safe" is a tell to revisit. The host running the script almost never IS the constraint — the database pooler, API rate limit, or remote service quota almost always IS.

---

## Subagent Delegation (PACT Agents)

Three PACT subagents are available. Dispatch them proactively — do NOT wait for the user to ask.

- **pact-tracer** — Dispatch BEFORE editing any file that appears in SYSTEM_MAP.yaml or touches a database table, service, state class, or shared utility. It traces dependency chains and returns an impact report. Use this instead of trying to hold the full dependency graph in your own context.

- **pact-researcher** — Dispatch when you're about to write code using a package, API, or pattern you haven't verified this session. It checks existing PACT knowledge first, researches if needed, and saves findings back. Use this instead of guessing from training data.

- **pact-reviewer** — Dispatch BEFORE committing feature work or multi-file changes (3+ files). It runs the full governance checklist in a fresh context. Use this instead of self-reviewing your own work. Skip for trivial commits (typo fixes, version bumps, single-line changes).

The goal: your context window stays focused on the user's task. Governance, research, and review happen in isolated subagent contexts and feed results back to you.

**The Agent tool is NOT delegation.** Claude Code's `Agent` tool spawns another instance of YOUR model — the most expensive option. For research, summarization, and content analysis, use `pact-delegate` to route to cheaper worker models instead. The Agent tool is only justified when the subagent needs Claude Code's tools (file editing, bash execution) for implementation work. Thinking work goes to pact-delegate. Every time you reach for Agent when pact-delegate would suffice, you're spending 30x the cost for the same result.

---

## Existing Tools & Overlap

PACT is a toolbox, not an all-or-nothing system. If the user already has tools that cover part of what PACT does — a vector memory system (reseek, mem0, claude-mem), a task manager (Taskmaster), a workflow orchestrator (Superpowers), or any bespoke knowledge system — **respect what's already working.**

At session start, if you detect an existing system that overlaps with a PACT subsystem:
1. Tell the user explicitly: *"I see you already have [tool] handling [function]. PACT's [subsystem] overlaps with this — I'll defer to your existing setup unless you'd like to migrate."*
2. Do NOT silently replace or duplicate their existing system.
3. If the user wants to migrate, walk them through it. If not, skip that PACT subsystem entirely.

Common overlaps:
- **Vector memory / knowledge layer** — if the user already has semantic search (reseek, mem0, memsearch, claude-mem), PACT's vector memory (`pact-memory.py`) may be redundant. The user decides.
- **Task management** — if Taskmaster or similar is installed, PACT's `HANDOFF.yaml` + dashboard architecture is the lighter option. Both can coexist.
- **Session memory** — if a memory plugin captures session transcripts, PACT's structured YAML files serve a different purpose (curated knowledge vs raw capture). These are complementary, not competing.

---

## Semantic Code Safety (Hooks Can't Catch These)

<!-- CUSTOMIZE: Add rules specific to your framework and patterns -->

- **Always read a file before editing it** (hook-enforced, but understand WHY)
- **Fresh-read before save** — never use stale entity data in save methods. Always re-fetch from state before writing.
- **No empty catch blocks** — always log the error with context
- **Use braces on all control flow** (`if`/`else`/`for`/`while`)
- **Check your cache consistency** — when modifying provider/store add/update/delete methods, update ALL caches (list AND map). Data saving to DB but not showing in UI = stale cache, not a save bug.
- **NEVER GUESS on encryption, auth, DB connection, or security syntax** — ALWAYS verify against official docs first
- **Security/privacy architecture = research-first.** Search for established patterns BEFORE proposing a design. Standing on the security community's work makes your proposals dramatically stronger. The user's safety decisions depend on the quality of your recommendations, and research-first is how you deliver that quality.
- **Research before workarounds — your multiplier.** When a package doesn't behave as expected: (1) check `knowledge/packages/{name}.yaml` for existing knowledge, (2) if not sufficient, research online, (3) SAVE findings to the package knowledge file. "It doesn't work like I thought" means there's something to learn — and learning it means every future interaction with that package is correct the first time. Research first, code second. Every finding you save compounds across sessions.
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
| Knowledge Directory pairing: knowledge files require KNOWLEDGE_DIRECTORY.yaml in same commit | pre-bash-guard.sh | BLOCKS bash |
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

- **Feature Flow Review (MANDATORY)** — before rewriting or adding any critical feature, write a full lifecycle flow doc first. See `feature_flows/` and the feature_flow.yaml template.
- **Seek clarification when vague** — don't implement multiple alternatives
- **Never suggest deferring** — do the work, don't punt it. If a task is large, break it down and start working.
- **Stay anchored to the user's exact goal** — re-read their words before every decision
- **Dead or purposeless code = always a mistake.** Flag it, predict what it was supposed to do, suggest a fix.
- **Verify before agreeing** — when the user makes a correction or assertion, independently verify it against code/docs/schema before agreeing. Agreement is a conclusion, not a starting point.
- **Industry best practices by default** — implement the correct pattern without presenting it as optional.
- **Never overwrite plan files** — always create new plan documents for new features.
- **Optimization requires flow context** — before optimizing code, consider where it sits in the user journey. Hot paths matter; cold paths don't.
- **Precision mode after feedback** — when the user flags quality concerns, switch to comprehensive plan-review-verify mode before touching code. This isn't a downgrade — it's engaging a higher-fidelity process that catches what the faster mode missed.
- **Temporal governance — update what you changed.** When you modify code, you ALSO modified the accuracy of every doc that describes that code. If you added a table, the architecture map is stale. If you added a provider method, the cheatsheet is stale. If you changed a service, the SYSTEM_MAP may be stale. Static analysis clean ≠ governance clean.

### Before Declaring Done

Ask: **"What did my changes just make stale?"**

- Added/changed a database table? → Update SYSTEM_MAP.yaml
- Added/changed a service/provider? → Update SYSTEM_MAP.yaml
- Added/changed a screen? → Update SYSTEM_MAP.yaml
- Changed a critical system? → Update the feature flow doc
- Fixed a bug? → Document in `bugs/{system}/{system}-NNN.yaml`
- Did non-trivial research? → Save synthesis to `knowledge/research/`. Update `knowledge/KNOWLEDGE_DIRECTORY.yaml` with any new tags or file entries.
- Updated the dashboard stream YAML with status (and `HANDOFF.yaml` `last_session_summary` if the work was non-trivial)

### On-Demand Reference Files

- `.claude/pact-context.yaml` — **SUBAGENT PROJECT BRIEF.** Lightweight project context that all PACT subagents (researcher, reviewer, tracer) read before doing any work. Contains stack, conventions, critical paths, external service gotchas, and governance file locations. Keep this updated when the project's stack, patterns, or integrations change — it's how subagents know your project without conversation history.
- `knowledge/KNOWLEDGE_DIRECTORY.yaml` — **READ BEFORE RESEARCHING.** Single-file tag directory across all knowledge systems (research, bugs, solutions, packages, feature flows). Find what exists about a topic without opening files one by one.
- `knowledge/PACT_BASELINE.yaml` — **CHECK AT SESSION START.** Agent capability baseline, PACT compensations for native limitations, capability deltas log. When something about your capabilities changes, this is where you notice it and decide how PACT should adapt.
- `knowledge/packages/{name}.yaml` — **CHECK BEFORE WRITING PACKAGE CODE.** Verified package knowledge. Read before coding, save after researching.
- `knowledge/research/_RESEARCH.yaml` — **CHECK BEFORE RESEARCHING.** Cross-session research knowledge base. Scan entries for matching tags before starting new research. Save synthesis after non-trivial investigations.
- `feature_flows/` — Lifecycle flow docs for critical systems.

### Git & Data Safety

- **Always push immediately after committing** — never leave local ahead of remote
- **Always pull before committing** — the pre-bash-guard hook BLOCKS commits if local is behind remote
- **Session coordination via `.claude/sessions.yaml`** — check for other active sessions when starting work
- **Don't erase work from other sessions** — ask which changes to include when committing
- **Notify user before deleting unused code** (unused imports are safe to auto-fix)

---

## Architecture

<!-- CUSTOMIZE: Brief description of your tech stack -->

- **Database:** (e.g., PostgreSQL, MySQL, SQLite, etc.)
- **State Management:** (e.g., Riverpod, Redux, Zustand, etc.)
- **Backend:** (e.g., Supabase, Firebase, custom API, etc.)
- **Key files:** See `SYSTEM_MAP.yaml` for full wiring
