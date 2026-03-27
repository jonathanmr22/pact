# PACT Multi-Agent Setup — Claude + Gemini

**When Claude is down, switch to Gemini. When Gemini is down, switch to Claude.**
Both agents share the same governance, the same hooks, and the same task tracker.
Switching feels like handing work to a coworker, not starting from scratch.

---

## Why Multi-Agent?

AI coding agents have outages. When your primary agent is degraded, you have three options:
1. **Wait** — lose hours of productivity
2. **Work without governance** — use the other agent raw, lose all your rules and context
3. **Use PACT** — both agents share the same infrastructure, handoffs are seamless

PACT chooses option 3.

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
| `.claude/bugs/` | Bug investigations | Claude, Gemini |
| `docs/feature_flows/` | Lifecycle flow docs | Claude, Gemini |
| `docs/reference/packages/` | Package knowledge | Claude, Gemini |

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
