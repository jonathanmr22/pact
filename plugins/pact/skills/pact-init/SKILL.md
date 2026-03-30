---
description: Initialize PACT governance files in the current project
disable-model-invocation: false
---

**Before scaffolding**, check the project for existing tools that overlap with PACT subsystems. Look for: `.mem0/`, `claude-mem` config, `memsearch` hooks, Taskmaster config, Superpowers skills, or any custom memory/knowledge system in the project's settings or CLAUDE.md.

If you find overlap, present this table to the user BEFORE creating files:

```
PACT Subsystem          Your Existing Tool       Recommendation
─────────────────────   ─────────────────────   ──────────────────────────
Vector memory           [detected tool]          Skip PACT's — yours works
Bug tracker             [none detected]          Install PACT's
Architecture map        [none detected]          Install PACT's
Research knowledge      [detected tool]          Your choice — complementary
Task tracking           [detected tool]          Coexist or pick one
Dashboard               [none detected]          Install PACT's
Hooks/enforcement       [none detected]          Install PACT's (unique to PACT)
Subagents               [none detected]          Install PACT's
```

Let the user decide per row. Only scaffold what they choose. If no overlaps are detected, scaffold everything.

---

Scaffold the PACT governance infrastructure into this project. Create the following files if they don't already exist (and the user hasn't opted out of that subsystem above):

1. **SYSTEM_MAP.yaml** — Architecture wiring map. Read the project's source files to populate it with actual tables, services, state management, and screens. Don't leave it as a template — fill in the real architecture.

2. **docs/feature_flows/** directory — Create the directory for lifecycle flow documents.

3. **docs/reference/packages/** directory — Create the directory for package knowledge files.

4. **docs/reference/research/_RESEARCH.yaml** — Research knowledge base index and format spec. Cross-session synthesis storage for decisions that combined local + external knowledge.

5. **docs/reference/KNOWLEDGE_DIRECTORY.yaml** — Cross-system tag directory. Single-file lookup for all knowledge across research, bugs, solutions, packages, and feature flows.

6. **docs/reference/PACT_BASELINE.yaml** — Capability baseline. Snapshot of the agent's current capabilities, PACT compensations for native limitations, and a capability deltas log for tracking changes over time. Fill in the baseline with the agent's actual model, context window, and available tools.

7. **docs/plans/** directory — Create the directory for implementation plans.

8. **cutting_room/** directory with **_INDEX.yaml** and **_TRIAL_TEMPLATE.yaml** — Visual prototyping workspace for iterating on complex visuals outside the framework.

9. **.claude/memory/PENDING_WORK.yaml** — Cross-session task tracker (use the PACT format with in_progress, todo, needs_verification, and completed sections).

10. **.claude/memory/file_edit_log.yaml** — Empty edit log (auto-populated by hooks).

11. **.claude/bugs/_INDEX.yaml** and **.claude/bugs/_SOLUTIONS.yaml** — Bug tracker format spec and solutions knowledge base.

12. **.claude/sessions.yaml** — Multi-session coordination file (auto-maintained by hooks).

13. **.claude/hooks/preflight-checks.yaml** — Data-driven architectural metacognitive checks. Each check fires based on file path + content patterns and shows a QUESTION (not a rule) that engages reasoning. Start with the template checks (aesthetic identity, research before building, knowledge directory awareness, destroy before verify, state without notification) and add project-specific checks as incidents occur.

14. **.claude/skills/{project}-aesthetic.md** — Project design identity skill with `user-invocable: false`. Ask the user about their project's design personality, emotional tone, color philosophy, and anti-patterns. Write an evocative skill (principles, not prescriptions) that auto-triggers when the agent builds UI. Use the aesthetic_skill.md template.

15. **.claude/hooks/pact-event-logger.sh** — Central PACT event logger. Copy from the dashboard templates. This is the backbone that other hooks call to log events for the dashboard.

16. **.claude/hooks/pact-prompt-logger.sh** — User prompt capture hook. Copy from the dashboard templates. Logs user messages as dashboard event cards with IDE context stripped.

17. **.claude/pact-dashboard.html** — Live dashboard UI. Copy from the dashboard templates.

18. **.claude/hooks/pact-server.py** — Dashboard server. Copy from the dashboard templates.

19. **~/.claude/pact-config.json** — Dashboard startup preference. Create with `{"dashboard": "ask"}`. Ask the user if they'd like it set to `"auto"` (start every session), `"ask"` (agent offers each time), or `"off"` (never).

20. **.claude/agents/** directory — Copy the three PACT subagents (`pact-tracer.md`, `pact-researcher.md`, `pact-reviewer.md`) to the project's `.claude/agents/` directory. These are auto-dispatched by Claude during normal work — the user doesn't need to invoke them manually.

After creating the files, update `.claude/settings.local.json` to register the prompt logger hook under `UserPromptSubmit` with a 10-second timeout. Also ensure the `SessionStart` hooks include `session-register.sh` (which checks dashboard status and emits session events).

Then add the PACT cognitive redirections to the project's CLAUDE.md (or create one if it doesn't exist). Include ALL of these:

- "When the user makes a correction: Is this right?"
- "When encountering a technology/library/API: What does this project actually use?"
- "When about to write code based on memory: Have I actually read this file?"
- "When declaring a task done: What wasn't checked?"
- "When about to say I'm satisfied: What happens to this system tomorrow?"
- "When a doc says X but you haven't verified: Is this still true?"
- "When about to edit any file: What depends on this, and what does this depend on?"
- "When about to remove or replace code: Why does this code exist?"
- "When a package doesn't behave as expected: Do I actually know this package?"
- "When proposing security/privacy architecture: Have I researched what exists?"
- "When finding an objection to your solution: Is this objection real, or am I folding?"
- "When something is broken or regressed: Can I fix this forward?"
- "When about to say I can't do X: What CLI tool handles this?"
- "When building a complex visual: Can I prototype this outside the framework first?"
- "Before declaring done: Did I do everything the user asked?"
- "After finishing any UI build: Am I the user right now?"
- "When something doesn't work: Is this a bug? Has it been solved before?"
- "When something about your capabilities feels different: Is this new, and does it change how PACT works?"
- "When about to research something: Does this need project understanding, online research, or both?"
- "When about to declare work done or commit: Have I dispatched pact-reviewer for a second opinion?"

Also add this section to CLAUDE.md under Workflow Rules:

### Subagent Delegation (PACT Agents)

Three PACT subagents are available. Dispatch them proactively — do NOT wait for the user to ask.

- **pact-tracer** — Dispatch BEFORE editing any file that appears in SYSTEM_MAP.yaml or touches a database table, service, state class, or shared utility. It traces dependency chains and returns an impact report. Use this instead of trying to hold the full dependency graph in your own context.

- **pact-researcher** — Dispatch when you're about to write code using a package, API, or pattern you haven't verified this session. It checks existing PACT knowledge first, researches if needed, and saves findings back. Use this instead of guessing from training data.

- **pact-reviewer** — Dispatch BEFORE committing feature work or multi-file changes (3+ files). It runs the full governance checklist in a fresh context. Use this instead of self-reviewing your own work. Skip for trivial commits (typo fixes, version bumps, single-line changes).

The goal: your context window stays focused on the user's task. Governance, research, and review happen in isolated subagent contexts and feed results back to you.

Report what was created and what was skipped (already existed).
