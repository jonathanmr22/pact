# PACT Multi-Model Delegation — Complete Guide

Claude orchestrates. Worker models execute. Hooks verify. You approve.

---

## Why Delegate?

60-80% of a typical session's tokens go to tasks that don't require frontier intelligence: reading documentation, writing boilerplate, classifying content, generating seed data. Delegating these to cheaper models saves budget for the work that actually needs Claude: architecture, debugging, security, and review.

---

## The Model Roster

| Model | Role | Cost | Best At |
|-------|------|------|---------|
| **Claude** (Opus 4.6) | Primary Orchestrator | $15-25/M | Architecture, security, debugging, review |
| **Gemini** (2.5 Pro) | Fallback Orchestrator | Free-$7/M | Takes over when Claude is down; manages workers |
| **Trinity** (Arcee) | Research Worker | $0.90/M | Web research, doc summary, classification, plans |
| **M2.5** (MiniMax) | Code Worker | $0.99/M | Boilerplate, tests, CRUD, pattern replication |

Models are configured in `model_roster.yaml`. Swap any model by editing one `model_id` line. Add new models by adding entries to the `workers` section.

---

## The Delegation Decision Tree

```
1. Does this task require project architectural knowledge?
   YES → Orchestrator does it
   NO  → Continue to 2

2. Does this task primarily involve reading/writing external content?
   YES → Delegate to Trinity (research)
   NO  → Continue to 3

3. Does this task involve writing code?
   YES → Continue to 4
   NO  → Delegate to Trinity (plan/doc writing)

4. Is the code security-sensitive, architecturally complex, or a bug fix?
   YES → Orchestrator does it
   NO  → Continue to 5

5. Is there an existing pattern in the codebase this code should follow?
   YES → Delegate to M2.5 with the pattern file as context
   NO  → Orchestrator does it (novel code needs frontier reasoning)
```

---

## The pact-delegate CLI

```bash
# Research task → Trinity
pact-delegate research "Summarize the Flutter 3.41 changelog"

# Code task → M2.5 with pattern file
pact-delegate code "Generate unit tests for BackupService" \
  --context-file lib/services/backup_service.dart --max-tokens 4000

# Classification task → Trinity
pact-delegate classify "Is this content appropriate?" \
  --context-file .claude/tools/prompts/content_classifier.txt

# Plan drafting → Trinity
pact-delegate plan "Design a bulk sync system for interest sources"

# Documentation → Trinity
pact-delegate document "Write API reference for the pulse Edge Function"

# Override model for any task
pact-delegate research "..." --model "google/gemini-2.5-pro"

# View the roster (terminal stats + opens image)
pact-delegate --roster

# Dry debug — see raw API response
pact-delegate research "test query" --raw

# Auto-verify code output
pact-delegate code "generate a function" --verify
```

### Web Search (Tavily integration)

Worker models can search the web before reasoning. Tavily runs the search,
results are injected into the prompt, and the worker synthesizes.

```bash
# Auto-search from the prompt (Tavily extracts queries)
pact-delegate research "What changed in Flutter 3.41?" --web-search

# Explicit search queries (more targeted, repeatable)
pact-delegate research "Find the best kayaking YouTube channel and podcast" \
  --search "best kayaking YouTube channel" \
  --search "best kayaking podcast"
```

This gives Trinity web-informed research at 98% less cost than Claude subagents
with WebSearch. Tavily's free tier provides 1,000 searches/month.

**Options:**
- `--context-file <path>` — Include file contents as context (repeatable)
- `--max-tokens <n>` — Max response tokens (default: 2000)
- `--verify` — Run project analyzer on code output before returning
- `--raw` — Output raw JSON response
- `--model <id>` — Override the routed model
- `--web-search` — Auto-search the web (Tavily) and inject results into prompt
- `--search "<query>"` — Explicit search query (repeatable, implies web search)

**Environment variables:**
- `OPENROUTER_API_KEY` — Required. Get from [openrouter.ai/keys](https://openrouter.ai/keys)
- `TAVILY_API_KEY` — Optional (for `--web-search`/`--search`). Get from [tavily.com](https://www.tavily.com) — free tier: 1,000 searches/month, no credit card required

---

## Verification — Trust Nothing

Worker model output is never committed directly. Every delegation passes through verification:

**Research output (Trinity):**
1. Orchestrator reads the summary
2. Spot-checks claims against its own knowledge
3. Verifies any API patterns or code examples
4. Edits, corrects, and integrates

**Code output (M2.5):**
1. Orchestrator reads the generated code
2. Project analyzer runs automatically (hook)
3. Orchestrator checks for project rule compliance
4. Fixes any issues, then commits

**The key insight:** The existing hook infrastructure catches most coding errors mechanically. Adding worker models doesn't weaken governance — hooks verify regardless of which model wrote the code.

---

## Delegation Log

Every delegation is logged to `docs/reference/delegation_log.yaml` with actual token counts:

```yaml
delegations:
  - timestamp: "2026-04-08T05:46:44Z"
    task_type: research
    model: "arcee-ai/trinity-large-thinking"
    model_name: "Trinity"
    prompt_summary: "Summarize the Flutter 3.41 changelog"
    input_tokens: 183
    output_tokens: 174
    quality: "good"  # Set by orchestrator after review
```

Over time, the log reveals which task types delegate well vs poorly, per-model quality trends, and actual cost savings.

---

## Gemini as Fallback Orchestrator

When Claude is unavailable (usage cap, outage, degraded):

```bash
# Launch Gemini as orchestrator in your terminal
bash .claude/tools/pact-orchestrate

# Or single headless task
bash .claude/tools/pact-orchestrate "finish the bulk sync migration"

# Check availability
bash .claude/tools/pact-orchestrate --status
```

Gemini inherits:
- The same CLAUDE.md rules
- The same hook enforcement
- The same delegation decision tree
- The same worker models via `pact-delegate`
- The same PENDING_WORK.yaml and sessions.yaml

**Auto-detection:** `session-status-check.sh` monitors `status.claude.com`. When Claude degradation is detected, `claude-unavailable-banner.sh` fires automatically with exact instructions for switching to Gemini.

---

## Context Management

Workers don't have access to SYSTEM_MAP.yaml, CLAUDE.md, or the full project context. This is a feature — it limits blast radius.

**Trinity receives:** The research question, relevant URLs, a brief project description if needed. Never: API keys, secrets, internal architecture.

**M2.5 receives:** The coding task, 1-3 pattern files from the codebase, a condensed style guide. Never: full CLAUDE.md, SYSTEM_MAP, security files.

---

## What the Orchestrator NEVER Delegates

- Security, encryption, or auth code
- Architecture decisions or schema changes
- PACT governance files (CLAUDE.md, SYSTEM_MAP, hooks)
- Bug fixes (causal chain tracing requires deep project context)
- Final code review before commit
- Content moderation policy
