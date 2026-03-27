<p align="center">
  <img src="assets/pact-handshake.png" alt="PACT — Human and AI shaking hands" width="640"/>
</p>

# PACT — Programmatic Agent Constraint Toolkit

**A framework for governing AI coding agents through infrastructure instead of instructions.**

> Rules are suggestions. Infrastructure is law.

<p align="center">
  <a href="https://buymeacoffee.com/jonathanmr22" target="_blank"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black" alt="Buy Me A Coffee"/></a>
  <img src="https://img.shields.io/badge/version-0.3.0-blue?style=for-the-badge" alt="Version 0.2.1"/>
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
5. **Multi-Agent Resilience** — When Claude is down, switch to Gemini (or vice versa) with zero context loss

---

## Multi-Agent Support (Claude + Gemini)

PACT supports running **multiple AI agents on the same project** — Claude Code and Gemini CLI share the same hooks, rules, and task tracker. When one agent is degraded, switch to the other without losing context.

- **Shared governance:** One set of rules (CLAUDE.md), one set of hooks, one task tracker
- **Model identity:** Sessions and commits are auto-tagged with the agent name
- **Seamless handoffs:** PENDING_WORK.yaml tracks what each agent was doing
- **Status monitoring:** `session-status-check.sh` warns you when Claude is degraded

**[Read the full Multi-Agent Setup Guide →](MULTI_AGENT.md)**

---

## Quick Start — Claude Code Plugin (Recommended)

Install PACT as a Claude Code plugin with one command:

```shell
/plugin marketplace add jonathanmr22/pact
/plugin install pact@pact
```

This gives you:
- **10 hooks** — automatically active (read-before-write, secrets blocker, git safety, multi-session coordination, edit warnings, feature flow protection, issue tracker gate, session tracking, timestamps, status page health check)
- **4 slash commands** — `/pact-init`, `/pact-check`, `/pact-flow`, `/pact-bug`

Then run `/pact-init` in your project to scaffold the governance files (architecture map, flow docs, bug tracker, cognitive redirections, cutting room).

### Customize

After installation, uncomment rules in the hook scripts for your project's specific patterns (forbidden imports, banned functions, critical file patterns, etc.). The hooks live in your Claude Code plugin cache — edit them directly or override with project-level hooks.

---

## Quick Start — Manual Setup (Any Agent)

If you're not using Claude Code, copy the templates manually:

```
your-project/
├── CLAUDE.md                    # ← from templates/instructions.md
├── SYSTEM_MAP.yaml              # ← from templates/architecture_map.yaml
├── cutting_room/                # ← from templates/cutting_room/
│   ├── _INDEX.yaml
│   └── _TRIAL_TEMPLATE.yaml
├── .claude/
│   ├── hooks/
│   │   ├── pre-edit-rules.sh
│   │   ├── pre-bash-guard.sh
│   │   ├── pre-edit-feature-flow.sh
│   │   ├── post-edit-warnings.sh
│   │   ├── post-read-tracker.sh
│   │   ├── post-edit-timestamp.sh
│   │   ├── post-sentry-bug-reminder.sh
│   │   └── session-register.sh
│   ├── bugs/
│   │   ├── _INDEX.yaml
│   │   └── _SOLUTIONS.yaml
│   ├── sessions.yaml            # (auto-maintained by hooks)
│   └── memory/
│       ├── PENDING_WORK.yaml
│       └── file_edit_log.yaml   # (auto-populated by hooks)
├── docs/
│   ├── feature_flows/           # ← lifecycle flow docs
│   ├── plans/                   # ← implementation plans
│   └── reference/
│       └── packages/            # ← per-package knowledge files
```

Configure hooks in `.claude/settings.local.json` (or your agent's equivalent):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          { "type": "command", "command": "bash .claude/hooks/pre-edit-rules.sh" },
          { "type": "command", "command": "bash .claude/hooks/pre-edit-feature-flow.sh" }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "bash .claude/hooks/pre-bash-guard.sh" }
        ]
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
        "hooks": [
          { "type": "command", "command": "bash .claude/hooks/post-read-tracker.sh" }
        ]
      },
      {
        "matcher": "mcp__sentry",
        "hooks": [
          { "type": "command", "command": "bash .claude/hooks/post-sentry-bug-reminder.sh" }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "bash .claude/hooks/session-register.sh" }
        ]
      },
      {
        "hooks": [
          { "type": "command", "command": "bash .claude/hooks/session-status-check.sh", "timeout": 8000 }
        ]
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
| `pre-edit-rules.sh` | PreToolUse (BLOCKS) | Stops hardcoded secrets, enforces read-before-write, gates source edits after issue fetch |
| `pre-bash-guard.sh` | PreToolUse (BLOCKS) | Git safety (no force push, no --no-verify, no reset --hard), multi-session coordination, bug tracker on fix commits |
| `pre-edit-feature-flow.sh` | PreToolUse (BLOCKS) | Requires feature flow doc before editing critical system files (auth, encryption, backup, sync) |
| `post-edit-warnings.sh` | PostToolUse (WARNS) | Large files, high imports, missing scroll wrappers, workaround language, comment deletion, name-based matching |
| `post-read-tracker.sh` | PostToolUse (LOGS) | Tracks file reads to enable read-before-write |
| `post-edit-timestamp.sh` | PostToolUse (LOGS) | Records file edit timestamps for cross-session awareness |
| `post-sentry-bug-reminder.sh` | PostToolUse (GATES) | After fetching an issue, blocks source edits until bug file is created |
| `session-register.sh` | SessionStart (LOGS) | Registers session for multi-session awareness, prunes old sessions |
| `session-status-check.sh` | SessionStart (WARNS) | Checks status.claude.com for major/critical incidents affecting Claude Code or API — warns user at session start, silent when healthy |

### Slash Commands

| Command | What It Does |
|---------|-------------|
| `/pact-init` | Scaffolds governance files into your project (architecture map, flow docs, bug tracker, cognitive redirections, cutting room, session coordination) |
| `/pact-check` | Runs cognitive redirections against your session's changes (staleness audit, dependency trace, cache check) |
| `/pact-flow` | Generates a lifecycle flow document for a feature |
| `/pact-bug` | Creates/updates structured bug investigation files |

### Templates (used by `/pact-init`)

| Template | Purpose |
|----------|---------|
| `architecture_map.yaml` | SYSTEM_MAP wiring map (tables → services → state → UI) |
| `feature_flow.yaml` | Lifecycle state machine (what happens across app states) |
| `instructions.md` | CLAUDE.md with 17 cognitive redirections, semantic safety rules, workflow rules |
| `package_knowledge.yaml` | Per-package research file (prevents guessing at APIs) |
| `pending_work.yaml` | Cross-session task tracker |
| `bugs/_INDEX.yaml` | Bug tracker format specification (30+ standardized tags) |
| `bugs/_SOLUTIONS.yaml` | Reusable solutions knowledge base (4 starter patterns) |
| `cutting_room/_INDEX.yaml` | Visual prototyping workspace registry |
| `cutting_room/_TRIAL_TEMPLATE.yaml` | Trial log format for visual iteration |

### Gemini Integration (templates/gemini/)

| Template | Purpose |
|----------|---------|
| `GEMINI.md` | Project context file for Gemini CLI (points to CLAUDE.md for shared rules) |
| `hooks/before-tool-adapter.sh` | Translates Gemini's JSON hook format → PACT env vars, delegates to `.claude/hooks/` |
| `hooks/after-tool-adapter.sh` | Same adapter pattern for AfterTool (PostToolUse equivalent) |
| `settings.json` | Gemini CLI hook configuration (drop into `.gemini/settings.json`) |

### Documentation

| File | Purpose |
|------|---------|
| `MULTI_AGENT.md` | **Complete guide to running Claude + Gemini on the same project** — installation, hook architecture, task handoffs, parallel sessions |
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
- Force-pushing to main/master
- Committing when local is behind remote

**Self-enforceable** — Requires semantic understanding. These stay as cognitive redirections in the instructions file. Examples:
- "Fresh-read the entity before saving" (stale data bug)
- "Update both the list AND the map cache in provider methods"
- "Trace 3 hops in both directions before editing"
- "Check what your changes made stale before declaring done"
- "Walk through the user journey after building UI"
- "Research before writing workarounds"

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

- After finishing any UI build:
  "Am I the user right now?"
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

### Cutting Room Floor

Complex visuals (heat maps, animations, shaders, charts) should be prototyped *outside* the app framework before committing. The `cutting_room/` directory provides:

- **Project registry** (`_INDEX.yaml`) — tracks active visual prototyping projects
- **Trial log format** (`_TRIAL_TEMPLATE.yaml`) — documents every iteration with parameters, results, and reasoning

Use adjacent tools (Python, HTML/CSS, Shadertoy) to iterate visually. Only move the winning config to the app after nailing the look locally. Four failed in-app attempts that each require a full rebuild could have been one 5-minute Python script.

### Multi-Session Coordination

When multiple AI sessions work on the same codebase simultaneously:

- **`session-register.sh`** records each session's start time and activity
- **`pre-bash-guard.sh`** blocks commits if the local branch is behind remote (another session pushed)
- **`.claude/sessions.yaml`** shows all active sessions — the agent checks this on startup

This prevents the most common multi-session failure: two sessions editing the same files, one pushes, the other commits on stale HEAD and force-pushes to recover, destroying the first session's work.

---

## Adoption Checklist

- [ ] Identify your top 3 recurring agent failures
- [ ] Create `pre-edit-rules.sh` with those 3 patterns
- [ ] Create `post-read-tracker.sh` (read-before-write enforcement)
- [ ] Create `pre-bash-guard.sh` (git safety + multi-session coordination)
- [ ] Create `silent-linter.sh` for your project's analyzer
- [ ] Write `SYSTEM_MAP.yaml` for your most-changed features
- [ ] Write cognitive redirections from your actual failure history
- [ ] Create `PENDING_WORK.yaml` for cross-session continuity
- [ ] Add session oath to instructions file
- [ ] Create `docs/reference/packages/` for package knowledge
- [ ] Create `docs/feature_flows/` for lifecycle flows of critical systems
- [ ] Write your first feature flow for your highest-risk system
- [ ] Create `cutting_room/` for visual prototyping
- [ ] Create `.claude/bugs/` with `_INDEX.yaml` and `_SOLUTIONS.yaml`
- [ ] Set up `session-register.sh` for multi-session awareness

---

## License

PACT is released into the public domain. Use it however you want.
