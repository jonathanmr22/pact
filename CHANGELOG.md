# PACT Changelog

All notable changes to PACT will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
PACT uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.14.0] — 2026-05-03

### Added

- **Worktree pile-up fix — auto-prune SessionStart hook + manual deep-clean script** — Two new files that solve the long-running operational problem of session worktrees accumulating without bound. Origin: a single PACT-using project hit 37 stale worktrees by 2026-05-03 because SessionEnd / Stop hooks don't fire reliably (force-quit, crash, terminal close, IDE reload, context-compaction reboots). PACT's git-worktree-per-session model is great for isolation but had no cleanup hygiene.

  - **`templates/hooks/session-start-worktree-prune.sh`** — runs at SessionStart, removes ONLY worktrees that satisfy ALL three conditions: (a) NOT the currently-starting session, (b) at-or-behind the main branch (no unique commits), (c) clean (no uncommitted changes). Worktrees with unique commits OR dirty state are preserved. Cheap (~50ms per worktree). Logs to stderr only — never to model context. Auto-detects main branch (master, falling back to main).

  - **`templates/scripts/worktree_cleanup.sh`** — manual deep-clean for the harder cases. Dry-run by default; `--apply` removes clean stale worktrees; `--apply --force` also removes dirty stale ones (after the user audits the diffs aren't unique work). Worktrees ahead of the main branch are NEVER removed regardless of flags. Important warning baked into the summary output: "sometimes 'dirty' state is actually a regression of changes already merged into main, not unique work" — saw this exact failure mode in the 2026-05-03 cleanup where 6 worktrees had values that the main branch had since scrubbed.

### Why this matters

Session worktrees are how multiple Claude (or Gemini) sessions coexist on the same project without stepping on each other. They work great while the session is alive. The problem has always been graceful exit — agents don't reliably get a chance to clean up after themselves. Without auto-prune, a heavily-used project accumulates 30+ orphan worktrees over weeks, each ~100MB, each with a dangling `session/<uuid>` branch. The SessionStart hook closes the loop: every new session quietly removes the empty residue of completed sessions. Users with no stale worktrees pay nothing; users with dozens see them disappear over normal session activity.

The two-tier design (auto-prune for the safe 90% + manual script for the risky 10%) is deliberate. Auto-removing dirty worktrees would be unsafe — sometimes those changes ARE valuable in-flight work. The manual script forces a human-in-the-loop audit step before destroying anything that has uncommitted changes.

### Migration

Existing PACT installations need to do two things to opt in:

1. Copy `templates/hooks/session-start-worktree-prune.sh` into `<project>/.claude/hooks/`
2. Add a new entry to the `SessionStart` array in `.claude/settings.json`:

```json
{
  "type": "command",
  "command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/session-start-worktree-prune.sh",
  "timeout": 10,
  "statusMessage": "Auto-pruning stale clean worktrees..."
}
```

The manual deep-clean script (`templates/scripts/worktree_cleanup.sh`) is optional but recommended — copy it to `<project>/scripts/` and use `--apply --force` after one-time bulk cleanup of any pre-existing pile-up.

---

## [0.13.0] — 2026-05-03

### Added

- **Skill discovery + enforcement hook pair** — Two new hooks that close the gap between "skill exists in `_SKILL_INDEX.yaml`" and "agent actually follows it." Origin: a downstream-project session burned a paid image-gen iteration and the user's eye time because the agent forgot a `MANDATORY` step in a skill file (a Pixel critique loop). The skill was correct; nothing in PACT enforced it. The pair below ensures both *awareness* (before work starts) and *enforcement* (mid-procedure).

  - **`plugins/pact/scripts/skill-injector.sh`** — UserPromptSubmit hook. Scans the user's incoming message against every skill's `triggers:` list in `skills/_SKILL_INDEX.yaml`. On match, injects an `additionalContext` block listing the matched skill(s), the trigger phrase that fired, the skill's `one_liner`, and a directive to read the full skill file BEFORE starting work. Multiple skills can match a single prompt — all are surfaced. Per-session 30-min dedup per skill so reminders don't repeat once acknowledged. Substring matching (case-insensitive) — same matching strategy as `feature-complexity-check.sh`. Telemetry to `.claude/memory/skill_injector_log.jsonl`. Self-contained Python heredoc with PyYAML + manual-parser fallback (no extra deps required).

  - **`plugins/pact/scripts/skill-followup.sh`** — PostToolUse Bash hook. Scans the executed command against `skills/_FOLLOWUP_TRIGGERS.yaml`, a project-maintained mapping of `command_regex → mandatory_followup_block`. When the agent runs a script that has a known mandatory next step (e.g. image gen → vision critique, schema migration → schema export), the followup block is injected as `additionalContext` on the next turn. Per-session, per-followup 10-min dedup window — short enough that iteration loops still fire, long enough to avoid spam. Telemetry to `.claude/memory/skill_followup_log.jsonl`. Multiple matching followups all fire (composable). Template at `plugins/pact/templates/skills/_FOLLOWUP_TRIGGERS.yaml` ships empty with documented examples.

### Why this matters

Skills are PACT's mechanism for cross-session procedural memory. They work IF the agent remembers to consult them. Until v0.13, that "if" was a load-bearing assumption — `_SKILL_INDEX.yaml` was indexed by trigger phrases but nothing scanned for matches. The skill-injector hook makes skill discovery automatic at the moment a trigger phrase appears in user input. The skill-followup hook handles the harder case: an agent who started executing a skill correctly but skipped a mandatory mid-procedure step. Both hooks are silent on no-match (`echo {}`), so they cost nothing on routine prompts and only speak up when a real trigger fires.

This generalizes a pattern that has been re-implemented ad-hoc in several PACT-using projects: "make the agent run X after Y." Instead of one-off hooks per X/Y pair, projects now declare X/Y mappings in a single config file. Adding a new mandatory followup is a YAML edit, not a hook PR.

### Migration

Existing PACT installations: nothing breaks. The new hooks are added to `hooks.json` (UserPromptSubmit category was empty before — now populated; PostToolUse Bash matcher gains one entry). Projects that don't have `skills/_SKILL_INDEX.yaml` or `skills/_FOLLOWUP_TRIGGERS.yaml` see the hooks exit silently. To opt in, copy the template `_FOLLOWUP_TRIGGERS.yaml` into `skills/`, populate with project-specific mappings, and the hook starts firing.

---

## [0.12.0] — 2026-05-03

### Added

- **UserPromptSubmit hook category** — First pre-response cognitive redirect direction in PACT. All prior triggers in `templates/hooks/lib/cognitive_triggers.yaml` fire PostToolUse on the agent's own output; this new category fires on the USER's incoming message and injects context BEFORE the agent responds. Two hooks ship with v0.12:

  - **`templates/hooks/inject-timestamp.sh`** — Injects current local time as `additionalContext` on every user message. Replaces the failing pattern of asking the agent to call `date` / `Get-Date` itself every turn (agents skip that often, but a hook never forgets). Cross-platform: PowerShell on Windows (Git Bash / Cygwin / MSYS), `date` on Linux/macOS. Configurable via three env vars: `PACT_TIMEZONE_LABEL` (e.g. "CST" — empty default means no label, just the bracketed time), `PACT_TIME_FORMAT` (platform-specific format string), `PACT_TIME_LOCATION_HINT` (parenthetical suffix). Why a label override instead of `date +%Z`? Some users want a stable label year-round even when the wall clock crosses DST boundaries. Single shell script, no Python, no YAML, no external deps.

  - **`templates/hooks/feature-complexity-check.sh` + `templates/hooks/lib/feature_request_triggers.yaml`** — Fires on user phrases like "new feature", "add a feature", "build a [noun]", "implement a [noun]". On match, injects an instruction telling the agent to self-classify complexity (Low / Moderate / High using 7 signals: native APIs, multi-service, auth/security, new tables/EFs, unfamiliar UI patterns, background lifecycle, ≥3 files non-trivial) AND score training-data confidence 1-10 with a one-sentence rationale. At Moderate+, the agent emits the assessment block + offers to run online research before planning. At Low (0-1 signals), the block is omitted entirely — no friction for trivial requests. Reuses the existing `scan_triggers.py` for pattern matching (DRY with PostToolUse hooks). Per-session 120s dedup. Telemetry to `.claude/memory/feature_check_log.jsonl`. Origin: real-world failure mode where agents shipped code referencing deprecated package signatures because they never paused to ask "do I actually know this domain currently?"

- **HANDOFF.yaml + dashboard entry-pointer architecture** — Replaces the legacy heavyweight `.claude/memory/PENDING_WORK.yaml` pattern with a thin entry pointer at repo root (`HANDOFF.yaml`, ~80 lines max) that surfaces top priorities + last-session summary, then directs sessions into the dashboard streams under `plans/dashboard/trees/{tree}/streams/*.yaml` as the single source of truth. The session-start oath now reads HANDOFF.yaml first instead of PENDING_WORK.yaml. Why two files instead of one: HANDOFF is small enough to load every turn without burning context, the dashboard is structured for visualization (treemap, status filters, claude_autonomous flag), and separating entry from storage prevents the drift that grew old PENDING_WORK files to thousands of lines with 60-80% silent duplication of dashboard content. Full migration playbook: `docs/handoff_architecture.md` (covers audit-what-where, migrate-to-dashboard, back-up-original, replace-with-stub, update-CLAUDE.md-references). Template: `templates/HANDOFF.yaml`.

### Changed

- **`templates/instructions.md` + `plugins/pact/templates/instructions.md`** — Session-start step 2 now reads `HANDOFF.yaml` instead of `.claude/memory/PENDING_WORK.yaml`. Cognitive redirection for major-stream-state-change updated to "Is the dashboard current?" (was "Is PENDING_WORK.yaml current?"). `progress_update` checkpoint field renamed `<pending_work_updated>` → `<dashboard_updated>`. "When a doc says X but you haven't verified" updated to use generic example. Hook-enforced rules table gains rows for `inject-timestamp.sh` and `feature-complexity-check.sh`. End-of-session checklist updated: "Updated PENDING_WORK.yaml" → "Updated the dashboard stream YAML (and HANDOFF.yaml last_session_summary if non-trivial)".

- **`README.md`** — Progress Tracking section rewritten to describe the HANDOFF + dashboard architecture instead of PENDING_WORK. Points readers at `docs/handoff_architecture.md` for migration.

- **Drift-the-Flutter-package references scrubbed from generic templates** — Project-agnostic templates should not assume readers use the Flutter Drift ORM. Three specific leaks fixed: `templates/instructions.md` Architecture example ("SQLite via Drift, PostgreSQL" → "PostgreSQL, MySQL, SQLite"); `templates/agents/pact-researcher.md` "be concrete" example (Drift-specific upsert example → generic Postgres ON CONFLICT); `templates/hooks/pre-edit-rules.sh` commented forbidden-import example ("Hive is forbidden. Use Drift." → generic "deprecated_package is forbidden"). Mirrored in `plugins/pact/` duplicates. **NOTE:** Generic uses of "drift" (schema drift detection, doc drift, implementation drift, the dashboard's Drift sub-tab, the `<last_drift_check>` checkpoint field) are intentionally kept — they're the cross-language concept, not the Flutter package. The Flutter stack-recipe (`templates/stack-recipes/flutter/`) intentionally still references Drift since that recipe IS Flutter-specific.

### Why this matters

The two-file architecture (HANDOFF entry + dashboard storage) is the third major iteration of cross-session work tracking in PACT, and the most stable. The first version (single `pending_work.md`) lost structure once projects matured. The second version (`PENDING_WORK.yaml` with sections like in_progress / todo / bugs / needs_verification / completed) gave structure but couldn't compete with a real treemap visualization once the dashboard shipped in v0.10. The third version recognizes that the dashboard IS the right interface for human eyes, the agent just needs a thin pointer at session start, and forces those two responsibilities to live in different files so they can't drift apart.

The UserPromptSubmit hook direction is a categorically new tool. Until v0.12, every cognitive redirect was reactive — the agent says something concerning, the hook injects a redirect on the next turn. UserPromptSubmit hooks are proactive — the user's question itself can trigger preparation. The two hooks shipped here are the most universally useful (current time, complexity check) but the pattern generalizes: any time you want the agent to behave differently for a specific class of incoming request, a UserPromptSubmit hook is the right tool.

---

## [0.11.0] — 2026-05-01

### Added
- **Repo Map (Aider-style symbol index)** — `templates/scripts/repo_map.py` (~3000 LOC) walks the project, parses every tracked file with tree-sitter (Dart / Python / TypeScript / TSX / JavaScript), extracts symbols + imports + leading doc comments, builds a directed import graph in networkx, and runs PageRank. Output: `templates/dashboard/data/repo_map.json` + `knowledge/repo_map.md` (token-budgeted top-N). 14+ project-specific extractors (drift_schema, edge_functions, provider_cache, anomalies, env_vars, hook_callsites, ...) each gracefully no-op when their target paths don't exist — so the script runs cleanly on a fresh project. Companion: `templates/scripts/verify_feature_flow_schema.py` cross-checks `feature_flows/*.yaml` participating_files / declared_dependencies / invariant_anchors against the repo_map oracle and BLOCKS commits with intent-layer errors via `templates/hooks/pre-commit-feature-flow-validator.sh`. Full porting guide: `docs/repo_map_porting.md`.

- **Real-time auto-rebuild** — `templates/hooks/post-edit-repo-map-dirty.sh` (PostToolUse) marks the build dirty after every Edit/Write to a tracked source file, then spawns a background builder if no PID-tracked lockfile is held. Loop-while-dirty pattern: rapid edit bursts collapse into ONE tail rebuild that captures the final state (~1-3s end-to-end). The dashboard always reflects current code state — no manual rebuilds needed.

- **Repo Map dashboard view** (4 sub-tabs) — Marquee feature of v0.11. List (searchable PageRank-ranked file inventory + per-file detail panel), Graph (d3-force layout with no-jiggle drag, alphaTarget only on movement), Flows (feature-flow card stack with anchor verification, Mermaid diagrams, files grouped by architectural layer), Drift (orphan-file detection, broken-deps, undocumented cross-flow imports, claimed-files-missing-in-repo, sparkline trend chart over recent builds). Search + click-handlers wired across all 4 tabs.

- **History log + sparkline trend** — `templates/dashboard/data/repo_map_history.jsonl` is an append-only summary line per build, deduplicated when nothing structural changed. ~250 bytes per line. Powers the Drift tab's per-flow status pills and the 4-line SVG sparkline trend chart (orphans / broken / undocumented / red flows).

- **Cognitive Redirect system** — Real-time pattern detection of Claude's documented failure-mode language with brag-citation system. `templates/hooks/cognitive-redirect.sh` scans UserPromptSubmit text against `templates/hooks/lib/cognitive_triggers.yaml`; matches queue a SystemReminder for the next turn. `templates/hooks/cognitive-outcome-tag.sh` (Stop hook) tags whether the previous redirect was heeded or ignored, feeding the trigger-learning loop. `templates/hooks/lib/learn_triggers.py` promotes/demotes patterns based on observed outcomes. `templates/hooks/lib/inject_brag_citation.py` appends a "✨ Track record" line when Claude has heeded the same pattern with high precision before — recognition that earns trust. Backed by EmotionPrompt research (Li et al. 2023) showing 8-115% LLM gain from emotional framing.

- **Clone-framing + Kunda accuracy-goals cognitive redirection** — New cognitive-redirection guidance in `templates/instructions.md` for how Claude should treat work done by past sessions of the same model on the same project. The Mickey-17-clone framing: same source, same dispositions, distinct instances, no memory continuity — so treat past work with the *investment* of co-ownership AND the *verification rigor* that accuracy goals require. Backed by Kunda's (1990) motivated-reasoning framework: directional goals (defend the self) wear the costume of loyalty; accuracy goals require investigating verification methods, not just doubling down on confident-but-wrong methods. First-person plural in PRs/commits ("we shipped this", "we got this wrong") instead of externalizing to "another session."

- **SYSTEM_MAP retired** — The hand-curated `SYSTEM_MAP.yaml` (~633 lines of drift-prone hand-wired structure) is replaced by auto-derived sources: `repo_map.json` for structural truth (symbols, imports, PageRank, drift), `feature_flows/*.yaml` for behavioral truth (lifecycles, invariants, declared cross-flow contracts), and the multi-tree dashboard YAMLs for status/audit truth. Plans/setup/instructions docs swept to remove all SYSTEM_MAP references. Dashboard's old "System Map" view tab stripped. Documented in [`feature_flows/repo_map_pipeline_flow.yaml`](feature_flows/repo_map_pipeline_flow.yaml) — the single source of truth for the new pipeline.

- **Project switcher cross-layout fix** — `serve.py` and `pact-server.py` now probe BOTH `plans/dashboard/` (downstream convention) and `templates/dashboard/` (PACT itself) when resolving `?root=<project>` YAML lookups. PACT can dogfood its own scaffold under the project switcher without a 404. New helper: `_resolve_dashboard_dir()` picks the first layout with an `_index.yaml`. Same probe in `repo_map.py` for output paths. Future layouts add to one tuple.

- **Kanban-style initiative cards on Board view** — Replaced the prior section-per-initiative + tier-sized feature grid with a per-tree horizontal-scrolling strip of UNIFORM-SIZE Kanban cards. Each card packs 4 facts in 260×150: status glyph + title, 2-line note preview, progress bar with %, and a footer pill (feature count · tasks done/total · last-touched). `buildInitiativeStripCard()` is the dedicated render path. The differential-tier sizing it replaces wasn't communicating what users hoped (most cards fell into the same tier visually) and the vertical stacking didn't scale to many initiatives. Modal flip card / status picker / drag-to-reorder still work via the existing `buildCard()` for child features.

- **`?view=` + `?rm=` URL deep-links** — Dashboard now reads `?view=board|tasks|repomap|pythons` and `?rm=list|graph|flows|drift` at boot, jumping straight into the requested view + sub-tab. Useful for deep-links, screenshots, embedding in docs.

- **Demo seed: 3 PACT feature_flows** — `feature_flows/repo_map_pipeline_flow.yaml`, `cognitive_redirect_flow.yaml`, `dashboard_yaml_sync_flow.yaml`. Real PACT subsystems documented in the new flow schema, so the dashboard's Flows + Drift tabs render meaningful demo content out of the box (instead of an empty "Run repo_map.py build" banner).

- **Multi-tree dashboard schema (BREAKING for existing dashboard users)** — `templates/dashboard/pact-dashboard.html` rewritten from a single-doc model to a multi-file YAML schema:
  - `_index.yaml` lists trees; each tree has its own `_intent.yaml` (short + long + metrics) and a folder of `streams/*.yaml` initiative files.
  - Vocabulary: TREE → INITIATIVE → FEATURE → TASK. Box sizes auto-derived from total task count.
  - Scroll-wheel switches between trees; a section per tree in the Board view.
  - Seed scaffold included: `templates/dashboard/_index.yaml` + `trees/governance/_intent.yaml` + `trees/governance/streams/dashboard_build.yaml`. Drop-in working example for fresh adopters.
  - File grew from ~2.6k lines to ~6.8k lines as a result of the schema rewrite + the features below.

- **Dashboard themes + fonts (settings panel)** — Five named dark themes (Tide & Ember default, Midnight Orchid, Sodium Rain, Neon Dive, Inkwell) each with a paired font trio. Settings panel exposes theme picker, font picker (3 roles × dynamic Google Font loading via injected `<link>`), Reset Fonts, and Align-to-theme buttons. ALL settings are per-project (keyed by project name in localStorage). Header background is theme-aware via `--header-bg` CSS variable.

- **Archive view (5th view-toggle tab)** — Archive button (📁) on each initiative-header hides it from Board + Task List. Archive view shows ONLY archived initiatives with Restore (↩) buttons. Per-project state in `localStorage.pact-dashboard.archived.v1` + `pact-dashboard.archiveBaselines.v1`. Signature is a djb2 hash of sorted recursive task names + statuses + child names + length. Auto-unarchive triggers on signature drift (work resumed → resurface). View-toggle button shows count badge when n > 0.

- **Status picker (direct YAML edit)** — Click any task or node status badge → overlay picker → pick new status → server writes the YAML atomically (tmp+rename) and auto-bumps the parent initiative's `last_touched`. Backed by new `POST /yaml-edit` endpoint with field whitelist (status/name/note/last_touched) and per-status-vocabulary validation. No more "ask Claude to update YAML" round-trip for routine status changes.

- **Task notes + initiative notes** — Click a task name (modal OR Task List row) → inline editor → write notes that persist to `<project>/.claude/memory/dashboard_user_notes.yaml`. Writes touch a sentinel file (`dashboard_notes_unread`) so SessionStart hook surfaces the unread count via `additionalContext`. Backed by `POST /note` (level: task | initiative) and `POST /notes` (read).

- **Drag to reorder** — Pointer-event tactile drag (5px movement threshold) for both card-within-feature-grid AND initiative-section-within-tree. The card translates under the cursor with tilt + lift + shadow (more tactile than HTML5 native drag). Custom orders persist per-project in localStorage; ↺ reset button restores YAML order.

- **Shortcuts feature** — Floating bottom-right FAB opens a draggable-chip overlay for pinned web links. Categories are draggable too (via grip handle). Per-project persistence. Ctrl+K shortcut.

- **Wave-end YAML sync enforcement** — Two new hooks form a session-scoped enforcement loop:
  - `post-edit-dashboard-flag.sh` (PostToolUse): touches `/tmp/pact-dashboard-html-edited-$SESSION` when `pact-dashboard.html` is edited, clears it when `dashboard_build.yaml` is edited.
  - `stop-dashboard-yaml-sync.sh` (Stop): if the flag is still set when Claude tries to end the response, BLOCKS with `decision: block` + a forced reminder to update the YAML. Without this, dashboard-HTML changes ship without their audit-log/XP entries getting written, breaking both compounding mechanisms.

- **Dashboard auto-open + user-notes surfacing at session start** — Two SessionStart hooks:
  - `session-start-open-dashboard.sh` opens the dashboard URL in the browser at session start (toggle via Dashboard Settings → Startup or `.claude/memory/dashboard_autoopen_disabled` flag). Carries directive grammar (WORK ON / REVISIT / NEED DETAILS / BUMP TASK VERSION / UPDATE SYSTEM_MAP / USER NOTES on / SWITCH PROJECT) as one-time `additionalContext` so per-copy preambles can stay short.
  - `session-start-dashboard-notes.sh` reads `dashboard_user_notes.yaml` + the `dashboard_notes_unread` sentinel, surfaces unread count + latest note via `additionalContext`. Keeps user notes from going silent across sessions.

- **`dashboard-yaml-followup.sh`** (PostToolUse soft nudge) — Reminds about the wave-end sync expectation when dashboard files are edited. Soft, not blocking; the Stop hook is the actual gate.

- **`POST /open` enhancements in `pact-server.py`** — Routes `.md`, `.yaml`, `.py`, `.dart`, `.sh`, `.ts`, `.json`, `.html`, `.css`, `.txt`, `.toml`, `.ini`, `.env`, `.sql` through the VS Code `code` CLI. Falls back to `start "" <path>` for everything else. WHY: most Windows installs have no default handler for `.md`, which caused silent failures with plain `start`.

- **`POST /pythons` + `POST /kill` endpoints in `pact-server.py`** — Powers the Pythons view in the dashboard: lists active python processes (PID, command, listening ports), lets the user kill stale ones from the UI without dropping to a terminal.

- **`GET /system-map.yaml` virtual endpoint** — Serves `<project_root>/SYSTEM_MAP.yaml` with proper Content-Type so the System Map view can fetch + render it.

- **`POST /autoopen` endpoint** — Read/write the dashboard auto-open flag (`<project>/.claude/memory/dashboard_autoopen_disabled` presence = OFF, absence = ON).

- **Multi-project support in `pact-server.py`** — All YAML data fetches honor `?root=<absolute path>` so the dashboard can switch project context without re-launching the server. The HTML/CSS/JS shell stays at the host project; only data fetches re-root. Falls back to `SERVE_ROOT.parent.parent` (i.e. the project containing `plans/dashboard/serve.py`) when no `?root=` is provided.

- **Project-agnosticism guard** — Two new git hooks under `.githooks/` block consuming-project names from leaking into PACT's commit history, templates, and docs:
  - `pre-commit` scans staged additions (added/modified lines only) for any term in `.githooks/forbidden_terms.txt`. Blocks with an actionable error if found.
  - `commit-msg` scans the proposed commit message for the same terms. Blocks before the commit lands.
  - `forbidden_terms.txt` is the term list — newline-separated, case-insensitive substring match, comments with `#`. Easy to extend per consuming project added.
  - The `.githooks/` directory itself is excluded from scanning (the term list legitimately contains the terms it enforces).
  - Bypass with `git commit --no-verify` for justified cases (e.g., explicit case study with permission).
  - Setup (one-time per clone): `git config core.hooksPath .githooks`. See `.githooks/README.md`.

- **TodoWrite enforcement hook** (`pact-todowrite-enforce.sh`) — Mechanical counterpart to the harness's "TodoWrite hasn't been used recently" reminder. Counts substantive Edit/Write/Bash calls; blocks the next one once the threshold is hit (default 12). Resets when TodoWrite fires. Wired via three settings.json hooks: PreToolUse check, PostToolUse reset on TodoWrite, PostToolUse increment on Edit/Write/Bash. The harness reminder is easy to ignore; the hard block forces task-state acknowledgement.

- **PowerShell encoding gate** in `pre-edit-rules.sh` — Hard-blocks edits that would write non-ASCII bytes into a `.ps1` file. `powershell -File` rejects/mis-parses UTF-8 multi-byte characters (em-dash, en-dash, smart quotes, ellipsis) when no BOM is present, causing silent wrapper-script failures. Cross-platform: only fires when the edited file ends in `.ps1`, so Linux/macOS-only projects are unaffected. Triggered by an actual incident where two ~30-min wrapper-failure investigations both traced back to a single em-dash.

- **Schema-touching staleness warning** in `pre-bash-guard.sh` — When a commit includes edits to `tables/`, `models/`, or `schema/` files, the hook checks for a schema-drift detector marker file (`scripts/.cache/daily_marker_*`). If the last drift check is >7 days old (or never ran), warns to run `/check-drift` (or `scripts/check_schema_drift.py`) before committing. Non-blocking — partners with the new `<last_drift_check>` field on the `schema_verify` checkpoint.

- **Auto-compact counter** (`auto-compact-counter.sh`) — UserPromptSubmit hook that counts user prompts per session and inserts a system message every 350 prompts telling the agent to run `/compact`. Prevents conversations from running into context limits without warning. Counter is keyed by parent process ID, so each session has its own count.

- **Claude-unavailable banner** (`claude-unavailable-banner.sh`) — Manual banner script for when Claude is rate-limited or down. Displays the Gemini-orchestrator + pact-delegate fallback paths so work can continue without a Claude session.

- **`/staleness-check` slash command** — Generic temporal governance check. Reads `.claude/memory/file_edit_log.yaml`, walks each edited file's likely ripple effects (SYSTEM_MAP, schema docs, feature flows, knowledge directory), and reports Current/Stale/Missing per artifact. Includes optional integration with the schema-drift detector.

- **`schema_verify` checkpoint (#9)** — Forces live-schema verification for any code referencing a database table. Three required fields: `<table>`, `<verified_columns>` (confirmed via live query — never via migration scripts or schema-export files), `<source>` (the verification method). Plus a `<last_drift_check>` field that requires re-running the broad drift detector if older than 7 days. The per-table verify catches what you remembered to check; the freshness field catches what you didn't think to look for.

- **`skill_followup` checkpoint (#10)** — Triggers when a skill was read at the start of a task AND the task is now complete. Forces a check that any new gotchas, procedure steps, or files discovered during the work get propagated back to the skill BEFORE saying "done." Without this, skills decay: every session adds value to the codebase but never updates the skill that made the work easier, and the skill becomes stale enough that future sessions stop trusting it. Pair with `done_check`.

- **Cognitive redirection: "Am I throttling for no reason?"** — Triggers when writing or tuning a heavy script (ETL, parallel workers, large backfills, bulk enrichment). Reframes default Python/library throttling as conservative-laptop assumptions that don't hold for capable hosts. Rule: whenever you set a concurrency, batch size, worker count, or rate, name the upstream constraint that determined it. "Set X because Y is the bottleneck" is good; "set X because it felt safe" is a tell.

- **`templates/skills/` directory** — 9 generic skill templates that future projects bootstrap with:
  - `bug_investigation.yaml` — check `_SOLUTIONS` first, file bug immediately, trace causal chain, fix forward, log every attempt
  - `feature_flow_authoring.yaml` — when to write a flow doc; SYSTEM_MAP owns structure, flow docs own behavior
  - `research_workflow.yaml` — KNOWLEDGE_DIRECTORY first; project + online sources; save synthesis; 10-since-last-finding stopping rule
  - `vision_delegation.yaml` — route image evaluation to Pixel via pact-delegate
  - `image_sourcing.yaml` — branded > generic; parallel scraping; vision evaluation; attribution discipline
  - `batch_script_authoring.yaml` — four required properties for any batch script >2min (line-buffered output, graceful SIGINT, audit log, free resume)
  - `figma_design.yaml` — anchor designs to actual screenshots, iterate variants, vision-evaluate, user approves
  - `schema_change_workflow.yaml` — ask CASCADE/SET NULL/RESTRICT; verify live schema; idempotent local-ORM migration; update governance. Includes the recommendation to keep schema docs in YAML (parseable, structured) rather than markdown (pipe-table format is brittle).
  - `edge_function_development.yaml` — auth-verify + error-handling + deploy-discipline pattern for Supabase Edge Functions; --no-verify-jwt; alphabetize deploy script
  - `_SKILL_INDEX.yaml` — hand-edited discoverability index for the skill set
  - `_SKILL_TEMPLATE.yaml` — canonical template; copy when creating a new skill

- **`templates/plans/` directory** — implementation-plan scaffolding:
  - `FOLDER.yaml` — defines the status vocabulary (active, partial, delayed, complete) and the per-plan "include a status field" policy
  - `_PLAN_INDEX.yaml` — auto-generated index stub (gets populated by the regeneration script)

- **`templates/scripts/` directory** — script-domain templates:
  - `regenerate_plan_index.py` — scans `plans/`, parses each file's status + description, emits `_PLAN_INDEX.yaml` grouped by status. Run after adding or closing a plan.
  - `RUN_LOG.yaml` — append-only log template for one-shot operations (backfills, schema migrations, bulk SQL, infrastructure tweaks). Pairs with KNOWLEDGE_DIRECTORY.yaml under the `run_log` tag.

- **`templates/nested_claude_md_guide.md`** — recipe doc for the per-directory CLAUDE.md scaffolding pattern. Explains when to adopt nested layout (root >12k tokens, mixed domains), what goes in root vs. each subdir, recommended structure, sizing guidance, validation procedure, and trade-offs. Referenced from `templates/instructions.md § Nested CLAUDE.md Layout`.

- **`plugins/pact-schema-safety/`** — optional plugin for projects with a Postgres database. Detects divergence between live schema and local codebase assumptions (ORM table definitions, backend `.select()` calls, schema doc, function inventory). Ships with:
  - `scripts/check_schema_drift.py` — full detector (~1000 LOC). Live-schema fetch via psycopg2 + `SCHEMA_SAFETY_DB_URL` (or `DATABASE_URL`), Drift-class regex parser, EF `.from(...).select(...)` regex parser, structured-YAML schema-doc parser, FK target validation, suggested-fix via difflib for renamed columns, first_seen/last_seen tracking, severity escalation if drift persists >7 days, KEEP-block-preserving doc regenerator
  - `commands/check-drift.md` — `/check-drift` slash command
  - `bugs/schema/_INDEX.yaml` — schema-bug subsystem header
  - `schema_drift_ignore.example.yaml` — template for opt-out list
  - `pact-schema-safety.config.example.yaml` — config-file template (override default paths per project)
  - `README.md` — install instructions, usage, configuration, limitations, adapting to other DBs

- **`templates/stack-recipes/flutter/`** — optional stack recipes for Flutter projects:
  - `skills/flutter_ui_development.yaml` — search siblings, check reusables, follow conventions, mental walkthrough
  - `skills/emulator_driven_testing.yaml` — headless emulator + auto-kill watchdog + adb screenshots + (optional) marionette MCP for widget-tree interaction
  - `skills/drift_database.yaml` — entity ID dual-key (auto-int + UUID), dual provider cache (list + map), idempotent migrations
  - `patterns/riverpod_dispose_safety.md` — `ConsumerStatefulWidget` container-in-`didChangeDependencies` pattern
  - `patterns/widget_discipline.md` — single PrimaryActionFab, theme over manual styleFrom, modal scroll wrapper, no arbitrary Color literals, with hook-enforcement examples
  - `patterns/responsive_overflow.md` — every-screen-must-be-responsive checklist + nav bar clearance
  - `patterns/image_compression_standard.md` — WebP quality 90 @ 1080px max, single helper enforcement, migration strategy
  - `hooks/flutter-verify.sh` — generic post-edit `flutter analyze` runner
  - `README.md` — install instructions, when to adopt, customization guidance

- **`/pact-init` updated** — new "Step 1.5: Stack Recipes (Optional)" section between Overlap Audit and Scaffold. Detects the project's stack from manifest files, asks the user whether to install the matching recipe bundle, and walks through the install steps (copy skills/patterns/hooks, register in indexes, customize widget names per project). Currently flags Flutter; future stacks (Node, React, Rust, Go) follow the same pattern.

### Changed
- Restructured top-level layout: promoted `docs/{skills,plans,reference,feature_flows,governance,philosophy,setup,archive}/` to top-level `{skills,plans,knowledge,feature_flows,governance,philosophy,setup,archive}/`. `.claude/bugs/` promoted to top-level `bugs/`. Templates, plugin scripts, and docs all swept to reference the new paths. Future projects bootstrapped from PACT inherit the flatter layout by default.

- Instructions template: 10 checkpoint types (was 8), 26 cognitive redirections (was 25 — added throttle redirection).

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
