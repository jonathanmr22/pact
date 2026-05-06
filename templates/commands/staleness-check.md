Check what governance artifacts went stale based on what was edited this session.

This is the TEMPORAL governance check — it answers: "What docs did my changes just make stale?" Run it before declaring a task complete.

## Steps

1. Read `.claude/memory/file_edit_log.yaml` to find files edited today.

2. For each edited file, check ripple effects against the project's governance layer:

   **If a file in `lib/database/`, `models/`, `tables/`, `schema/`, or `migrations/` was edited (database/schema-touching code):**
   - Is the schema doc current? (`knowledge/schema.{yaml,md}` or whatever your project uses)
   - Was a new column added but FK targets/indexes/constraints not documented?
   - If the table is claimed by any `feature_flows/*.yaml`, is that flow's `participating_files` and `invariants` still accurate?

   **If a service/handler/api/endpoint file was edited:**
   - If it's a critical-system service (auth, encryption, sync, payments, broadcast, or any flow tagged critical in your project's feature flow inventory), check the matching `feature_flows/{system}_flow.yaml` "last_updated" date — is it today? Are `participating_files` and `declared_dependencies` current?

   **If a new screen / view / route was added:**
   - Is it claimed by the relevant feature flow's `participating_files`?
   - If the screen lives in a critical user journey, is there a flow doc for it at all?

   **If any feature flow was edited:**
   - Is the "last_updated" date today?
   - Do `declared_dependencies` between flows still resolve to existing flow files?
   - If you removed a `participating_files` entry, did you confirm the file is genuinely no longer part of the flow (vs. just renamed)?

   **If a Postgres / Supabase function / Edge Function / API route source was edited:**
   - Is the function listed in `knowledge/tech_stack.yaml` (or your equivalent) under the relevant section?
   - Is the relevant feature flow's `participating_files` updated?

3. Check feature flow freshness overall — flag any flow whose `last_updated` is >7 days ago AND whose `participating_files` were touched this session.

4. If your project has an automated schema-drift detector (e.g., `scripts/check_schema_drift.py`), check its last run from `scripts/RUN_LOG.yaml`. If >7 days old AND any schema-touching file was edited this session, recommend running `/check-drift` (or equivalent).

5. Report:
   - **Current** — files whose docs/flows are accurate
   - **Stale** — docs/flows that should be updated as a consequence of the changes
   - **Missing** — code paths edited that have no corresponding documentation

## Output format

```
=== Staleness Check ===

Edited this session: 7 files

Current (3):
  - lib/services/foo_service.dart       (feature_flows/foo_flow.yaml current, participating_files updated)
  - knowledge/tech_stack.yaml           (synced with edge_functions/foo)
  - bugs/auth/auth-002_login_loop.yaml  (newly resolved, commit hash recorded)

Stale (3):
  - lib/database/tables/orders.dart       -> feature_flows/checkout_flow.yaml NOT updated (cascade behavior changed)
  - supabase/functions/checkout/index.ts  -> tech_stack.yaml inventory NOT updated
  - lib/screens/cart_screen.dart          -> participating_files in checkout_flow.yaml does not include this file

Missing (1):
  - lib/services/payment_service.dart     -> NO feature flow exists; create one before declaring done

Schema drift check: last run 12 days ago. Recommend /check-drift before commit.
```

## Why this command exists

Static analysis clean ≠ governance clean. Code correctness is necessary but not sufficient — the docs and feature flow YAMLs that describe the code must also stay current. This command catches the gap between "I changed the code" and "I forgot to update the flow that explains the code."

## Related

- `feature_flow_authoring.yaml` skill — when to create/update flow docs
- `schema_change_workflow.yaml` skill — schema-touching workflow
- `scripts/check_schema_drift.py` (if installed) — automated drift detection
