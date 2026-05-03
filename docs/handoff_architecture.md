# HANDOFF Architecture

**Replaces the legacy heavyweight `PENDING_WORK.yaml` pattern with a thin entry pointer + dashboard source-of-truth.**

---

## The problem with `PENDING_WORK.yaml`

Old PACT installations tracked all open work in `.claude/memory/PENDING_WORK.yaml` — a single file that grew to thousands of lines as projects matured. Once it crossed ~1000 lines, three failure modes set in:

1. **Silent duplication.** Sessions started writing the same item to both `PENDING_WORK.yaml` AND a dashboard stream YAML, with subtly different status. Audits typically found 60–80% of items in only one place.
2. **Read-skew.** The session-start oath says "read PENDING_WORK first," but past 25k tokens the agent's recall was unreliable — it would action the top of the file and miss buried decision-pending items.
3. **No structural visualization.** A 2000-line YAML can't be scanned at a glance the way a dashboard treemap can. The data was there; the *signal* wasn't.

The dashboard (added in v0.10) was always meant to be the source of truth. `PENDING_WORK.yaml` was supposed to be a thin pre-dashboard handoff. It drifted.

## The replacement

Two files, two responsibilities:

### `HANDOFF.yaml` — entry pointer (repo root)

A thin file (~80 lines max) that the agent reads first at session start. Contents:

- **`top_priorities`** — up to 8 dashboard task references (tree → stream → task name + one-line "why")
- **`last_session_summary`** — newest-first list (max ~5) of what shipped in recent sessions, what changed, what's awaiting human action
- **Dashboard tree index** — informational pointer to `plans/dashboard/_index.yaml`

The agent reads HANDOFF, picks up the top priorities, and clicks through to the dashboard streams for the actual content.

### `plans/dashboard/trees/{tree}/streams/*.yaml` — source of truth

Where every task lives. Already PACT's existing dashboard system. Each stream YAML has:

- A top-level `node` with name, status, last_touched, optional note
- `children` (feature nodes) with their own status + tasks
- Tasks have `status`, `last_touched`, optional `claude_autonomous: true`, `claude_notes: |` (multi-line concrete deltas)

The dashboard at `http://localhost:8800/dashboard.html` renders all of this as a navigable treemap with status filters, claude-autonomous flag, recently-touched sort.

## Migration playbook

If your project still has a `PENDING_WORK.yaml`:

### Step 1 — audit what's where

For each top-level item in `PENDING_WORK.yaml`, classify:

- **MIGRATED** — this item is already represented as a real task or feature node in a dashboard stream YAML, with the same substantive content
- **PARTIAL** — the dashboard mentions the initiative name but the underlying decision-pending content is missing
- **NOT_MIGRATED** — no meaningful trace in any dashboard tree

Run this with a search subagent or grep loop. Real audits typically find ~17% migrated, ~21% partial, ~62% not migrated.

### Step 2 — migrate everything not yet in the dashboard

For each NOT_MIGRATED + insufficient-PARTIAL item:

- Pick the right tree (governance / domain / qa_bugs / etc.)
- Either add a task to an existing stream's feature node, OR create a new feature node if the work doesn't fit
- Preserve substantive content verbatim in the `note: |` field — decision-pending blocks, gotchas, file refs, historical context

`completed` items should still be migrated (the dashboard tracks history, not just current work).

`done_not_committed` items become `status: done` with `note: "Status at migration: done_not_committed"`.

### Step 3 — back up the original

```bash
cp .claude/memory/PENDING_WORK.yaml .claude/memory/PENDING_WORK.archived_YYYY-MM-DD.yaml
```

This preserves the historical record in case any item was missed in migration.

### Step 4 — replace `PENDING_WORK.yaml` with a stub

Overwrite the original with a short pointer:

```yaml
# PENDING_WORK.yaml — RETIRED YYYY-MM-DD
#
# This file is no longer the source of truth for work tracking.
# All actionable items have been migrated to the dashboard trees.
#
# READ INSTEAD:
#   1. /HANDOFF.yaml at repo root — entry pointer for this session
#   2. /plans/dashboard/trees/{tree}/streams/*.yaml — current AND historical work
#
# Original file backed up at .claude/memory/PENDING_WORK.archived_YYYY-MM-DD.yaml

retired: YYYY-MM-DD
replaced_by:
  primary: /HANDOFF.yaml
  source_of_truth: /plans/dashboard/trees/
```

### Step 5 — create `HANDOFF.yaml` at repo root

Copy `templates/HANDOFF.yaml` to your repo root. Populate `top_priorities` with the most important dashboard tasks the next session should pick up. Add the most recent session summary.

### Step 6 — update CLAUDE.md / instructions.md SessionStart oath

Find every reference to `PENDING_WORK.yaml` in your project's CLAUDE.md (root + nested) and instructions.md. Replace with HANDOFF.yaml + dashboard references. Common spots:

- SessionStart step 2 (read first)
- "When a major work stream changes state" cognitive redirection
- "No memory files" rule (PENDING_WORK is no longer in the allow-list)
- Done-check rule (update the dashboard, not PENDING_WORK)
- Hook-enforced rules table

## Why two files instead of one

You might ask: why not just have HANDOFF.yaml contain everything? Or just have the dashboard be readable directly?

- **HANDOFF.yaml is small enough to load every turn without burning context.** The dashboard YAMLs combined can be hundreds of KB. HANDOFF.yaml is ~80 lines.
- **The dashboard is structured for visualization, not first-read scanning.** A treemap with status colors and click-through is the right interface for human eyes. A flat top-priority list is the right interface for an agent's first 30 seconds.
- **Separating entry from storage prevents drift.** When everything lived in one file, it grew. When the entry is *forced* to be thin, the temptation to dump session detail there disappears — that detail goes to the dashboard where it belongs.

## What stays in `.claude/memory/`

After migration:

- `file_edit_log.yaml` — auto-maintained by hooks, tracks fresh-read timestamps. Stays.
- `PENDING_WORK.archived_YYYY-MM-DD.yaml` — historical backup of the migration source. Stays.
- `PENDING_WORK.yaml` — now a stub pointer to HANDOFF.yaml. Optional; can be deleted entirely once the team is comfortable.
- `cognitive_redirect_log.jsonl`, `feature_check_log.jsonl`, dedup files — telemetry. Stays.

## Field reference for HANDOFF.yaml

```yaml
last_updated: YYYY-MM-DD

top_priorities:
  - tree: governance        # required: tree name from plans/dashboard/_index.yaml
    stream: pact_remediation.yaml  # required: stream filename
    task: "Component N — feature X awaiting verification"  # required: matches task name in stream YAML
    why: "One sentence on why this is top priority right now"  # required

last_session_summary:
  - date: YYYY-MM-DD            # required
    session_id_prefix: abcd1234  # optional but useful for cross-referencing logs
    headline: "One-sentence summary"  # required
    what_changed: |               # required: multi-line concrete deltas
      - File paths, behaviors, deltas
    awaiting_user:                # optional: what blocks before next session continues
      - Items needing human decision/test
```

## When to bump `last_session_summary`

End-of-session, after work that:

- Shipped a feature or substantial refactor
- Completed a multi-step migration (like this one)
- Made architectural decisions the next session must know
- Left work in an `awaiting_user_test` state

Skip it for:

- Single-file bug fixes
- Doc-only changes
- Read-only research sessions
- Routine commits with clear messages

If in doubt, write the summary — it's cheap, and the next session may not have time to scroll commit history.
