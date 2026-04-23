# PACT Multi-Agent Setup — Claude + Gemini

**When Claude is down, switch to Gemini. When Gemini is down, switch to Claude.**
Both agents share the same governance, the same hooks, and the same task tracker.
Switching feels like handing work to a coworker, not starting from scratch.

---

## Why Multi-Agent?

AI coding agents have outages. When your primary agent is degraded, you have three options:
1. **Wait** — lose hours of productivity.
2. **Work without governance** — use the other agent raw, lose all your rules and context.
3. **Use PACT** — both agents share the same infrastructure, handoffs are seamless.

---

## Quick Setup

### Prerequisites
- **Claude Code** installed and authenticated
- **Node.js** installed (for Gemini CLI)

### Step 1: Install Gemini CLI

```bash
npm install -g @google/gemini-cli
```

Then run `gemini` once and choose "Sign in with Google" for OAuth.
Free tier: 1,000 requests/day — enough for a full work session.

For higher limits: get an API key from https://aistudio.google.com/apikey
and set `export GEMINI_API_KEY="YOUR_KEY"`.

### Step 2: Create GEMINI.md

Copy `templates/gemini/GEMINI.md` to your project root. Customize the
`{{PROJECT_NAME}}` placeholder. This file tells Gemini where to find
your rules, how to identify itself, and how to pick up work from Claude.

### Step 3: Set Up Gemini Hooks

```bash
# Create the Gemini hooks directory
mkdir -p .gemini/hooks

# Copy the adapter scripts
cp templates/gemini/hooks/before-tool-adapter.sh .gemini/hooks/
cp templates/gemini/hooks/after-tool-adapter.sh .gemini/hooks/

# Copy the settings file
cp templates/gemini/settings.json .gemini/settings.json
```

The adapter scripts translate Gemini's JSON hook format to PACT's
environment variable format, then delegate to the SAME hook scripts
in `.claude/hooks/`. One set of rules, two agents.

### Step 4: Verify

```bash
# Start a Gemini session in your project
cd your-project
gemini

# You should see:
# [Session] Registered: 2026-03-27T... (gemini)
# [Status] All systems operational     ← or a warning if Claude/Gemini is degraded
```

---

## How It Works

### Shared Infrastructure

Both agents read and write to the same files:

| File | Purpose | Who Writes |
|---|---|---|
| `CLAUDE.md` | Project rules (applies to ALL agents despite the name) | Human, Claude, Gemini |
| `GEMINI.md` | Gemini-specific context + pointer to CLAUDE.md | Human, Gemini |
| `SYSTEM_MAP.yaml` | Architecture wiring map | Claude, Gemini |
| `.claude/sessions.yaml` | Active session tracker (all agents) | Hooks (auto) |
| `.claude/memory/PENDING_WORK.yaml` | Cross-session task tracker | Claude, Gemini |
| `.claude/memory/file_edit_log.yaml` | Edit timestamps | Hooks (auto) |
| `bugs/` | Bug investigations | Claude, Gemini |
| `feature_flows/` | Lifecycle flow docs | Claude, Gemini |
| `knowledge/packages/` | Package knowledge | Claude, Gemini |
| `knowledge/research/` | Cross-session research synthesis | Claude, Gemini |
| `knowledge/KNOWLEDGE_DIRECTORY.yaml` | Tag index across all knowledge systems | Claude, Gemini |
| `knowledge/PACT_BASELINE.yaml` | Agent capability baseline + deltas | Claude, Gemini |

### Model Identity in Sessions

The `session-register.sh` hook auto-detects which agent is running and tags sessions:

```yaml
sessions:
  - id: "2026-03-27T10:00:00Z_a1b2"
    started: "2026-03-27T10:00:00Z"
    model: claude        # ← auto-detected
    status: active
  - id: "2026-03-27T14:00:00Z_c3d4"
    started: "2026-03-27T14:00:00Z"
    model: gemini        # ← auto-detected
    status: active
```

### Model Identity in Commits

Each agent uses a different `Co-Authored-By`:
- **Claude:** `Co-Authored-By: Claude <noreply@anthropic.com>`
- **Gemini:** `Co-Authored-By: Gemini <noreply@google.com>`

This makes `git log` instantly show who did what.

### Hook Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Claude Code │────▶│  .claude/hooks/  │◀────│  Gemini CLI      │
│  PreToolUse  │     │  pre-edit-rules  │     │  BeforeTool      │
│  PostToolUse │     │  pre-bash-guard  │     │  AfterTool       │
│  SessionStart│     │  post-edit-warn  │     │  SessionStart    │
└──────────────┘     │  session-register│     └──────────────────┘
                     │  status-check    │              ▲
                     └──────────────────┘              │
                              ▲                 ┌──────┴─────────┐
                              │                 │ .gemini/hooks/ │
                              └─────────────────│ adapter scripts│
                                                │ (JSON → env)   │
                                                └────────────────┘
```

Claude Code calls `.claude/hooks/` directly.
Gemini CLI calls `.gemini/hooks/` adapters, which translate the JSON format
and delegate to the same `.claude/hooks/` scripts.

**One set of rules. Two agents. Zero drift.**

### Task Handoff

When switching agents mid-task:

1. **The outgoing agent** updates `PENDING_WORK.yaml` with current status
2. **The incoming agent** reads `PENDING_WORK.yaml` on session start
3. **The incoming agent** runs `git pull` (hooks enforce this)
4. **The incoming agent** fresh-reads all files in the task's files list
5. Work continues

The incoming agent knows:
- What was being worked on (PENDING_WORK.yaml)
- What files were recently edited (file_edit_log.yaml)
- Whether the outgoing agent committed (sessions.yaml + git log)
- What the project rules are (CLAUDE.md)
- What the architecture looks like (SYSTEM_MAP.yaml)

This is the same context a human coworker would need. PACT just makes it machine-readable.

---

## Multi-Model Delegation — The Model Roster

Beyond failover, PACT supports **multi-model delegation** — routing tasks to
specialized worker models via OpenRouter, orchestrated by whichever agent
(Claude or Gemini) is currently active.

### The Roster

| Model | Role | Cost | Best At |
|-------|------|------|---------|
| **Claude** (Opus 4.6) | Primary Orchestrator | $15-25/M | Architecture, security, debugging, review |
| **Gemini** (2.5 Pro) | Fallback Orchestrator | Free-$7/M | Takes over when Claude is down; manages workers |
| **Trinity** (Arcee) | Research Worker | $0.90/M | Web research, doc summary, classification, plans |
| **M2.5** (MiniMax) | Code Worker | $0.99/M | Boilerplate, tests, CRUD, pattern replication |

### How It Works

1. The active orchestrator (Claude or Gemini) evaluates each task
2. Tasks that don't need frontier reasoning get delegated to workers via `pact-delegate`
3. Workers return output → orchestrator reviews, fixes, integrates
4. Hooks verify ALL code regardless of which model wrote it

**When Gemini is orchestrator**, it follows the same delegation decision tree as
Claude and invokes `pact-delegate` to route tasks to Trinity/M2.5. The workers
don't know or care which orchestrator is managing them — they receive a prompt
and return a response.

### Setup

```bash
# Copy delegation templates to your project
cp -r templates/delegation/ .claude/tools/

# Set your OpenRouter API key (for worker models)
export OPENROUTER_API_KEY="your-key-from-openrouter.ai"

# View the roster
bash .claude/tools/pact-delegate --roster

# Delegate a research task to Trinity
bash .claude/tools/pact-delegate research "Summarize the Flutter 3.41 changelog"

# Delegate a coding task to M2.5 with pattern context
bash .claude/tools/pact-delegate code "Generate unit tests" \
  --context-file lib/services/my_service.dart
```

See `templates/delegation/model_roster.yaml` for the full roster config.
Swap models by changing one `model_id` line. Add new models by adding entries.

---

## Cooperative Mode — Agents Working Together

Beyond failover, PACT supports **cooperative delegation** — one agent dispatching
tasks to the other in real time. This is not a "second opinion" chat; Gemini gets
full tool access and can edit files, run commands, and search the web.

### How It Works

The `delegate-to-gemini.sh` script invokes Gemini CLI in headless mode (`--prompt`).
The calling agent (e.g., Claude) passes a task description, and Gemini executes it
with access to the full project — governed by the same PACT hooks.

### Usage (from Claude Code)

```bash
# Research mode (default) — read-only, safe to run anytime
bash .gemini/delegate-to-gemini.sh "research the maplibre API for custom marker clustering"

# Edit mode — Gemini can modify files (check git diff after)
bash .gemini/delegate-to-gemini.sh --edit "extract the retry logic from pulse_service.dart into a reusable helper"

# Explicit research mode — web search enabled
bash .gemini/delegate-to-gemini.sh --research "what breaking changes are in supabase-flutter v2.12"
```

### When to Delegate

Good delegation tasks:
- **Research** — "what does this API look like?" (Gemini has Google Search built-in)
- **Parallel work** — "refactor this file while I work on the provider"
- **Package investigation** — "check the changelog for breaking changes in X"
- **Boilerplate** — "generate the Drift table and migration for this schema"
- **Second implementation** — "write an alternative approach so we can compare"

Bad delegation tasks:
- Anything touching security, encryption, or auth (too high risk for unsupervised edits)
- Tasks that require deep context about the current conversation
- UI work that needs iterative visual feedback

### Safety

- Default mode is **read-only** — Gemini can research but not edit files
- `--edit` mode enables file changes, but PACT hooks still enforce all rules
  (read-before-write, no secrets, no force push, feature flow requirements)
- After any `--edit` delegation, the calling agent should `git diff` to review changes
- Both agents' edits appear in `file_edit_log.yaml` for auditability

### Adding to Your Instructions File

Tell your primary agent when and how to delegate. Example for CLAUDE.md:

```markdown
## Cooperative Delegation
When facing research-heavy tasks or parallelizable work, delegate to Gemini:
- `bash .gemini/delegate-to-gemini.sh "task"` — research mode (safe)
- `bash .gemini/delegate-to-gemini.sh --edit "task"` — edit mode (review after)
Always review Gemini's changes with `git diff` before committing.
```

---

## When to Switch

The `session-status-check.sh` hook warns you at session start when there's
a major incident on status.claude.com. When you see:

```
[Status] Active incident on status.claude.com:
[Status] WARNING: Elevated error rates on Opus 4.6 [monitoring] (since ...)
```

That's your signal to run `gemini` instead of `claude` for this session.

---

## Parallel Sessions

Both agents can work simultaneously on the same repo (on different tasks).
The `pre-bash-guard.sh` hook blocks commits when local is behind remote,
forcing a `git pull` before pushing. This prevents destructive overwrites.

Sessions file tracks both agents:
```
[Session] WARNING: 3 active sessions detected (Claude: ~2, Gemini: ~1)
```

---

## FAQ

**Q: Do I need to maintain two sets of rules?**
No. CLAUDE.md is the single source of truth for rules. GEMINI.md just points to it
and adds Gemini-specific context (tool mapping, identity).

**Q: Do I need to maintain two sets of hooks?**
No. The `.gemini/hooks/` adapters are thin wrappers (~20 lines each) that delegate
to `.claude/hooks/`. When you update a PACT hook, both agents get the change.

**Q: What if Gemini interprets CLAUDE.md differently than Claude?**
The cognitive redirections and rules are written as questions and clear instructions,
not Claude-specific syntax. They work with any reasoning model. If you find a rule
that one agent follows and the other doesn't, make it more explicit or add a hook.

**Q: Can I use other agents (Copilot, Cursor, Aider)?**
The hook adapter pattern works for any agent with a hook system. The governance
files (SYSTEM_MAP, PENDING_WORK, feature flows) are plain YAML/markdown — any
agent can read them. You'd need to write adapters for that agent's hook format.

**Q: Is this free?**
Gemini CLI: free with a Google account (1,000 req/day).
Claude Code: requires Anthropic API key or subscription.
PACT: free and open source.
