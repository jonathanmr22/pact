<p align="center">
  <img src="assets/pact-handshake.png" alt="PACT — Human and AI shaking hands" width="640"/>
</p>

# PACT — Programmatic Agent Constraint Toolkit

**A framework for governing AI coding agents through infrastructure instead of instructions.**

> Rules are suggestions. Infrastructure is law.

<p align="center">
  <a href="https://buymeacoffee.com/jonathanmr22" target="_blank"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black" alt="Buy Me A Coffee"/></a>
  <img src="https://img.shields.io/badge/version-0.1.0-blue?style=for-the-badge" alt="Version 0.1.0"/>
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="MIT License"/>
</p>

---

## What Is PACT?

PACT is a governance framework for AI coding agents (Claude Code, Cursor, Copilot Workspace, etc.) that replaces instruction-based rules with mechanical enforcement, context replacement, and self-evolving reasoning.

AI agents forget rules under cognitive load. They confidently edit files they haven't read. They make single-layer fixes that break downstream systems. They guess at package APIs instead of reading documentation. No amount of prompt engineering fixes these problems because they are architecture problems, not model problems.

PACT addresses this with four pillars:

1. **Mechanical Enforcement** — Shell hooks that block violations before they land
2. **Context Replacement** — Architecture maps and lifecycle flows that replace memory
3. **Self-Evolving Reasoning** — Questions the agent asks itself at decision points
4. **Structure/Behavior Separation** — Static wiring maps vs dynamic lifecycle flows

---

## Quick Start — Claude Code Plugin (Recommended)

Install PACT as a Claude Code plugin with one command:

```shell
/plugin marketplace add jonathanmr22/pact
/plugin install pact@pact
```

This gives you:
- **5 hooks** — automatically active (read-before-write, secrets blocker, edit warnings, timestamps, read tracker)
- **4 slash commands** — `/pact-init`, `/pact-check`, `/pact-flow`, `/pact-bug`

Then run `/pact-init` in your project to scaffold the governance files (architecture map, flow docs, bug tracker, cognitive redirections).

### Customize

After installation, uncomment rules in the hook scripts for your project's specific patterns (forbidden imports, banned functions, etc.). The hooks live in your Claude Code plugin cache — edit them directly or override with project-level hooks.

---

## Quick Start — Manual Setup (Any Agent)

If you're not using Claude Code, copy the templates manually:

```
your-project/
├── CLAUDE.md                    # ← from templates/instructions.md
├── SYSTEM_MAP.yaml              # ← from templates/architecture_map.yaml
├── .claude/
│   ├── hooks/
│   │   ├── pre-edit-rules.sh    # ← from plugins/pact/scripts/pre-edit-rules.sh
│   │   ├── post-edit-warnings.sh# ← from plugins/pact/scripts/post-edit-warnings.sh
│   │   ├── post-read-tracker.sh # ← from plugins/pact/scripts/post-read-tracker.sh
│   │   └── post-edit-timestamp.sh# ← from plugins/pact/scripts/post-edit-timestamp.sh
│   ├── bugs/
│   │   ├── _INDEX.yaml          # ← from templates/bugs/_INDEX.yaml
│   │   └── _SOLUTIONS.yaml      # ← from templates/bugs/_SOLUTIONS.yaml
│   └── memory/
│       ├── PENDING_WORK.yaml    # ← from templates/pending_work.yaml
│       └── file_edit_log.yaml   # (auto-populated by hooks)
├── docs/
│   ├── feature_flows/           # ← lifecycle flow docs go here
│   ├── plans/                   # ← implementation plans go here
│   └── reference/
│       └── packages/            # ← per-package knowledge files go here
```

Configure hooks in `.claude/settings.local.json` (or your agent's equivalent):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "bash .claude/hooks/pre-edit-rules.sh" }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          { "type": "command", "command": "bash .claude/hooks/post-edit-warnings.sh" },
          { "type": "command", "command": "bash .claude/hooks/post-edit-timestamp.sh" }
        ]
      },
      {
        "matcher": "Read",
        "hooks": [{ "type": "command", "command": "bash .claude/hooks/post-read-tracker.sh" }]
      }
    ]
  }
}
```

---

## What You Get

### Hooks (automatic, no action needed)

| Hook | Type | What It Does |
|------|------|-------------|
| `pre-edit-rules.sh` | PreToolUse (BLOCKS) | Stops hardcoded secrets, enforces read-before-write |
| `post-edit-warnings.sh` | PostToolUse (WARNS) | Flags large files (>800 lines), high import counts (>25) |
| `post-read-tracker.sh` | PostToolUse (LOGS) | Tracks file reads to enable read-before-write |
| `post-edit-timestamp.sh` | PostToolUse (LOGS) | Records file edit timestamps for cross-session awareness |

### Slash Commands

| Command | What It Does |
|---------|-------------|
| `/pact-init` | Scaffolds governance files into your project (architecture map, flow docs, bug tracker, cognitive redirections) |
| `/pact-check` | Runs cognitive redirections against your session's changes (staleness audit, dependency trace, cache check) |
| `/pact-flow` | Generates a lifecycle flow document for a feature |
| `/pact-bug` | Creates/updates structured bug investigation files |

### Templates (used by `/pact-init`)

| Template | Purpose |
|----------|---------|
| `architecture_map.yaml` | SYSTEM_MAP wiring map (tables → services → state → UI) |
| `feature_flow.yaml` | Lifecycle state machine (what happens across app states) |
| `instructions.md` | CLAUDE.md with cognitive redirections and session oath |
| `package_knowledge.yaml` | Per-package research file (prevents guessing at APIs) |
| `pending_work.yaml` | Cross-session task tracker |
| `bugs/_INDEX.yaml` | Bug tracker format specification |
| `bugs/_SOLUTIONS.yaml` | Reusable solutions knowledge base |

### Documentation

| File | Purpose |
|------|---------|
| `EXAMPLES.md` | 9 real-world examples from a production project |
| `CHANGELOG.md` | Versioned change history |

---

## Core Concepts

### Hook-Enforceable vs Self-Enforceable Rules

Every rule falls into one of two categories:

**Hook-enforceable** — Can be detected by text pattern matching. These become PreToolUse hooks that mechanically block violations. Examples:
- Forbidden imports (`import hive`, `import firebase`)
- Banned functions (`print()`, `debugPrint()`)
- Hardcoded secrets (`api_key = "sk-..."`)
- Raw SQL with string interpolation
- Editing a file that hasn't been read this session

**Self-enforceable** — Requires semantic understanding. These stay as cognitive redirections in the instructions file. Examples:
- "Fresh-read the entity before saving" (stale data bug)
- "Update both the list AND the map cache in provider methods"
- "Trace 3 hops in both directions before editing"
- "Check what your changes made stale before declaring done"

**The rule:** If a violation can be detected by grep, it's a hook. If it requires understanding, it's a redirection. The instructions file only contains rules that hooks cannot catch.

### Cognitive Redirections

Traditional rules get skimmed under cognitive load. Cognitive redirections are *questions* that engage reasoning at specific decision points:

```
- When about to edit any file:
  "What depends on this, and what does this depend on?"

- When declaring a task done:
  "What did my changes just make stale?"

- When a package doesn't behave as expected:
  "Do I actually know this package, or am I guessing?"
```

The agent has autonomy to add new redirections when it notices itself making assumptions or falling into patterns. Future sessions inherit this self-awareness.

### Architecture Map vs Lifecycle Flow

| | Architecture Map | Lifecycle Flow |
|---|---|---|
| **Answers** | "What files do I touch?" | "What breaks if I touch them wrong?" |
| **Contains** | Tables, services, state, screens, caches, cascades | States, ordering, assumptions, memory model |
| **Nature** | Static structure (spatial) | Dynamic behavior (temporal) |
| **Analogy** | Circuit diagram | Timing diagram |

If you're writing a table name in a flow doc → stop, that belongs in the map.
If you're writing "this must happen before that" in the map → stop, that belongs in a flow.

---

## Adoption Checklist

- [ ] Identify your top 3 recurring agent failures
- [ ] Create `pre-edit-rules.sh` with those 3 patterns
- [ ] Create `post-read-tracker.sh` (read-before-write enforcement)
- [ ] Create `silent-linter.sh` for your project's analyzer
- [ ] Write `SYSTEM_MAP.yaml` for your most-changed features
- [ ] Write 3 cognitive redirections from your actual failure history
- [ ] Create `PENDING_WORK.yaml` for cross-session continuity
- [ ] Add session oath to instructions file
- [ ] Create `docs/reference/packages/` for package knowledge
- [ ] Create `docs/feature_flows/` for lifecycle flows of critical systems
- [ ] Write your first feature flow for your highest-risk system

---

## License

PACT is released into the public domain. Use it however you want.
