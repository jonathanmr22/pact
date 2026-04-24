# Nested CLAUDE.md Scaffolding — Recommended Layout

Claude Code automatically loads `CLAUDE.md` files at multiple levels:

- The **root** `CLAUDE.md` is always loaded (cross-cutting rules, session-start oath, hook-enforced rule index, behavioral checkpoints).
- A `CLAUDE.md` inside a **subdirectory** is loaded as supplementary context when the agent works on files under that directory.

This means you can split a large root `CLAUDE.md` into a small always-loaded **behavioral core** plus per-domain layers that only load when the agent is editing in that domain. Token-cost win for the always-loaded portion; signal-to-noise win because domain-specific rules surface only when they matter.

## When to use this pattern

Use nested `CLAUDE.md` if your project has any of:

- A root `CLAUDE.md` that's grown past ~12-15k tokens (it's now slowing every session)
- Cleanly separable domains (e.g., a Flutter app with a Supabase backend — Flutter rules and Edge Function rules don't both need to load every turn)
- Stack-specific guidance that only applies to certain directories (database conventions only matter when editing `tables/`)
- Multiple "always-on" rule sets that compete for context space

If your project is small enough that a single root `CLAUDE.md` stays comfortably under ~10k tokens, you don't need this. Use it when the root file becomes a problem, not preemptively.

## Recommended structure

```
/CLAUDE.md                 (always loaded; ~10-12k tokens; behavioral core)
/SYSTEM_MAP.yaml

/lib/CLAUDE.md             (loaded when working under lib/)
/scripts/CLAUDE.md         (loaded when working under scripts/)
/supabase/CLAUDE.md        (loaded when working under supabase/)
/docs/CLAUDE.md            (loaded when working under docs/)

/skills/CLAUDE.md          (loaded when authoring skills)
/plans/CLAUDE.md           (loaded when authoring plans)
/knowledge/CLAUDE.md       (loaded when adding to the knowledge directory)
/feature_flows/CLAUDE.md   (loaded when authoring feature flows)
/bugs/CLAUDE.md            (loaded when investigating or filing bugs)
```

The root file is the **behavioral core**: how to start a session, the cognitive redirections, the checkpoint format, the hook-enforced rule index, the cross-cutting workflow rules. The subdir files are **domain layers**: only the rules and references that matter when actually editing in that subtree.

## What goes in the root vs. each subdir

### Root (always loaded)

- Session-start oath + first-things-to-read list
- All cognitive redirections that apply across domains
- The full Required Checkpoints section (with format spec)
- Hook-enforced rules index (with the WHY behind each — agents need to understand the principle, not just be blocked)
- Cross-cutting workflow rules (TodoWrite discipline, never-overwrite-plans, never-suggest-deferring)
- Pointers to subdir CLAUDE.md files (a one-line index at the top)
- Project mission / playful design principles / domain context

### Subdir layers (loaded on edit in that subtree)

- Domain-specific code-safety rules (e.g., `lib/CLAUDE.md` has Riverpod dispose safety)
- Domain-specific tooling commands (e.g., `scripts/CLAUDE.md` has the detached-PowerShell pattern)
- Domain-specific reference file pointers (e.g., `supabase/CLAUDE.md` has the schema export discipline)
- Domain-specific anti-patterns and gotchas

## What NOT to duplicate

- Don't repeat checkpoints in subdir files — they're loaded from root.
- Don't repeat cognitive redirections that aren't specifically domain-flavored.
- Don't restate the hook-enforced rule index — it lives in root.
- Cross-cutting safety rules (NEVER GUESS on encryption, security/privacy = research-first) stay in root.

## Setup procedure

1. **Audit your current root `CLAUDE.md`** — identify sections that only matter for one domain.
2. **Carve those sections into subdir CLAUDE.md files** at the appropriate paths.
3. **Trim the root** to behavioral core + cross-cutting rules + pointers to the subdir files.
4. **Add a Subdirectory CLAUDE.md table** at the bottom of root listing each subdir + its domain.
5. **Validate in a fresh Claude Code session**: edit a file in each promoted directory and confirm the corresponding `CLAUDE.md` shows up in the loaded context.

## Sizing guidance

| Project size | Recommendation |
|---|---|
| Root <8k tokens, single domain | Stay flat — no nested layout needed |
| Root 8-15k tokens, mixed domains | Optional nested — start with the heaviest domain (e.g., `lib/`) |
| Root >15k tokens | Strongly recommended — root will be slowing every session |
| Root >25k tokens | Required — past this size the agent's effective working context shrinks meaningfully |

## Validation

After setting up nested `CLAUDE.md` files, in a fresh session:

1. Read the root file (you'll see this in the system prompt automatically).
2. Edit a file under each promoted subdirectory.
3. Confirm in the loaded context that the matching subdirectory `CLAUDE.md` appears.

If a subdirectory file does NOT auto-load, the structure isn't working and you should fall back to a single root with selective on-demand loading via skill matchers.

## Trade-offs

**Wins:**
- Smaller always-loaded root file = faster turn-around + cheaper per-turn cost
- Domain-specific signal surfaces only when relevant
- Easier to add new domain layers (just add a new `{dir}/CLAUDE.md`)
- Each subdir's rules are co-located with the code they govern

**Costs:**
- More files to maintain
- Cross-references between root and subdir files can drift if either side changes
- New contributors need to understand the convention (this guide helps)
