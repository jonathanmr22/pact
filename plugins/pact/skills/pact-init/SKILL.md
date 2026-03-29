---
description: Initialize PACT governance files in the current project
disable-model-invocation: false
---

Scaffold the PACT governance infrastructure into this project. Create the following files if they don't already exist:

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

After creating the files, add the PACT cognitive redirections to the project's CLAUDE.md (or create one if it doesn't exist). Include ALL of these:

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

Report what was created and what was skipped (already existed).
