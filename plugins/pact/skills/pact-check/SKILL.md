---
description: Run PACT cognitive redirections against recent changes
disable-model-invocation: false
---

Review the changes made in this session against PACT's cognitive redirections. For each question, evaluate honestly:

**1. Dependency trace:** For every file edited this session, what depends on it and what does it depend on? Were all downstream consumers updated?

**2. Staleness audit:** What did the changes make stale? Check:
   - Architecture map (SYSTEM_MAP.yaml) — does it still reflect reality?
   - Feature flow docs — do they still describe the correct behavior?
   - Package knowledge files — any new packages used without research?
   - Pending work tracker — updated with current status?

**3. Cache consistency:** If any provider/state management was modified, were ALL caches updated (both list and map caches)?

**4. Package verification:** Were any packages used based on assumption rather than verified documentation? Check `docs/reference/packages/` for knowledge files.

**5. Lifecycle impact:** Do the changes survive all app states? Fresh install, normal open, background, force close, backup restore?

Report findings as:
- **PASS** — checked and correct
- **STALE** — needs updating (specify what)
- **UNCHECKED** — couldn't verify (explain why)
- **VIOLATION** — cognitive redirection was not followed (specify which)
