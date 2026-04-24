Check what governance artifacts went stale based on what was edited this session.

This is the TEMPORAL governance check — it answers: "What docs did my changes just make stale?" Run it before declaring a task complete.

## Steps

1. Read `.claude/memory/file_edit_log.yaml` to find files edited today.

2. For each edited file, check ripple effects against the project's governance layer:

   **If a file in `lib/database/`, `models/`, `tables/`, `schema/`, or `migrations/` was edited (database/schema-touching code):**
   - Is the table/entity listed in `SYSTEM_MAP.yaml` under the correct wiring section?
   - Is the schema doc current? (`knowledge/schema.{yaml,md}` or whatever your project uses)
   - Was a new column added but FK targets/indexes/constraints not documented?

   **If a service/handler/api/endpoint file was edited:**
   - Is the service listed in `SYSTEM_MAP.yaml` under the relevant wiring section?
   - If it's a critical-system service (auth, encryption, sync, payments, broadcast, or any flow tagged critical in your project's feature flow inventory), check the matching `feature_flows/{system}_flow.yaml` "last_updated" date — is it today?

   **If a new screen / view / route was added:**
   - Is it listed in `SYSTEM_MAP.yaml` screens / routes section?

   **If `SYSTEM_MAP.yaml` itself was edited:**
   - Is the "last_verified" or top-level date stamp today?
   - Validate all `feature_flow` cross-references still resolve.

   **If any feature flow was edited:**
   - Is the "last_updated" date today?
   - Does the `system_map_section` reference still resolve?

   **If a Postgres / Supabase function / Edge Function / API route source was edited:**
   - Is the function listed in `knowledge/tech_stack.yaml` (or your equivalent) under the relevant section?
   - Is `SYSTEM_MAP.yaml` updated?

3. Check `SYSTEM_MAP.yaml` overall freshness — flag if last verified >3 days ago.

4. If your project has an automated schema-drift detector (e.g., `scripts/check_schema_drift.py`), check its last run from `scripts/RUN_LOG.yaml`. If >7 days old AND any schema-touching file was edited this session, recommend running `/check-drift` (or equivalent).

5. Report:
   - **Current** — files whose docs/maps are accurate
   - **Stale** — docs that should be updated as a consequence of the changes
   - **Missing** — code paths edited that have no corresponding documentation

## Output format

```
=== Staleness Check ===

Edited this session: 7 files

Current (3):
  - lib/services/foo_service.dart       (SYSTEM_MAP.yaml updated, feature_flow current)
  - knowledge/tech_stack.yaml           (synced with edge_functions/foo)
  - bugs/auth/auth-002_login_loop.yaml  (newly resolved, commit hash recorded)

Stale (3):
  - lib/database/tables/orders.dart     -> SYSTEM_MAP.yaml NOT updated (cascade behavior changed)
  - supabase/functions/checkout/index.ts -> tech_stack.yaml inventory NOT updated
  - lib/screens/cart_screen.dart        -> SYSTEM_MAP.yaml screens list NOT updated

Missing (1):
  - lib/services/payment_service.dart   -> NO feature flow exists; create one before declaring done

Schema drift check: last run 12 days ago. Recommend /check-drift before commit.
```

## Why this command exists

`dart analyze` (or your linter) checking clean ≠ governance clean. Code correctness is necessary but not sufficient — the docs and maps that describe the code must also stay current. This command catches the gap between "I changed the code" and "I forgot to update the doc that explains the code."

## Related

- `feature_flow_authoring.yaml` skill — when to create/update flow docs
- `schema_change_workflow.yaml` skill — schema-touching workflow
- `scripts/check_schema_drift.py` (if installed) — automated drift detection
