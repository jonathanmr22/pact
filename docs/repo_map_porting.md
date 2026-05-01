# Repo Map — porting to non-Flutter / non-Dart projects

> Canonical reference for the Repo Map system. Code lives at:
> - `templates/scripts/repo_map.py` (extractors + graph + dashboard JSON emit)
> - `templates/scripts/verify_feature_flow_schema.py` (intent-layer validator)
> - `templates/dashboard/pact-dashboard.html` (Repo Map view + Flows + Drift sub-tabs)
> - `templates/hooks/post-edit-repo-map-dirty.sh` (real-time auto-rebuild)
> - `templates/hooks/pre-commit-feature-flow-validator.sh` (blocking validator hook)

The dashboard's Repo Map view (List / Graph / Flows / Drift) is intentionally
project-agnostic at the data layer. This doc is a reproducibility guide for
adapting it to a different stack.

## What stays the same

- `plans/dashboard/dashboard.html` — the entire UI is data-driven. It reads
  one JSON file (`plans/dashboard/data/repo_map.json`) and renders against
  the schema described below. No Flutter or Dart references in the HTML or
  JavaScript.
- `feature_flows/*.yaml` — the schema (`purpose`, `triggers`, `invariants`,
  `lifecycle_states` / `states`, `participating_files`,
  `declared_dependencies`, `flow_kind`) is project-neutral. Whatever your
  project does, you write a flow file describing it.
- `scripts/verify_feature_flow_schema.py` — same schema check works for any
  project that follows the structure above.

## What needs to change for a different stack

### 1. `scripts/repo_map.py` — the structural extractor

This is the only piece that's stack-aware. It uses tree-sitter to parse
source files, extract symbols (classes / functions / methods), and build
the import graph. To port:

- **Add or remove language entries in `LANG_FOR_EXT`** (top of file). Each
  key is a file extension, each value is a tree-sitter-language-pack name.
  e.g., for a Rust project: `".rs": "rust"`. Remove `.dart` if not needed.

- **Update `INCLUDE_DIRS`** — the directories to walk. Default is
  `["lib", "scripts", "supabase/functions"]`. Replace with whatever
  directories matter for your project (e.g., `["src", "tests", "scripts"]`
  for a Python project).

- **Update `DEF_NODE_TYPES`** — the per-language map of tree-sitter node
  types that mark symbol definitions. Add an entry for any language you
  added in `LANG_FOR_EXT`. The tree-sitter grammars all have slightly
  different node-type names; consult the grammar's `node-types.json` if
  unsure.

- **Update `file_kind()`** — the function that classifies a file path into
  a `kind` string ("service", "screen", "widget", etc.). The dashboard
  uses these kinds for color-coding and architectural-layer placement.
  Default heuristics are Flutter-conventional (`/screens/`, `/services/`,
  etc.). Replace with patterns that match YOUR project's conventions.

  Example for a typical web app:
  ```python
  def file_kind(path: str) -> str:
      p = path.lower()
      if "/components/" in p: return "screen"   # UI layer
      if "/hooks/" in p: return "provider"      # State layer
      if "/api/" in p or "/services/" in p: return "service"
      if "/models/" in p or "/db/" in p: return "database"
      if path.startswith("scripts/"): return "script"
      return "other"
  ```

### 2. `dashboard.html` — `RM_LAYER_FOR_KIND` mapping

In the JavaScript at the top of the Flows-view section:

```javascript
const RM_LAYER_FOR_KIND = {
  screen: 0, widget: 0,            // UI column
  provider: 1,                     // State column
  service: 2, edge_function: 2,    // Service column
  model: 3, database: 3, script: 3, // Data column
  other: 4,                        // Misc column
};
```

If you added new kind strings in `repo_map.py.file_kind()`, add them here
with the column index they belong in. The 5 columns are UI / State /
Service / Data / Misc — those names are generic enough that most projects
won't need to rename them, but if you do, update `RM_LAYER_LABELS` too.

### 3. The `/open` endpoint

The dashboard makes a POST to `/open` with an absolute file path to open
the file in the user's editor. The absolute path is built by prepending
the project root (function `rmOpenFile`) — typically a constant near the
top of the function.

**For a port:** change that prefix to the absolute path of the project
root on your machine, OR (better) have the server return the project root
path in `repo_map.json` so the dashboard can compute the absolute path
without hardcoded knowledge. Marked as a future improvement.

### 4. Hooks (optional)

The hooks under `.claude/hooks/` reference original-use-case paths (`lib/`,
`feature_flows/`, etc.). Most are project-agnostic in structure — they
just need their path globs updated. The PACT plugin templates under
`templates/hooks/` are the canonical source if you're starting fresh.

## What an LLM reproducing this on a different project should do

1. Copy `scripts/repo_map.py`, edit the four customization points listed
   above (`LANG_FOR_EXT`, `INCLUDE_DIRS`, `DEF_NODE_TYPES`, `file_kind`).
2. Copy `plans/dashboard/dashboard.html` verbatim. Edit `RM_LAYER_FOR_KIND`
   to match your `file_kind` vocabulary.
3. Copy `scripts/verify_feature_flow_schema.py` verbatim.
4. Author your project's `feature_flows/*.yaml` files following the
   schema in `feature_flows/CLAUDE.md`.
5. Run `python scripts/repo_map.py build` once for the initial build. After
   that, install the `post-edit-repo-map-dirty.sh` PostToolUse hook
   (referenced from `.claude/settings.json`) so subsequent edits trigger a
   real-time background rebuild — the dashboard will always reflect current
   code state without manual invocations.

The whole system is deliberately a single JSON file passed between a
data-extraction script and a static HTML/JS renderer. If your data
matches the schema, the dashboard works.

## Schema reference (the contract)

`repo_map.json` has these top-level fields the dashboard reads:

```json
{
  "node_count":  <int>,
  "edge_count":  <int>,
  "flow_count":  <int>,
  "nodes": [
    { "id": "<rel-path>", "kind": "<service|screen|widget|...>",
      "lang": "<dart|python|...>", "score": <float, 0..1>,
      "symbol_count": <int>, "est_tokens": <int, byte_count // 4>,
      "top_symbols": ["<name>", ...],
      "top_symbol_details": [
        {"name": "<sym>", "kind": "<class|method|...>", "line": <int>,
         "doc": "<first sentence of leading doc-comment>",
         "signature": "<single-line def excerpt>"}
      ],
      "flows": ["<flow-name>", ...] }
  ],
  "edges": [ { "from": "<id>", "to": "<id>", "weight": <int> } ],
  "flow_index": {
    "<flow-name>": {
      "name":        "<string>",
      "file":        "<rel-path-to-yaml>",
      "purpose":     "<string>",
      "description": "<string>",
      "flow_kind":   "feature|cross_cutting_concern|infrastructure",
      "triggers":    ["<string>", ...],
      "invariants":  ["<string>", ...],
      "invariant_count":   <int>,
      "lifecycle_states":  ["<state-name>", ...],
      "participating_files": ["<rel-path>", ...],
      "declared_dependencies": [
        { "target": "<flow-name>", "kind": "depends_on|communicates_with|...",
          "via": ["<symbol>", ...], "purpose": "<string>" }
      ],
      "author_notes": ["<comment-line>", ...]
    }
  },
  "drift_report": {
    "summary": { "flows_red": <int>, "flows_amber": <int>, "flows_info": <int>, "flows_green": <int>,
                 "orphaned_high_centrality_files": <int>,
                 "claimed_files_missing_in_repo": <int>,
                 "undocumented_cross_flow_pairs": <int>,
                 "broken_declared_dependencies": <int> },
    "per_flow_status":            { "<flow-name>": { "status": "red|amber|info|green", ... } },
    "orphaned_high_centrality_files":   [ { "path", "rank", "score", "kind", "importer_count", "suggested_flow" } ],
    "claimed_files_missing_in_repo":     [ { "flow", "missing_path" } ],
    "undocumented_cross_flow_imports":  [ { "from_flow", "to_flow", "edge_count" } ],
    "broken_declared_dependencies":     [ { "flow", "target", "issue", "detail" } ]
  },
  "drift_migrations": {
    "schema_version": <int, current schemaVersion getter value>,
    "migrations": [
      { "version":     <int>,
        "description": "<extracted from leading // comment>",
        "operations": [
          { "op": "create_table|drop_table|add_column|drop_column|custom_sql",
            "target":     "<table or class name>",
            "column":     "<col name, for add_column / drop_column>",
            "sql":        "<raw SQL excerpt, for custom_sql>",
            "idempotent": <bool, true for *_IfNotExists / *_IfExists patterns> }
        ]
      }
    ]
  },
  "edge_functions": {
    "<function-name>": {
      "name":            "<function name (folder name under supabase/functions/)>",
      "file":            "<rel-path-to-index.ts>",
      "actions":         ["<action_name>", ...],
      "secrets":         ["<UPPER_CASE_ENV_VAR>", ...],
      "buckets":         ["<storage_bucket_name>", ...],
      "rpcs":            ["<rpc_function_name>", ...],
      "external_hosts":  ["<host>", ...],
      "tables_referenced": ["<table_name>", ...]
    }
  },
  "anomaly_catalog": {
    "<anomaly_string_id>": {
      "constant_name": "<Dart const name>",
      "category":      "<part before the dot>",
      "description":   "<from leading /// doc comment>",
      "callsites":     [{ "file": "<rel-path>", "line": <int> }]
    }
  },
  "provider_caches": {
    "<ClassName>": {
      "file":   "<rel-path>",
      "fields": [{ "name": "<_field>", "type": "<TypeExpr>",
                   "shape": "list|map|set|singleton|stream|timer|future" }]
    }
  },
  "cross_cutting_calls": {
    "<HookClassName>": {
      "definition_file": "<rel-path-or-null>",
      "callsites":       [{ "file": "<rel-path>", "line": <int>, "method": "<method-called>" }]
    }
  },
  "postgres_objects": {
    "tables":         [{ "name": "<table>",   "created_in":   "<sql-filename>" }],
    "functions":      [{ "name": "<fn>",      "created_in":   "<sql-filename>" }],
    "triggers":       [{ "name": "<trigger>", "created_in":   "<sql-filename>" }],
    "indexes":        [{ "name": "<idx>",     "on_table": "<t>", "created_in": "<sql-filename>" }],
    "cron_jobs":      [{ "name": "<job>",     "schedule": "<cron-expr>", "scheduled_in": "<sql-filename>" }],
    "column_changes": [{ "table": "<t>", "column": "<c>", "op": "add|drop", "in_migration": "<sql-filename>" }]
  },
  "env_var_usage": {
    "<ENV_VAR_NAME>": [
      { "file": "<rel-path>", "line": <int>,
        "syntax": "deno|dart_string|dart_bool|dart_int|python_get|python_idx|python_getenv" }
    ]
  },
  "static_data": {
    "files": {
      "<rel-path>": [
        { "name": "<varName>", "type": "<TypeExpr>", "item_count": <int> }
      ]
    },
    "relationship_reciprocals": { "<relationship_type>": "<inverse_type>" }
  },
  "symbol_index": {
    "<symbol_name>": [
      { "file": "<rel-path>", "line": <int>,
        "kind": "class|method|function|getter|setter|constructor|...",
        "doc":  "<first sentence of leading /// or /** */ comment>",
        "signature": "<single-line excerpt of the def line>" }
    ]
  },
  "symbol_callers": {
    "<symbol_name>": [
      { "file": "<caller-rel-path>", "line": <int>,
        "receiver": "<ClassName for static dispatch, or null for bare call>" }
    ]
  },
  "class_usage": {
    "<ClassName>": [
      { "file": "<caller-rel-path>", "line": <int>, "method": "<method-called-on-this-class>" }
    ]
  },
  "class_hierarchy": {
    "<ClassName>": {
      "file":       "<rel-path>",
      "line":       <int>,
      "abstract":   <bool>,
      "extends":    "<superclass or null>",
      "implements": ["<iface>", ...],
      "with":       ["<mixin>", ...],
      "kind":       "class | mixin"
    }
  },
  "asset_paths": {
    "<asset/path/to/file.png>": [{ "file": "<caller>", "line": <int> }]
  },
  "ui_strings": {
    "<user-facing prose literal>": [{ "file": "<caller>", "line": <int> }]
  },
  "test_pairing": {
    "<lib/.../x.dart>": "<test/.../x_test.dart>"
  },
  "bug_catalog": {
    "by_file":   { "<file>": [{ "bug_id", "status", "title", "file" }] },
    "by_system": { "<system>": [{ "bug_id", "status", "title", "file" }] },
    "summary":   { "total", "open", "resolved" }
  },
  "supabase_migrations": [
    { "filename":    "<sql migration filename>",
      "description": "<extracted from leading -- comment>",
      "operations": [
        { "op": "create_table|add_column|drop_column|create_function|create_trigger|create_index|schedule_cron",
          "target":   "<table/function/trigger/etc>",
          "column":   "<col name, for add_column / drop_column>",
          "name":     "<index or cron job name>",
          "schedule": "<cron expression, for schedule_cron>" }
      ]
    }
  ],
  "_history_file_": "plans/dashboard/data/repo_map_history.jsonl — append-only JSONL written by repo_map.py at end of each build (deduplicated against the previous line). Each line: { ts, node_count, edge_count, flow_count, orphans, broken_deps, undocumented_pairs, claimed_files_missing, flows_red, flows_amber, flows_info, flows_green, drift_table_count, edge_function_count, anomaly_type_count, provider_count, env_var_count, schema_version, flows_with_invariants }. Drives the dashboard's Drift sub-tab trend sparkline. Use case: 'is orphan count rising?' / 'when did broken_deps first hit non-zero?' / build cadence diagnostics.",
  "drift_schema": {
    "<TableClassName>": {
      "class_name":      "<dart class name, e.g. JournalEntries>",
      "sql_name":        "<snake_case sql name, e.g. journal_entries>",
      "data_class_name": "<from @DataClassName(...) annotation, or null>",
      "file":            "<rel-path-to-table-dart-file>",
      "columns": [
        { "name": "<col_name>",
          "dart_type": "IntColumn|TextColumn|BoolColumn|DateTimeColumn|RealColumn|BlobColumn",
          "sql_type":  "INTEGER|TEXT|BOOLEAN|DATETIME|REAL|BLOB",
          "nullable":       <bool>,
          "unique":         <bool>,
          "auto_increment": <bool>,
          "default":        "<expression text or null>"
        }
      ],
      "foreign_keys": [
        { "from_column": "<col on this table>",
          "to_table":    "<referenced TableClassName>",
          "to_column":   "<col on referenced table>",
          "on_delete":   "cascade|restrict|setNull|setDefault|noAction",
          "nullable":    <bool, true if FK column itself is nullable> }
      ],
      "primary_key": ["<col_name>", ...]
    }
  }
}
```

Any tool that emits this JSON shape can drive the dashboard. The dashboard
makes no other assumptions about your project.

## Per-extractor reference (Phase 1 of system_map_decomposition_plan.yaml)

The `drift_schema` field above is one of nine auto-extraction passes that
replace the editorial claims that used to live in `SYSTEM_MAP.yaml`. Each
extractor is independent and stack-aware. To port to a different stack,
write the equivalent extractor for your ORM / runtime / tooling and emit
the same JSON shape — the dashboard reads JSON and doesn't care which
language produced it.

### `drift_schema` (Drift / SQLite for Flutter projects)
- **Source:** `lib/database/tables/*.dart`
- **Implementation:** `extract_drift_schema()` in `scripts/repo_map.py`
- **Replaces in SYSTEM_MAP:** all hand-written `cascade_on_delete` fields,
  the `entity_relationships` block, per-section foreign-key prose, table
  column shape narratives.
- **Port equivalents for other stacks:**
  - Prisma project → parse `schema.prisma` for `model X { ... }` blocks
    and the `@relation(onDelete: ...)` attributes.
  - SQLAlchemy project → parse `class X(Base):` declarations and the
    `ForeignKey(..., ondelete=...)` calls.
  - TypeORM project → parse `@Entity()` classes and `@ManyToOne(..., { onDelete: ... })`.
  - Plain SQL migration files → parse `CREATE TABLE` + `REFERENCES ... ON DELETE`.
  - In each case, emit the same `drift_schema` JSON shape (or rename to
    e.g. `prisma_schema` and update the dashboard renderer to read it).

### `drift_migrations` (Drift `onUpgrade` switch)
- **Source:** `lib/database/app_database.dart` — the `schemaVersion` getter
  and the `onUpgrade: (Migrator m, int from, int to) async {...}` callback.
- **Implementation:** `extract_drift_migrations()` in `scripts/repo_map.py`.
- **Replaces in SYSTEM_MAP:** `database.schema_version`, `database.recent_migrations`.
- **Port equivalents:**
  - Prisma → walk `prisma/migrations/*/migration.sql` directories.
  - Rails / Active Record → walk `db/migrate/*.rb` files.
  - SQLAlchemy / Alembic → walk `alembic/versions/*.py`.
  - In each case, emit a `{ schema_version, migrations: [{version, description, operations: [...]}] }` shape.

### `supabase_migrations` (server-side SQL migrations)
- **Source:** `supabase/migrations/*.sql` (date-prefixed SQL files run by
  `supabase db push` / `supabase migration up`).
- **Implementation:** `extract_supabase_migrations()` in `scripts/repo_map.py`.
- **Replaces in SYSTEM_MAP:** per-section `supabase_columns_added`,
  `perception_signals.supabase_functions`, per-section trigger fields,
  cron-job narratives.
- **Port equivalents:**
  - Plain Postgres migrations folder → identical regex parser will work.
  - Knex → walk `migrations/*.js` and parse `.createTable(...)` / `.alterTable(...)`.
  - Sequelize → walk `migrations/*.js` and parse `queryInterface.*` calls.
  - In each case, emit a list of `{ filename, description, operations: [...] }` objects.

### `edge_functions` (server-side function/handler runtime artifacts)
- **Source:** `supabase/functions/*/index.ts`. Detects three dispatch styles:
  switch/case on `action`, `if (action === "...")` chains, and `const handlers = {...}` object literals.
- **Implementation:** `extract_edge_function_actions()` in `scripts/repo_map.py`.
- **Replaces in SYSTEM_MAP:** per-section `edge_function: 'name (action1, ...)'`,
  `supabase_secrets`, `supabase_buckets`, `external_api`, `scan_providers`.
- **Port equivalents:**
  - AWS Lambda / Cloudflare Workers / Vercel functions → walk the per-function
    folder, parse the same dispatch + secret-reading patterns.
  - Express / Fastify routes → parse `app.get('/path', ...)` / `app.post(...)`
    instead of action dispatch — emit routes as the equivalent of `actions`.
  - Common to all: each function emits `{ actions, secrets, buckets, rpcs,
    external_hosts, tables_referenced }` regardless of stack.

### `anomaly_catalog` (instrumented anomaly types + callsites)
- **Source:** `lib/utils/app_anomaly_reporter.dart` (the canonical type list)
  + every `AppAnomalyReporter.report(anomalyType: AnomalyTypes.X)` callsite in `lib/`.
- **Implementation:** `extract_anomaly_catalog()` in `scripts/repo_map.py`.
- **Replaces in SYSTEM_MAP:** `anomaly_detection.instrumented` map.
- **Port equivalents:**
  - Sentry custom-issue projects → walk for `Sentry.captureMessage(...)` /
    `captureEvent(...)` callsites and group by fingerprint.
  - Generic logger.warn / logger.error grep → catalog by warning-string-id.
  - Replace `lib/utils/app_anomaly_reporter.dart` with whatever file
    centralizes your instrumentation type definitions.

### `provider_caches` (state-management cache shapes)
- **Source:** `lib/providers/*.dart` — private fields with cache-shape types
  (`List<X>`, `Map<K,V>`, `Set<X>`, singletons, streams, timers, futures).
- **Implementation:** `extract_provider_caches()` in `scripts/repo_map.py`.
- **Replaces in SYSTEM_MAP:** per-section provider field narratives.
- **Port equivalents:**
  - React projects → parse `useState<...>(...)`, `useReducer<...>`, Context state shapes.
  - Vue → parse `data() { return { ... } }` returns + Pinia store state.
  - Redux/MobX → parse store `state` interface declarations.
  - In each case, emit `{ <ClassName/Store>: { file, fields: [{name, type, shape}] } }`.

### `cross_cutting_calls` (concern hooks invoked across providers/services)
- **Source:** explicit list of cross-cutting class names (in
  `CROSS_CUTTING_HOOKS` constant in `repo_map.py`) + grep for static-method
  invocations across `lib/`.
- **Implementation:** `extract_cross_cutting_calls()` in `scripts/repo_map.py`.
- **Replaces in SYSTEM_MAP:** the `cross_cutting_hooks` block.
- **Port equivalents:**
  - Aspect-oriented frameworks → walk for `@Around(...)` / interceptor wirings.
  - Plain inversion-of-control → walk for known service-locator gets.
  - Heuristic option: classes whose name ends with `Tagger`/`Service`/`Reporter`
    AND that are invoked as `ClassName.method(...)` (static dispatch).

### `postgres_objects` (inverted index by object type → migration that created it)
- **Source:** rolled up from `supabase_migrations` operations.
- **Implementation:** `build_postgres_objects()` in `scripts/repo_map.py`.
- **Replaces in SYSTEM_MAP:** per-section `supabase_tables` lists,
  `supabase_functions`, per-section triggers fields.
- **Port equivalents:** any project with a migration history can roll up its
  per-migration operations into a flat `{ tables, functions, triggers, indexes,
  cron_jobs, column_changes }` index.

### `env_var_usage` (compile-time + runtime env reads)
- **Source:** grep of `Deno.env.get`, `String.fromEnvironment`,
  `bool.fromEnvironment`, `int.fromEnvironment`, `os.environ.get`,
  `os.environ['NAME']`, `os.getenv` across all source dirs.
- **Implementation:** `extract_env_var_usage()` in `scripts/repo_map.py`.
- **Replaces in SYSTEM_MAP:** per-section `env_vars` fields.
- **Port equivalents:** the patterns above already cover Deno, Dart, and
  Python. For Node.js add `process.env.NAME` / `process.env['NAME']`. For
  Go add `os.Getenv("NAME")`.

### `static_data` (top-level const collections)
- **Source:** `lib/data/*.dart` — top-level `const`/`final` Map / List
  declarations + the `RelationshipPairService._reciprocals` map specifically.
- **Implementation:** `extract_static_data_maps()` in `scripts/repo_map.py`.
- **Replaces in SYSTEM_MAP:** `relationships.reciprocal_map`,
  `interests.seed_data` count, `activities.inference_engine.crosswalk_data` count.
- **Port equivalents:**
  - TypeScript → parse `export const X: Map<...> = new Map([...])`.
  - Python → parse module-level `X: dict[...] = {...}` or `X = {...}`.
  - JSON-driven data (no code) → just `len(json.load(...))` per file.

### `symbol_index` / `symbol_callers` / `class_usage` / `class_hierarchy` (Tier-A grep replacers, added 2026-04-30)
The biggest grep-saver for an LLM agent navigating an unfamiliar codebase.
Four indexes that together answer "where is X defined / called / extended"
without spawning a Grep tool call.

- **`symbol_index`** — `name → [{file, line, kind, doc, signature}]`. Replaces
  `grep "class X\|^def X\|function X"`. Includes the leading doc comment
  (Dart `///`, Python `"""..."""`, TS `/** */`) so the agent gets a one-line
  summary in-band.
- **`symbol_callers`** — `name → [{file, line, receiver}]`. Replaces
  `grep "X("`. Captures `Class.method(` static dispatch + bare-call sites
  where the called name is a known top-level definition. Plain
  `instance.method(` calls are SKIPPED — without type info there's no way
  to disambiguate which `add` is being called.
- **`class_usage`** — `ClassName → [{file, line, method}]`. Aggregated
  inverse of `symbol_callers` keyed by RECEIVER. Replaces "where is
  AppLogger used?"-style queries with one O(1) lookup instead of
  scanning all method entries.
- **`class_hierarchy`** — `ClassName → {extends, implements[], with[],
  abstract, kind, file, line}`. Replaces `grep "class X extends"`.
  Multi-language as of 2026-04-30 (Dart, Python, TS/JS).

#### Per-language extension points

| Language | Class-hierarchy regex | Doc-comment style |
|---|---|---|
| Dart | `_DART_CLASS_HIERARCHY_RX`, `_DART_MIXIN_HIERARCHY_RX` | `///` line above def, multi-line collected |
| Python | `_PY_CLASS_HIERARCHY_RX` (captures `class X(Base1, Base2)`, ABC detection) | `"""..."""` BELOW the def line |
| TS / TSX / JS | `_TS_CLASS_HIERARCHY_RX` (captures `[abstract] class X extends Y implements I1, I2`) | `/** ... */` block above def |
| Go (TODO) | not yet — pattern: `type X struct {` + `func (x *X) ...` |
| Rust (TODO) | not yet — pattern: `impl X for Y` + `///` line comments |
| Java (TODO) | not yet — pattern matches Dart closely; reuse `_DART_CLASS_HIERARCHY_RX` shape |

To add a language: (1) add a regex following the existing per-language
pattern in `repo_map.py`, (2) extend `extract_class_hierarchy()`'s `if
fi.lang == ...` branch, (3) extend `_extract_leading_doc()` with the
new comment style.

- **Implementation:** `build_symbol_index()`, `extract_call_graph()`,
  `build_class_usage()`, `extract_class_hierarchy()` in `scripts/repo_map.py`.
- **Cost:** adds ~9 MB to repo_map.json on a 1284-file project.
  Acceptable for localhost dev — fetched once per page load.
- **Port equivalents:** `symbol_index` falls out for free from any
  language tree-sitter already supports — the existing per-file
  symbol extraction already has all the data; just inverting the
  index gives you the global lookup. `symbol_callers` needs a
  per-language regex for call expressions; the patterns in
  `_CALL_RX` are a starting point.

### `asset_paths` / `ui_strings` / `test_pairing` / `bug_catalog` / per-node `est_tokens` (Tier-A++, added 2026-04-30 second pass)

Five low-cost additions that each replace a real grep target. Building
them was almost free given the auto-rebuild loop, so the bar shifted from
"high-ROI" to "non-zero diagnostic value":

- **`asset_paths`** — `"assets/foo.png" → [{file, line}]`. Where each
  bundled asset is referenced. Currently Dart-only (matches the Flutter
  `assets/`, `images/`, `fonts/`, `lib/data/` directory conventions).
- **`ui_strings`** — `"Activity Trends" → [{file, line}]`. Heuristic
  index of multi-word user-facing prose literals (5–80 chars,
  lowercase-then-space-then-letter pattern). Useful for "where does
  this label come from?" and label-translation work. False positives
  are tolerable; lookup is O(1).
- **`test_pairing`** — `"lib/services/x.dart" → "test/services/x_test.dart"`.
  Pairs source files to their tests by filename convention. Scans `test/`
  directly (not in INCLUDE_DIRS by default).
- **`bug_catalog`** — `{by_file, by_system, summary}`. Walks
  `bugs/{system}/*.yaml`, links each bug to source files it references,
  and aggregates per-system. The `summary.open` count is the diagnostic
  signal: "are there open bugs in this area before I edit?"
- **`est_tokens`** (per node) — rough `byte_count // 4` estimate.
  Informs Read-vs-delegate decisions ("is this 2k tokens or 50k?").

To port: each of these has a clear language/convention assumption
(Flutter assets, Dart `_test.dart` suffix, `bugs/{system}/` folder
layout). For a non-Flutter project, swap the regex prefixes / folder
names. None of them are load-bearing — drop the ones that don't apply
to your stack.
