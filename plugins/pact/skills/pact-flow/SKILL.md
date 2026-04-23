---
description: Generate a lifecycle flow document for a feature
disable-model-invocation: false
---

Create a PACT lifecycle flow document for the feature the user specifies. Save it to `feature_flows/{feature_name}_flow.yaml`.

Read the relevant source code first to understand the feature's actual behavior. Then generate a YAML flow document covering:

1. **purpose** — one sentence: what this feature does and why
2. **system_map_section** — pointer to SYSTEM_MAP.yaml (don't duplicate structure)
3. **invariants** — things that must ALWAYS be true
4. **states:**
   - `fresh_install` — what exists, what's empty, what's defaulted
   - `normal_open` — numbered order of operations + assumptions
   - `background` — what's active, held in memory, lost
   - `force_close_reopen` — what's lost, what's persisted, recovery path
   - `background_resume` — what re-initializes, what gets checked
   - `error_paths` — what happens when things go wrong
5. **gotchas** — non-obvious interactions, race conditions, things previous sessions got wrong

After generating, present a verbal summary of the flow to the user for verification before finalizing.

Do NOT duplicate table names, file paths, or provider names from SYSTEM_MAP.yaml — use `system_map_section` to point there instead. This file owns BEHAVIOR (temporal). The map owns STRUCTURE (spatial).
