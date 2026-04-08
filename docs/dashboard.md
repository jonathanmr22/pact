# PACT Dashboard — Real-Time Observability & Task Rating

A live dashboard that visualizes everything your AI agent does — every file edit, preflight check, hook block, commit, and governance update appears as a card in a horizontal timeline. Your own prompts show up too, so you can see the full conversation flow alongside the agent's actions.

---

## Quick Start

```bash
# Start the dashboard (runs on localhost:7246)
python .claude/hooks/pact-server.py &

# Or set auto-start in config
echo '{"dashboard": "auto"}' > ~/.claude/pact-config.json
```

The `session-register.sh` hook auto-starts the dashboard if configured.

---

## What You See

### Session Lanes
Each active session appears as a horizontal lane with:
- **Avatar** — Claude (tan) or Gemini (blue) with a green pulse dot when active
- **Model identity** and project name
- **Meta chips** — edit count, hook blocks, commits
- **Action buttons** — diagnosis panel, delete session

### Event Timeline
A horizontal scroll of event cards, newest on the right. Each card type has a distinct color and animated icon:

| Event Type | Color | Animation |
|------------|-------|-----------|
| File edit | Blue | Pencil writing |
| Preflight check | Amber | Lightning strike |
| Hook block | Red | Card shake |
| Hook warning | Amber | Gentle pulse |
| Flow read | Cyan | Page turn |
| Governance update | Green | Star twinkle |
| Commit | Purple | Check mark |
| Task rating | Gold | Star burst |

### Pipeline Indicators
Five dots in the header show real-time activity across subsystems: edit, preflight, flow, governance, commits. Each dot lights up (green/amber/red) based on the most recent event in that category.

### Sidebar
- **Scorecard** — Rolling average score (last 10 tasks), current streak, weakest areas by tag
- **Metrics** — Total edits, hook blocks, preflight warnings, commits, active sessions
- **Actions** — Generate feedback report, vector search recall

---

## Task Rating System

Click "Track Next Task" on any session, describe what you're asking the agent to do, and all subsequent events flow into that task's sub-row.

When the task is done, rate it:
- **Score** (1-5)
- **What went wrong** (free text)
- **What went right** (free text)
- **Tags** — UI, Backend, Logic, Missed Requirements, Hallucination, etc.

### How Ratings Feed Back

Ratings are compiled into a **scorecard** at `~/.claude/pact-scorecard.md`:
- Rolling average (last 10 tasks)
- Streak counter (consecutive 4+ ratings)
- Weakest areas by tag (frequency, avg score, examples)
- What's working (tags with consistent high scores)
- Action items (specific improvements based on patterns)

The agent reads this scorecard at session start, creating a direct feedback loop: past ratings shape future behavior.

---

## Diagnosis Panel

Toggle the diagnosis view on any session to see:
- **Hook blocks** — What was blocked and why (red dots)
- **Preflight issues** — Architectural warnings raised (amber dots)
- **Governance staleness** — Docs/maps that weren't updated (amber dots)
- **Coverage** — Which PACT subsystems were exercised during this session

---

## Server API

The dashboard server exposes endpoints for programmatic access:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Dashboard HTML |
| `/events?after=N` | GET | Events since index N |
| `/ratings` | GET | All task ratings |
| `/rate` | POST | Submit a task rating |
| `/scorecard` | GET | Current scorecard markdown |
| `/pact-config` | GET/POST | Read/update PACT config |
| `/recall?q=TEXT&top=5` | GET | Vector search via pact-memory |

---

## Data Flow

```
Hooks → pact-event-logger.sh → pact-events.jsonl ← pact-server.py → Dashboard
User → pact-prompt-logger.sh → pact-events.jsonl
User → /rate endpoint → _FEEDBACK.jsonl → pact-server.py → scorecard
```

All data is local. Nothing is sent anywhere unless you explicitly choose to share a feedback report.
