# PACT vs Other Plugins — What's Different?

There are a lot of tools in the Claude Code ecosystem now. This document explains where PACT fits and how it compares to the most popular alternatives. The goal isn't to say "PACT is better" — these tools solve different problems, and many work well together.

**Last updated:** 2026-03-30

---

## Quick Reference

| Tool | Stars | What It Does | Overlap with PACT |
|------|------:|-------------|-------------------|
| [Superpowers](https://github.com/obra/superpowers) | 120K+ | Workflow orchestration (brainstorm → plan → TDD → subagent dispatch → review) | Low — different layer |
| [feature-dev](https://github.com/anthropics/claude-code/tree/main/plugins/feature-dev) | Official | 7-phase feature development workflow with specialized agents | Low |
| [claude-mem](https://github.com/thedotmack/claude-mem) | 42K+ | Automatic session capture → SQLite → context injection | Medium — both do memory |
| [Agents](https://github.com/wshobson/agents) | 32K+ | Multi-agent orchestration with specialized agent roles | Low |
| [Taskmaster](https://github.com/eyaltoledano/claude-task-master) | 26K+ | AI-powered task management across 13 IDEs | Low — PACT has PENDING_WORK |
| [Repomix](https://github.com/yamadashy/repomix) | 23K+ | Pack entire repo into a single AI-friendly file | None |
| [claude-supermemory](https://github.com/supermemoryai/claude-supermemory) | 2.4K+ | Real-time learning and knowledge persistence | Medium — both do memory |
| [memsearch](https://github.com/zilliztech/memsearch) | 1K+ | Markdown-first memory with vector search | Medium — both do memory |
| [code-review](https://github.com/anthropics/claude-code/tree/main/plugins/code-review) | Official | 4 parallel review agents (compliance, bugs, git history) | Low |
| [claude-code-workflows](https://github.com/shinpr/claude-code-workflows) | 254 | Dev workflow recipes (frontend, backend, fullstack) | Low |
| **PACT** | — | Cross-session governance: knowledge accumulation, mechanical enforcement, multi-tree status board + Aider-style Codebase Intent Map (auto-rebuilding) | — |

---

## Detailed Comparisons

### PACT vs Superpowers

The most common comparison. These tools look similar on the surface but operate at different layers.

| | Superpowers | PACT |
|---|---|---|
| **Core question** | "How should the agent work through this task?" | "What should the agent know and what must it never do?" |
| **Scope** | Within a single session | Across all sessions |
| **Enforcement** | Skill triggers (prompt-based) | Shell hooks (mechanical — can't be skipped) |
| **Memory** | None — each session starts fresh | Persistent — research, bugs, packages, architecture |
| **Workflow** | Rigid phases: brainstorm → plan → TDD → review | Flexible — augments your existing workflow |
| **TDD** | Core philosophy, deeply enforced | Not addressed |
| **Subagent dispatch** | Core feature with two-stage review | 3 auto-dispatched agents (tracer, researcher, reviewer) |
| **Architecture awareness** | Not addressed | SYSTEM_MAP + feature flows |
| **Knowledge accumulation** | Not addressed | Core feature (compound intelligence) |
| **Multi-agent** | Supports Cursor, Codex, Gemini, OpenCode | Claude + Gemini with shared governance |

**Verdict:** Complementary. Superpowers makes the agent disciplined within a session. PACT makes the agent knowledgeable across sessions. You could run both.

---

### PACT vs Memory Plugins (claude-mem, supermemory, memsearch)

This is where the overlap is highest, but the approach is fundamentally different.

| | Memory Plugins | PACT |
|---|---|---|
| **How memory works** | Automatic capture → compress → inject | Structured YAML files the agent reads and writes |
| **What gets saved** | Everything (session transcripts, tool calls, decisions) | Synthesis only (the reasoning, not the raw data) |
| **Memory format** | Opaque (SQLite, vector DB, compressed blobs) | Human-readable YAML you can edit, review, and version control |
| **Search** | Semantic/vector search | Tag-based directory (KNOWLEDGE_DIRECTORY.yaml) |
| **Runs a service?** | Yes — background Express server, daemon, or cloud API | No — just files in your repo |
| **Dependencies** | SQLite3, Express, agent-sdk, or external API | None — plain shell scripts and YAML |
| **Version controlled?** | No (external database) | Yes — lives in your git repo |
| **What else PACT does** | — | Mechanical enforcement, architecture maps, cognitive redirections, bug tracker, multi-agent coordination |

**Verdict:** Memory plugins are "record everything automatically." PACT is "save the reasoning that matters, in a format humans can audit." PACT's memory is narrower but more structured and comes bundled with enforcement, architecture awareness, and multi-agent support that memory plugins don't touch.

If you want zero-effort memory capture, use a memory plugin. If you want structured, version-controlled knowledge that compounds meaningfully across sessions — plus all the governance features — use PACT.

---

### PACT vs Workflow Plugins (feature-dev, code-review, claude-code-workflows)

| | Workflow Plugins | PACT |
|---|---|---|
| **What they do** | Structured multi-phase development workflows with specialized agents | Governance framework — knowledge, enforcement, and architecture awareness |
| **Agent orchestration** | Core feature (code-explorer, code-architect, code-reviewer agents) | Not a focus |
| **Code review** | Parallel review agents with severity-based blocking | Not built-in (use alongside a review plugin) |
| **Architecture** | Explored per-session by code-architect agent | Persistent SYSTEM_MAP.yaml — always available, never re-explored |
| **Memory** | None | Persistent across sessions |

**Verdict:** No overlap. Workflow plugins handle the development process. PACT handles what the agent knows and what it's not allowed to do. Use both.

---

### PACT vs Taskmaster

| | Taskmaster | PACT |
|---|---|---|
| **Task tracking** | Full-featured task management with dependencies, priorities, subtasks | Simple PENDING_WORK.yaml for cross-session continuity |
| **IDE support** | 13 IDEs (Cursor, Claude Code, Windsurf, VS Code, etc.) | Claude Code + Gemini CLI |
| **What else?** | Focused exclusively on task management | Knowledge accumulation, enforcement hooks, architecture maps, bug tracker, multi-agent |

**Verdict:** If you need serious task management, use Taskmaster. PACT's PENDING_WORK.yaml is intentionally minimal — it's a handoff file, not a project management tool. They complement each other.

---

### PACT vs Repomix

No overlap. Repomix packs your repo into a single file for feeding to LLMs. PACT governs how the agent works within the repo. Completely different tools.

---

## What Makes PACT Unique

Looking across all these tools, PACT occupies a space that none of them individually cover:

1. **Mechanical enforcement via shell hooks** — Not prompt-based suggestions. The agent literally cannot skip them. No other plugin uses PreToolUse/PostToolUse hooks for governance this way.

2. **Structured knowledge accumulation** — Not automatic capture of everything, but deliberate synthesis in human-readable, version-controlled YAML. Research files have depth levels, staleness conditions, and evolution actions (deepen, reframe, update, supersede).

3. **Cross-system Knowledge Directory** — One file that indexes tags across ALL knowledge systems (research, bugs, solutions, packages, feature flows). No other tool provides this.

4. **Capability Baseline** — PACT tracks what the agent can do natively vs what PACT compensates for. When the agent provider ships a new capability, PACT adapts instead of accumulating stale workarounds. No other tool does this.

5. **Cognitive redirections** — 19 self-directed questions at decision points that the agent can extend on its own. Not rules (rules get skimmed). Questions that engage reasoning.

6. **Multi-agent with shared governance** — Claude and Gemini share the same hooks, rules, and knowledge base. Switching agents means zero context loss.

7. **Live multi-tree status board + Codebase Intent Map** — Multi-tree Kanban-style status board (TREE → INITIATIVE → FEATURE → TASK) with click-to-edit YAML status (no agent round-trip), drag-to-reorder, themes, archive view, and task notes that surface to the agent at session start. Plus an Aider-style Repo Map of the codebase (List / Graph / Flows / Drift sub-tabs) with PageRank + symbol index + drift detection that auto-rebuilds on every file edit. No other plugin offers a codebase intent map at this depth.

8. **Auto-dispatched subagents** — Three Sonnet subagents (tracer, researcher, reviewer) that the main session dispatches proactively. Dependency tracing, knowledge research, and pre-commit review happen in isolated contexts so the main session's context window stays focused on the user's task. Other plugins do multi-agent orchestration at the workflow level; PACT does it at the governance level.

9. **Zero external dependencies** — No daemons, no databases, no cloud services for core governance. Just shell scripts and YAML files in your repo. (The dashboard server is an optional lightweight Python script on localhost.)

---

## Can I Use PACT With Other Plugins?

Yes. PACT plays well with others because it operates at a different layer:

| Combination | Why It Works |
|---|---|
| PACT + Superpowers | Disciplined workflow + persistent knowledge |
| PACT + feature-dev | Structured feature development + architecture awareness |
| PACT + code-review | Review agents + mechanical enforcement hooks |
| PACT + Taskmaster | Full task management + cross-session governance |
| PACT + Repomix | Repo context + persistent knowledge layer |

The only combination that might create friction is PACT + a memory plugin (claude-mem, supermemory, memsearch), since both try to solve cross-session persistence. Even there, they approach it differently enough that both could run — the memory plugin captures breadth, PACT captures depth.

---

## Summary

| Need | Best Tool |
|------|-----------|
| "I want a structured development workflow" | Superpowers or feature-dev |
| "I want automatic memory across sessions" | claude-mem or supermemory |
| "I want the agent to accumulate *structured* knowledge that I can audit" | **PACT** |
| "I want mechanical enforcement of rules" | **PACT** |
| "I want architecture awareness that persists" | **PACT** |
| "I want to see what the agent is doing in real time and rate its work" | **PACT** (dashboard) |
| "I want to switch between Claude and Gemini seamlessly" | **PACT** |
| "I want task management" | Taskmaster |
| "I want code review" | code-review |
| "I want up-to-date package docs in context" | Context7 (MCP server — works great alongside PACT's package knowledge files) |
| "I want all of the above" | PACT + Superpowers + Taskmaster + code-review + Context7 |
