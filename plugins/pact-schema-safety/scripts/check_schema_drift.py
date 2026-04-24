#!/usr/bin/env python3
"""Schema drift detection: live Postgres schema vs local codebase assumptions.

Compares four sources:
  LIVE     â€” Postgres information_schema (via psycopg2 + SCHEMA_SAFETY_DB_URL)
  DRIFT    â€” Drift table definitions in lib/database/tables/*.dart
  EF       â€” .select() / .from() calls in supabase/functions/**/index.ts
  DOC      â€” knowledge/supabase_schema.yaml (structured: tables.{name}.columns)
  TECH     â€” knowledge/tech_stack.yaml Â§ edge_functions inventory

Outputs:
  - bugs/schema/schema-drift-{date}.yaml (created or updated; tracks first_seen/last_seen)
  - knowledge/supabase_schema.yaml regenerated from live (preserving per-table `keep:` blocks)
  - scripts/RUN_LOG.yaml entry
  - .claude/memory/PENDING_WORK.yaml Â§ schema_drift_detected (when criticals > 0; cleared otherwise)

Usage:
  python scripts/check_schema_drift.py            # use cache if <12h old
  python scripts/check_schema_drift.py --no-cache # force fresh fetch
  python scripts/check_schema_drift.py --quiet    # silent unless drift
  python scripts/check_schema_drift.py --no-doc   # skip doc regeneration (skip writing supabase_schema.yaml)
  python scripts/check_schema_drift.py --no-bug   # skip bug file write
  python scripts/check_schema_drift.py --json     # emit machine-readable summary

Phases (per plans/schema_drift_detection_plan.yaml):
  Phase 1 = parse + diff + bug-file output + doc regeneration  [shipped here]
  Phase 2 = scheduling/slash-command/checkpoint integration    [shipped in companion files]
  Phase 3 = suggested fixes + first_seen tracking + severity escalation  [shipped here]
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("FATAL: psycopg2 not installed. Run: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(2)

try:
    import yaml
except ImportError:
    print("FATAL: pyyaml not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Paths
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

PROJECT_ROOT = Path(__file__).parent.parent
LIB_TABLES_DIR = PROJECT_ROOT / "lib" / "database" / "tables"
EF_DIR = PROJECT_ROOT / "supabase" / "functions"
SCHEMA_DOC = PROJECT_ROOT / "knowledge" / "supabase_schema.yaml"
TECH_STACK = PROJECT_ROOT / "knowledge" / "tech_stack.yaml"
IGNORE_FILE = PROJECT_ROOT / "scripts" / ".schema_drift_ignore.yaml"
CACHE_DIR = PROJECT_ROOT / "scripts" / ".cache"
RUN_LOG = PROJECT_ROOT / "scripts" / "RUN_LOG.yaml"
BUGS_SCHEMA_DIR = PROJECT_ROOT / "bugs" / "schema"
PENDING_WORK = PROJECT_ROOT / ".claude" / "memory" / "PENDING_WORK.yaml"

CACHE_TTL_HOURS = 12
DRIFT_AGE_ESCALATION_DAYS = 7

# Optional config override: if pact-schema-safety.config.yaml exists at the
# project root, its values override the defaults above. Lets a project keep
# its ORM tables somewhere other than lib/database/tables/, etc.
CONFIG_FILE = PROJECT_ROOT / "pact-schema-safety.config.yaml"
if CONFIG_FILE.exists():
    try:
        import yaml as _yaml
        _cfg = _yaml.safe_load(CONFIG_FILE.read_text()) or {}
        if _cfg.get("orm_tables_dir"):    LIB_TABLES_DIR = PROJECT_ROOT / _cfg["orm_tables_dir"]
        if _cfg.get("edge_functions_dir"): EF_DIR        = PROJECT_ROOT / _cfg["edge_functions_dir"]
        if _cfg.get("schema_doc"):         SCHEMA_DOC    = PROJECT_ROOT / _cfg["schema_doc"]
        if _cfg.get("tech_stack"):         TECH_STACK    = PROJECT_ROOT / _cfg["tech_stack"]
        if _cfg.get("ignore_file"):        IGNORE_FILE   = PROJECT_ROOT / _cfg["ignore_file"]
        if _cfg.get("bugs_schema_dir"):    BUGS_SCHEMA_DIR = PROJECT_ROOT / _cfg["bugs_schema_dir"]
        if _cfg.get("cache_ttl_hours"):    CACHE_TTL_HOURS = int(_cfg["cache_ttl_hours"])
        if _cfg.get("drift_age_escalation_days"): DRIFT_AGE_ESCALATION_DAYS = int(_cfg["drift_age_escalation_days"])
    except Exception as _e:
        print(f"WARN: failed to load pact-schema-safety.config.yaml: {_e}")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Data shapes
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@dataclass
class LiveColumn:
    table: str
    column: str
    data_type: str
    is_nullable: bool
    default: str | None


@dataclass
class LiveFK:
    table: str
    column: str
    foreign_table: str
    foreign_column: str


@dataclass
class LiveSchema:
    columns: list[LiveColumn]
    fks: list[LiveFK]
    fetched_at: str

    def column_set(self, table: str) -> set[str]:
        return {c.column for c in self.columns if c.table == table}

    def column_type(self, table: str, column: str) -> str | None:
        for c in self.columns:
            if c.table == table and c.column == column:
                return c.data_type
        return None

    def tables(self) -> set[str]:
        return {c.table for c in self.columns}


@dataclass
class DriftColumn:
    name: str          # snake_case
    drift_type: str    # 'integer' | 'text' | 'real' | 'boolean' | 'dateTime' | 'blob'
    nullable: bool
    fk_target_table: str | None = None  # snake_case
    fk_target_column: str | None = None


@dataclass
class DriftTable:
    file: str
    class_name: str
    table_name: str    # snake_case
    columns: list[DriftColumn]


@dataclass
class EFColumnRef:
    file: str
    line: int
    table: str
    columns: list[str]  # parsed from .select('a, b, c'); empty for select('*')


@dataclass
class DocTable:
    name: str
    columns: set[str]


@dataclass
class Diff:
    severity: str            # critical | warning
    kind: str                # missing_in_live | extra_in_live | type_mismatch | fk_target_drift | function_inventory_mismatch
    source: str              # drift | ef | doc | tech_stack
    table: str
    column: str | None
    expected: str | None
    actual: str | None
    location: str | None     # file:line
    suggested_fix: str | None = None


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Live schema fetch
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

LIVE_COLS_SQL = """
SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;
"""

LIVE_FKS_SQL = """
SELECT
  tc.table_name,
  kcu.column_name,
  ccu.table_name  AS foreign_table,
  ccu.column_name AS foreign_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema    = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
  ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public';
"""


def fetch_live_schema(cache_ok: bool) -> LiveSchema:
    today = dt.date.today().isoformat()
    cache_path = CACHE_DIR / f"live_schema_{today}.json"

    if cache_ok and cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < CACHE_TTL_HOURS:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            return LiveSchema(
                columns=[LiveColumn(**c) for c in data["columns"]],
                fks=[LiveFK(**f) for f in data["fks"]],
                fetched_at=data["fetched_at"],
            )

    db_url = os.environ.get("SCHEMA_SAFETY_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print(
            "FATAL: SCHEMA_SAFETY_DB_URL env var not set.\n"
            "  Set via PowerShell:\n"
            "    [Environment]::SetEnvironmentVariable('SCHEMA_SAFETY_DB_URL', '<url>', 'User')",
            file=sys.stderr,
        )
        sys.exit(2)

    conn = psycopg2.connect(db_url, connect_timeout=15)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(LIVE_COLS_SQL)
            cols = [
                LiveColumn(
                    table=r["table_name"],
                    column=r["column_name"],
                    data_type=r["data_type"],
                    is_nullable=(r["is_nullable"] == "YES"),
                    default=r["column_default"],
                )
                for r in cur.fetchall()
            ]
            cur.execute(LIVE_FKS_SQL)
            fks = [
                LiveFK(
                    table=r["table_name"],
                    column=r["column_name"],
                    foreign_table=r["foreign_table"],
                    foreign_column=r["foreign_column"],
                )
                for r in cur.fetchall()
            ]
    finally:
        conn.close()

    schema = LiveSchema(columns=cols, fks=fks, fetched_at=dt.datetime.now(dt.timezone.utc).isoformat())

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "fetched_at": schema.fetched_at,
                "columns": [c.__dict__ for c in cols],
                "fks": [f.__dict__ for f in fks],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return schema


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Drift table parser
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

CLASS_RE = re.compile(
    r"(?:@DataClassName\([\"']([^\"']+)[\"']\)\s*\n)?\s*class\s+(\w+)\s+extends\s+Table\s*\{",
    re.MULTILINE,
)
COL_RE = re.compile(
    r"(Int|Text|Real|Bool|DateTime|Blob)Column\s+get\s+(\w+)\s*=>\s*"
    r"(integer|text|real|boolean|dateTime|blob)\(\)"
    r"((?:\.[a-zA-Z]+\([^)]*\))*)\s*\(\)\s*;",
)
NAMED_RE = re.compile(r"\.named\([\"']([^\"']+)[\"']\)")
REFS_RE = re.compile(r"\.references\(\s*(\w+)\s*,\s*#(\w+)")


def to_snake(name: str) -> str:
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


def extract_class_body(text: str, brace_start: int) -> str:
    """Return text from brace_start (the '{') to the matching '}'."""
    depth = 0
    for i in range(brace_start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start + 1 : i]
    return text[brace_start + 1 :]


def parse_drift_tables() -> list[DriftTable]:
    tables: list[DriftTable] = []
    for path in sorted(LIB_TABLES_DIR.rglob("*.dart")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in CLASS_RE.finditer(text):
            class_name = m.group(2)
            brace = text.find("{", m.end() - 1)
            if brace < 0:
                continue
            body = extract_class_body(text, brace)
            cols: list[DriftColumn] = []
            for cm in COL_RE.finditer(body):
                method_name = cm.group(2)
                drift_type = cm.group(3)
                modifiers = cm.group(4) or ""
                nullable = ".nullable()" in modifiers
                # named() override wins over snake_case of method
                named_match = NAMED_RE.search(modifiers)
                col_name = named_match.group(1) if named_match else to_snake(method_name)
                fk_table = fk_col = None
                refs = REFS_RE.search(modifiers)
                if refs:
                    fk_table = to_snake(refs.group(1))
                    fk_col = to_snake(refs.group(2))
                cols.append(
                    DriftColumn(
                        name=col_name,
                        drift_type=drift_type,
                        nullable=nullable,
                        fk_target_table=fk_table,
                        fk_target_column=fk_col,
                    )
                )
            if not cols:
                continue
            tables.append(
                DriftTable(
                    file=str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    class_name=class_name,
                    table_name=to_snake(class_name),
                    columns=cols,
                )
            )
    return tables


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Edge Function .select() parser
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# .from('table')  followed within ~600 chars by  .select('a, b')
# (handles multi-line selects by treating . as anychar)
EF_PAIR_RE = re.compile(
    r"\.from\(\s*[\"']([\w_]+)[\"']\s*\)[\s\S]{0,600}?"
    r"\.select\(\s*[\"']([^\"']+)[\"']\s*[,\)]",
    re.MULTILINE,
)


def parse_edge_function_refs() -> list[EFColumnRef]:
    refs: list[EFColumnRef] = []
    if not EF_DIR.exists():
        return refs
    for path in sorted(EF_DIR.rglob("index.ts")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in EF_PAIR_RE.finditer(text):
            table = m.group(1)
            cols_str = m.group(2).strip()
            # Skip *
            if cols_str == "*":
                cols: list[str] = []
            else:
                cols = []
                for piece in cols_str.split(","):
                    raw = piece.strip()
                    # Strip ' as alias' suffix
                    raw = re.split(r"\s+as\s+", raw, maxsplit=1)[0].strip()
                    # Strip nested ( ... ) like  count(*)
                    if "(" in raw or "*" in raw or not raw:
                        continue
                    # Strip foreign-table embed:  some_table(col1, col2)
                    if not re.match(r"^[\w_]+$", raw):
                        continue
                    cols.append(raw)
            line = text[: m.start()].count("\n") + 1
            refs.append(
                EFColumnRef(
                    file=str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    line=line,
                    table=table,
                    columns=cols,
                )
            )
    return refs


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Doc + tech_stack parsers
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def parse_schema_yaml() -> list[DocTable]:
    """Parse knowledge/supabase_schema.yaml â€” structured format.

    Expected shape:
      tables:
        table_name:
          columns:
            col1: { type: ..., nullable: ..., default: ..., fk: ... }
            col2: ...
          keep: |   # optional manual notes
            ...
    """
    if not SCHEMA_DOC.exists():
        return []
    try:
        data = yaml.safe_load(SCHEMA_DOC.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    tables_node = data.get("tables") or {}
    if not isinstance(tables_node, dict):
        return []
    out: list[DocTable] = []
    for name, body in tables_node.items():
        if not isinstance(body, dict):
            continue
        cols_node = body.get("columns") or {}
        if isinstance(cols_node, dict):
            cols = set(cols_node.keys())
        else:
            cols = set()
        if cols:
            out.append(DocTable(name=str(name), columns=cols))
    return out


def parse_tech_stack_functions() -> set[str]:
    if not TECH_STACK.exists():
        return set()
    try:
        data = yaml.safe_load(TECH_STACK.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if not isinstance(data, dict):
        return set()
    funcs = data.get("edge_functions") or {}
    if isinstance(funcs, dict):
        return set(funcs.keys())
    if isinstance(funcs, list):
        return {f if isinstance(f, str) else f.get("name", "") for f in funcs}
    return set()


def list_local_functions() -> set[str]:
    if not EF_DIR.exists():
        return set()
    return {p.name for p in EF_DIR.iterdir() if p.is_dir() and (p / "index.ts").exists()}


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Ignore file
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@dataclass
class IgnoreEntry:
    table: str
    column: str | None  # None means ignore whole table
    reason: str
    added: str


def load_ignores() -> list[IgnoreEntry]:
    if not IGNORE_FILE.exists():
        return []
    data = yaml.safe_load(IGNORE_FILE.read_text(encoding="utf-8")) or {}
    out = []
    for e in data.get("ignored", []):
        out.append(
            IgnoreEntry(
                table=e.get("table", ""),
                column=e.get("column"),
                reason=e.get("reason", ""),
                added=e.get("added", ""),
            )
        )
    return out


def is_ignored(table: str, column: str | None, ignores: list[IgnoreEntry]) -> bool:
    for ig in ignores:
        if ig.table == table and (ig.column is None or ig.column == column):
            return True
    return False


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Diff logic + suggested fixes
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# Loose drift-type â†’ live-type compatibility (fuzzy match for common cases)
TYPE_COMPAT = {
    "integer": {"integer", "bigint", "smallint"},
    "text":    {"text", "character varying", "varchar", "uuid", "character"},
    "real":    {"real", "double precision", "numeric"},
    "boolean": {"boolean"},
    "datetime":{"timestamp without time zone", "timestamp with time zone", "date"},
    "blob":    {"bytea"},
}


def compatible_type(drift_type: str, live_type: str) -> bool:
    drift_key = drift_type.lower()
    live_norm = live_type.lower()
    return live_norm in TYPE_COMPAT.get(drift_key, set())


def suggest_rename(want: str, available: set[str]) -> str | None:
    if not want or not available:
        return None
    matches = difflib.get_close_matches(want, list(available), n=1, cutoff=0.6)
    return matches[0] if matches else None


def diff_all(
    live: LiveSchema,
    drift: list[DriftTable],
    efs: list[EFColumnRef],
    docs: list[DocTable],
    tech_funcs: set[str],
    local_funcs: set[str],
    ignores: list[IgnoreEntry],
) -> list[Diff]:
    diffs: list[Diff] = []

    # â”€â”€â”€ Drift table column drift â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    for dt_ in drift:
        live_cols = live.column_set(dt_.table_name)
        if not live_cols:
            # Drift table maps to a Postgres table that doesn't exist in public.
            # This is often a Drift-only local table â€” skip.
            continue
        for col in dt_.columns:
            if is_ignored(dt_.table_name, col.name, ignores):
                continue
            if col.name not in live_cols:
                fix = suggest_rename(col.name, live_cols)
                diffs.append(Diff(
                    severity="critical",
                    kind="missing_in_live",
                    source="drift",
                    table=dt_.table_name,
                    column=col.name,
                    expected=col.name,
                    actual=None,
                    location=dt_.file,
                    suggested_fix=(
                        f"Drift column `{col.name}` does not exist in live schema. "
                        + (f"Closest live column: `{fix}` â€” likely renamed." if fix else "No close match in live schema; column may have been dropped.")
                    ),
                ))
            else:
                live_type = live.column_type(dt_.table_name, col.name) or ""
                if live_type and not compatible_type(col.drift_type, live_type):
                    diffs.append(Diff(
                        severity="critical",
                        kind="type_mismatch",
                        source="drift",
                        table=dt_.table_name,
                        column=col.name,
                        expected=col.drift_type,
                        actual=live_type,
                        location=dt_.file,
                        suggested_fix=f"Drift declares `{col.drift_type}` but live is `{live_type}`. Update Drift column type or add a converter.",
                    ))
            # FK target validation
            if col.fk_target_table and col.fk_target_column:
                ft_cols = live.column_set(col.fk_target_table)
                if not ft_cols:
                    diffs.append(Diff(
                        severity="critical",
                        kind="fk_target_drift",
                        source="drift",
                        table=dt_.table_name,
                        column=col.name,
                        expected=f"{col.fk_target_table}.{col.fk_target_column}",
                        actual="(table does not exist)",
                        location=dt_.file,
                        suggested_fix=f"FK target table `{col.fk_target_table}` not in live schema. Was the table renamed or dropped?",
                    ))
                elif col.fk_target_column not in ft_cols:
                    fix = suggest_rename(col.fk_target_column, ft_cols)
                    diffs.append(Diff(
                        severity="critical",
                        kind="fk_target_drift",
                        source="drift",
                        table=dt_.table_name,
                        column=col.name,
                        expected=f"{col.fk_target_table}.{col.fk_target_column}",
                        actual=f"{col.fk_target_table}.(missing)",
                        location=dt_.file,
                        suggested_fix=(
                            f"FK references `{col.fk_target_table}.{col.fk_target_column}` but that column doesn't exist. "
                            + (f"Closest: `{fix}`." if fix else "")
                        ),
                    ))

    # â”€â”€â”€ Edge Function .select() drift â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    for ef in efs:
        live_cols = live.column_set(ef.table)
        if not live_cols:
            continue  # table doesn't exist; skip noisy ef table errors
        for col in ef.columns:
            if is_ignored(ef.table, col, ignores):
                continue
            if col not in live_cols:
                fix = suggest_rename(col, live_cols)
                diffs.append(Diff(
                    severity="critical",
                    kind="missing_in_live",
                    source="ef",
                    table=ef.table,
                    column=col,
                    expected=col,
                    actual=None,
                    location=f"{ef.file}:{ef.line}",
                    suggested_fix=(
                        f"Edge Function selects `{col}` from `{ef.table}` but no such column exists. "
                        + (f"Closest: `{fix}`." if fix else "")
                    ),
                ))

    # â”€â”€â”€ Doc drift â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    for doc in docs:
        live_cols = live.column_set(doc.name)
        if not live_cols:
            continue
        for col in doc.columns:
            if is_ignored(doc.name, col, ignores):
                continue
            if col not in live_cols:
                diffs.append(Diff(
                    severity="warning",
                    kind="missing_in_live",
                    source="doc",
                    table=doc.name,
                    column=col,
                    expected=col,
                    actual=None,
                    location=str(SCHEMA_DOC.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    suggested_fix=f"Doc references `{col}` in `{doc.name}` but live schema lacks it. Doc will be regenerated.",
                ))

    # â”€â”€â”€ Function inventory drift (tech_stack vs local dirs) â”€â”€â”€â”€â”€â”€
    only_local = local_funcs - tech_funcs
    only_tech = tech_funcs - local_funcs
    for fn in sorted(only_local):
        diffs.append(Diff(
            severity="warning",
            kind="function_inventory_mismatch",
            source="ef",
            table="(edge_functions)",
            column=fn,
            expected="listed in tech_stack.yaml",
            actual="present in supabase/functions/ but not documented",
            location="knowledge/tech_stack.yaml",
            suggested_fix=f"Add `{fn}` to tech_stack.yaml Â§ edge_functions.",
        ))
    for fn in sorted(only_tech):
        diffs.append(Diff(
            severity="warning",
            kind="function_inventory_mismatch",
            source="tech_stack",
            table="(edge_functions)",
            column=fn,
            expected="present in supabase/functions/",
            actual="documented but not present",
            location="knowledge/tech_stack.yaml",
            suggested_fix=f"Either restore the EF directory or remove `{fn}` from tech_stack.yaml.",
        ))

    return diffs


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Bug file management (Phase 1 + Phase 3 first_seen tracking)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def existing_open_bug() -> Path | None:
    if not BUGS_SCHEMA_DIR.exists():
        return None
    for p in sorted(BUGS_SCHEMA_DIR.glob("schema-drift-*.yaml"), reverse=True):
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            if data.get("status") not in {"resolved", "closed"}:
                return p
        except Exception:
            continue
    return None


def write_or_update_bug(diffs: list[Diff]) -> Path | None:
    criticals = [d for d in diffs if d.severity == "critical"]
    if not criticals and len([d for d in diffs if d.severity == "warning"]) < 3:
        # Below threshold â€” don't bug-file
        return None

    BUGS_SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    open_bug = existing_open_bug()
    if open_bug:
        existing = yaml.safe_load(open_bug.read_text(encoding="utf-8")) or {}
        first_seen = existing.get("first_seen", today)
    else:
        first_seen = today

    age_days = (dt.date.today() - dt.date.fromisoformat(first_seen)).days
    severity = "critical" if criticals else "warning"
    if age_days >= DRIFT_AGE_ESCALATION_DAYS and criticals:
        severity = "high"  # escalated

    bug_id = open_bug.stem if open_bug else f"schema-drift-{today}"
    bug_path = open_bug if open_bug else BUGS_SCHEMA_DIR / f"{bug_id}.yaml"

    body = {
        "id": bug_id,
        "title": f"Schema drift detected â€” {len(criticals)} critical, {len([d for d in diffs if d.severity == 'warning'])} warnings",
        "severity": severity,
        "status": "open",
        "system": "schema",
        "auto_generated": True,
        "first_seen": first_seen,
        "last_seen": today,
        "age_days": age_days,
        "discovered": {
            "date": today,
            "session": "scripts/check_schema_drift.py",
            "how": "Automated daily drift detection comparing live Postgres schema against Drift tables, Edge Function .select() calls, supabase_schema.yaml, and tech_stack.yaml inventory.",
        },
        "summary": {
            "criticals": len(criticals),
            "warnings": len([d for d in diffs if d.severity == "warning"]),
            "by_kind": kind_counts(diffs),
            "by_source": source_counts(diffs),
        },
        "diffs": [
            {
                "severity": d.severity,
                "kind": d.kind,
                "source": d.source,
                "table": d.table,
                "column": d.column,
                "expected": d.expected,
                "actual": d.actual,
                "location": d.location,
                "suggested_fix": d.suggested_fix,
            }
            for d in diffs
        ],
        "resolution_protocol": [
            "Review each `diffs[]` entry. critical = real broken column reference; warning = documentation drift only.",
            "For critical drift in source=drift: rename the Drift column or its `.named()` alias to match live.",
            "For critical drift in source=ef: update the Edge Function `.select(...)` string and redeploy.",
            "For critical fk_target_drift: fix the Drift `.references()` target.",
            "For warning drift in source=doc: rerun this script with --no-bug to regenerate the doc.",
            "When resolved: set status: resolved + add resolution.commit + run /check-drift to confirm.",
        ],
        "tags": ["schema", "supabase", "drift", "auto"],
        "last_run": now,
    }

    bug_path.write_text(
        yaml.safe_dump(body, sort_keys=False, allow_unicode=True, width=1000),
        encoding="utf-8",
    )
    return bug_path


def kind_counts(diffs: list[Diff]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in diffs:
        out[d.kind] = out.get(d.kind, 0) + 1
    return out


def source_counts(diffs: list[Diff]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in diffs:
        out[d.source] = out.get(d.source, 0) + 1
    return out


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Doc regeneration (preserve <!-- KEEP --> blocks)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def extract_existing_keeps() -> tuple[str | None, dict[str, str]]:
    """Read existing supabase_schema.yaml (if any), return (file_keep, per_table_keep_map)."""
    if not SCHEMA_DOC.exists():
        return None, {}
    try:
        data = yaml.safe_load(SCHEMA_DOC.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return None, {}
    file_keep = data.get("keep")
    per_table: dict[str, str] = {}
    tables_node = data.get("tables") or {}
    if isinstance(tables_node, dict):
        for name, body in tables_node.items():
            if isinstance(body, dict) and body.get("keep"):
                per_table[str(name)] = body["keep"]
    return file_keep, per_table


def _yaml_inline_col(col: LiveColumn, fk: LiveFK | None) -> str:
    """Emit a column as an inline YAML mapping for compactness."""
    parts = [f"type: {col.data_type}"]
    if col.is_nullable:
        parts.append("nullable: true")
    if col.default:
        # Compact + escape single quotes
        d = col.default.replace("'", "''")
        if len(d) > 60:
            d = d[:57] + "..."
        parts.append(f"default: '{d}'")
    if fk:
        parts.append(f"fk: {fk.foreign_table}.{fk.foreign_column}")
    return "{ " + ", ".join(parts) + " }"


def regenerate_schema_yaml(live: LiveSchema, fk_lookup: dict[tuple[str, str], LiveFK]) -> None:
    """Regenerate knowledge/supabase_schema.yaml from live, preserving `keep:` blocks."""
    file_keep, per_table_keeps = extract_existing_keeps()
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    by_table: dict[str, list[LiveColumn]] = {}
    for c in live.columns:
        by_table.setdefault(c.table, []).append(c)

    out: list[str] = []
    out.append("# Postgres Schema (auto-generated)")
    out.append(f"# Regenerated by scripts/check_schema_drift.py on {now}")
    out.append("# DO NOT EDIT BY HAND except inside `keep:` blocks (file-level or per-table).")
    out.append("# `keep:` blocks survive regeneration and are the only place to add manual annotations.")
    out.append("")
    out.append(f"schema_version: '{dt.date.today().isoformat()}'")
    out.append(f"generated_at: '{now}'")
    out.append(f"tables_total: {len(by_table)}")
    out.append(f"columns_total: {len(live.columns)}")
    out.append(f"fks_total: {len(live.fks)}")

    if file_keep:
        out.append("")
        out.append("# Manual annotations preserved across regeneration:")
        out.append("keep: |")
        for line in str(file_keep).rstrip().split("\n"):
            out.append(f"  {line}")

    out.append("")
    out.append("tables:")

    for table in sorted(by_table.keys()):
        cols = by_table[table]
        out.append("")
        out.append(f"  {table}:")
        out.append("    columns:")
        # Right-pad column names so the inline mappings line up nicely
        max_name = max((len(c.column) for c in cols), default=0)
        for c in cols:
            fk = fk_lookup.get((table, c.column))
            inline = _yaml_inline_col(c, fk)
            out.append(f"      {c.column:<{max_name}}: {inline}")
        if table in per_table_keeps:
            out.append("    keep: |")
            for line in str(per_table_keeps[table]).rstrip().split("\n"):
                out.append(f"      {line}")

    out.append("")  # trailing newline
    SCHEMA_DOC.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_DOC.write_text("\n".join(out), encoding="utf-8")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Run log + PENDING_WORK update
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def append_run_log(diffs: list[Diff], doc_regenerated: bool, bug_path: Path | None) -> None:
    if not RUN_LOG.exists():
        return
    crits = sum(1 for d in diffs if d.severity == "critical")
    warns = sum(1 for d in diffs if d.severity == "warning")
    entry = (
        f"\n  - timestamp: {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}\n"
        f"    script: scripts/check_schema_drift.py\n"
        f"    criticals: {crits}\n"
        f"    warnings: {warns}\n"
        f"    doc_regenerated: {str(doc_regenerated).lower()}\n"
        f"    bug_file: {(str(bug_path.relative_to(PROJECT_ROOT)).replace(chr(92), '/') if bug_path else 'null')}\n"
    )
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(entry)


def update_pending_work(diffs: list[Diff], bug_path: Path | None) -> None:
    """Add or clear PENDING_WORK entry. Best-effort; no-op on parse failure."""
    if not PENDING_WORK.exists():
        return
    text = PENDING_WORK.read_text(encoding="utf-8")
    has_entry = "schema_drift_detected:" in text
    crits = sum(1 for d in diffs if d.severity == "critical")
    if crits == 0 and has_entry:
        # Mark as cleared â€” append a comment, don't try to splice yaml
        marker = (
            "\n# Schema drift cleared on "
            + dt.date.today().isoformat()
            + " â€” `schema_drift_detected` entry above is stale, can be removed.\n"
        )
        if marker.strip() not in text:
            PENDING_WORK.write_text(text + marker, encoding="utf-8")
    elif crits > 0 and not has_entry:
        appended = (
            "\n  schema_drift_detected:\n"
            f"    what: \"Live Supabase schema diverges from local codebase assumptions ({crits} critical diffs)\"\n"
            f"    status: open\n"
            f"    added: {dt.date.today().isoformat()}\n"
            f"    bug_file: {(str(bug_path.relative_to(PROJECT_ROOT)).replace(chr(92), '/') if bug_path else 'bugs/schema/')}\n"
            "    next_step: \"Read bug file, apply suggested_fix per diff, redeploy Edge Functions, rerun /check-drift\"\n"
        )
        # Insert under in_progress: heading
        if "in_progress:" in text:
            new_text = text.replace("in_progress:", "in_progress:" + appended, 1)
            PENDING_WORK.write_text(new_text, encoding="utf-8")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Main
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-cache", action="store_true", help="Force live schema fetch (skip 12h cache)")
    ap.add_argument("--quiet", action="store_true", help="Only emit output when drift detected")
    ap.add_argument("--no-doc", action="store_true", help="Skip regenerating knowledge/supabase_schema.yaml")
    ap.add_argument("--no-bug", action="store_true", help="Skip writing bug file")
    ap.add_argument("--json", action="store_true", help="Emit JSON summary to stdout")
    args = ap.parse_args()

    if not args.quiet:
        print("[check_schema_drift] fetching live schema...")
    live = fetch_live_schema(cache_ok=not args.no_cache)

    if not args.quiet:
        print(f"[check_schema_drift] live: {len(live.tables())} tables, {len(live.columns)} columns, {len(live.fks)} FKs")
        print("[check_schema_drift] parsing local sources...")

    drift = parse_drift_tables()
    efs = parse_edge_function_refs()
    docs = parse_schema_yaml()
    tech_funcs = parse_tech_stack_functions()
    local_funcs = list_local_functions()
    ignores = load_ignores()

    if not args.quiet:
        print(f"[check_schema_drift] drift tables: {len(drift)} | EF refs: {len(efs)} | doc tables: {len(docs)} | tech funcs: {len(tech_funcs)} | local funcs: {len(local_funcs)} | ignores: {len(ignores)}")

    diffs = diff_all(live, drift, efs, docs, tech_funcs, local_funcs, ignores)
    crits = [d for d in diffs if d.severity == "critical"]
    warns = [d for d in diffs if d.severity == "warning"]

    fk_lookup = {(f.table, f.column): f for f in live.fks}
    doc_regenerated = False
    if not args.no_doc:
        regenerate_schema_yaml(live, fk_lookup)
        doc_regenerated = True

    bug_path = None
    if not args.no_bug:
        bug_path = write_or_update_bug(diffs)

    append_run_log(diffs, doc_regenerated, bug_path)
    update_pending_work(diffs, bug_path)

    if args.json:
        print(json.dumps({
            "criticals": len(crits),
            "warnings": len(warns),
            "doc_regenerated": doc_regenerated,
            "bug_file": str(bug_path.relative_to(PROJECT_ROOT)).replace("\\", "/") if bug_path else None,
            "by_kind": kind_counts(diffs),
            "by_source": source_counts(diffs),
        }, indent=2))
    elif not args.quiet or diffs:
        print()
        print(f"[check_schema_drift] DONE â€” {len(crits)} critical, {len(warns)} warnings")
        if doc_regenerated:
            print(f"[check_schema_drift] regenerated: {SCHEMA_DOC.relative_to(PROJECT_ROOT)}")
        if bug_path:
            print(f"[check_schema_drift] bug file:    {bug_path.relative_to(PROJECT_ROOT)}")
        if crits:
            print()
            print("First 5 critical diffs:")
            for d in crits[:5]:
                print(f"  [{d.kind}] {d.table}.{d.column or '*'} ({d.source}) at {d.location}")
                if d.suggested_fix:
                    print(f"    fix: {d.suggested_fix}")

    return 1 if crits else 0


if __name__ == "__main__":
    sys.exit(main())
