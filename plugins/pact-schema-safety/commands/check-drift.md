Run schema drift detection — compare the live Postgres schema against ORM table definitions, backend function `.select()` calls, the schema doc, and the tech_stack inventory.

Run this PROACTIVELY when:
- Last `scripts/RUN_LOG.yaml` entry for `check_schema_drift.py` is older than 7 days
- About to edit any ORM table definition file
- About to write or modify a backend function that queries the database
- After a migration that touched DDL (apply_migration via MCP, manual ALTER, etc.)
- The `schema_verify` checkpoint's `<last_drift_check>` field is stale

Steps:
1. Run: `python scripts/check_schema_drift.py`
   - Defaults: regenerates the schema doc (path from `pact-schema-safety.config.yaml` or default), writes/updates a bug file in `bugs/schema/` if drift detected, appends to `scripts/RUN_LOG.yaml`, updates `.claude/memory/PENDING_WORK.yaml § schema_drift_detected` when criticals exist.
   - Add `--no-cache` to force a live fetch (skips the 12-hour cache).
   - Add `--no-doc` to skip doc regeneration (use for quick checks).
   - Add `--no-bug` to skip bug file write (use for dry runs).
   - Add `--quiet` to suppress non-drift output.
   - Add `--json` to emit a machine-readable summary.

2. Read the resulting bug file (if any) at `bugs/schema/schema-drift-{date}.yaml`. Each `diffs[]` entry has:
   - `severity` (critical | warning | high), `kind`, `source`, `table`, `column`, `expected`, `actual`, `location`, `suggested_fix`
   - Apply each `suggested_fix` per diff. Critical drift in `source: drift` → rename ORM column or its alias. Critical drift in `source: ef` → fix the `.select(...)` string + redeploy. Critical `fk_target_drift` → fix the `.references()` target.

3. After applying fixes, rerun `/check-drift` to confirm the bug file count drops to zero, then mark the bug file `status: resolved` with the commit hash.

4. If a diff is intentional/acceptable (deprecated column being phased out, ORM-only local table with no DB counterpart), add it to `scripts/.schema_drift_ignore.yaml` with a `reason` and `added` date.

Reads: live Postgres schema via `SCHEMA_SAFETY_DB_URL` (or `DATABASE_URL`) env var.
Writes: schema doc (regenerated), `bugs/schema/*.yaml`, `scripts/RUN_LOG.yaml`, `scripts/.cache/live_schema_*.json`, `.claude/memory/PENDING_WORK.yaml`.

Reference: `plugins/pact-schema-safety/README.md` for installation + configuration + adapting to other stacks.
