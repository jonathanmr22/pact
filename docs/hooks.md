# PACT Hooks — Mechanical Enforcement Reference

Shell scripts that block violations before they land. Hooks don't care which model wrote the code — they enforce the same rules on Claude, Gemini, or any agent with a hook system.

**The rule:** If a violation can be detected by grep, it's a hook. If it requires understanding, it's a checkpoint or a redirection.

---

## Hook Types

| Type | When | Can Block? | Example |
|------|------|------------|---------|
| **PreToolUse** | Before a tool executes | Yes — exit 1 blocks | Stopping a file edit that hasn't been read first |
| **PostToolUse** | After a tool executes | No — warns only | Flagging that a file is >800 lines |
| **SessionStart** | When a session begins | No — informational | Registering the session, checking status pages |

---

## PreToolUse Hooks (Blocking)

### pre-edit-rules.sh
**Triggers on:** File edits (Edit/Write tools)

**Blocks:**
- **Hardcoded secrets** — Regex detects `api_key`, `secret_key`, `password`, `auth_token` assigned to string literals 8+ chars
- **Empty catch blocks** — `catch (_) {}` or `catch (e) {}`
- **Raw SQL with string interpolation** — `execute(`, `rawQuery(`, `customSelect(`, `customStatement(` combined with `$variable`
- **Read-before-write** — Tracks all file reads via `post-read-tracker.sh`. Blocks edits on files not yet read this session. Only enforces for existing files.
- **Issue tracker gate** — After fetching a Sentry/GitHub issue, blocks source code edits (`lib/`, `src/`, `app/`, `packages/`) until a `.claude/bugs/*.yaml` file is created

**Customizable patterns (uncomment for your project):**
- Forbidden imports (e.g., `import hive` → use Drift)
- Forbidden logging (e.g., `print()` → use structured logger)
- No hardcoded project refs
- No manual styling on themed widgets
- No arbitrary colors outside design system
- No raw dialogs/snackbars without wrappers

### pre-bash-guard.sh
**Triggers on:** Bash commands

**Hard blocks:**
- `git --no-verify` — never skip hooks
- `git push --force` to main/master
- `git reset --hard`
- `git branch -D` (force delete)
- `git checkout .` / `git restore .` / `git clean -f` (bulk discard)
- `rm -rf` on project directories (`lib/`, `src/`, `test/`, `.claude/`)

**Multi-session safety:**
- Before commit/push: runs `git fetch` and counts commits behind remote
- If behind: blocks with "LOCAL BRANCH IS N COMMIT(S) BEHIND REMOTE"
- On commit: updates `.claude/sessions.yaml` with commit hash and message

**Knowledge directory pairing (on commit):**
- If staging a new research/bug/package/feature-flow file, requires `KNOWLEDGE_DIRECTORY.yaml` also staged

**Bug tracker enforcement (on fix commits):**
- If commit message contains `fix`, `bug`, `resolve`, `patch`, `hotfix`: requires a `.claude/bugs/` file in staging

**Staleness warnings (non-blocking):**
- Service edited today → "is SYSTEM_MAP.yaml wiring current?"
- Screen edited today → "is SYSTEM_MAP.yaml screens list current?"
- Table/model edited → "is SYSTEM_MAP.yaml tables current?"

### pre-edit-feature-flow.sh
**Triggers on:** Edits to critical system files

**Critical file patterns (customizable):**
- `encryption_service`, `crypto_service`
- `auth_service`, `auth_provider`, `auth_gate`
- `backup_service`, `restore_service`
- `sync_service`, `sync_provider`
- `app_startup`, `app_init`

**Requires:** A corresponding lifecycle flow doc in `docs/feature_flows/{category}_flow.yaml`. The flow must cover: fresh_install, normal_open, background, force_close_reopen, error_paths. Must include invariants, assumptions, lost/persisted state, and gotchas.

---

## PostToolUse Hooks (Non-blocking)

### post-edit-warnings.sh
**Triggers on:** After file edits

| Warning | Threshold | Message |
|---------|-----------|---------|
| File too large | >800 lines | "Consider extracting sub-modules" |
| Too many imports | >25 imports | "Decompose into focused modules" |
| Modal without scroll wrapper | Missing `SingleChildScrollView`/`ListView` | "Modal body must be scroll-safe" |
| Code deletion with comments removed | ≥1 comment removed AND ≥3 net lines deleted | "Comments document WHY code exists" |
| Workaround language | `workaround`, `hack`, `kludge`, `bandaid` in comments | "STOP AND RESEARCH. Check docs first" |
| Name-based matching | `.name == .name` | "Use IDs, not display names" |
| Entity ID interpolation | `'prefix_${...id}'` | "Verify ID isn't already prefixed" |
| Braceless control flow | `if (x) return` without braces | Shows matching lines |

### post-edit-timestamp.sh
Logs every file edit with UTC timestamp to `.claude/memory/file_edit_log.yaml`. Used by other hooks for cross-session awareness and staleness detection.

### post-read-tracker.sh
Appends normalized file paths to `${PACT_TEMP}/pact_read_files.txt`. Consumed by `pre-edit-rules.sh` for read-before-write enforcement.

### post-sentry-bug-reminder.sh
After issue tracker MCP calls, extracts issue IDs and writes a flag file. `pre-edit-rules.sh` reads this flag and blocks source edits until a bug file is created. Non-blocking warning printed with template instructions.

### post-edit-progress-check.sh
**Thresholds:**
- 30 edits without updating `PENDING_WORK.yaml`
- 20 minutes since last `PENDING_WORK.yaml` update

Warns: "Would a future session know what you're doing, what's complete, and where to pick up?"

### post-edit-checkpoint-audit.sh
Observability hook — detects when checkpoints *should* have been used but weren't. Logs to `pact-events.jsonl` for dashboard correlation. Currently detects: bug_fix checkpoint expected when issue flag is active.

### post-edit-preflight.sh
Data-driven architectural checks from `preflight-checks.yaml`. Each check has a file pattern trigger, content pattern, severity (think/warn), and message. Checks are added as YAML entries, not code.

**Default checks:**
- **aesthetic_engagement** — UI file edited → "Does this project have a design identity?"
- **research_check** — Service file edited → "Check KNOWLEDGE_DIRECTORY and package docs"
- **knowledge_update** — Knowledge file edited → "Will you update KNOWLEDGE_DIRECTORY.yaml?"
- **destroy_before_verify** — Delete/remove/truncate call → "Is replacement verified?"
- **state_without_notification** — Static state changed → "What widget needs to know?"

---

## SessionStart Hooks

### session-register.sh
- Generates session ID, auto-detects agent model (Claude/Gemini)
- Writes to `.claude/sessions.yaml` with start time, model, status
- Prunes sessions >24 hours old
- Warns if ≥2 active sessions detected
- Checks dashboard availability, auto-starts if configured
- Reports vector memory document count
- Checks feedback milestones (day 2, week 2)

### session-status-check.sh
- Checks `status.claude.com` for Claude incidents (major/critical only)
- Checks `status.cloud.google.com` for Gemini incidents (medium/high severity, <24h)
- If Claude degraded: auto-fires `claude-unavailable-banner.sh` with Gemini fallback instructions

---

## Shared Utilities — pact-common.sh

All hooks source this file for cross-platform compatibility:
- `$PACT_PYTHON` — detects python3 or python
- `$PACT_TEMP` — platform-safe temp directory
- `pact_random_hex(n)` — cryptographic random hex (Windows-safe)
- `pact_date_to_epoch(date)` — date string to epoch (macOS/Git Bash compatible)
- `pact_parent_name()` — parent process name lookup

---

## Writing Custom Hooks

1. Create a shell script in `.claude/hooks/` (or `plugins/pact/scripts/`)
2. Exit 1 to block, exit 0 to allow
3. Environment variables available: `$TOOL_NAME`, `$TOOL_INPUT` (JSON), `$FILE_PATH`
4. Source `pact-common.sh` for utilities
5. Register in `.claude/settings.local.json` under the appropriate trigger type
6. For data-driven checks (no code needed): add entries to `preflight-checks.yaml`
