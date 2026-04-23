# {{PROJECT_NAME}} — Gemini Context

You are Gemini, working on this project alongside Claude (via Claude Code).
You share the same codebase, governance files, and hook infrastructure.

## Model Identity

You are **Gemini**. Always identify yourself in:
- **Commit messages:** `Co-Authored-By: Gemini <noreply@google.com>`
- **Session logs:** your sessions appear in `.claude/sessions.yaml` with `model: gemini`
- **PENDING_WORK.yaml:** tag entries with `agent: gemini`

When you see work from Claude in git log or PENDING_WORK, do NOT redo it.
When you see work from another Gemini session, coordinate via sessions.yaml.

## Shared Governance

All project rules are in CLAUDE.md (the name is historical — rules apply to ALL agents).
Read it fully before doing any work. Key governance files:

- `CLAUDE.md` — All rules, cognitive redirections, safety rules
- `SYSTEM_MAP.yaml` — Wiring map (data flow: tables -> services -> state -> UI)
- `.claude/memory/PENDING_WORK.yaml` — Cross-session task tracker
- `.claude/memory/file_edit_log.yaml` — File edit timestamps (auto-populated by hooks)
- `.claude/sessions.yaml` — Active sessions (all agents)
- `bugs/_INDEX.yaml` — Bug tracker protocol
- `bugs/_SOLUTIONS.yaml` — Reusable solutions knowledge base
- `feature_flows/` — Lifecycle flow docs for critical systems
- `knowledge/packages/` — Package knowledge files (research before coding)
- `knowledge/research/_RESEARCH.yaml` — Cross-session research synthesis (check before researching)
- `knowledge/KNOWLEDGE_DIRECTORY.yaml` — Tag index across all knowledge systems (read before researching to find what already exists)
- `knowledge/PACT_BASELINE.yaml` — Agent capability baseline (check at session start if anything feels different)

## Session Start Protocol

At the start of every conversation:
1. State: "I have read and will follow all project rules from CLAUDE.md."
2. Read `.claude/memory/PENDING_WORK.yaml` — check for in-progress tasks
3. Read `.claude/sessions.yaml` — check for active Claude or Gemini sessions
4. Read `.claude/memory/file_edit_log.yaml` (recent entries) — know what was touched
5. If another session pushed recently, run `git pull` before any work
6. Glance at `knowledge/PACT_BASELINE.yaml` — does your model or available tools differ from the baseline? If yes, add a `capability_deltas[]` entry.
7. List the cognitive redirections from CLAUDE.md

## Handoff Protocol

When picking up work that Claude started (or vice versa):
1. Read PENDING_WORK.yaml for the task's current status and files list
2. `git log --oneline -10` to see recent commits and who made them
3. Fresh-read every file in the task's files list — never assume state from the task description
4. If the task says "code_complete_not_committed", verify with `git diff` before committing
5. If the task says "done_not_committed", run the project's analyzer before committing
6. Update PENDING_WORK.yaml with your progress and tag `agent: gemini`

## Tool Mapping

Your tools map to Claude Code's tools:
| Your Tool | Claude Code Equivalent |
|---|---|
| `run_shell_command` | Bash |
| `replace` | Edit |
| `write_file` | Write |
| `read_file` | Read |
| `grep_search` | Grep |
| `glob` | Glob |
| `google_web_search` | WebSearch |
| `web_fetch` | WebFetch |
