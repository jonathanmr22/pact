# PACT Changelog

All notable changes to PACT will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
PACT uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.1] — 2026-03-27

### Added
- `session-status-check.sh` — SessionStart hook that checks `status.claude.com/api/v2/incidents/unresolved.json` for active incidents affecting Claude Code or Claude API. Only warns on major/critical impact — no false positives from minor/maintenance incidents. Fails silently on network errors (4s timeout). Tells the user what's wrong and links to the status page.

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
