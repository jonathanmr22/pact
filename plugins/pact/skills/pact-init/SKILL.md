---
description: Initialize PACT governance files in the current project
disable-model-invocation: false
---

Scaffold the PACT governance infrastructure into this project. Create the following files if they don't already exist:

1. **SYSTEM_MAP.yaml** — Architecture wiring map. Read the project's source files to populate it with actual tables, services, state management, and screens. Don't leave it as a template — fill in the real architecture.

2. **docs/feature_flows/** directory — Create the directory for lifecycle flow documents.

3. **docs/reference/packages/** directory — Create the directory for package knowledge files.

4. **docs/plans/** directory — Create the directory for implementation plans.

5. **.claude/memory/PENDING_WORK.yaml** — Cross-session task tracker (use the PACT format with in_progress, todo, needs_verification, and completed sections).

6. **.claude/memory/file_edit_log.yaml** — Empty edit log (auto-populated by hooks).

7. **.claude/bugs/_INDEX.yaml** and **.claude/bugs/_SOLUTIONS.yaml** — Bug tracker format spec and solutions knowledge base.

After creating the files, add the PACT cognitive redirections to the project's CLAUDE.md (or create one if it doesn't exist). Include at minimum:
- "When about to edit any file: What depends on this, and what does this depend on?"
- "When declaring a task done: What did my changes just make stale?"
- "When a package doesn't behave as expected: Do I actually know this package, or am I guessing?"
- "When the user makes a correction: Is this right?"
- "When about to remove code: Why does this code exist?"

Report what was created and what was skipped (already existed).
