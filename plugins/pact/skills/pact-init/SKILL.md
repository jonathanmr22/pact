---
description: Initialize PACT governance files in the current project
disable-model-invocation: false
---

Scaffold the PACT governance infrastructure into this project. Create the following files if they don't already exist:

1. **SYSTEM_MAP.yaml** — Architecture wiring map. Read the project's source files to populate it with actual tables, services, state management, and screens. Don't leave it as a template — fill in the real architecture.

2. **docs/feature_flows/** directory — Create the directory for lifecycle flow documents.

3. **docs/reference/packages/** directory — Create the directory for package knowledge files.

4. **docs/plans/** directory — Create the directory for implementation plans.

5. **cutting_room/** directory with **_INDEX.yaml** and **_TRIAL_TEMPLATE.yaml** — Visual prototyping workspace for iterating on complex visuals outside the framework.

6. **.claude/memory/PENDING_WORK.yaml** — Cross-session task tracker (use the PACT format with in_progress, todo, needs_verification, and completed sections).

7. **.claude/memory/file_edit_log.yaml** — Empty edit log (auto-populated by hooks).

8. **.claude/bugs/_INDEX.yaml** and **.claude/bugs/_SOLUTIONS.yaml** — Bug tracker format spec and solutions knowledge base.

9. **.claude/sessions.yaml** — Multi-session coordination file (auto-maintained by hooks).

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

Report what was created and what was skipped (already existed).
