# PACT Changelog

All notable changes to PACT will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
PACT uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.7.0] — 2026-03-30

### Added

**Vector Memory — Semantic Search for Compound Intelligence**
- `templates/memory/pact-memory.py` — Vector store manager using sqlite-vec + all-MiniLM-L6-v2 (ONNX). Zero infrastructure: no server, no API keys, no GPU. Single file at `~/.claude/pact-memory.db`. Indexes bugs (symptoms + resolutions), graduated solutions, research synthesis, and task feedback. CLI: `store`, `query`, `reindex`, `stats`.
- `templates/memory/pact-migrate.py` — One-time migration script. Reads existing YAML knowledge files, embeds them, builds the vector index. Non-destructive (YAML untouched).
- `plugins/pact/skills/pact-recall/SKILL.md` — On-demand semantic search skill. `/pact-recall` lets the agent search PACT memory by describing what they're looking for.
- `UPGRADE.md` — Step-by-step upgrade guide for existing users (dependency install, migration, verification).

**Feedback Consolidation**
- Task ratings (formerly `pact-ratings.jsonl`) now live at `.claude/bugs/_FEEDBACK.jsonl` — alongside bugs and solutions under one conceptual system. Server reads from both locations for backward compatibility.
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
- `templates/dashboard/pact-server.py` — Feedback writes to `.claude/bugs/_FEEDBACK.jsonl`, new `/recall` endpoint, auto-indexes ratings into vector store.
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
