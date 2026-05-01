# PACT Dashboard — Multi-Tree Status Board + Codebase Intent Map

A live dashboard that surfaces what your project is doing AND what it's working over. Four views: Board (multi-tree Kanban), Task List (flat searchable), Repo Map (codebase intent), Pythons (process inventory).

---

## Quick Start

```bash
# Start the dashboard
python templates/dashboard/pact-server.py &
# Opens at http://127.0.0.1:8800/pact-dashboard.html
```

Or have the SessionStart hook auto-open it (toggle via `Dashboard Settings → Startup` in the dashboard, or remove `<project>/.claude/memory/dashboard_autoopen_disabled` to re-enable).

---

## Schema — TREE → INITIATIVE → FEATURE → TASK

The dashboard reads a multi-file YAML schema rooted at `templates/dashboard/_index.yaml` (or `plans/dashboard/_index.yaml` in downstream projects):

- **TREE** — top-level domain of work (Governance, Frontend, Infrastructure, …). Each tree has its own intent (`_intent.yaml` — short tagline + long description + 1-3 metrics) and its own folder of streams.
- **INITIATIVE** — a major effort within a tree (e.g. "Auth rewrite"). One YAML file per initiative under `streams/`. The file's top-level `node:` becomes one Kanban card on the tree's strip.
- **FEATURE** — a discrete capability inside an initiative. Children of an initiative's `node`. Surfaced inside the modal when you click an initiative card.
- **TASK** — a concrete unit of work. Lives in a feature's `tasks:` array. Done tasks stay (history-preserving).

---

## Board view — Multi-tree Kanban

Each tree renders as its own section with a header, a per-tree sort button, and a horizontal-scrolling strip of UNIFORM-SIZE Kanban-style initiative cards. Each card shows four facts in 260×150:

- **Status glyph + title** (color-coded: done / in_flight / blocked_user / blocked_external / not_started)
- **Note preview** (2-line description from the YAML's `note:` field)
- **Progress bar** with percent (auto-derived from task done/total)
- **Footer pill**: feature count · tasks done/total · last-touched (relative time)

Click any card → modal flip card. Front: feature list + tasks + author framing. Back: PACT references (plans, knowledge, feature flows).

**Color modes:** toggle between `status` (color = current state) and `recency` (color = how recent the last edit was).

**Filters:** hide completed tasks, hide completed plans, Claude-autonomous-only.

**Drag-to-reorder:** pointer-event tactile drag (5px movement threshold) for both card-within-feature-grid AND initiative-section-within-tree. Custom orders persist per-project in localStorage; ↺ reset button restores YAML order.

**Archive view:** the 📁 button on each initiative-header hides it from Board + Task List. Archive view shows ONLY archived initiatives with Restore (↩) buttons. Auto-resurfaces when an archived initiative's task signature changes (work resumed).

---

## Status picker — Direct YAML editing

Click any task or node status badge → overlay picker → pick new status → server writes the YAML atomically (tmp+rename) and auto-bumps the parent initiative's `last_touched`. Backed by `POST /yaml-edit` with field whitelist (status / name / note / last_touched) and per-status-vocabulary validation. **No agent round-trip needed for routine status changes.**

---

## Task notes — Surface to the agent at session start

Click any task name (modal OR Task List row) → inline editor → notes persist to `<project>/.claude/memory/dashboard_user_notes.yaml` PLUS a sentinel file (`dashboard_notes_unread`) is touched. The SessionStart hook reads the sentinel and surfaces the unread count + latest note via `additionalContext` so notes don't go silent across sessions. Mark them `status: read` once acknowledged.

---

## Themes + Google Fonts

Five named dark themes (Tide & Ember default, Midnight Orchid, Sodium Rain, Neon Dive, Inkwell) each with paired font trios. Settings panel exposes:
- Theme picker with per-theme color preview
- Per-role font picker (UI / monospace / display) with dynamic Google Fonts loading via injected `<link>` tag
- Reset Fonts + Align-to-theme buttons

All settings are per-project (keyed by project name in localStorage).

---

## Prompt builder

Paste-able directive grammar at the top of the dashboard. Click any task chip in the modal to add a directive line ("WORK ON:", "REVISIT:", "NEED DETAILS:", "BUMP TASK VERSION:", "UPDATE FLOW:", "USER NOTES on:", "SWITCH PROJECT:"). Copy the assembled prompt and paste into your agent session to redirect work.

---

## Pythons view

Running Python process inventory (via `wmic` on Windows, `ps` elsewhere). Shows PID, command line, and listening ports. Kill switch (`POST /kill`) for stale ones; protected-row badges for processes you shouldn't kill (your own PACT server, e.g.).

---

## Project switcher (multi-project)

Pill in the header → menu of registered projects. Switching sends a fetch to `_index.yaml?root=<absolute-project-path>`. The server probes both `plans/dashboard/` (downstream convention) and `templates/dashboard/` (PACT itself) to find the project's scaffold. The dashboard SHELL stays on PACT's HTML/CSS/JS; only the YAML data re-roots.

---

## Server API

The dashboard server exposes endpoints for programmatic access:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/pact-dashboard.html` | GET | Dashboard HTML |
| `/_index.yaml`, `/trees/.../*.yaml` | GET | Tree + initiative YAML data (re-rooted via `?root=`) |
| `/dashboard-version` | GET | Local PACT VERSION (powers the update notifier) |
| `/yaml-edit` | POST | Atomic field-edit on a tree YAML (status / name / note / last_touched) |
| `/note` | POST | Append a task or initiative note |
| `/notes` | POST | List all notes |
| `/autoopen` | POST | Read/write the dashboard auto-open flag |
| `/pythons` | POST | List running Python processes |
| `/kill` | POST | Kill a Python process by PID |
| `/open` | POST | Open a file in the user's editor (VS Code for code files, default handler otherwise) |

---

## Data Flow

```
YAML edits → /yaml-edit → atomic tmp+rename → tree YAML → next dashboard fetch
Source edits → post-edit-repo-map-dirty.sh → repo_map.json ← Repo Map view
User notes → /note → dashboard_user_notes.yaml + sentinel → SessionStart hook → agent context
```

All data is local. Nothing is sent anywhere.

---

## Repo Map view (Codebase Intent Map)

Aider-style symbol index over your codebase, surfaced as a dashboard view with four sub-tabs.

### List sub-tab

<p align="center">
  <img src="../assets/pact-dashboard-repomap-list.png" alt="Repo Map — List sub-tab" width="700"/>
</p>

Searchable, sortable, kind-filtered file list ranked by import-graph PageRank. Each row surfaces the file's symbol count, est-tokens, top symbols, and flow membership. Click any row → side detail panel.

The detail panel pulls from `repo_map.json` and shows:
- **Top symbols** (with leading doc-comment + signature line) — replaces "what does this class do?" grep
- **Imports + importers** — replaces "what depends on this?" grep
- **Flow membership** — which `feature_flows/*.yaml` claim this file
- **Drift schema** (for Drift table files) — columns, types, foreign keys, on-delete rules
- **Edge function metadata** (for `supabase/functions/*/index.ts`) — actions, secrets, buckets, RPCs, external hosts, tables referenced
- **Provider cache shape** (for `lib/providers/*.dart`) — list/map/singleton fields
- **Cross-cutting callers** — if this file is a known hook (AutoPrivacyTagger, etc.), every callsite
- **Anomalies emitted from this file** — `AppAnomalyReporter.report()` callsites
- **Env vars read from this file** — `Deno.env.get`, `String.fromEnvironment`, etc.

### Graph sub-tab

d3-force layout of the top 100 most-central files. Click a node → same detail panel. Useful for spotting hub files at a glance.

### Flows sub-tab

<p align="center">
  <img src="../assets/pact-dashboard-repomap-flows.png" alt="Repo Map — Flows sub-tab" width="700"/>
</p>

Card stack of every `feature_flows/*.yaml`. Each card answers WHO / WHAT / WHEN / WHERE / WHY for that flow:

- **Author framing** (collapsible) — top-of-file YAML comments
- **Purpose** + description
- **Triggers** ("when this fires") — what user action / system event / scheduled job kicks the flow off
- **Lifecycle states / phases** — named state objects describing each app state
- **Participating files** — grouped by architectural layer (UI / State / Service / Data / Misc)
- **Declared dependencies** — outbound (depends_on / communicates_with) + inbound (auto-computed from other flows)
- **Invariants** — testable claims that must always be true
- **Diagram** (collapsible Mermaid block, full-screen expand with zoom)
- **References** — pointers to plan_doc / design_manifest / figma / spec / package_knowledge

Search filters across all 4 tabs. Per-flow status filter (red / amber / info / green). Flow status comes from the drift detector.

### Drift sub-tab

<p align="center">
  <img src="../assets/pact-dashboard-repomap-drift.png" alt="Repo Map — Drift sub-tab" width="700"/>
</p>

Mechanical drift between flow claims and structural reality:
- **Orphaned high-centrality files** — top-25% PageRank but in no flow's `participating_files`. These are files that probably *should* be claimed but aren't.
- **Claimed files missing in repo** — flow YAML references a path that doesn't exist (refactor surfaced).
- **Undocumented cross-flow imports** — file in flow A imports file in flow B without a `declared_dependencies` entry between them. Either add the declaration or remove the import.
- **Broken declared dependencies** — a flow's `via:` symbol no longer exists in the target's symbol set, or the target flow itself was deleted.

**Sparkline trend chart** — last ~100 builds plotted: orphans, broken_deps, undocumented_pairs, flows_red. Answers "is drift accumulating?" without diffing per-commit.

### Auto-rebuild

The dashboard fetches `plans/dashboard/data/repo_map.json` on load. The `post-edit-repo-map-dirty.sh` PostToolUse hook touches a dirty flag after every Edit/Write to a tracked source file (`lib/*.dart`, `scripts/*.py`, `supabase/functions/*.{ts,tsx,js}`, `feature_flows/*.yaml`). A background builder loops while the dirty flag exists, consuming it before each iteration — so a flurry of edits collapses into a single tail rebuild that captures the final state. ~1-3s end-to-end.

The dashboard always reflects current code state. No manual `python scripts/repo_map.py build` needed.

### History log + sparkline

`plans/dashboard/data/repo_map_history.jsonl` — append-only summary line per build, deduplicated when nothing structural changed. ~250 bytes per line. Drives the Drift tab's sparkline.

Each line:
```json
{"ts": 1761935600, "node_count": 1284, "edge_count": 6366, "flow_count": 38,
 "orphans": 229, "broken_deps": 0, "undocumented_pairs": 286, "flows_red": 0,
 "flows_amber": 30, "schema_version": 48, ...}
```

Forensic queries like "when did `X` first appear in the anomaly catalog?" become single-file `grep` instead of `git log -p` on the 14MB JSON.

### Pre-commit validator

`pre-commit-feature-flow-validator.sh` (PreToolUse Bash hook) runs `scripts/verify_feature_flow_schema.py` before every `git commit`. **BLOCKS** commits with intent-layer errors:
- `missing_purpose` — flow YAML missing top-level `purpose:` field
- `participating_files_path_not_in_repo` — claimed file doesn't exist in `repo_map.json`
- `declared_dep_unknown_target` — `depends_on:` references a non-existent flow
- `declared_dep_via_symbol_not_found` — `via:` symbol not in target's symbol set
- `invariant_anchor_index_out_of_range` — invariant_anchors[].invariant_index is invalid

Warnings are advisory (don't block).

### Porting to other stacks

`templates/scripts/repo_map.py` is project-agnostic at the core (tree-sitter parsing, import graph, PageRank, symbol extraction, class hierarchy, call graph) and project-specific in the EXTRACTORS (drift_schema for Flutter+Drift, edge_functions for Supabase, etc.). Every project-specific extractor checks if its target directory exists and returns `{}` if not — so on a fresh project, the script runs cleanly and just doesn't populate the missing fields.

Full porting guide: [`docs/repo_map_porting.md`](repo_map_porting.md).
