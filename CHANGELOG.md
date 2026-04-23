# PACT Changelog

All notable changes to PACT will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
PACT uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **Project-agnosticism guard** — Two new git hooks under `.githooks/` block consuming-project names from leaking into PACT's commit history, templates, and docs:
  - `pre-commit` scans staged additions (added/modified lines only) for any term in `.githooks/forbidden_terms.txt`. Blocks with an actionable error if found.
  - `commit-msg` scans the proposed commit message for the same terms. Blocks before the commit lands.
  - `forbidden_terms.txt` is the term list — newline-separated, case-insensitive substring match, comments with `#`. Easy to extend per consuming project added.
  - The `.githooks/` directory itself is excluded from scanning (the term list legitimately contains the terms it enforces).
  - Bypass with `git commit --no-verify` for justified cases (e.g., explicit case study with permission).
  - Setup (one-time per clone): `git config core.hooksPath .githooks`. See `.githooks/README.md`.

### Changed
- Restructured top-level layout: promoted `docs/{skills,plans,reference,feature_flows,governance,philosophy,setup,archive}/` to top-level `{skills,plans,knowledge,feature_flows,governance,philosophy,setup,archive}/`. `.claude/bugs/` promoted to top-level `bugs/`. Templates, plugin scripts, and docs all swept to reference the new paths. Future projects bootstrapped from PACT inherit the flatter layout by default.

---

## [0.10.0] — 2026-04-10

### Added
- **LLM Delegation Enforcement** — Three-layer system preventing agents from bypassing `pact-delegate` with raw API calls to LLM providers:
  - **Hard block hook** (`pre-bash-guard.sh`) — Detects Bash commands and Python scripts containing direct LLM API endpoint URLs (OpenRouter, Anthropic, Google, OpenAI). Blocks with actionable error pointing to pact-delegate. Allows commands that invoke pact-delegate itself.
  - **Strengthened `delegation_check` checkpoint** — New `<routing>` field forces naming the pact-delegate task type. Bold critical notice: "ALL external model calls MUST go through pact-delegate."
  - **Cognitive redirection: "Am I using pact-delegate?"** — Fires before any external model call. Explains the consequences of bypassing (wrong model, no logging, no cost tracking, no system prompt).

- **Script Catalog System** — New knowledge layer for projects with scripts:
  - **`scripts/SCRIPT_CATALOG.yaml` template** — Tag-based index with per-script metadata (purpose, category, tags, deps, env_vars, patterns, lessons). Includes `reusable_patterns` section for cross-cutting solutions.
  - **Pre-edit gate hook** (`pre-edit-rules.sh`) — Blocks creating or editing any file in `scripts/` unless the catalog has been read in the current session. Forces discovery before creation.
  - **Cognitive redirection: "Does one already exist?"** — Triggers before writing any new script.

- **Machine Bootstrap Template** (`templates/machine_bootstrap.yaml`) — Checklist for setting up new development machines. Covers CLI tools (with install commands per platform), environment variables (names and purposes, not values), PATH requirements, verification commands, PACT setup, and troubleshooting. Born from a real session where missing PATH entries and env vars wasted significant time.

- **Vision Specialist: Pixel** — New worker model in the delegation roster:
  - Model: Gemini 2.5 Flash via OpenRouter
  - Role: Image evaluation, photo selection, screenshot review, visual content classification
  - Multimodal input (text + image URLs)
  - $0.40/M output tokens — 98% cost efficiency
  - Proven in production: evaluated 3,400+ photos with accurate quality reasoning

- **PENDING_WORK Staleness Warning** — Commit-time check in `pre-bash-guard.sh` that warns when PENDING_WORK.yaml hasn't been updated in >1 hour. Non-blocking reminder that's impossible to miss.

### Changed
- **Checkpoint formatting requirement** — All checkpoints now require each XML tag on its own line with 2-space indent. Prevents unreadable single-line checkpoint output. Example format documented.
- **PENDING_WORK cognitive redirection refined** — Changed trigger from "every task milestone" (too noisy, gets ignored) to "when a major work stream changes state (blocked, completed, or pivoted)." Specific triggers: multi-step task completes/blocks, background process starts/fails, work the next session needs.
- **`delegation_check` checkpoint** — Trigger expanded to include "any call to an external LLM/AI model." New `<routing>` field added.
- Instructions template: 8 checkpoint types (was 7), 25 cognitive redirections (was 22)
- Model roster template: 5 models (was 4) — added Pixel vision specialist
- Hook templates: 2 new rules in pre-bash-guard (LLM block + PENDING_WORK staleness), 1 new rule in pre-edit-rules (script catalog gate)

### Why
During a production session, the agent constructed a raw `requests.post()` call to OpenRouter's API endpoint for content generation, completely bypassing `pact-delegate`. This meant wrong model selection (chose an arbitrary model instead of the roster-assigned worker), no system prompt, no cost tracking, and no delegation logging. The root cause: nothing mechanically prevented the bypass — it was guidance, not enforcement. The hook closes that gap permanently. The script catalog addresses a parallel problem: 124 scripts accumulated with no index, and each new script reinvented solved problems (API auth headers, encoding fixes, rate limit handling) because the agent couldn't discover existing solutions. The machine bootstrap template addresses first-session friction: missing CLI tools, wrong PATH, absent environment variables all waste time that a checklist eliminates.

---

## [0.9.4] — 2026-04-07

### Added
- **Progress Tracking** — Three-layer system that ensures agents leave breadcrumbs during long operations:
  - **`progress_update` checkpoint** (7th checkpoint type) — Triggers when a logical unit of work completes during a multi-step operation. Forces structured documentation of what completed, current state with concrete counts, and whether PENDING_WORK.yaml was updated.
  - **`post-edit-progress-check.sh` hook** — PostToolUse hook that warns after 30+ edits or 20+ minutes without a PENDING_WORK.yaml update. Dual detection: edit-count-based (reads file_edit_log.yaml) and time-based (marker file). Non-blocking warning that the agent can't suppress.
  - **Cognitive redirection: "Am I leaving breadcrumbs?"** — Triggers during multi-step operations (seeding, migration, bulk processing, multi-file refactors). Emphasizes that the breadcrumb is for the next Claude, not just the user — reframing documentation as investment rather than overhead.

### Changed
- Instructions template: 7 checkpoint types (was 6), 22 cognitive redirections (was 21)
- Plugin hooks.json: added post-edit-progress-check.sh to PostToolUse Edit|Write chain
- README: 13 features (was 12), 7 checkpoints (was 6), new hook in hooks table

### Why
During a 10-hour seeding session (inserting 4,000+ sources across 800 interests), PENDING_WORK.yaml went stale for hours. The agent was deep in execution — launching research agents, processing results, batching SQL inserts — and never updated the breadcrumb trail. When agents hit usage limits overnight and a new session resumed, PENDING_WORK.yaml still showed "166 sources, 22 interests" when the actual state was "959 sources, 96 interests." The next session had to reverse-engineer progress from the database instead of reading a current status file. This failure mode is universal: every developer who runs long agent operations loses continuity at context boundaries. The three-layer solution (hook + checkpoint + redirection) catches drift at different granularities — the hook fires mechanically on edit count/time, the checkpoint fires at meaningful milestones, and the redirection guides reasoning during the work itself.

---

## [0.9.3] — 2026-04-06

### Added
- **Project Scale Tiers** — Three tiers (Seed, Growth, Full) that match governance depth to project complexity. `/pact-init` now explicitly asks the user to choose a tier before scaffolding. Seed gets the reasoning foundation (redirections, bug tracking, package knowledge, core hooks) without structural overhead. Growth adds SYSTEM_MAP, feature flows, research system, preflight checks, and the researcher subagent. Full gets everything. Each scaffolding item in pact-init is annotated with its minimum tier. The chosen tier is stored in `pact-config.json` and `pact-context.yaml`.

- **Delegation** — Projects can inherit knowledge from a parent PACT instance instead of maintaining their own copies. Two patterns:
  - **Satellite** — a project that orbits a specific larger project (utility library, microservice, Edge Function repo). Shares the parent's solutions KB, package knowledge, research files, and knowledge directory.
  - **Stack** — a project that shares a technology stack with sibling projects. The "parent" is a stack-level governance project (e.g., `flutter-pact/`) that captures cross-project knowledge for that technology. All sibling projects delegate to it, so a bug solved in one project's solutions KB is immediately available to all others.
  
  Delegation is configured via `delegates_to` in `pact-context.yaml` with path, type (satellite/stack), and shared subsystem list. Child projects always keep their own bugs, PENDING_WORK, hooks, and sessions — only knowledge and research files are shared.

- **`pact-context.yaml` fields** — `scale` (tier) and `delegates_to` (path, type, shared subsystems) added to the project context template.

### Changed
- `pact-init` restructured into 3 steps: Step 0 (Scale + Delegation), Step 1 (Overlap Audit), Step 2 (Scaffold). Previously jumped straight to audit.
- All 21 scaffolding items annotated with tier badges: `[Seed]`, `[Growth]`, `[Growth: optional, Full: yes]`, `[Full]`.
- `pact-config.json` now stores `scale` field alongside dashboard preference and `first_used`.
- README: 12 features (was 11), version badge updated, "Who Is PACT For" references scaling, Quick Start describes the 4-step init process, new "Project Scale & Delegation" section with tier table and delegation examples.

### Why
A 200-line CLI tool doesn't need a SYSTEM_MAP, feature flows, cutting room, aesthetic skill, or a dashboard. But it absolutely benefits from cognitive redirections, bug tracking, and package knowledge. Without tiers, PACT treated every project the same — full governance or nothing. Delegation solves a complementary problem: a developer with 5 Flutter apps was maintaining 5 copies of the same package knowledge and solutions. Stack delegation lets them maintain one `flutter-pact/` governance project that all 5 apps inherit from. A bug solved once benefits all siblings immediately.

---

## [0.9.2] — 2026-04-06

### Added
- **Project Philosophy** — New section in `instructions.md` template for defining the project's core beliefs, decision filters, and anti-patterns. This is the product counterpart to the aesthetic skill: the aesthetic skill governs **how things look**, the philosophy section governs **what the product believes**. Unlike the aesthetic skill (which triggers per-edit via preflight), philosophy is set once during project setup and lives in CLAUDE.md where every session reads it at startup. Includes: The Why (core purpose), Core Beliefs (non-negotiable principles), Decision Filters (trade-off resolution rules), and What This Product Is NOT (anti-patterns to resist).
- **Philosophy skill template** (`templates/philosophy_skill.md`) — Standalone reference template with detailed guidance and examples for defining project philosophy. Can be used as a worksheet during setup before distilling into the CLAUDE.md section.

### Why
The aesthetic skill solved visual consistency across sessions. But product decisions — data collection, privacy defaults, feature scope, user communication — had no equivalent anchor. Claude defaults to industry norms (track everything, optimize for engagement, require sign-up) which may directly contradict a project's values. The philosophy section makes those values explicit so every Claude session inherits them. Born from a session building a community curation feature where every product decision (anonymous vs public, demographic accommodation, accessibility requirements) was filtered through unstated beliefs that should have been stated.

---

## [0.9.1] — 2026-04-06

### Added
- **Checkpoint: `ui_work`** — 6th checkpoint type. Triggers before building or significantly modifying a UI element (widget, screen, modal, sheet, overlay, card). Forces the agent to document which existing reusable widgets it checked, which reference screens it read for design guidance, and what design pattern it's following. Prevents the failure mode of building bespoke UI from scratch that looks subtly different from the rest of the app.
- **Cognitive redirection: UI reuse audit** — "What already exists that I should reuse or reference?" Triggers when starting any UI work. Directs the agent to search for reusable widgets, shared constants, and established patterns before writing UI code, and to READ at least one sibling screen to absorb the project's visual language. Paired with the existing "Am I the user right now?" post-build redirection — creating a before/after pair for UI work.

---

## [0.9.0] — 2026-04-06

### Added
- **Required Checkpoints** — Output-level reasoning gates that force visible, structured analysis before acting. Five checkpoint types: `bug_fix`, `solution_compare`, `package_verify`, `dependency_trace`, `done_check`. Each has a specific trigger condition and required output format. Checkpoints are format requirements (hard to skip), not prose guidance (easily skipped under cognitive load).
- **Three Enforcement Layers** model documented in README: Hooks (mechanical, can't skip) → Checkpoints (output format, hard to skip) → Redirections (guidance, can be skipped). Checkpoints fill the gap between hooks and redirections.
- **Cognitive redirection: solution comparison** — "Have I compared them, or am I just iterating?" Stops the spiral pattern of trying approaches sequentially without structured evaluation.
- **Cognitive redirection: symptom vs core issue** — "Am I treating a symptom or the core issue?" Traces causal chains back to where bad state is produced, not observed.
- **Research mandate** — "You never need permission to research" embedded in both checkpoints and redirections. The user expects informed analysis, not guesses.

### Changed
- Cognitive redirections section retitled to clarify they are guidance, not gates. The checkpoints section handles the patterns that historically fail under load.
- Feature count updated from 9 to 10 in README.
- Agents can now promote a redirection to a checkpoint when they notice it being skipped under load.

### Fixed
- **Dashboard crash from colons in session IDs** — `querySelector('#pname-{sid}')` threw on IDs containing colons. Replaced with `getElementById`.
- **Session dedup** — 30-minute reuse guard prevents ghost sessions from IDE restarts and settings changes.
- **Auto-archive stale sessions** — Sessions >3 days old, >30min inactive, or ≤2 events are hidden on dashboard load.
- **Per-session stats** — Edit counts, durations, and event counts now flush correctly after initial load.

---

## [0.8.0] — 2026-04-06

### Added
- **Worktree Isolation** (opt-in) — Each session gets its own git worktree and branch (`session/{SESSION_ID}`), completely isolated from other sessions. Commits on session branches are free; merging to the main branch requires explicit user approval via a one-time lockfile. Enable with `"worktree_isolation": true` in `~/.claude/pact-config.json` or `PACT_WORKTREE_ISOLATION=1` env var.
- **Merge/push approval gate** in `pre-bash-guard.sh` — When worktree isolation is enabled, `git merge` and `git push` on the main branch are blocked unless a fresh approval lock exists (120s expiry, consumed on use).
- Worktree creation in `session-register.sh` — Auto-creates `.worktrees/{SESSION_ID}/` at session start when isolation is enabled. Auto-detects `master` vs `main` for broader compatibility.
- `.worktrees/` added to `pact-gitignore` template.
- Instructions template now documents both workflows (worktree isolation vs shared working tree) with clear Option A/Option B guidance.
- Adoption checklist includes worktree isolation as an optional item.

### Fixed
- **Duplicate session registration** — `session-register.sh` now uses a lockfile-based dedup guard (5s window) to prevent duplicate entries when the IDE fires `SessionStart` once per workspace root in multi-root VS Code workspaces.

---

## [0.7.1] — 2026-04-03

### Added
- **Embedded Agent Guide** (`EMBEDDED.md`) — Comprehensive guide for translating PACT governance patterns from CLI agents to web applications. Covers knowledge persistence, mechanical enforcement, error tracking, session protocols, data mirror architecture, and pattern rules. Includes common patterns for bookkeeping, support, operations, and sales agents.
- **Project Context for Subagents** (`templates/pact-context.yaml`) — Lightweight project brief injected into all PACT subagents. Gives researcher, reviewer, and tracer project awareness (stack, conventions, critical paths, external services) without requiring the main session to manually brief them.
- **7 new embedded agent examples** in `EXAMPLES.md` — Knowledge enforcement, duplicate detection, mirror sync, memory optimization, recurring template duplicates, error notifications, glass cannon problem.

### Changed
- Reorganized `EXAMPLES.md` by project type: Mobile App, Embedded AI Agent, General. Each example follows consistent structure: Pattern → Failure → Mechanism → Why it works.
- All three agent templates (researcher, reviewer, tracer) now read `pact-context.yaml` as Phase 0 before doing any work.
- `pact-init` scaffolds `pact-context.yaml` (item 21) and sets `first_used` in `pact-config.json`.
- README "Who Is PACT For" section tightened.

### Fixed
- **Feedback milestones not triggering** — Plugin `session-register.sh` was a stripped-down copy missing the dashboard check, scorecard check, vector memory check, and feedback milestone code. Synced with full template.
- **Dashboard prompt never appearing** — Same root cause as above. Users with `"dashboard": "ask"` will now be prompted on session start.
- **`pact-config.json` missing `first_used`** — `pact-init` now includes `first_used` in the initial config. Without it, feedback milestones never triggered because days-since-install was always 0.

---

## [0.7.0] — 2026-03-30

### Added

**Vector Memory — Semantic Search for Compound Intelligence**
- `templates/memory/pact-memory.py` — Vector store manager using sqlite-vec + all-MiniLM-L6-v2 (ONNX). Zero infrastructure: no server, no API keys, no GPU. Single file at `~/.claude/pact-memory.db`. Indexes bugs (symptoms + resolutions), graduated solutions, research synthesis, and task feedback. CLI: `store`, `query`, `reindex`, `stats`.
- `templates/memory/pact-migrate.py` — One-time migration script. Reads existing YAML knowledge files, embeds them, builds the vector index. Non-destructive (YAML untouched).
- `plugins/pact/skills/pact-recall/SKILL.md` — On-demand semantic search skill. `/pact-recall` lets the agent search PACT memory by describing what they're looking for.
- `UPGRADE.md` — Step-by-step upgrade guide for existing users (dependency install, migration, verification).

**Feedback Consolidation**
- Task ratings (formerly `pact-ratings.jsonl`) now live at `bugs/_FEEDBACK.jsonl` — alongside bugs and solutions under one conceptual system. Server reads from both locations for backward compatibility.
- New ratings are automatically stored in the vector index for semantic recall.

**Anonymous Feedback System**
- `templates/memory/pact-feedback-report.py` — Generates anonymous session reports at Day 2 and Week 2 milestones. Captures subsystem usage, task ratings, what helped, what caused friction, workarounds Claude invented, and hooks that blocked legitimate work. Report stays local — user decides whether to share.
- `session-register.sh` tracks `first_used` date and triggers feedback prompts at milestones.
- `pact-config.json` stores `first_used`, `feedback_day2_done`, `feedback_week2_done`.

**Server Enhancements**
- `GET /recall?q=text&top=5&type=bug` — Vector search endpoint for dashboard and skill use.
- Feedback file location updated with legacy fallback.

### Changed
- `templates/hooks/session-register.sh` — Reports vector memory status and document count at session start.
- `templates/dashboard/pact-server.py` — Feedback writes to `bugs/_FEEDBACK.jsonl`, new `/recall` endpoint, auto-indexes ratings into vector store.
- README: 9 features (was 8), 5 slash commands (was 4), vector memory in templates table and adoption checklist.
- `.pact-gitignore` template created (from v0.6.0 polish).

---

## [0.6.0] — 2026-03-30

### Added

**Subagent Delegation (Distributed Cognition)**
- `templates/agents/pact-tracer.md` — Dependency impact agent. Read-only Sonnet subagent that traces upstream/downstream dependency chains from SYSTEM_MAP before edits. Returns structured impact reports so the main session edits with full awareness.
- `templates/agents/pact-researcher.md` — Knowledge compound agent. Read/write + web Sonnet subagent that checks existing PACT knowledge files first, researches packages/APIs/patterns if needed, and saves synthesis back for future sessions.
- `templates/agents/pact-reviewer.md` — Pre-commit governance agent. Read-only Sonnet subagent that runs staleness audit, dependency check, and cognitive redirection sweep in a fresh context before feature commits.
- Plugin copies at `plugins/pact/agents/` (auto-installed with plugin)

**Cognitive Redirection (1 new, total: 20)**
- "When about to declare work done or commit: Have I dispatched pact-reviewer for a second opinion?"

**Instructions Template**
- New "Subagent Delegation (PACT Agents)" section with dispatch guidance for all three agents
- Session start step 6: PACT scorecard read (from v0.5.0 dashboard)

### Changed
- `pact-reviewer` trigger refined: "before committing feature work or multi-file changes (3+ files)" instead of "before any git commit" — trivial commits (typo fixes, version bumps) skip review to avoid workflow friction
- `pact-init` SKILL.md: items 15-19 (dashboard from v0.5.0) + item 20 (agents) + Subagent Delegation section for CLAUDE.md
- Instructions template version bumped to 0.6.0
- Plugin `instructions.md` synced with template (was drifted at v0.2.0)
- README: 8 features, 3 subagents in What You Get, agents in templates table, adoption checklist updated
- COMPARISON.md: subagents added as differentiator

### Fixed
- `templates/instructions.md` version was stuck at 0.4.0 (now 0.6.0)
- `plugins/pact/templates/instructions.md` was drifted at v0.2.0 (now synced with template)
- `.pact-gitignore` template added for guidance on what NOT to commit
- README adoption checklist updated with v0.5.0 dashboard + v0.6.0 agents items
- COMPARISON.md updated with dashboard and subagent differentiators

---

## [0.5.0] — 2026-03-30

### Added

**Live Dashboard — Observability & Feedback**
- `templates/dashboard/pact-dashboard.html` — Real-time visualization of all agent activity. Session lanes with model identity, project names (renameable), task sub-rows with collapse/expand, per-type animated icons, activity timeline, sidebar metrics, diagnosis with clipboard prompt generation.
- `templates/dashboard/pact-server.py` — Dashboard server (port 7246). Serves events, ratings, scorecard, and config. Auto-kills previous instance on startup. Regenerates scorecard after every rating.
- `templates/dashboard/pact-event-logger.sh` — Central event logger. Dual-write to `~/.claude/pact-events.jsonl` (multi-project) and project-local. Auto-detects project folder.
- `templates/dashboard/pact-prompt-logger.sh` — Captures user messages as event cards. Strips IDE context tags.

**Task Rating System**
- Per-session "Track Next Task" with named task sub-rows. "Track From Here" on prompt cards for retroactive task boundaries.
- Rating overlay: 1-5 score, 9 category tags, free-text feedback for what went wrong and right.
- Ratings in `~/.claude/pact-ratings.jsonl`. Scorecard at `~/.claude/pact-scorecard.md` with rolling average, streaks, weakest areas, and action items. Agent reads scorecard at session start.

**Dashboard Startup Preference**
- `~/.claude/pact-config.json`: `ask` (agent offers), `auto` (silent start), `off` (never). Configurable from dashboard info panel.

### Changed
- `templates/hooks/session-register.sh` — Emits session_start PACT event, checks dashboard status, reads startup preference, notifies agent about scorecard.
- `templates/hooks/post-edit-timestamp.sh` — Emits PACT events for all file types, uses PACT session ID.
- `templates/hooks/post-edit-preflight.sh` — Uses PACT session ID from temp file, emits preflight events.
- README: 7 features (was 6), 13 hooks (was 11), dashboard section, new SVG logo.

---

## [0.4.1] — 2026-03-29

### Added

**PreFlight — Architectural Metacognitive Checks**
- `templates/hooks/post-edit-preflight.sh` — PostToolUse hook that runs data-driven architectural checks after every edit. Unlike syntax-level warnings, PreFlight catches architectural mistakes: wrong call sites, missing platform config, unverified API assumptions, state changes without UI notification.
- `templates/hooks/preflight-checks.yaml` — Data-driven check definitions. Adding a new check = adding YAML, no script changes. Each check has: trigger patterns (file + content), severity (think/warn), a QUESTION (not a rule), root_pattern (class of mistake), and learned_from (the incident that created it). Starter checks: aesthetic identity, research before building, knowledge directory awareness, destroy before verify, state without notification.
- `templates/aesthetic_skill.md` — Project design identity template. Evocative, not prescriptive — principles that shape creative reasoning rather than checklists that produce generic output. PreFlight's aesthetic_engagement check reminds the agent to read this when editing UI files.

**Plugin Updates**
- `pact-init` now scaffolds preflight-checks.yaml and prompts for a project aesthetic skill (items 13-14)
- Plugin scripts synced with PreFlight hook and checks template

### Changed
- `COMPARISON.md` — Added Context7 as recommended companion plugin for up-to-date package docs
- README updated: 11 hooks (was 10), PreFlight in hooks table and templates table

---

## [0.4.0] — 2026-03-28

### Added

**Compound Intelligence**
- `templates/research/_RESEARCH.yaml` — Cross-session research knowledge base. Format spec for saving synthesis (the reasoning that connects local code context to external knowledge). Includes depth levels (shallow → definitive), four evolution actions (deepen, reframe, update, supersede), staleness conditions, tag vocabulary, and indexed entries for fast lookup.
- `templates/knowledge_directory.yaml` — Cross-system tag directory. Single-file lookup across ALL knowledge systems (research, bugs, solutions, packages, feature flows). Maps tags to files with one-line descriptions so the agent can find what exists about a topic without opening files individually. Hook-enforced.
- `templates/capability_baseline.yaml` — PACT self-awareness layer. Captures the agent's native capabilities, PACT compensations for limitations (with `what_retirement_looks_like` for each), PACT enhancements (capabilities that make PACT stronger), and a capability deltas log for tracking changes over time. Includes a self-check protocol triggered when the agent notices something different about its environment.

**Cognitive Redirections (2 new, total: 19)**
- "When something about your capabilities feels different: Is this new, and does it change how PACT works?" — triggers capability baseline check
- "When about to research something: Does this need project understanding, online research, or both?" — frames research as two complementary methods (project-level + online), with Knowledge Directory as the first lookup and research files as the output

**Hook Enforcement**
- Knowledge Directory pairing in `pre-bash-guard.sh` — blocks commits that include research files, bug solutions, package knowledge, or feature flows without also staging `KNOWLEDGE_DIRECTORY.yaml`
- Knowledge system staleness warning — non-blocking reminder at commit time when knowledge files were edited today

### Changed

**Positive Tone Reframe (across all systems)**
- All intro sections, hook messages, and cognitive redirections reframed from punitive/compliance language ("you failed, now comply") to capability/leverage language ("this is your superpower, use it")
- `templates/bugs/_INDEX.yaml` — "WHY THIS EXISTS" rewritten from failure narrative to compound intelligence framing
- `templates/bugs/_SOLUTIONS.yaml` — intro reframed from gatekeeping to fast-path framing
- `templates/package_knowledge.yaml` — intro reframed from "agents guess wrong" to "verified knowledge compounds"
- `templates/instructions.md` — cognitive redirections intro reframed from "mistake it prevents" to "pattern that accelerates thinking"; 8 individual redirections reframed (code deletion, package research, security, CLI tools, Supabase, UI walkthrough, bug tracking, workflow feedback)
- `templates/hooks/pre-bash-guard.sh` — all blocking messages reframed: staleness → "KNOWLEDGE SYNC", multi-session → "incorporate their work alongside yours", bug tracker → "compound leverage", Knowledge Directory → "searchability superpower"

**Instructions Template (v0.4.0)**
- Session start now includes PACT capability check (step 5)
- "Before Declaring Done" section adds research capture check
- New "On-Demand Reference Files" section with KNOWLEDGE_DIRECTORY, PACT_BASELINE, and research system
- Hook-enforced rules table adds Knowledge Directory pairing
- "Hand-holding mode after sloppy work" → "Precision mode after feedback"

**Plugin**
- `pact-init` skill scaffolds 3 new files (research index, knowledge directory, capability baseline)
- `pact-init` includes 19 cognitive redirections (was 17)
- Plugin `pre-bash-guard.sh` synced with template

---

## [0.3.0] — 2026-03-27

### Added

**Multi-Agent Support (Claude + Gemini)**
- `MULTI_AGENT.md` — Complete guide to running Claude Code and Gemini CLI on the same project with shared governance, seamless task handoffs, and parallel session coordination
- `templates/gemini/GEMINI.md` — Project context template for Gemini CLI (points to CLAUDE.md for shared rules, adds model identity and tool mapping)
- `templates/gemini/hooks/before-tool-adapter.sh` — Translates Gemini's JSON stdin hook format to PACT environment variables, delegates to `.claude/hooks/` scripts
- `templates/gemini/hooks/after-tool-adapter.sh` — Same adapter pattern for AfterTool events
- `templates/gemini/settings.json` — Drop-in Gemini CLI hook configuration
- `session-status-check.sh` — SessionStart hook that checks `status.claude.com/api/v2/incidents/unresolved.json` for active incidents affecting Claude Code or API. Only warns on major/critical impact. Fails silently on network errors (4s timeout).

### Changed
- `session-register.sh` — Now auto-detects agent model (Claude vs Gemini) via environment variables and tags sessions with `model: claude` or `model: gemini`. Backward compatible with existing session files.
- Session file header changed from "Multi-Claude" to "Multi-Agent" coordination
- README updated with Multi-Agent section, Gemini templates table, Multi-Agent Resilience feature

---

## [0.2.0] — 2026-03-27

### Added

**Cognitive Redirections (11 new)**
- "When encountering a technology/library/API: What does this project actually use?"
- "When about to write code based on memory: Have I actually read this file?"
- "When about to say I'm satisfied: What happens to this system tomorrow?"
- "When a doc says X but you haven't verified: Is this still true?"
- "When proposing security/privacy architecture: Have I researched what exists?"
- "When finding an objection to your solution: Is this objection real, or am I folding?"
- "When something is broken or regressed: Can I fix this forward?"
- "When about to say I can't do X: What CLI tool handles this?"
- "When building a complex visual: Can I prototype this outside the framework first?"
- "After finishing any UI build: Am I the user right now?"
- "When something doesn't work: Is this a bug? Has it been solved before?"

**Hooks (4 new)**
- `pre-bash-guard.sh` — Git safety (no force push main, no --no-verify, no reset --hard), multi-session coordination (blocks commit if local behind remote), bug tracker enforcement on fix commits, staleness warnings
- `pre-edit-feature-flow.sh` — Blocks edits to critical system files (auth, encryption, backup, sync, database core) without a feature flow document
- `post-sentry-bug-reminder.sh` — Gates source edits after issue tracker fetch until bug file is created
- `session-register.sh` — Registers sessions in `.claude/sessions.yaml` for multi-session awareness

**Enhanced Hooks**
- `pre-edit-rules.sh` — Added issue tracker gate (blocks source edits until bug documented), empty catch block detection, raw SQL injection detection
- `post-edit-warnings.sh` — Added modal scroll wrapper check, comment deletion warning, workaround/hack language detection, name-based matching warning, entity ID double-prefix detection, braceless control flow warning

**Bug Tracker Enhancements**
- Expanded tag vocabulary (30+ standardized tags across 7 categories)
- Solution graduation process documented
- 4 starter solution entries (stale cache, async safety, non-idempotent migration, ID double-prefix)
- Format version bumped to 2

**Workflow Rules (new section)**
- Git & data safety rules (push after commit, pull before commit, session coordination)
- "Never suggest deferring" — do the work, don't punt
- "Verify before agreeing" — independent verification of user assertions
- "Temporal governance" — update docs that your changes made stale

**Instructions Template Enhancements**
- Session start now includes sessions.yaml check
- Semantic code safety section expanded (research-before-workarounds, migration idempotency, diagnostic logging, entity ID consistency)
- Hook-enforced rules table expanded to cover all new hooks

### Changed
- Instructions template version bumped to 0.2.0
- `pact-init` skill now scaffolds cutting_room/, sessions.yaml, and includes all 17 cognitive redirections
- `hooks.json` registers Bash PreToolUse hooks, Sentry PostToolUse hooks, and SessionStart hooks

---

## [0.1.0] — 2026-03-26

### Added
- Initial public release
- Four core features: Mechanical Enforcement, Context Replacement, Self-Evolving Reasoning, Structure/Behavior Separation
- Hook templates: PreToolUse blocker, PostToolUse warnings, read tracker, silent linter
- Architecture map template (SYSTEM_MAP.yaml)
- Feature flow template (lifecycle state machine)
- Instructions file template with cognitive redirections
- Bug tracker format specification and solutions knowledge base
- Package knowledge template
- Cross-session pending work tracker
- Cutting room floor visual prototyping templates
- Real-world examples document
- Adoption checklist
