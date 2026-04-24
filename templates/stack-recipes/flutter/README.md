# Flutter Stack Recipes

**Optional templates for Flutter projects.** PACT itself is stack-agnostic, but Flutter is a popular stack with enough idiosyncratic patterns (Riverpod dispose safety, ORM dual-cache, widget discipline, responsive layout, image compression) that they're worth shipping as recipes a Flutter project can copy into its own `skills/` and `knowledge/`.

## What's here

| Path | Type | Purpose |
|---|---|---|
| `skills/flutter_ui_development.yaml` | Skill | Procedure for building UI: search siblings, check reusables, follow conventions, mental walkthrough, quality gates |
| `skills/emulator_driven_testing.yaml` | Skill | Headless emulator + auto-kill watchdog + screenshots + (optional) marionette-MCP for widget-tree interaction |
| `skills/drift_database.yaml` | Skill | Entity ID dual-key (auto-int + UUID), dual provider cache (list + map), idempotent migrations |
| `patterns/riverpod_dispose_safety.md` | Pattern | The `ConsumerStatefulWidget` container-in-`didChangeDependencies` pattern that prevents the `_dependents.isEmpty` red screen |
| `patterns/widget_discipline.md` | Pattern | One PrimaryActionFab over raw FloatingActionButton, theme over manual `styleFrom`, modal scroll wrapper requirement |
| `patterns/responsive_overflow.md` | Pattern | The every-screen-must-be-responsive checklist + nav bar clearance |
| `patterns/image_compression_standard.md` | Pattern | WebP quality 90 @ 1080px max, single helper enforcement |
| `hooks/flutter-verify.sh` | Hook | PostToolUse hook that runs `flutter analyze` after `.dart` edits |

## When to install

If your project is a Flutter app and uses any of:

- Riverpod (any version)
- Drift (or another local-DB ORM with dual-key entity IDs)
- A pattern of having a single FAB / single primary-action button per screen
- A modal-heavy UI (bottom sheets, dialogs)
- Image upload / persistence

Then these recipes capture patterns that have repeatedly bitten Flutter projects in production. Adopt the ones that match your stack; skip the ones that don't.

## How to install (one-time)

1. **Skills:** copy `skills/*.yaml` into your project's `skills/` directory. Add an entry for each to `skills/_SKILL_INDEX.yaml`.

2. **Patterns:** copy `patterns/*.md` into your project's `knowledge/patterns/` directory. Add an entry to `knowledge/KNOWLEDGE_DIRECTORY.yaml` for each.

3. **Hook:** copy `hooks/flutter-verify.sh` into your project's `.claude/hooks/`. Wire it in `.claude/settings.json` under `hooks.PostToolUse`:
   ```json
   {
     "matcher": "Edit|Write",
     "hooks": [
       {
         "type": "command",
         "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/flutter-verify.sh"
       }
     ]
   }
   ```

4. **Customize per project:** the skills and patterns reference generic widget names (`PrimaryActionFab`, `AppPalette`, `AppTheme.modalScrollWrapper()`). Replace those with your project's actual widget names — the patterns survive renaming, the names don't.

## What this is NOT

- **Not a Flutter starter app** — PACT doesn't ship application scaffolding, only governance
- **Not Flutter-specific PACT mechanisms** — those go in PACT proper (templates/, plugins/pact/)
- **Not a substitute for project-specific knowledge** — these are patterns; your project will accumulate its own conventions on top

## Adapting to other stacks

The structure here is the model for future `templates/stack-recipes/{stack}/` additions:
- `skills/` for procedural how-tos
- `patterns/` for idiomatic gotchas + their fixes
- `hooks/` for stack-specific pre/post hooks
- `README.md` describing what's there + when to adopt

Future contributions for `node/`, `react/`, `rust/`, `go/`, etc. would follow the same shape.

## Versioning

This recipe directory is bundled with PACT and follows PACT's semantic version. When patterns evolve (new Flutter version breaks an idiom, a better approach emerges), the recipes get updated and projects can re-copy.
