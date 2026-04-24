# pact-schema-safety

**Optional plugin for PACT projects that use a Postgres database** (Supabase, RDS, vanilla Postgres, etc.). Detects divergence between the **live database schema** and what the **local codebase assumes** — ORM table definitions, query strings inside backend functions, and the schema documentation.

## What it catches

| Drift kind | Example |
|---|---|
| Renamed column | ORM declares `personality_description`, live has `personality_tags` |
| Removed column | Backend selects `photo_url` from a table where the column was dropped |
| Type mismatch | ORM declares `integer`, live has `uuid` |
| FK target gone | ORM `.references(other_table, #id)` but `other_table.id` doesn't exist anymore |
| Doc drift | `knowledge/postgres_schema.yaml` lists 8 columns, live has 11 |
| Function inventory drift | `knowledge/tech_stack.yaml § edge_functions` lists 3 functions, the directory has 27 |

## When to install this plugin

If your project has all three of:

1. A Postgres database (any flavor)
2. Local code that hardcodes column names (ORM table classes, query strings inside backend functions)
3. A schema documentation file you'd like to keep current

Then this plugin will save you the multi-file fix when columns get renamed/dropped/retyped without the codebase being updated in step.

## Currently supports

- **Database:** Postgres (any host — Supabase, RDS, self-hosted)
- **ORM table parser:** Drift (Dart). The class regex is reusable for similar
  ORMs that use a `class XxxYyy extends Table { ... }` shape — swap the regex
  if your ORM differs.
- **Backend function parser:** TypeScript `.from('table').select('col1, col2')`
  patterns (Supabase Edge Functions, PostgREST clients, supabase-js). Other
  ORMs/clients that use the same `.from(table).select(cols)` chain work too.
- **Schema doc format:** YAML (`tables.{name}.columns` shape). The skill
  `templates/skills/schema_change_workflow.yaml` explains why YAML over
  Markdown for this file.

## Install (one-time per project)

1. Copy `scripts/check_schema_drift.py` into your project's `scripts/` directory.
2. Copy `commands/check-drift.md` into your project's `.claude/commands/` directory (so `/check-drift` becomes available as a slash command).
3. Copy `bugs/schema/` skeleton into your project's `bugs/` directory.
4. Copy `.schema_drift_ignore.yaml` into your project's `scripts/` directory (empty starter).
5. Optionally copy `pact-schema-safety.config.example.yaml` to your project root as `pact-schema-safety.config.yaml` and adjust paths if your layout differs from the defaults.

## Setup environment

Set the database URL via env var:

```bash
# Linux / macOS
export SCHEMA_SAFETY_DB_URL='postgresql://user:pass@host:6543/dbname'

# Windows PowerShell
[Environment]::SetEnvironmentVariable('SCHEMA_SAFETY_DB_URL', 'postgresql://user:pass@host:6543/dbname', 'User')
```

The script also accepts `DATABASE_URL` as a fallback if `SCHEMA_SAFETY_DB_URL` is not set.

Install Python deps:

```bash
pip install psycopg2-binary pyyaml
```

## Usage

```bash
# Default: regenerates schema doc, writes/updates a bug file if drift detected
python scripts/check_schema_drift.py

# Force fresh fetch (skip the 12-hour cache)
python scripts/check_schema_drift.py --no-cache

# Quick dry-run (skip both writes)
python scripts/check_schema_drift.py --no-doc --no-bug

# Machine-readable summary
python scripts/check_schema_drift.py --json

# Run via slash command (after installing commands/check-drift.md)
/check-drift
```

## Output

| File | What it contains |
|---|---|
| `bugs/schema/schema-drift-{date}.yaml` | Full diff list with severity, kind, source, table, column, expected, actual, location, suggested_fix per drift. Tracks `first_seen`/`last_seen` across runs; escalates severity if persists >7 days. |
| `knowledge/postgres_schema.yaml` (or your configured path) | Auto-regenerated from live schema. Preserves manual annotations inside `keep:` blocks. |
| `scripts/RUN_LOG.yaml` | Append-only run journal entry per run. |
| `.claude/memory/PENDING_WORK.yaml § schema_drift_detected` | Created when criticals exist; cleared otherwise. |

## Configuration

If your project layout differs from the defaults, drop a `pact-schema-safety.config.yaml` at the project root. Example:

```yaml
# All paths are relative to the project root.
orm_tables_dir:    src/db/tables       # default: lib/database/tables
edge_functions_dir: backend/handlers   # default: supabase/functions
schema_doc:        docs/schema.yaml    # default: knowledge/postgres_schema.yaml
tech_stack:        docs/tech_stack.yaml # default: knowledge/tech_stack.yaml
ignore_file:       schema_ignore.yaml  # default: scripts/.schema_drift_ignore.yaml
bugs_schema_dir:   bugs/schema         # default: bugs/schema
cache_ttl_hours:   24                  # default: 12
drift_age_escalation_days: 14         # default: 7
```

## Recommended hook integration

If you have PACT's `pre-bash-guard.sh` installed, the staleness warning under "schema-touching edits + stale verify" will automatically check for the drift detector's marker file and warn at commit time when the last drift check is >7 days old. No additional setup required — the warning fires only if `scripts/.cache/daily_marker_*` exists.

If you have PACT's `daily-checks.sh` (SessionStart hook) installed, drift detection runs automatically once per day on the first session of the day.

## Limitations + adapting to other stacks

- **Postgres only.** The script queries `information_schema.columns` and uses psycopg2. Other DBs (MySQL, SQLite, MS SQL) would need adapter changes (~50 LOC for the live-fetch portion).
- **Drift ORM regex is opinionated.** Other ORMs (Prisma, sqlx, sqlc, SQLAlchemy) need a different parser. The diff/output scaffolding is reusable — swap the parser.
- **Backend `.select()` parser assumes the supabase-js / PostgREST chain shape.** Other clients that use a different chain (raw SQL, query builders) would need a different parser.

The script is ~1000 LOC. Most of it is the diff logic, bug-file writer, doc regenerator, and CLI — those are all reusable. Only the live-fetch and parser portions are stack-specific.

## Changelog

This plugin ships at PACT v0.11.0 (Unreleased). Versioning follows PACT's semantic version.
