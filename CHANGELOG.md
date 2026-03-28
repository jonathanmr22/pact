# PACT Changelog

All notable changes to PACT will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
PACT uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.4.0] — 2026-03-28

### Added

**Compound Intelligence (Pillar 6)**
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
- README updated with Multi-Agent section, Gemini templates table, fifth pillar (Multi-Agent Resilience)

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
- Four pillars: Mechanical Enforcement, Context Replacement, Self-Evolving Reasoning, Structure/Behavior Separation
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
