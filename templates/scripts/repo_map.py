#!/usr/bin/env python3
"""
PACT Repo Map — Aider-style symbol map for AI coding agents.

Walks the codebase, extracts symbol definitions per file via tree-sitter,
builds an import-dependency graph, ranks files by personalized PageRank,
and emits a token-budgeted Markdown summary the agent can hold in context
to know "what exists" before deciding to build.

Inspired by https://aider.chat/docs/repomap.html. Uses tree-sitter-language-pack
for grammars and networkx for graph ranking. No embeddings, no API keys, fully
deterministic — regenerated whenever source files change.

Outputs:
  - knowledge/repo_map.md                   (LLM + human consumable)
  - plans/dashboard/data/repo_map.json      (graph data for dashboard viz)
  - plans/dashboard/data/repo_map_history.jsonl (append-only summary per build)

CLI:
  python scripts/repo_map.py build [--budget 2000] [--no-private] [--quiet]
  python scripts/repo_map.py status

═══════════════════════════════════════════════════════════════════════
PORTING TO OTHER PROJECTS — what to customize
═══════════════════════════════════════════════════════════════════════

This script is project-agnostic at the CORE (tree-sitter parsing, import
graph, PageRank, symbol extraction, class hierarchy, call graph), and
project-specific in the EXTRACTORS (drift_schema, edge_functions,
anomaly_catalog, etc.). Every project-specific extractor checks if its
target directory exists and returns {} if not — so on a fresh project,
the script runs cleanly and just doesn't populate project-specific fields.

Four customization points (top of this file):

1. LANG_FOR_EXT — file extension → tree-sitter language. Add languages
   as needed (e.g., ".rs": "rust", ".go": "go", ".java": "java").

2. INCLUDE_DIRS — directories to walk. Default: ["lib", "scripts",
   "supabase/functions"]. Replace with your project's source roots
   (e.g., ["src", "scripts", "tests"] for a typical web project).

3. DEF_NODE_TYPES — per-language tree-sitter node types that mark
   symbol definitions. Reference: each language's `node-types.json`.

4. file_kind() — classifies a file path into a kind string ("service",
   "screen", "widget", etc.) used by the dashboard for color-coding.
   Replace with patterns matching YOUR project's conventions.

The project-specific extractors (extract_drift_schema, extract_drift_migrations,
extract_supabase_migrations, extract_edge_function_actions,
extract_anomaly_catalog, extract_provider_caches, extract_cross_cutting_calls,
extract_static_data_maps, build_test_pairing) all gracefully no-op when
their target paths don't exist. Either delete them, replace with stack-
appropriate equivalents (e.g., extract_prisma_schema for Prisma projects),
or leave them as-is and they'll just emit empty maps.

The HEADER COMMENT below was preserved during the port (intentional —
it documents the original use case + serves as a reference for what
extracts looks like in practice). The project-specific bits below this
header degrade gracefully on any other project.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Where the dashboard scaffold lives. Most projects use plans/dashboard/;
# PACT itself uses templates/dashboard/ (the scaffold IS the deliverable).
# Probe in priority order; first one that contains _index.yaml wins.
def _find_dashboard_dir(root: Path) -> Path:
    for layout in ("plans/dashboard", "templates/dashboard"):
        candidate = root / layout
        if (candidate / "_index.yaml").is_file():
            return candidate
    return root / "plans" / "dashboard"

DASHBOARD_DIR = _find_dashboard_dir(PROJECT_ROOT)
OUTPUT_MD = PROJECT_ROOT / "knowledge" / "repo_map.md"
OUTPUT_JSON = DASHBOARD_DIR / "data" / "repo_map.json"
OUTPUT_HISTORY_JSONL = DASHBOARD_DIR / "data" / "repo_map_history.jsonl"
CACHE_FILE = PROJECT_ROOT / ".claude" / "cache" / "repo_map_parses.json"
DIRTY_FLAG = PROJECT_ROOT / ".claude" / "memory" / "repo_map_dirty"
EDIT_LOG = PROJECT_ROOT / ".claude" / "memory" / "file_edit_log.yaml"
FEATURE_FLOWS_DIR = PROJECT_ROOT / "feature_flows"
DRIFT_TABLE_DIR = PROJECT_ROOT / "lib" / "database" / "tables"

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

LANG_FOR_EXT = {
    ".dart": "dart",
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
}

# Dart import-resolution: replace with your project's package name if using
# Flutter/Dart. Used by resolve_import() to map `package:<your_pkg>/foo.dart`
# back to a `lib/foo.dart` path so the import-graph picks up cross-file edges.
# Non-Flutter projects: leave as-is — it just won't match anything.
DART_PACKAGE_PREFIX = "package:project/"

INCLUDE_DIRS = ["lib", "scripts", "supabase/functions"]

EXCLUDE_GLOBS = (
    ".dart_tool", "build", "node_modules", ".venv", "venv", "__pycache__",
    ".next", "dist", ".worktrees", "cutting_room",
)
EXCLUDE_SUFFIXES = (".g.dart", ".freezed.dart", ".mocks.dart", ".gr.dart")

MAX_FILE_BYTES = 500_000

# Per-language tree-sitter node types that mark symbol definitions.
DEF_NODE_TYPES = {
    "dart": {
        "class_definition": "class",
        "mixin_declaration": "mixin",
        "extension_declaration": "extension",
        "enum_declaration": "enum",
        "function_signature": "function",
        "method_signature": "method",
        "getter_signature": "getter",
        "setter_signature": "setter",
        "constructor_signature": "constructor",
        "factory_constructor_signature": "factory",
        "type_alias": "typedef",
    },
    "python": {
        "class_definition": "class",
        "function_definition": "function",
        "decorated_definition": "decorated",
    },
    "typescript": {
        "class_declaration": "class",
        "function_declaration": "function",
        "method_definition": "method",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
    },
    "tsx": {
        "class_declaration": "class",
        "function_declaration": "function",
        "method_definition": "method",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
    },
    "javascript": {
        "class_declaration": "class",
        "function_declaration": "function",
        "method_definition": "method",
    },
}


@dataclass
class Symbol:
    kind: str
    name: str
    signature: str
    line: int
    # Leading `///` (Dart) / `"""` (Python) / `/** */` (TS) doc-comment, first line only.
    # Empty string when no doc was found above the def. Surfaced in
    # repo_map.json so future Claude sessions can see what a class/method does
    # without opening the file.
    doc: str = ""


@dataclass
class FileInfo:
    path: str
    lang: str
    mtime: float
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    score: float = 0.0


def is_excluded(path: Path) -> bool:
    parts = set(path.parts)
    if parts & set(EXCLUDE_GLOBS):
        return True
    name = path.name
    return any(name.endswith(suf) for suf in EXCLUDE_SUFFIXES)


def discover_files() -> list[Path]:
    files: list[Path] = []
    for inc in INCLUDE_DIRS:
        base = PROJECT_ROOT / inc
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if is_excluded(p):
                continue
            if p.suffix.lower() not in LANG_FOR_EXT:
                continue
            try:
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            files.append(p)
    return files


def get_node_name(node) -> Optional[str]:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        try:
            return name_node.text.decode("utf-8", errors="replace")
        except Exception:
            return None
    for child in node.children:
        if child.type in ("identifier", "type_identifier"):
            try:
                return child.text.decode("utf-8", errors="replace")
            except Exception:
                continue
    # Dart wraps `static` / `final` modifiers around an inner signature node
    # (e.g. method_signature → function_signature for `static int detectMetro()`).
    # Recurse one level into wrapper children to find the inner identifier.
    for child in node.children:
        if child.type in (
            "function_signature", "method_signature", "getter_signature",
            "setter_signature", "constructor_signature", "factory_constructor_signature",
        ):
            inner = get_node_name(child)
            if inner:
                return inner
    return None


def _extract_leading_doc(src_lines: list[bytes], line_idx: int, lang: str) -> str:
    """
    Walk backwards from the def line to capture the leading doc comment.
    Dart:        consecutive `///` lines
    Python:      `\"\"\"...\"\"\"` block on the line(s) immediately above (or after the def)
    TS/JS:       `/** ... */` block above the def
    Returns the FIRST sentence of the doc (truncated to 200 chars), so future
    sessions get a one-line summary in repo_map.json without opening the file.
    """
    if line_idx <= 0 or line_idx > len(src_lines):
        return ""
    if lang == "dart":
        doc_lines: list[str] = []
        i = line_idx - 1
        while i >= 0:
            try:
                line = src_lines[i].decode("utf-8", errors="replace").strip()
            except Exception:
                break
            if line.startswith("///"):
                doc_lines.insert(0, line.lstrip("/").strip())
                i -= 1
                continue
            if line == "" or line.startswith("@"):
                # Skip blank lines + annotations between doc and def.
                i -= 1
                continue
            break
        if not doc_lines:
            return ""
        first = " ".join(s for s in doc_lines if s).strip()
        first = re.sub(r"\s+", " ", first)[:200]
        return first
    if lang in ("typescript", "tsx", "javascript"):
        # Look for `*/` on a line above; if found, walk back to the matching `/**`.
        i = line_idx - 1
        while i >= 0:
            try:
                line = src_lines[i].decode("utf-8", errors="replace").strip()
            except Exception:
                break
            if line == "":
                i -= 1
                continue
            if line.endswith("*/"):
                # Found end of block comment; walk back to /**
                end = i
                start = end
                while start >= 0:
                    try:
                        l = src_lines[start].decode("utf-8", errors="replace").strip()
                    except Exception:
                        break
                    if l.startswith("/**"):
                        break
                    start -= 1
                if start >= 0:
                    body = []
                    for j in range(start, end + 1):
                        try:
                            l = src_lines[j].decode("utf-8", errors="replace").strip()
                        except Exception:
                            continue
                        l = l.lstrip("/").lstrip("*").strip()
                        l = l.rstrip("/").rstrip("*").strip()
                        if l and not l.startswith("@"):  # skip JSDoc tags
                            body.append(l)
                    return re.sub(r"\s+", " ", " ".join(body))[:200]
                return ""
            break
        return ""
    if lang == "python":
        # Python doc-strings sit on the FIRST line(s) AFTER the def, not above.
        i = line_idx
        while i < len(src_lines):
            try:
                line = src_lines[i].decode("utf-8", errors="replace").strip()
            except Exception:
                return ""
            if line == "":
                i += 1
                continue
            if line.startswith('"""') or line.startswith("'''"):
                quote = line[:3]
                # Single-line docstring
                if line.endswith(quote) and len(line) > 6:
                    return line[3:-3].strip()[:200]
                # Multi-line — collect until closing quote
                body = [line[3:].strip()]
                i += 1
                while i < len(src_lines):
                    try:
                        l = src_lines[i].decode("utf-8", errors="replace")
                    except Exception:
                        break
                    if quote in l:
                        body.append(l.split(quote)[0].strip())
                        break
                    body.append(l.strip())
                    i += 1
                return re.sub(r"\s+", " ", " ".join(body).strip())[:200]
            return ""
        return ""
    return ""


def extract_symbols(root, src: bytes, lang: str, include_private: bool) -> list[Symbol]:
    types = DEF_NODE_TYPES.get(lang, {})
    if not types:
        return []
    src_lines = src.split(b"\n")
    out: list[Symbol] = []

    def add(node, kind: str):
        name = get_node_name(node)
        if not name:
            return
        if not include_private and name.startswith("_") and lang in ("dart", "typescript", "tsx", "javascript"):
            return
        line_idx = node.start_point[0]
        if 0 <= line_idx < len(src_lines):
            sig = src_lines[line_idx].decode("utf-8", errors="replace").strip()
            sig = re.sub(r"\s+", " ", sig)[:140]
        else:
            sig = name
        doc = _extract_leading_doc(src_lines, line_idx, lang)
        out.append(Symbol(kind=kind, name=name, signature=sig, line=line_idx + 1, doc=doc))

    def walk(node, depth=0):
        if depth > 60:
            return
        if node.type in types:
            kind = types[node.type]
            if kind == "decorated":
                # Python decorated_definition wraps a function/class. Pick the inner def.
                for c in node.children:
                    if c.type == "function_definition":
                        add(c, "function")
                    elif c.type == "class_definition":
                        add(c, "class")
            else:
                add(node, kind)
        for child in node.children:
            walk(child, depth + 1)

    walk(root)
    # Deduplicate by (name, line) — overload methods can produce duplicates.
    seen = set()
    deduped = []
    for s in out:
        key = (s.name, s.line)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(s)
    return deduped


def extract_imports(src: bytes, lang: str) -> list[str]:
    text = src.decode("utf-8", errors="replace")
    imports: list[str] = []
    if lang == "dart":
        for m in re.finditer(r"^\s*import\s+['\"]([^'\"]+)['\"]", text, re.MULTILINE):
            imports.append(m.group(1))
    elif lang == "python":
        for m in re.finditer(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", text, re.MULTILINE):
            mod = m.group(1) or m.group(2)
            if mod:
                imports.append(mod)
    elif lang in ("typescript", "tsx", "javascript"):
        for m in re.finditer(
            r"""^\s*(?:import\s+(?:.+?\s+from\s+)?|export\s+.+?\s+from\s+)['"]([^'"]+)['"]""",
            text, re.MULTILINE,
        ):
            imports.append(m.group(1))
    return imports


def parse_file(path: Path, include_private: bool) -> Optional[FileInfo]:
    from tree_sitter_language_pack import get_parser
    lang = LANG_FOR_EXT.get(path.suffix.lower())
    if not lang:
        return None
    try:
        src = path.read_bytes()
        mtime = path.stat().st_mtime
    except OSError:
        return None
    try:
        parser = get_parser(lang)
        tree = parser.parse(src)
    except Exception as e:
        print(f"  parse failed: {path.name}: {e}", file=sys.stderr)
        return None
    rel = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    return FileInfo(
        path=rel,
        lang=lang,
        mtime=mtime,
        symbols=extract_symbols(tree.root_node, src, lang, include_private),
        imports=extract_imports(src, lang),
    )


def resolve_import(imp: str, source_path: str, all_paths: set[str], lang: str) -> Optional[str]:
    if lang == "dart":
        if imp.startswith("dart:") or imp.startswith("package:flutter"):
            return None
        if imp.startswith(DART_PACKAGE_PREFIX):
            cand = "lib/" + imp[len(DART_PACKAGE_PREFIX):]
            return cand if cand in all_paths else None
        if imp.startswith("package:"):
            return None
        # relative
        try:
            base = (PROJECT_ROOT / source_path).parent
            cand = (base / imp).resolve().relative_to(PROJECT_ROOT)
            cand_str = str(cand).replace("\\", "/")
            return cand_str if cand_str in all_paths else None
        except Exception:
            return None
    if lang == "python":
        as_path = imp.replace(".", "/")
        for prefix in ("scripts/", "supabase/functions/", ""):
            for suf in (".py", "/__init__.py"):
                cand = f"{prefix}{as_path}{suf}"
                if cand in all_paths:
                    return cand
        return None
    if lang in ("typescript", "tsx", "javascript"):
        if not imp.startswith("."):
            return None
        try:
            base = (PROJECT_ROOT / source_path).parent
            target = (base / imp).resolve().relative_to(PROJECT_ROOT)
            target_str = str(target).replace("\\", "/")
            for suf in ("", ".ts", ".tsx", ".js", "/index.ts"):
                cand = target_str + suf
                if cand in all_paths:
                    return cand
        except Exception:
            return None
    return None


def load_cache() -> dict:
    if not CACHE_FILE.is_file():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")


def fileinfo_to_cache(fi: FileInfo) -> dict:
    return {
        "path": fi.path,
        "lang": fi.lang,
        "mtime": fi.mtime,
        "symbols": [s.__dict__ for s in fi.symbols],
        "imports": fi.imports,
    }


def fileinfo_from_cache(d: dict) -> FileInfo:
    return FileInfo(
        path=d["path"],
        lang=d["lang"],
        mtime=d["mtime"],
        symbols=[Symbol(**s) for s in d.get("symbols", [])],
        imports=list(d.get("imports", [])),
    )


def load_recent_edits() -> list[str]:
    if not EDIT_LOG.is_file():
        return []
    try:
        text = EDIT_LOG.read_text(encoding="utf-8")
    except Exception:
        return []
    edits = re.findall(r"-\s*path:\s*['\"]?([^'\"\n]+)['\"]?", text)
    out = []
    for e in edits[-30:]:
        e = e.strip().replace("\\", "/")
        if e:
            out.append(e)
    return out


def build_graph(files: list[FileInfo]):
    import networkx as nx
    g = nx.DiGraph()
    paths = {fi.path for fi in files}
    by_path = {fi.path: fi for fi in files}
    for fi in files:
        g.add_node(fi.path)
    for fi in files:
        for imp in fi.imports:
            target = resolve_import(imp, fi.path, paths, fi.lang)
            if target and target != fi.path:
                if g.has_edge(fi.path, target):
                    g[fi.path][target]["weight"] += 1
                else:
                    g.add_edge(fi.path, target, weight=1)
    return g


def rank_files(g, recent: list[str]) -> dict[str, float]:
    import networkx as nx
    personalization = None
    if recent:
        nodes = list(g.nodes())
        recent_set = set(recent)
        weights = {n: (3.0 if n in recent_set else 1.0) for n in nodes}
        total = sum(weights.values())
        personalization = {n: w / total for n, w in weights.items()}
    try:
        # In a dependency graph, importer → imported. PageRank flow goes to
        # popular shared modules. We want shared modules ranked high.
        scores = nx.pagerank(g, alpha=0.85, personalization=personalization, max_iter=100)
    except Exception:
        scores = {n: 1.0 / max(g.number_of_nodes(), 1) for n in g.nodes()}
    return scores


def file_kind(path: str) -> str:
    p = path.lower()
    if "/screens/" in p or "_screen.dart" in p:
        return "screen"
    if "/services/" in p or "_service.dart" in p or "_service.py" in p:
        return "service"
    if "/providers/" in p or "_provider.dart" in p:
        return "provider"
    if "/widgets/" in p or "_widget.dart" in p:
        return "widget"
    if "/models/" in p or "_model.dart" in p:
        return "model"
    if "/database/" in p:
        return "database"
    if path.startswith("scripts/"):
        return "script"
    if path.startswith("supabase/functions/"):
        return "edge_function"
    return "other"


def estimate_tokens(text: str) -> int:
    # ~4 chars per token, conservative
    return max(1, len(text) // 4)


def render_markdown(files: list[FileInfo], scores: dict[str, float], budget: int, file_to_flows: Optional[dict] = None) -> tuple[str, list[FileInfo]]:
    ordered = sorted(files, key=lambda fi: scores.get(fi.path, 0.0), reverse=True)
    header = (
        f"# Repo Map\n\n"
        f"_Auto-generated by [scripts/repo_map.py](scripts/repo_map.py) — DO NOT EDIT._\n"
        f"_Generated: {time.strftime('%Y-%m-%d %H:%M %Z')} • files scanned: {len(files)} • token budget: {budget}_\n\n"
        "This map shows the most central source files by import-graph PageRank "
        "(personalized by recent edits). Each section lists the public symbols "
        "the file defines. **Read this before declaring a feature 'doesn't exist'.**\n\n"
        "---\n\n"
    )
    out_parts: list[str] = [header]
    used = estimate_tokens(header)
    included: list[FileInfo] = []

    by_kind: dict[str, list[FileInfo]] = {}
    for fi in ordered:
        by_kind.setdefault(file_kind(fi.path), []).append(fi)

    KIND_ORDER = ["service", "provider", "screen", "widget", "model", "database", "edge_function", "script", "other"]
    for kind in KIND_ORDER:
        bucket = by_kind.get(kind, [])
        if not bucket:
            continue
        section = f"## {kind.replace('_', ' ').title()} ({len(bucket)})\n\n"
        if estimate_tokens(section) + used > budget:
            break
        out_parts.append(section)
        used += estimate_tokens(section)
        for fi in bucket:
            block = render_file_block(fi, scores.get(fi.path, 0.0), file_to_flows=file_to_flows)
            cost = estimate_tokens(block)
            if used + cost > budget:
                # Try a shorter form (top 3 symbols only)
                block = render_file_block(fi, scores.get(fi.path, 0.0), max_symbols=3, file_to_flows=file_to_flows)
                cost = estimate_tokens(block)
                if used + cost > budget:
                    continue
            out_parts.append(block)
            used += cost
            included.append(fi)

    out_parts.append(
        f"\n---\n_Truncated to fit budget. {len(files) - len(included)} of {len(files)} files not shown — "
        f"run `python scripts/repo_map.py build --budget 5000` to expand._\n"
    )
    return "".join(out_parts), included


def render_file_block(fi: FileInfo, score: float, max_symbols: int = 8, file_to_flows: Optional[dict] = None) -> str:
    if not fi.symbols:
        return ""
    name_only = fi.path.split("/")[-1]
    lines = [f"### {fi.path}  _(score {score:.4f})_\n"]
    flows_for_file = (file_to_flows or {}).get(fi.path, [])
    if flows_for_file:
        lines.append(f"_flows: {', '.join(flows_for_file)}_\n")
    syms = fi.symbols[:max_symbols]
    for s in syms:
        sig = s.signature.rstrip(" {").rstrip(":").strip()
        lines.append(f"- `{s.kind} {s.name}` — `{sig}` (L{s.line})")
    if len(fi.symbols) > max_symbols:
        lines.append(f"- _… +{len(fi.symbols) - max_symbols} more symbols_")
    lines.append("")
    return "\n".join(lines) + "\n"


def _extract_yaml_header_comments(raw_text: str) -> list:
    """
    Pull author-written comment lines from the top of a flow YAML file.

    PyYAML drops comments on parse; the dashboard's "Flows" cards want to
    surface the human prose the author wrote at the top of each flow file
    (the WHO/WHEN/WHY framing that's typically encoded as comments before
    the first key). We read the raw text and grab consecutive `# ...` lines
    from the top, stopping at the first non-comment, non-blank line.

    Returns a list of strings (one per comment line), with the leading `# `
    stripped and surrounding whitespace trimmed. Empty entries (`#`) are
    represented as empty strings so paragraph breaks survive.
    """
    out = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            # Strip leading `#` and one optional space.
            content = stripped[1:]
            if content.startswith(" "):
                content = content[1:]
            out.append(content)
            continue
        if stripped == "":
            # Allow blank lines between comment blocks.
            if out:
                out.append("")
            continue
        # First real key — stop.
        break
    # Trim trailing empties so we don't pad the UI.
    while out and out[-1] == "":
        out.pop()
    return out


def load_feature_flows() -> dict:
    """
    Read feature_flows/*.yaml and return:
      {
        flow_index: { flow_name: { participating_files, declared_dependencies, status, kind, ... } },
        file_to_flows: { file_path: [flow_names] }
      }
    Flows that don't parse cleanly are silently skipped (the validator handles
    those separately). Flows without participating_files contribute nothing.

    PROJECT-AGNOSTIC NOTE: this loader reads YAML files in a fixed schema
    (purpose, triggers, invariants, states, lifecycle, participating_files,
    declared_dependencies, flow_kind). The schema is documented in
    feature_flows/CLAUDE.md and skills/feature_flow_authoring.yaml. To adapt
    PACT to a different project, keep the same schema in your flow YAMLs —
    the dashboard reads JSON, not YAML, so any tool that produces equivalent
    JSON via repo_map.py's render_json() works.
    """
    try:
        import yaml
    except ImportError:
        return {"flow_index": {}, "file_to_flows": {}}

    flow_index: dict[str, dict] = {}
    file_to_flows: dict[str, list[str]] = {}

    if not FEATURE_FLOWS_DIR.is_dir():
        return {"flow_index": {}, "file_to_flows": {}}

    for path in sorted(FEATURE_FLOWS_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        flow_name = re.sub(r"_flow$", "", path.stem)
        try:
            raw_text = path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw_text)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        # Extract human-written framing comments from the top of the file.
        # These are the "why this flow exists" notes the author left as YAML
        # comments — the dashboard surfaces them so users don't have to open
        # the file to read them.
        author_notes = _extract_yaml_header_comments(raw_text)
        pfs = data.get("participating_files") or []
        if not isinstance(pfs, list):
            continue
        norm_pfs = []
        for p in pfs:
            if isinstance(p, str):
                np = p.replace("\\", "/")
                norm_pfs.append(np)
                file_to_flows.setdefault(np, []).append(flow_name)

        deps_raw = data.get("declared_dependencies") or []
        deps: list[dict] = []
        if isinstance(deps_raw, list):
            for d in deps_raw:
                if not isinstance(d, dict):
                    continue
                target = d.get("depends_on") or d.get("communicates_with") or d.get("consumes")
                if not target:
                    continue
                deps.append({
                    "target": target,
                    "kind": d.get("kind", "depends_on"),
                    "via": list(d.get("via") or []),
                    "purpose": d.get("purpose", ""),
                })

        # Surface the WHO / WHAT / WHEN / WHERE / WHY context that lives in
        # the flow YAML so the dashboard's Flows view can answer those
        # questions per card without making the user open the YAML.
        # Each field is normalized to a JSON-safe shape (string or list of
        # strings) for the dashboard to consume directly.

        def _to_str_list(val) -> list:
            if val is None: return []
            if isinstance(val, list):
                return [str(x) for x in val if x is not None]
            if isinstance(val, str):
                return [val]
            return [str(val)]

        # WHEN this flow fires (entry triggers).
        triggers_field = data.get("triggers") or data.get("entry_points") or []
        triggers = _to_str_list(triggers_field)

        # WHAT must always be true (architectural promises this flow makes).
        invariants = _to_str_list(data.get("invariants") or [])

        # WHERE the user lands at each life-cycle stage. Some flows use
        # `states:` (named-state map) and others use `lifecycle:` (numbered
        # ordered steps). We expose just the state NAMES so the card can
        # show "this flow has lifecycle states: fresh_install, normal_open,
        # error_paths" without dumping every step.
        states_summary: list = []
        states_obj = data.get("states") or {}
        if isinstance(states_obj, dict):
            states_summary = list(states_obj.keys())
        lifecycle = data.get("lifecycle")
        if not states_summary and isinstance(lifecycle, list):
            # If lifecycle is a numbered list, surface the count rather than
            # individual step names (which are usually full sentences).
            states_summary = [f"{len(lifecycle)} ordered lifecycle steps"]

        # WHY this flow exists at the high level — author commentary written
        # near the top of the YAML, plus the longer-form description if any.
        # We keep both because they answer different questions: `purpose` is
        # the elevator pitch; `description` is the rationale.
        purpose = data.get("purpose")
        if isinstance(purpose, str):
            purpose = purpose.strip()
        else:
            purpose = ""
        description = data.get("description")
        if isinstance(description, str):
            description = description.strip()
        else:
            description = ""

        flow_index[flow_name] = {
            "name": flow_name,
            "file": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "purpose": purpose,                    # WHAT (one-line capability statement)
            "description": description,            # WHY (longer rationale, optional)
            "flow_kind": data.get("flow_kind", "feature"),  # WHO (feature / cross-cutting / infrastructure)
            "triggers": triggers,                  # WHEN (what kicks off this flow)
            "invariants": invariants,              # WHAT-MUST-BE-TRUE (architectural promises)
            "invariant_count": len(invariants),
            "lifecycle_states": states_summary,    # WHERE (named lifecycle phases)
            "participating_files": norm_pfs,       # WHERE (which code files implement this)
            "declared_dependencies": deps,         # CONTRACTS WITH OTHER FLOWS
            "author_notes": author_notes,          # AUTHOR FRAMING (raw # ... comments from top of file)
        }

    return {"flow_index": flow_index, "file_to_flows": file_to_flows}


def compute_drift_report(
    files: list[FileInfo],
    scores: dict[str, float],
    graph,
    flow_data: dict,
    file_to_symbols: dict[str, set[str]],
) -> dict:
    """
    Compute the four drift signals defined in the unification plan. The result
    feeds both repo_map.json's drift_report field and the dashboard's Drift
    sub-tab.

    Signals:
      1. orphaned_high_centrality_files: top-25-percentile-by-rank files that
         appear in no feature_flow. These are candidates for adoption.
      2. claimed_files_missing_in_repo: flow.participating_files entries that
         don't resolve to any node in the structural map.
      3. undocumented_cross_flow_imports: edges (importer -> importee) where
         the two endpoints belong to different flows AND no declared_dependency
         covers the relationship.
      4. broken_declared_dependencies: declared_dependency targets that don't
         resolve to a known flow (subsystem-stub or real flow), OR `via:`
         symbols that don't exist in the target's symbol set.
    """
    flow_index = flow_data.get("flow_index", {}) or {}
    file_to_flows = flow_data.get("file_to_flows", {}) or {}

    repo_paths = {fi.path for fi in files}

    # ── 1. orphaned_high_centrality_files ──
    sorted_files = sorted(files, key=lambda fi: scores.get(fi.path, 0.0), reverse=True)
    cutoff = max(1, len(sorted_files) // 4)  # top 25%
    orphans: list[dict] = []
    for fi in sorted_files[:cutoff]:
        if fi.path not in file_to_flows:
            # Suggest the flow whose noun has the highest overlap with this file's basename
            basename = fi.path.rsplit("/", 1)[-1].lower()
            best_flow = None
            best_score = 0
            for flow_name in flow_index:
                fn_l = flow_name.lower()
                hits = 0
                for part in fn_l.split("_"):
                    if len(part) >= 3 and part in basename:
                        hits += 1
                if hits > best_score:
                    best_score = hits
                    best_flow = flow_name
            orphans.append({
                "path": fi.path,
                "rank": next(i + 1 for i, x in enumerate(sorted_files) if x.path == fi.path),
                "score": round(scores.get(fi.path, 0.0), 6),
                "kind": file_kind(fi.path),
                "importer_count": graph.in_degree(fi.path) if graph.has_node(fi.path) else 0,
                "suggested_flow": best_flow if best_score > 0 else None,
            })

    # ── 2. claimed_files_missing_in_repo ──
    missing: list[dict] = []
    for flow_name, info in flow_index.items():
        for p in info.get("participating_files", []):
            if p not in repo_paths:
                missing.append({"flow": flow_name, "missing_path": p})

    # ── 3. undocumented_cross_flow_imports ──
    # Index declared dependencies for fast lookup: (from_flow, to_flow) -> True
    declared_pairs: set[tuple[str, str]] = set()
    for flow_name, info in flow_index.items():
        for d in info.get("declared_dependencies", []):
            tgt = d.get("target")
            if tgt:
                # Strip _flow suffix from target if present
                tgt_canon = re.sub(r"_flow$", "", str(tgt))
                declared_pairs.add((flow_name, tgt_canon))

    cross_flow: list[dict] = []
    for u, v, d in graph.edges(data=True):
        u_flows = file_to_flows.get(u, [])
        v_flows = file_to_flows.get(v, [])
        if not u_flows or not v_flows:
            continue
        # An edge is "cross-flow" if there's no flow shared between u and v
        shared = set(u_flows) & set(v_flows)
        if shared:
            continue
        # Check if any declared_dependency between u_flows and v_flows covers this
        covered = False
        for fa in u_flows:
            for fb in v_flows:
                if (fa, fb) in declared_pairs:
                    covered = True
                    break
            if covered:
                break
        if not covered:
            cross_flow.append({
                "from_flow": u_flows[0] if len(u_flows) == 1 else u_flows,
                "to_flow":   v_flows[0] if len(v_flows) == 1 else v_flows,
                "from_file": u,
                "to_file":   v,
                "weight":    d.get("weight", 1),
            })

    # Aggregate cross_flow by (from_flow, to_flow) for summary
    cross_flow_aggregated: dict[tuple, dict] = {}
    for c in cross_flow:
        ff = tuple(c["from_flow"]) if isinstance(c["from_flow"], list) else (c["from_flow"],)
        tf = tuple(c["to_flow"]) if isinstance(c["to_flow"], list) else (c["to_flow"],)
        for f in ff:
            for t in tf:
                key = (f, t)
                if key not in cross_flow_aggregated:
                    cross_flow_aggregated[key] = {"from_flow": f, "to_flow": t, "edges": [], "edge_count": 0}
                cross_flow_aggregated[key]["edges"].append({"from_file": c["from_file"], "to_file": c["to_file"]})
                cross_flow_aggregated[key]["edge_count"] += 1

    # ── 4. broken_declared_dependencies ──
    known_flow_names = set(flow_index.keys())
    KNOWN_SUBSYSTEMS = {"supabase", "drift", "platform", "sentry", "stadia", "overture", "freerasp", "stripe", "google_play"}
    broken: list[dict] = []
    for flow_name, info in flow_index.items():
        deps = info.get("declared_dependencies", [])
        for d in deps:
            tgt = d.get("target")
            if not tgt:
                continue
            tgt_canon = re.sub(r"_flow$", "", str(tgt))
            if tgt_canon not in known_flow_names and tgt_canon not in KNOWN_SUBSYSTEMS:
                broken.append({
                    "flow": flow_name,
                    "target": str(tgt),
                    "issue": "target_not_found",
                    "detail": f"'{tgt}' is neither a feature_flow nor a recognized subsystem",
                })
                continue
            via = d.get("via", []) or []
            if via and tgt_canon in flow_index:
                target_pfs = flow_index[tgt_canon].get("participating_files", [])
                target_symbols: set[str] = set()
                for tp in target_pfs:
                    target_symbols.update(file_to_symbols.get(tp, set()))
                missing_syms = [s for s in via if isinstance(s, str) and s.lower() not in target_symbols]
                if missing_syms and target_symbols:
                    broken.append({
                        "flow": flow_name,
                        "target": str(tgt),
                        "issue": "via_symbol_not_found",
                        "missing_symbols": missing_syms,
                        "detail": f"declared via [{', '.join(missing_syms)}] not found in {tgt_canon}'s top_symbols",
                    })

    # ── per-flow drift status (rolled up) ──
    per_flow_status: dict[str, dict] = {}
    for flow_name in flow_index:
        cnt_orphans_suggested = sum(1 for o in orphans if o.get("suggested_flow") == flow_name)
        cnt_missing = sum(1 for m in missing if m["flow"] == flow_name)
        cnt_undoc = sum(1 for k, v in cross_flow_aggregated.items() if k[0] == flow_name)
        cnt_broken = sum(1 for b in broken if b["flow"] == flow_name)
        if cnt_broken or cnt_missing:
            status = "red"
        elif cnt_undoc:
            status = "amber"
        elif cnt_orphans_suggested:
            status = "info"
        else:
            status = "green"
        per_flow_status[flow_name] = {
            "status": status,
            "orphans_suggested": cnt_orphans_suggested,
            "claimed_files_missing": cnt_missing,
            "undocumented_cross_flow_imports": cnt_undoc,
            "broken_declared_dependencies": cnt_broken,
        }

    return {
        "summary": {
            "orphaned_high_centrality_files": len(orphans),
            "claimed_files_missing_in_repo": len(missing),
            "undocumented_cross_flow_pairs": len(cross_flow_aggregated),
            "broken_declared_dependencies": len(broken),
            "flows_red": sum(1 for s in per_flow_status.values() if s["status"] == "red"),
            "flows_amber": sum(1 for s in per_flow_status.values() if s["status"] == "amber"),
            "flows_info": sum(1 for s in per_flow_status.values() if s["status"] == "info"),
            "flows_green": sum(1 for s in per_flow_status.values() if s["status"] == "green"),
        },
        "orphaned_high_centrality_files": orphans[:50],
        "claimed_files_missing_in_repo": missing,
        "undocumented_cross_flow_imports": list(cross_flow_aggregated.values())[:80],
        "broken_declared_dependencies": broken,
        "per_flow_status": per_flow_status,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Drift schema extractor (Phase 1 of system_map_decomposition_plan.yaml)
# Replaces SYSTEM_MAP.yaml's hand-narrated cascade_on_delete fields,
# entity_relationships block, and per-section foreign-key prose.
# ─────────────────────────────────────────────────────────────────────────────

DRIFT_TYPE_TO_SQL = {
    "IntColumn": "INTEGER",
    "TextColumn": "TEXT",
    "BoolColumn": "BOOLEAN",
    "DateTimeColumn": "DATETIME",
    "RealColumn": "REAL",
    "BlobColumn": "BLOB",
    "Int64Column": "BIGINT",
}

DRIFT_CLASS_RX = re.compile(r"class\s+(\w+)\s+extends\s+Table\b")
DATACLASS_NAME_RX = re.compile(r"@DataClassName\(\s*['\"]([^'\"]+)['\"]")
DRIFT_COLUMN_RX = re.compile(
    r"(IntColumn|TextColumn|BoolColumn|DateTimeColumn|RealColumn|BlobColumn|Int64Column)"
    r"\s+get\s+(\w+)\s*=>\s*",
)
REFERENCES_RX = re.compile(
    r"\.references\(\s*(\w+)\s*,\s*#(\w+)(?:\s*,\s*onDelete:\s*KeyAction\.(\w+))?",
)
WITH_DEFAULT_RX = re.compile(r"\.withDefault\(\s*(.+?)\s*\)\s*\(", re.DOTALL)
PRIMARY_KEY_RX = re.compile(
    r"Set<Column>\s+get\s+primaryKey\s*=>\s*\{([^}]+)\}",
)


def _pascal_to_snake(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _extract_column_chain(text: str, start: int) -> str:
    """
    From offset `start` (just past `=>`), grab the chained Drift expression
    up to the terminating `;` at paren-depth 0. Drift columns end like
    `()();` — nested parens are respected.
    """
    depth = 0
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == ";" and depth == 0:
            return text[start:i]
        i += 1
    return text[start:i]


def _parse_drift_table(file_path: Path, raw: str) -> Optional[dict]:
    cls_m = DRIFT_CLASS_RX.search(raw)
    if not cls_m:
        return None
    class_name = cls_m.group(1)

    # @DataClassName('Foo') annotation typically sits immediately above the class.
    dc_m = DATACLASS_NAME_RX.search(raw[: cls_m.start()])
    data_class_name = dc_m.group(1) if dc_m else None

    columns: list[dict] = []
    foreign_keys: list[dict] = []

    for m in DRIFT_COLUMN_RX.finditer(raw):
        col_type = m.group(1)
        col_name = m.group(2)
        chain = _extract_column_chain(raw, m.end())

        nullable = ".nullable()" in chain
        unique = ".unique()" in chain
        auto_increment = ".autoIncrement()" in chain

        default_val: Optional[str] = None
        wd_m = WITH_DEFAULT_RX.search(chain + "(")  # sentinel so terminator matches
        if wd_m:
            default_val = re.sub(r"\s+", " ", wd_m.group(1)).strip()

        ref_m = REFERENCES_RX.search(chain)
        if ref_m:
            foreign_keys.append({
                "from_column": col_name,
                "to_table": ref_m.group(1),
                "to_column": ref_m.group(2),
                "on_delete": ref_m.group(3) or "noAction",
                "nullable": nullable,
            })

        columns.append({
            "name": col_name,
            "dart_type": col_type,
            "sql_type": DRIFT_TYPE_TO_SQL.get(col_type, "UNKNOWN"),
            "nullable": nullable,
            "unique": unique,
            "auto_increment": auto_increment,
            "default": default_val,
        })

    pk_m = PRIMARY_KEY_RX.search(raw)
    primary_key: list[str] = []
    if pk_m:
        primary_key = [s.strip() for s in pk_m.group(1).split(",") if s.strip()]
    else:
        # Implicit primary key: any column with autoIncrement().
        for c in columns:
            if c["auto_increment"]:
                primary_key = [c["name"]]
                break

    return {
        "class_name": class_name,
        "sql_name": _pascal_to_snake(class_name),
        "data_class_name": data_class_name,
        "file": str(file_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "columns": columns,
        "foreign_keys": foreign_keys,
        "primary_key": primary_key,
    }


def extract_drift_schema() -> dict:
    """
    Walk lib/database/tables/*.dart and emit a structured schema map.

    Output shape:
      {
        "<ClassName>": {
          "class_name":      "<dart class name>",
          "sql_name":        "<snake_case sql table name>",
          "data_class_name": "<from @DataClassName(...) or null>",
          "file":            "<rel path>",
          "columns":         [{name, dart_type, sql_type, nullable, unique, auto_increment, default}],
          "foreign_keys":    [{from_column, to_table, to_column, on_delete, nullable}],
          "primary_key":     ["col_name", ...]
        }
      }

    Replaces SYSTEM_MAP.yaml's hand-narrated cascade_on_delete + entity_relationships +
    per-section fk prose. Truth is now the .dart file.

    PROJECT-AGNOSTIC NOTE: this is Drift-specific. For a port targeting another ORM,
    write a sibling extractor (e.g. extract_prisma_schema, extract_sqlalchemy_schema)
    that emits the same JSON shape — the dashboard renders whatever it gets.
    """
    if not DRIFT_TABLE_DIR.is_dir():
        return {}
    out: dict = {}
    for p in sorted(DRIFT_TABLE_DIR.glob("*.dart")):
        try:
            raw = p.read_text(encoding="utf-8")
        except OSError:
            continue
        parsed = _parse_drift_table(p, raw)
        if parsed:
            out[parsed["class_name"]] = parsed
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Migration history extractor (Phase 1.2 of system_map_decomposition_plan.yaml)
# Replaces SYSTEM_MAP.yaml's database.recent_migrations + per-section
# supabase_columns_added narratives + perception_signals.aggregation.cron_job.
# ─────────────────────────────────────────────────────────────────────────────

APP_DB_FILE = PROJECT_ROOT / "lib" / "database" / "app_database.dart"
SUPABASE_MIG_DIR = PROJECT_ROOT / "supabase" / "migrations"


def _walk_braces(text: str, start: int) -> int:
    """Return index of the matching close-brace for the open-brace at start-1."""
    depth = 1
    i = start
    n = len(text)
    while i < n and depth > 0:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return i


def extract_drift_migrations() -> dict:
    """
    Parse the `onUpgrade` switch in lib/database/app_database.dart.

    Returns:
      {
        "schema_version": <int>,
        "migrations": [
          { "version": <int>, "description": "<from leading comment>",
            "operations": [ { "op": "create_table"|"drop_table"|"add_column"|"drop_column"|"custom_sql", ... } ] }
        ]
      }
    """
    if not APP_DB_FILE.is_file():
        return {}
    text = APP_DB_FILE.read_text(encoding="utf-8")

    sv_m = re.search(r"int\s+get\s+schemaVersion\s*=>\s*(\d+)", text)
    schema_version = int(sv_m.group(1)) if sv_m else None

    upgrade_m = re.search(r"onUpgrade:\s*\([^)]*\)\s*async\s*\{", text)
    if not upgrade_m:
        return {"schema_version": schema_version, "migrations": []}

    body_start = upgrade_m.end()
    body_end = _walk_braces(text, body_start)
    body = text[body_start:body_end]

    migrations: list[dict] = []
    # Find each `if (from < N) {` block and walk its body.
    for m in re.finditer(r"if\s*\(\s*from\s*<\s*(\d+)\s*\)\s*\{", body):
        version = int(m.group(1))
        block_start = m.end()
        block_end = _walk_braces(body, block_start)
        block = body[block_start:block_end]

        # Description: leading `// ...` comment lines until the first non-comment.
        desc_parts: list[str] = []
        for line in block.split("\n"):
            s = line.strip()
            if s.startswith("//"):
                desc_parts.append(s.lstrip("/").strip())
            elif s == "":
                continue
            else:
                break
        description = " ".join(p for p in desc_parts if p).strip()

        ops: list[dict] = []
        for cm in re.finditer(r"m\.createTable\(\s*(\w+)", block):
            ops.append({"op": "create_table", "target": cm.group(1)})
        for cm in re.finditer(r"_createTableIfNotExists\(\s*m\s*,\s*(\w+)", block):
            ops.append({"op": "create_table", "target": cm.group(1), "idempotent": True})
        for dm in re.finditer(r"m\.deleteTable\(\s*['\"]([^'\"]+)['\"]", block):
            ops.append({"op": "drop_table", "target": dm.group(1)})
        for am in re.finditer(r"m\.addColumn\(\s*(\w+)\s*,\s*\w+\.(\w+)", block):
            ops.append({"op": "add_column", "target": am.group(1), "column": am.group(2)})
        for am in re.finditer(
            r"_addColumnIfNotExists\(\s*m\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]",
            block,
        ):
            ops.append({"op": "add_column", "target": am.group(1), "column": am.group(2), "idempotent": True})
        for dm in re.finditer(
            r"_dropColumnIfExists\(\s*m\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]",
            block,
        ):
            ops.append({"op": "drop_column", "target": dm.group(1), "column": dm.group(2), "idempotent": True})
        # Raw SQL: customStatement('...') OR m.database.customStatement('...')
        for sm in re.finditer(
            r"customStatement\(\s*['\"]([^'\"]+)['\"]",
            block,
        ):
            ops.append({"op": "custom_sql", "sql": sm.group(1)[:200]})
        # Multi-line concatenated customStatement (joined string literals)
        for sm in re.finditer(
            r"customStatement\(\s*\n((?:\s*['\"][^'\"]*['\"]\s*\n?)+)",
            block,
        ):
            joined = re.sub(r"['\"]", "", sm.group(1))
            joined = re.sub(r"\s+", " ", joined).strip()
            if joined and not any(o.get("sql") == joined[:200] for o in ops):
                ops.append({"op": "custom_sql", "sql": joined[:200]})

        migrations.append({
            "version": version,
            "description": description,
            "operations": ops,
        })

    return {"schema_version": schema_version, "migrations": migrations}


def extract_supabase_migrations() -> list:
    """
    Walk supabase/migrations/*.sql in filename order and extract operations.

    Returns:
      [
        { "filename": "<sql file>", "description": "<from leading -- comments>",
          "operations": [ { "op": "create_table"|"add_column"|"drop_column"|"create_function"|"create_trigger"|"create_index"|"schedule_cron", ... } ] }
      ]
    """
    if not SUPABASE_MIG_DIR.is_dir():
        return []
    out: list[dict] = []
    for p in sorted(SUPABASE_MIG_DIR.glob("*.sql")):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue

        # Header: first contiguous block of `--` lines, skipping decorative lines.
        desc_parts: list[str] = []
        for line in text.split("\n"):
            s = line.strip()
            if s.startswith("--"):
                cleaned = s.lstrip("-").strip()
                if cleaned and not re.fullmatch(r"[=\-─]+", cleaned):
                    desc_parts.append(cleaned)
            elif s == "":
                if desc_parts and len(desc_parts) >= 3:
                    break
                continue
            else:
                break
        description = " | ".join(desc_parts[:3])[:300]

        ops: list[dict] = []
        for m in re.finditer(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z_][a-z0-9_]*)",
            text, re.IGNORECASE,
        ):
            ops.append({"op": "create_table", "target": m.group(1)})
        for m in re.finditer(
            r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?([a-z_][a-z0-9_]*)\s+ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z_][a-z0-9_]*)",
            text, re.IGNORECASE,
        ):
            ops.append({"op": "add_column", "target": m.group(1), "column": m.group(2)})
        for m in re.finditer(
            r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?([a-z_][a-z0-9_]*)\s+DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?([a-z_][a-z0-9_]*)",
            text, re.IGNORECASE,
        ):
            ops.append({"op": "drop_column", "target": m.group(1), "column": m.group(2)})
        for m in re.finditer(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([a-zA-Z_][a-zA-Z0-9_.]*)",
            text, re.IGNORECASE,
        ):
            ops.append({"op": "create_function", "target": m.group(1)})
        for m in re.finditer(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+([a-z_][a-z0-9_]*)",
            text, re.IGNORECASE,
        ):
            ops.append({"op": "create_trigger", "target": m.group(1)})
        for m in re.finditer(
            r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?([a-z_][a-z0-9_]*)\s+ON\s+(?:public\.)?([a-z_][a-z0-9_]*)",
            text, re.IGNORECASE,
        ):
            ops.append({"op": "create_index", "name": m.group(1), "target": m.group(2)})
        # cron.schedule('job_name', 'cron_expr', $$body$$)
        for m in re.finditer(
            r"cron\.schedule\(\s*'([^']+)'\s*,\s*'([^']+)'",
            text,
        ):
            ops.append({"op": "schedule_cron", "name": m.group(1), "schedule": m.group(2)})

        out.append({
            "filename": p.name,
            "description": description,
            "operations": ops,
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Edge Function action extractor (Phase 1.3 of system_map_decomposition_plan.yaml)
# Replaces SYSTEM_MAP.yaml's per-section "edge_function: 'name (action1, ...)'"
# narratives, supabase_secrets fields, supabase_buckets / supabase_buckets_read
# fields, perception_signals.scheduled_function, safety_scan.scan_providers,
# cybertipline_reporting.external_api.
# ─────────────────────────────────────────────────────────────────────────────

EDGE_FN_DIR = PROJECT_ROOT / "supabase" / "functions"

# Common Deno / external libs we DON'T want flagged as "external API call"
KNOWN_DENO_HOSTS = {
    "deno.land", "esm.sh", "cdn.jsdelivr.net", "raw.githubusercontent.com",
}


def _parse_edge_function_file(path: Path) -> Optional[dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    # ── actions ──
    actions: list[str] = []
    seen: set[str] = set()

    # Pattern A: `switch (action) { case "name": ... }`
    sw_m = re.search(r"switch\s*\(\s*action\s*\)\s*\{", text)
    if sw_m:
        body_end = _walk_braces(text, sw_m.end())
        body = text[sw_m.end():body_end]
        for cm in re.finditer(r'case\s+["\']([^"\']+)["\']\s*:', body):
            name = cm.group(1)
            if name not in seen:
                seen.add(name)
                actions.append(name)

    # Pattern B: `if (action === "name") ... else if (action === "name") ...`
    for m in re.finditer(r'action\s*===?\s*["\']([^"\']+)["\']', text):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            actions.append(name)

    # Pattern C: object dispatch table — `const handlers = { name: handlerFn, ... }`
    handler_obj = re.search(
        r"(?:const|let|var)\s+(?:actionHandlers|handlers|routes)\s*[:=]\s*\{",
        text,
    )
    if handler_obj:
        body_end = _walk_braces(text, handler_obj.end())
        body = text[handler_obj.end():body_end]
        for km in re.finditer(r'(?:^|,)\s*["\']?([a-zA-Z_][a-zA-Z0-9_]*)["\']?\s*:', body):
            name = km.group(1)
            if name not in seen and len(name) >= 3:
                seen.add(name)
                actions.append(name)

    # ── secrets (Deno.env.get) ──
    secrets: list[str] = []
    secrets_seen: set[str] = set()
    for m in re.finditer(r'Deno\.env\.get\(\s*["\']([A-Z][A-Z0-9_]*)["\']', text):
        s = m.group(1)
        if s not in secrets_seen:
            secrets_seen.add(s)
            secrets.append(s)

    # ── buckets (storage.from) ──
    # Real code splits the chain across lines:
    #   supabase.storage
    #     .from("seed-data")
    # so we allow whitespace/newlines between `.storage` and `.from(`.
    buckets: list[str] = []
    buckets_seen: set[str] = set()
    for m in re.finditer(r'\.storage\s*\.from\(\s*["\']([^"\']+)["\']', text, re.DOTALL):
        b = m.group(1)
        if b not in buckets_seen:
            buckets_seen.add(b)
            buckets.append(b)

    # ── RPC calls ──
    rpcs: list[str] = []
    rpcs_seen: set[str] = set()
    for m in re.finditer(r'\.rpc\(\s*["\']([a-z_][a-z0-9_]*)["\']', text):
        r = m.group(1)
        if r not in rpcs_seen:
            rpcs_seen.add(r)
            rpcs.append(r)

    # ── external API hosts (best-effort: extract https://host/... literals) ──
    external_hosts: list[str] = []
    hosts_seen: set[str] = set()
    for m in re.finditer(r'["\']https?://([a-zA-Z0-9.\-]+)(?::\d+)?(?:/[^"\']*)?["\']', text):
        host = m.group(1).lower()
        if host in KNOWN_DENO_HOSTS:
            continue
        if host.endswith(".supabase.co"):
            continue
        if host not in hosts_seen:
            hosts_seen.add(host)
            external_hosts.append(host)

    # ── tables read/written (best-effort: .from('table') NOT followed by .storage) ──
    tables_seen: set[str] = set()
    for m in re.finditer(r'(?<!storage)\.from\(\s*["\']([a-z_][a-z0-9_]*)["\']', text):
        tables_seen.add(m.group(1))

    return {
        "name": path.parent.name,
        "file": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "actions": actions,
        "secrets": secrets,
        "buckets": buckets,
        "rpcs": rpcs,
        "external_hosts": external_hosts,
        "tables_referenced": sorted(tables_seen),
    }


def extract_edge_function_actions() -> dict:
    """
    Walk supabase/functions/*/index.ts and emit per-function:
      actions, secrets, buckets, RPCs, external API hosts, tables referenced.

    Replaces SYSTEM_MAP.yaml's per-section edge_function action lists,
    supabase_secrets, supabase_buckets, external_api fields.
    """
    if not EDGE_FN_DIR.is_dir():
        return {}
    out: dict = {}
    for fn_dir in sorted(EDGE_FN_DIR.iterdir()):
        if not fn_dir.is_dir() or fn_dir.name.startswith("_"):
            continue
        idx = fn_dir / "index.ts"
        if not idx.is_file():
            continue
        parsed = _parse_edge_function_file(idx)
        if parsed:
            out[parsed["name"]] = parsed
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Anomaly catalog extractor (Phase 1.4 of system_map_decomposition_plan.yaml)
# Replaces SYSTEM_MAP.yaml's anomaly_detection.instrumented map.
# ─────────────────────────────────────────────────────────────────────────────

ANOMALY_REPORTER_FILE = PROJECT_ROOT / "lib" / "utils" / "app_anomaly_reporter.dart"


def extract_anomaly_catalog() -> dict:
    """
    Build a catalog of all canonical anomaly types + their callsites.

    Returns:
      {
        "<string_id e.g. seed.zero_places>": {
          "constant_name": "<Dart const name e.g. seedZeroPlaces>",
          "category":      "<part before the dot e.g. seed>",
          "description":   "<leading /// comment from app_anomaly_reporter.dart>",
          "callsites":     [{"file": "<rel-path>", "line": <int>}, ...]
        }
      }
    """
    catalog: dict[str, dict] = {}
    constant_to_id: dict[str, str] = {}  # e.g. seedZeroPlaces -> "seed.zero_places"

    if ANOMALY_REPORTER_FILE.is_file():
        text = ANOMALY_REPORTER_FILE.read_text(encoding="utf-8")
        # Walk lines so we can attach doc comments to each constant.
        lines = text.split("\n")
        pending_doc: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("///"):
                pending_doc.append(stripped[3:].strip())
                continue
            # `static const seedZeroPlaces = 'seed.zero_places';`
            m = re.match(
                r"\s*static\s+const\s+(\w+)\s*=\s*['\"]([^'\"]+)['\"]\s*;",
                line,
            )
            if m:
                const_name = m.group(1)
                str_id = m.group(2)
                category = str_id.split(".")[0] if "." in str_id else str_id
                catalog[str_id] = {
                    "constant_name": const_name,
                    "category": category,
                    "description": " ".join(pending_doc).strip(),
                    "callsites": [],
                }
                constant_to_id[const_name] = str_id
                pending_doc = []
                continue
            if stripped == "" or stripped.startswith("//"):
                # blank / non-doc comment — keep pending_doc, lets blank line break? Reset on blank.
                if stripped == "":
                    pending_doc = []
                continue
            # Any other code line resets the pending doc.
            pending_doc = []

    # Walk lib/ for callsites: AppAnomalyReporter.report(anomalyType: AnomalyTypes.<X>, ...)
    callsite_rx = re.compile(
        r"AppAnomalyReporter\.report\s*\(\s*\n?\s*anomalyType:\s*AnomalyTypes\.(\w+)",
    )
    lib_dir = PROJECT_ROOT / "lib"
    if lib_dir.is_dir():
        for p in lib_dir.rglob("*.dart"):
            if any(p.name.endswith(suf) for suf in EXCLUDE_SUFFIXES):
                continue
            try:
                src = p.read_text(encoding="utf-8")
            except OSError:
                continue
            if "AppAnomalyReporter.report" not in src:
                continue
            # Use line-aware match for accurate line numbers.
            for m in callsite_rx.finditer(src):
                const_name = m.group(1)
                str_id = constant_to_id.get(const_name)
                if not str_id:
                    # Constant referenced but not in catalog (catalog source missed?).
                    # Add with bare metadata so the dashboard still surfaces it.
                    catalog.setdefault(const_name, {
                        "constant_name": const_name,
                        "category": "uncategorized",
                        "description": "",
                        "callsites": [],
                    })
                    str_id = const_name
                line_no = src.count("\n", 0, m.start()) + 1
                rel = str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
                catalog[str_id]["callsites"].append({"file": rel, "line": line_no})

    return catalog


# ─────────────────────────────────────────────────────────────────────────────
# Provider cache shape extractor (Phase 1.5 of system_map_decomposition_plan.yaml)
# Replaces SYSTEM_MAP.yaml's per-section provider field narratives.
# ─────────────────────────────────────────────────────────────────────────────

PROVIDERS_DIR = PROJECT_ROOT / "lib" / "providers"

CLASS_DECL_RX = re.compile(r"class\s+(\w+)\s+(?:extends|with|implements|=)\s+")

# Captures field decls inside a class body. The type group is non-greedy so it
# stops at the first whitespace + `_name` token. We accept type expressions up
# to one level of generic (Map<String, List<Foo>> works because the `<...>` is
# not constrained against `<` in inner content — we just match until the field
# name).
PROVIDER_FIELD_RX = re.compile(
    r"^[ \t]*(?:final\s+|late\s+(?:final\s+)?|static\s+(?:final\s+)?)*"
    r"((?:[A-Za-z_]\w*\s*<[^>]+(?:<[^>]+>[^>]*)?>|[A-Za-z_]\w*)\??)"
    r"\s+(_[a-zA-Z_]\w*)\s*[=;]",
    re.MULTILINE,
)


def _classify_field_shape(type_str: str) -> str:
    t = type_str.strip()
    if t.startswith("List<") or t.startswith("List?"):
        return "list"
    if t.startswith("Map<") or t.startswith("Map?"):
        return "map"
    if t.startswith("Set<") or t.startswith("Set?"):
        return "set"
    if t.startswith("Stream") or t.startswith("StreamController") or t.startswith("StreamSubscription"):
        return "stream"
    if t.startswith("Timer") or t.endswith("Timer"):
        return "timer"
    if t.startswith("Future"):
        return "future"
    return "singleton"


def extract_provider_caches() -> dict:
    """
    Walk lib/providers/*.dart and extract private cache fields per class.

    Returns:
      {
        "<ClassName>": {
          "file":   "<rel-path>",
          "fields": [{"name": "<_field>", "type": "<TypeExpr>", "shape": "list|map|set|singleton|stream|timer|future"}]
        }
      }

    Replaces SYSTEM_MAP.yaml's per-section provider field narratives, e.g.
    "ProfileProvider — caches: _profiles (List), _profilesById (Map)".
    """
    if not PROVIDERS_DIR.is_dir():
        return {}
    out: dict = {}
    for p in sorted(PROVIDERS_DIR.glob("*.dart")):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
        # Iterate every class in the file (some files have multiple).
        for cls_m in CLASS_DECL_RX.finditer(text):
            class_name = cls_m.group(1)
            body_start = text.find("{", cls_m.end())
            if body_start < 0:
                continue
            body_end = _walk_braces(text, body_start + 1)
            body = text[body_start + 1:body_end]

            fields: list[dict] = []
            seen_names: set[str] = set()
            for fm in PROVIDER_FIELD_RX.finditer(body):
                type_str = re.sub(r"\s+", " ", fm.group(1)).strip()
                name = fm.group(2)
                if name in seen_names:
                    continue
                # Filter out obvious non-fields: function-typed locals tend not
                # to start with our patterns, but skip anything that looks like
                # a variable in a method body. Heuristic: count leading tabs +
                # spaces — class fields have 2-space indent; method locals
                # usually have 4+. Body after opening brace has trailing
                # whitespace inconsistencies, so we instead require the line
                # starts immediately within the class scope (we're on a top-level
                # member — checked by current paren-depth ≈ 0 within body, which
                # we don't track). In practice, filtering out fields whose type
                # starts with `void` (callbacks declared as locals) covers most
                # noise.
                if type_str.lower() in ("void", "var", "dynamic"):
                    continue
                seen_names.add(name)
                fields.append({
                    "name": name,
                    "type": type_str,
                    "shape": _classify_field_shape(type_str),
                })

            if fields:
                out[class_name] = {
                    "file": rel,
                    "fields": fields,
                }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Cross-cutting hook invocation extractor (Phase 1.6 of decomposition plan)
# Replaces SYSTEM_MAP.yaml's cross_cutting_hooks block.
# ─────────────────────────────────────────────────────────────────────────────

# Known hook classes. Each is a static-method singleton invoked from providers
# / services to wire a cross-cutting concern (privacy tagging, photo capture,
# preference persistence, anonymous data improvement). Classes whose name ends
# with Tagger or Service AND that are invoked statically (i.e. `Foo.method(...)`,
# not `instance.method(...)`) qualify. The list is explicit because heuristic
# detection produces too many false positives (every Service class has
# instance methods and isn't a true cross-cutting concern).
CROSS_CUTTING_HOOKS = [
    "AutoPrivacyTagger",
    "PeoplePreferencesService",
    "MapScreenshotService",
    "DataImprovementService",
    "DemographicsPreferencesService",
    "CardPreferencesService",
    "FrameCardPreferencesService",
    "InterestsFilterPreferencesService",
    "RadarChartPreferencesService",
]


def extract_cross_cutting_calls(files: list[FileInfo]) -> dict:
    """
    For each known cross-cutting hook class, find:
      - the file that DEFINES it (top symbol matches the class name)
      - every callsite where `<HookClass>.<method>(` appears in lib/

    Output shape:
      {
        "<HookClass>": {
          "definition_file": "<rel-path-to-defining-file or null>",
          "callsites": [
            { "file": "<rel-path>", "line": <int>, "method": "<method-called>" }
          ]
        }
      }

    Replaces SYSTEM_MAP.yaml's cross_cutting_hooks block.
    """
    # Map class name -> defining file via the already-parsed symbol table.
    class_to_file: dict[str, str] = {}
    for fi in files:
        for sym in fi.symbols:
            if sym.kind == "class" and sym.name in CROSS_CUTTING_HOOKS:
                class_to_file.setdefault(sym.name, fi.path)

    out: dict = {}
    for hook in CROSS_CUTTING_HOOKS:
        out[hook] = {
            "definition_file": class_to_file.get(hook),
            "callsites": [],
        }

    # Walk lib/ for `<HookClass>.<method>(` invocations.
    rx = re.compile(
        r"\b(" + "|".join(re.escape(h) for h in CROSS_CUTTING_HOOKS) + r")\.(\w+)\(",
    )
    lib_dir = PROJECT_ROOT / "lib"
    if lib_dir.is_dir():
        for p in lib_dir.rglob("*.dart"):
            if any(p.name.endswith(suf) for suf in EXCLUDE_SUFFIXES):
                continue
            try:
                src = p.read_text(encoding="utf-8")
            except OSError:
                continue
            if not any(h in src for h in CROSS_CUTTING_HOOKS):
                continue
            rel = str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
            for m in rx.finditer(src):
                hook = m.group(1)
                method = m.group(2)
                # Skip the file that defines the class.
                if rel == out[hook]["definition_file"]:
                    continue
                line_no = src.count("\n", 0, m.start()) + 1
                out[hook]["callsites"].append({
                    "file": rel,
                    "line": line_no,
                    "method": method,
                })

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Postgres objects extractor (Phase 1.7 of decomposition plan)
# Inverted index over supabase_migrations: given an object type + name,
# which migration file created it? Replaces SYSTEM_MAP.yaml's per-section
# supabase_tables lists, supabase_functions, triggers fields.
# ─────────────────────────────────────────────────────────────────────────────


def build_postgres_objects(supabase_migrations: list) -> dict:
    """
    Roll up the per-migration `supabase_migrations` operations into a flat,
    lookup-friendly index by object type. Each object entry remembers which
    migration file created/altered it.

    Returns:
      {
        "tables":    [{"name": "...", "created_in": "<sql filename>"}, ...],
        "functions": [{"name": "...", "created_in": "..."}, ...],
        "triggers":  [{"name": "...", "created_in": "..."}, ...],
        "indexes":   [{"name": "...", "on_table": "...", "created_in": "..."}],
        "cron_jobs": [{"name": "...", "schedule": "...", "scheduled_in": "..."}],
        "column_changes": [
          {"table": "...", "column": "...", "op": "add|drop", "in_migration": "..."}
        ]
      }

    Replaces SYSTEM_MAP.yaml per-section supabase_tables / supabase_functions /
    triggers / cron narratives.
    """
    tables: list[dict] = []
    functions: list[dict] = []
    triggers: list[dict] = []
    indexes: list[dict] = []
    cron_jobs: list[dict] = []
    column_changes: list[dict] = []

    seen_tables: set[str] = set()
    seen_functions: set[str] = set()
    seen_triggers: set[str] = set()
    seen_indexes: set[str] = set()
    seen_crons: set[str] = set()

    for mig in supabase_migrations:
        fn = mig["filename"]
        for op in mig["operations"]:
            kind = op["op"]
            if kind == "create_table":
                name = op["target"]
                if name not in seen_tables:
                    seen_tables.add(name)
                    tables.append({"name": name, "created_in": fn})
            elif kind == "create_function":
                name = op["target"]
                if name not in seen_functions:
                    seen_functions.add(name)
                    functions.append({"name": name, "created_in": fn})
            elif kind == "create_trigger":
                name = op["target"]
                if name not in seen_triggers:
                    seen_triggers.add(name)
                    triggers.append({"name": name, "created_in": fn})
            elif kind == "create_index":
                key = op.get("name") or op.get("target", "")
                if key not in seen_indexes:
                    seen_indexes.add(key)
                    indexes.append({
                        "name": op.get("name", ""),
                        "on_table": op.get("target", ""),
                        "created_in": fn,
                    })
            elif kind == "schedule_cron":
                name = op["name"]
                if name not in seen_crons:
                    seen_crons.add(name)
                    cron_jobs.append({
                        "name": name,
                        "schedule": op.get("schedule", ""),
                        "scheduled_in": fn,
                    })
            elif kind == "add_column":
                column_changes.append({
                    "table": op["target"],
                    "column": op["column"],
                    "op": "add",
                    "in_migration": fn,
                })
            elif kind == "drop_column":
                column_changes.append({
                    "table": op["target"],
                    "column": op["column"],
                    "op": "drop",
                    "in_migration": fn,
                })

    return {
        "tables": sorted(tables, key=lambda t: t["name"]),
        "functions": sorted(functions, key=lambda t: t["name"]),
        "triggers": sorted(triggers, key=lambda t: t["name"]),
        "indexes": sorted(indexes, key=lambda t: t["name"]),
        "cron_jobs": sorted(cron_jobs, key=lambda t: t["name"]),
        "column_changes": column_changes,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Env-var usage extractor (Phase 1.8 of decomposition plan)
# Replaces SYSTEM_MAP.yaml's per-section env_vars fields.
# ─────────────────────────────────────────────────────────────────────────────

ENV_VAR_PATTERNS = [
    # Edge Functions (Deno)
    (re.compile(r"""Deno\.env\.get\(\s*["']([A-Z][A-Z0-9_]*)["']"""), "deno"),
    # Flutter compile-time
    (re.compile(r"""String\.fromEnvironment\(\s*["']([A-Z][A-Z0-9_]*)["']"""), "dart_string"),
    (re.compile(r"""bool\.fromEnvironment\(\s*["']([A-Z][A-Z0-9_]*)["']"""), "dart_bool"),
    (re.compile(r"""int\.fromEnvironment\(\s*["']([A-Z][A-Z0-9_]*)["']"""), "dart_int"),
    # Python
    (re.compile(r"""os\.environ\.get\(\s*["']([A-Z][A-Z0-9_]*)["']"""), "python_get"),
    (re.compile(r"""os\.environ\[\s*["']([A-Z][A-Z0-9_]*)["']\s*\]"""), "python_idx"),
    (re.compile(r"""os\.getenv\(\s*["']([A-Z][A-Z0-9_]*)["']"""), "python_getenv"),
]


def extract_env_var_usage() -> dict:
    """
    Walk lib/, scripts/, supabase/functions/ for env var references and emit:
      {
        "<ENV_NAME>": [
          { "file": "<rel-path>", "line": <int>, "syntax": "deno|dart_string|python_get|..." }
        ]
      }

    Replaces SYSTEM_MAP.yaml's per-section env_vars narratives.
    """
    out: dict[str, list[dict]] = {}

    for inc in INCLUDE_DIRS:
        base = PROJECT_ROOT / inc
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if is_excluded(p):
                continue
            if p.suffix.lower() not in LANG_FOR_EXT:
                continue
            try:
                src = p.read_text(encoding="utf-8")
            except OSError:
                continue
            rel = str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
            # Cheap pre-filter: skip files that don't mention env at all.
            if not any(needle in src for needle in
                       ("Deno.env.get", "fromEnvironment", "os.environ", "os.getenv")):
                continue
            for rx, syntax in ENV_VAR_PATTERNS:
                for m in rx.finditer(src):
                    name = m.group(1)
                    line_no = src.count("\n", 0, m.start()) + 1
                    out.setdefault(name, []).append({
                        "file": rel,
                        "line": line_no,
                        "syntax": syntax,
                    })
    # Stable sort callsites within each var.
    for name in out:
        out[name].sort(key=lambda c: (c["file"], c["line"]))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Static data maps extractor (Phase 1.9 of decomposition plan)
# Replaces SYSTEM_MAP.yaml's relationships.reciprocal_map narrative,
# interests.seed_data file pointer + count, activities.inference_engine.crosswalk_data.
# ─────────────────────────────────────────────────────────────────────────────

LIB_DATA_DIR = PROJECT_ROOT / "lib" / "data"
RELATIONSHIP_PAIR_SERVICE = PROJECT_ROOT / "lib" / "services" / "relationship_pair_service.dart"

CONST_DECL_RX = re.compile(
    r"^(?:final|const)\s+([A-Za-z_]\w*(?:\s*<[^>]+(?:<[^>]+>[^>]*)?>)?)"
    r"\s+([a-zA-Z_]\w*)\s*=\s*",
    re.MULTILINE,
)


def _count_top_level_items_in(text: str, start: int) -> int:
    """
    text[start] must be `[`, `{`, or `(`. Counts comma-separated top-level
    items inside the matching close bracket. Honors string literals (so
    commas inside strings don't count) and nested brackets of any type.
    """
    if start >= len(text):
        return 0
    open_c = text[start]
    if open_c not in "[{(":
        return 0
    depth = 1
    i = start + 1
    items = 0
    saw_content = False
    in_string: Optional[str] = None
    while i < len(text) and depth > 0:
        c = text[i]
        if in_string is not None:
            if c == "\\":
                i += 2
                continue
            if c == in_string:
                in_string = None
            i += 1
            continue
        if c in ("'", '"'):
            in_string = c
            saw_content = True
        elif c in "[{(":
            depth += 1
        elif c in "]})":
            depth -= 1
        elif c == "," and depth == 1:
            items += 1
        elif not c.isspace():
            saw_content = True
        i += 1
    return (items + 1) if saw_content else 0


def extract_static_data_maps() -> dict:
    """
    Walk lib/data/*.dart for top-level `const Foo` and `final Foo` declarations
    and emit a compact summary of each, plus a special-case extraction of
    RelationshipPairService._reciprocals.

    Returns:
      {
        "files": {
          "lib/data/<file>.dart": [
            { "name": "<varName>", "type": "<TypeExpr>", "item_count": <int> }
          ]
        },
        "relationship_reciprocals": {
          "<relationship_type>": "<inverse_type>", ...
        }
      }

    Replaces SYSTEM_MAP.yaml's static-data narratives.
    """
    files_out: dict[str, list[dict]] = {}

    if LIB_DATA_DIR.is_dir():
        for p in sorted(LIB_DATA_DIR.glob("*.dart")):
            try:
                text = p.read_text(encoding="utf-8")
            except OSError:
                continue
            rel = str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
            entries: list[dict] = []
            for m in CONST_DECL_RX.finditer(text):
                type_str = re.sub(r"\s+", " ", m.group(1)).strip()
                name = m.group(2)
                # Find the first `[` or `{` after the `=` to start counting items.
                value_start = m.end()
                # Skip leading whitespace and an optional `const` keyword
                while value_start < len(text) and (text[value_start].isspace() or text[value_start] == "c"):
                    if text[value_start] == "c":
                        # Could be `const`. Allow it.
                        if text[value_start:value_start + 5] == "const":
                            value_start += 5
                            continue
                        break
                    value_start += 1
                if value_start >= len(text):
                    continue
                first_char = text[value_start]
                if first_char not in "[{(":
                    # Not a collection literal — could be a string, number, etc.
                    continue
                count = _count_top_level_items_in(text, value_start)
                entries.append({
                    "name": name,
                    "type": type_str,
                    "item_count": count,
                })
            if entries:
                files_out[rel] = entries

    # Special-case: RelationshipPairService._reciprocals (a map of relationship
    # type → its inverse). The plan specifically calls this out because its
    # contents document business logic (50+ relationship inverses) that
    # SYSTEM_MAP previously narrated in prose.
    reciprocals: dict[str, str] = {}
    if RELATIONSHIP_PAIR_SERVICE.is_file():
        rps = RELATIONSHIP_PAIR_SERVICE.read_text(encoding="utf-8")
        # Find `_reciprocals` map declaration body.
        m = re.search(
            r"_reciprocals\s*=\s*(?:const\s*)?\{",
            rps,
        )
        if m:
            body_start = rps.find("{", m.start())
            if body_start >= 0:
                body_end = _walk_braces(rps, body_start + 1)
                body = rps[body_start + 1:body_end]
                # Match `'key': 'value',` pairs.
                for pm in re.finditer(
                    r"['\"]([^'\"]+)['\"]\s*:\s*['\"]([^'\"]+)['\"]",
                    body,
                ):
                    reciprocals[pm.group(1)] = pm.group(2)

    return {
        "files": files_out,
        "relationship_reciprocals": reciprocals,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tier-A symbol enrichments — added 2026-04-30
#
# Three additions that replace the most common grep-cycles a Claude session
# burns when navigating an unfamiliar codebase:
#
#   class_hierarchy  — every class's extends / implements / with relationships
#   symbol_index     — global "where is X DEFINED" lookup (name → [{file,line,kind}])
#   symbol_callers   — global call graph for static + bare-call sites
#                      (name → [{file, line}])
#
# All three are derived from text scans against the indexed file set; tree-sitter
# is used only for symbol DEFINITIONS (already done upstream). Call sites are
# captured via regex with a deliberately narrow scope: we record `Class.method(`
# (high-precision static dispatch) and bare `name(` calls where the name matches
# a known top-level definition. Plain `instance.method(` calls without a class
# receiver are SKIPPED — there's no type info to disambiguate `add` from `add`,
# so listing them would produce noise that defeats the point.
#
# Caveat: this is heuristic. If a name has multiple definitions, callers can't
# be attributed to one specific def. The dashboard surfaces the ambiguity
# (multiple def entries in symbol_index for the same name).
# ─────────────────────────────────────────────────────────────────────────────

# Reserved words / built-ins that look like identifiers + `(` but aren't
# user-defined symbols. Kept narrow on purpose; the goal is to skip obvious
# noise, not to enumerate every keyword.
_CALL_FILTER_DART = {
    "if", "for", "while", "switch", "return", "throw", "await", "yield",
    "assert", "print", "super", "this", "new", "is", "as",
}
_CALL_FILTER_PY = {
    "if", "for", "while", "return", "yield", "raise", "with", "lambda",
    "print", "super", "self", "True", "False", "None", "len", "range", "str",
    "int", "float", "list", "dict", "set", "tuple",
}
_CALL_FILTER_TS = _CALL_FILTER_DART | {"function", "console", "typeof", "of"}

# Per-language regex set for call extraction. Compiled once.
# group(1) = receiver (Class identifier, may be empty), group(2) = method name
_CALL_RX = {
    "dart":       re.compile(r"(?<![\w.])(?:([A-Z][A-Za-z0-9_]*)\.)?([a-zA-Z_][A-Za-z0-9_]*)\s*\("),
    "python":     re.compile(r"(?<![\w.])(?:([A-Z][A-Za-z0-9_]*)\.)?([a-zA-Z_][A-Za-z0-9_]*)\s*\("),
    "typescript": re.compile(r"(?<![\w.])(?:([A-Z][A-Za-z0-9_]*)\.)?([a-zA-Z_][A-Za-z0-9_]*)\s*\("),
    "tsx":        re.compile(r"(?<![\w.])(?:([A-Z][A-Za-z0-9_]*)\.)?([a-zA-Z_][A-Za-z0-9_]*)\s*\("),
    "javascript": re.compile(r"(?<![\w.])(?:([A-Z][A-Za-z0-9_]*)\.)?([a-zA-Z_][A-Za-z0-9_]*)\s*\("),
}

# Class-hierarchy patterns: `class X extends Y implements I1, I2 with M1, M2`
# Captures only Dart for now (the bulk of class declarations in the original use case); Python
# / TS would need their own patterns and the win is smaller (less inheritance
# depth there).
_DART_CLASS_HIERARCHY_RX = re.compile(
    r"(?m)^\s*(abstract\s+)?class\s+(\w+)"
    r"(?:\s*<[^>]+>)?"          # optional generics
    r"(?:\s+extends\s+(\w+(?:\s*<[^>]+>)?))?"
    r"(?:\s+with\s+([\w\s,<>]+?))?"
    r"(?:\s+implements\s+([\w\s,<>]+?))?"
    r"\s*(?:\{|;|=|/\*|//|$)"
)
_DART_MIXIN_HIERARCHY_RX = re.compile(
    r"(?m)^\s*mixin\s+(\w+)(?:\s*<[^>]+>)?(?:\s+on\s+([\w\s,<>]+?))?\s*(?:\{|//|/\*|$)"
)

# Python: `class X(Base1, Base2, metaclass=ABC):` — bases are inside the parens.
_PY_CLASS_HIERARCHY_RX = re.compile(
    r"(?m)^\s*class\s+(\w+)(?:\s*\(([^)]*)\))?\s*:"
)

# TS / TSX / JS: `[abstract] class X<T> extends Y implements I1, I2 {`
_TS_CLASS_HIERARCHY_RX = re.compile(
    r"(?m)^\s*(?:export\s+(?:default\s+)?)?(abstract\s+)?class\s+(\w+)"
    r"(?:\s*<[^>]+>)?"                                   # generics
    r"(?:\s+extends\s+([\w$.]+(?:\s*<[^>]+>)?))?"        # extends
    r"(?:\s+implements\s+([^\{\n]+))?"                   # implements
    r"\s*\{"
)


def extract_class_hierarchy(files: list[FileInfo]) -> dict:
    """
    Walk every Dart file and capture per-class extends/implements/with chains.

    Output:
      {
        "<ClassName>": {
          "file": "<rel-path>",
          "line": <int>,           # 1-based, line of `class X` keyword
          "abstract": <bool>,
          "extends":    "<superclass or null>",
          "implements": ["<iface>", ...],
          "with":       ["<mixin>", ...],
          "kind":       "class" | "mixin"
        }
      }

    Replaces grep-for-`class X extends Y` patterns. The dashboard can also
    use this to render a class tree per file.
    """
    out: dict[str, dict] = {}
    for fi in files:
        if fi.lang not in ("dart", "python", "typescript", "tsx", "javascript"):
            continue
        try:
            text = (PROJECT_ROOT / fi.path).read_text(encoding="utf-8")
        except OSError:
            continue

        if fi.lang == "dart":
            for m in _DART_CLASS_HIERARCHY_RX.finditer(text):
                is_abstract = bool(m.group(1))
                class_name = m.group(2)
                extends = m.group(3).strip() if m.group(3) else None
                with_m = m.group(4)
                impls_m = m.group(5)
                with_list = (
                    [s.strip() for s in re.split(r"[,\s]+", with_m) if s.strip()]
                    if with_m else []
                )
                impls_list = (
                    [s.strip() for s in re.split(r"[,\s]+", impls_m) if s.strip()]
                    if impls_m else []
                )
                line_no = text.count("\n", 0, m.start()) + 1
                out[class_name] = {
                    "file": fi.path,
                    "line": line_no,
                    "abstract": is_abstract,
                    "extends": extends,
                    "implements": impls_list,
                    "with": with_list,
                    "kind": "class",
                }
            for m in _DART_MIXIN_HIERARCHY_RX.finditer(text):
                mixin_name = m.group(1)
                on_m = m.group(2)
                on_list = (
                    [s.strip() for s in re.split(r"[,\s]+", on_m) if s.strip()]
                    if on_m else []
                )
                line_no = text.count("\n", 0, m.start()) + 1
                out[mixin_name] = {
                    "file": fi.path,
                    "line": line_no,
                    "abstract": False,
                    "extends": None,
                    "implements": [],
                    "with": on_list,
                    "kind": "mixin",
                }

        elif fi.lang == "python":
            for m in _PY_CLASS_HIERARCHY_RX.finditer(text):
                class_name = m.group(1)
                bases_str = m.group(2) or ""
                # Filter out keyword args (e.g. metaclass=ABC); keep positional bases.
                bases = []
                is_abstract = False
                for part in bases_str.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    if "=" in part:
                        if "ABC" in part:
                            is_abstract = True
                        continue
                    bases.append(part)
                    if part in ("ABC", "ABCMeta"):
                        is_abstract = True
                line_no = text.count("\n", 0, m.start()) + 1
                # Python: first base is conceptually `extends`; rest go to implements
                extends = bases[0] if bases else None
                impls = bases[1:] if len(bases) > 1 else []
                out[class_name] = {
                    "file": fi.path,
                    "line": line_no,
                    "abstract": is_abstract,
                    "extends": extends,
                    "implements": impls,
                    "with": [],
                    "kind": "class",
                }

        else:  # typescript / tsx / javascript
            for m in _TS_CLASS_HIERARCHY_RX.finditer(text):
                is_abstract = bool(m.group(1))
                class_name = m.group(2)
                extends = m.group(3).strip() if m.group(3) else None
                impls_m = m.group(4)
                impls_list = (
                    [s.strip() for s in re.split(r"\s*,\s*", impls_m) if s.strip()]
                    if impls_m else []
                )
                line_no = text.count("\n", 0, m.start()) + 1
                out[class_name] = {
                    "file": fi.path,
                    "line": line_no,
                    "abstract": is_abstract,
                    "extends": extends,
                    "implements": impls_list,
                    "with": [],
                    "kind": "class",
                }
    return out


def extract_call_graph(files: list[FileInfo], symbol_definitions: dict[str, list[dict]]) -> dict:
    """
    For every file, scan for call expressions and emit a global
    name → [{file, line}] map of where each known top-level symbol is called.

    SCOPE:
      - `Class.method(`  → captured (high-precision static dispatch)
      - bare `name(`     → captured ONLY when `name` matches a known def
      - plain `instance.method(` without a Class receiver → SKIPPED
        (no type info to disambiguate)

    The high-value queries this answers without grep:
      - "where is _addColumnIfNotExists called?"
      - "where is EncryptionService.derivedKey accessed?"
      - "where is the SeedPlaceService constructor invoked?"

    Returns: { name → [{file, line, receiver: "ClassName" or null}] }
    """
    callers: dict[str, list[dict]] = {}
    known_names = set(symbol_definitions.keys())

    for fi in files:
        rx = _CALL_RX.get(fi.lang)
        if not rx:
            continue
        flt = (
            _CALL_FILTER_DART if fi.lang == "dart"
            else _CALL_FILTER_PY if fi.lang == "python"
            else _CALL_FILTER_TS
        )
        try:
            text = (PROJECT_ROOT / fi.path).read_text(encoding="utf-8")
        except OSError:
            continue
        # Skip the file's own DEFINITION lines — calls on the def line are
        # rarely calls (and self-references would be noise).
        defined_here = {s.line for s in fi.symbols}

        # We also want to skip calls INSIDE comments + string literals. A
        # cheap pass: strip line-comments and single-quoted strings before
        # scanning. Triple-quoted/docstring blocks are uncommon enough we
        # accept some noise; it's lower-cost than a full parser.
        cleaned_lines: list[str] = []
        for line in text.split("\n"):
            stripped = re.sub(r"//.*$", "", line)         # Dart/JS/TS line comments
            stripped = re.sub(r"#.*$", "", stripped)      # Python line comments
            stripped = re.sub(r"'[^']*'", "''", stripped) # single-quoted strings
            stripped = re.sub(r'"[^"]*"', '""', stripped) # double-quoted strings
            cleaned_lines.append(stripped)

        for i, line_text in enumerate(cleaned_lines, start=1):
            if i in defined_here:
                continue
            for m in rx.finditer(line_text):
                receiver = m.group(1) or None
                method = m.group(2)
                if method in flt:
                    continue
                # Bare-call gate: only count if the bare name is a known
                # PROJECT symbol (excludes language built-ins / unknown names).
                # We DO include same-file callers — `_addColumnIfNotExists`
                # is called many times within app_database.dart and that's
                # the most useful information about it. Excluding same-file
                # calls (a previous heuristic) hid the real call graph.
                if not receiver and method not in known_names:
                    continue
                callers.setdefault(method, []).append({
                    "file": fi.path,
                    "line": i,
                    "receiver": receiver,
                })

    # Sort each entry's list by file then line for stable output.
    for name in callers:
        callers[name].sort(key=lambda c: (c["file"], c["line"]))
    return callers


def build_class_usage(symbol_callers: dict) -> dict:
    """
    Inverse view of symbol_callers: aggregate by RECEIVER class.

    Replaces "where is AppLogger used?" — without this, the answer requires
    iterating over all 7000+ symbol_callers entries to find ones with
    receiver=AppLogger. With this index, it's one lookup.

    Output: { ClassName → [{file, line, method}] }
    """
    out: dict[str, list[dict]] = {}
    for method_name, sites in symbol_callers.items():
        for s in sites:
            recv = s.get("receiver")
            if not recv:
                continue
            out.setdefault(recv, []).append({
                "file": s["file"],
                "line": s["line"],
                "method": method_name,
            })
    for cls in out:
        out[cls].sort(key=lambda c: (c["file"], c["line"]))
    return out


def build_symbol_index(files: list[FileInfo]) -> dict:
    """
    Global "where is X defined" lookup. For each symbol name, list every
    place it's defined (file + line + kind + doc). Multiple definitions
    happen for overloaded names across files (rare but possible).

    Output: { name → [{file, line, kind, doc, signature}] }

    Replaces the most common grep pattern: "find me the definition of X."
    """
    out: dict[str, list[dict]] = {}
    for fi in files:
        for s in fi.symbols:
            out.setdefault(s.name, []).append({
                "file": fi.path,
                "line": s.line,
                "kind": s.kind,
                "doc": s.doc,
                "signature": s.signature,
            })
    # Sort definitions by file then line for deterministic output.
    for name in out:
        out[name].sort(key=lambda d: (d["file"], d["line"]))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Tier-A++ extractors (added 2026-04-30, second pass)
# Each one replaces a grep-cycle that's small per-call but adds up across a
# session. Cost-of-build is near-zero given the auto-rebuild loop, so the bar
# for inclusion is "non-zero diagnostic value" rather than "high ROI."
# ─────────────────────────────────────────────────────────────────────────────

_ASSET_PATH_RX = re.compile(r"""['"]((?:assets|images|fonts|lib/data)/[A-Za-z0-9_./\-]+\.[a-z0-9]+)['"]""")
# UI-string-literal heuristic: at least 5 chars, mostly letters with at least
# one space (i.e. user-visible prose), no path separators / template chars.
_UI_STRING_RX = re.compile(
    r"""['"]((?=[^'"]{5,80}['"])(?:(?!\$\{)[^'"\\\n])+?[a-z]\s+[A-Za-z][^'"\\\n]*?)['"]"""
)


def extract_asset_string_index(files: list[FileInfo]) -> dict:
    """
    Two indexes for "where is this string referenced?" queries:
      - asset_paths:   { "assets/foo.png" → [{file, line}] }
      - ui_strings:    { "Activity Trends" → [{file, line}] }   (best-effort prose)

    The asset-path index is high-precision (regex matches a known directory
    prefix + extension). The UI-string index is a heuristic: literals 5–80
    chars long with a lowercase letter followed by a space followed by a
    capitalized letter — i.e. multi-word user-facing prose. False positives
    are tolerable; the win is "where does this label come from?" lookups.
    """
    assets: dict[str, list[dict]] = {}
    strings: dict[str, list[dict]] = {}
    for fi in files:
        if fi.lang not in ("dart",):
            # Restrict UI-string scan to Dart for precision; assets too,
            # since the directory conventions are Flutter-specific.
            continue
        try:
            text = (PROJECT_ROOT / fi.path).read_text(encoding="utf-8")
        except OSError:
            continue
        for i, line_text in enumerate(text.split("\n"), start=1):
            for m in _ASSET_PATH_RX.finditer(line_text):
                assets.setdefault(m.group(1), []).append({"file": fi.path, "line": i})
            for m in _UI_STRING_RX.finditer(line_text):
                s = m.group(1).strip()
                # Skip code-like literals (URLs, regex bodies, JSON keys)
                if "://" in s or s.startswith("@") or s.startswith("/"):
                    continue
                strings.setdefault(s, []).append({"file": fi.path, "line": i})
    return {"asset_paths": assets, "ui_strings": strings}


def build_test_pairing(files: list[FileInfo]) -> dict:
    """
    Pair each lib/ source file with its test (if any) by filename convention.

    Test files live under `test/` which is NOT in INCLUDE_DIRS — they're not
    fully indexed (no symbol scan), but their EXISTENCE is high-value
    information. Scan the filesystem directly for test/**.dart and pair by
    name.

    Output: { "lib/path/x.dart": "test/path/x_test.dart" }

    Replaces the "ls test/services/" first-question grep when starting a
    bug investigation.
    """
    test_dir = PROJECT_ROOT / "test"
    if not test_dir.is_dir():
        return {}
    test_paths: set[str] = set()
    for p in test_dir.rglob("*_test.dart"):
        rel = str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
        test_paths.add(rel)
    out: dict[str, str] = {}
    for fi in files:
        p = fi.path
        if not p.startswith("lib/") or not p.endswith(".dart"):
            continue
        # Convention 1: lib/services/x.dart → test/services/x_test.dart
        candidate = "test/" + p[len("lib/"):-len(".dart")] + "_test.dart"
        if candidate in test_paths:
            out[p] = candidate
            continue
        # Convention 2: lib/services/x.dart → test/x_test.dart  (flat layout)
        flat = "test/" + p.split("/")[-1][:-len(".dart")] + "_test.dart"
        if flat in test_paths:
            out[p] = flat
    return out


def build_bug_catalog_index(files: list[FileInfo]) -> dict:
    """
    Walk bugs/{system}/*.yaml and link each bug entry to source files
    referenced in its `affected_files` / `participating_files` / `files`
    fields, OR matched by system→file naming.

    Output:
      {
        "by_file": { "lib/services/encryption_service.dart": [{bug_id, status, title}] },
        "by_system": { "encryption": [{bug_id, status, title}] },
        "summary":   { "total": N, "open": M, "resolved": K }
      }
    """
    bugs_dir = PROJECT_ROOT / "bugs"
    out_by_file: dict[str, list[dict]] = {}
    out_by_system: dict[str, list[dict]] = {}
    summary = {"total": 0, "open": 0, "resolved": 0}
    if not bugs_dir.is_dir():
        return {"by_file": {}, "by_system": {}, "summary": summary}

    indexed_paths = {fi.path for fi in files}
    for system_dir in sorted(bugs_dir.iterdir()):
        if not system_dir.is_dir() or system_dir.name.startswith("_"):
            continue
        system_name = system_dir.name
        for p in sorted(system_dir.glob("*.yaml")):
            try:
                text = p.read_text(encoding="utf-8")
            except OSError:
                continue
            # Light parse — extract bug_id, status, title without yaml.load
            bug_id_m = re.search(r"^(?:bug_id|id):\s*[\"']?([^\"'\n]+)", text, re.MULTILINE)
            status_m = re.search(r"^status:\s*[\"']?([^\"'\n]+)", text, re.MULTILINE)
            title_m = re.search(r"^(?:title|description):\s*[\"']?([^\"'\n]+)", text, re.MULTILINE)
            bug_id = (bug_id_m.group(1).strip() if bug_id_m else p.stem)
            status = (status_m.group(1).strip() if status_m else "unknown")
            title = (title_m.group(1).strip()[:120] if title_m else "")

            entry = {"bug_id": bug_id, "status": status, "title": title,
                     "file": str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")}

            summary["total"] += 1
            if status.lower() in ("resolved", "fixed", "closed"):
                summary["resolved"] += 1
            else:
                summary["open"] += 1

            out_by_system.setdefault(system_name, []).append(entry)

            # Find any source paths referenced inside the bug yaml
            for path_m in re.finditer(r"['\"]?(lib/[A-Za-z0-9_./\-]+\.dart)['\"]?", text):
                src = path_m.group(1)
                if src in indexed_paths:
                    out_by_file.setdefault(src, []).append(entry)

    return {"by_file": out_by_file, "by_system": out_by_system, "summary": summary}


def estimate_token_cost(file_path: str) -> int:
    """
    Rough char-count → token estimate (chars / 4). Useful for read-vs-delegate
    decisions. Faster than running an actual tokenizer; good enough for
    "is this file 2k tokens or 50k tokens?"-class questions.
    """
    try:
        size = (PROJECT_ROOT / file_path).stat().st_size
    except OSError:
        return 0
    return size // 4


def render_json(files: list[FileInfo], scores: dict[str, float], graph, flow_data: Optional[dict] = None) -> dict:
    flow_index = (flow_data or {}).get("flow_index", {})
    file_to_flows = (flow_data or {}).get("file_to_flows", {})

    nodes = []
    for fi in files:
        flows_for_file = file_to_flows.get(fi.path, [])
        # `top_symbols` stays as a flat name list for backward compatibility
        # with the dashboard's existing renderer + the validator's via-symbol
        # lookup. `top_symbol_details` carries the rich data: line, kind, doc.
        top_5 = fi.symbols[:5]
        nodes.append({
            "id": fi.path,
            "kind": file_kind(fi.path),
            "lang": fi.lang,
            "score": round(scores.get(fi.path, 0.0), 6),
            "symbol_count": len(fi.symbols),
            "est_tokens": estimate_token_cost(fi.path),
            "top_symbols": [s.name for s in top_5],
            "top_symbol_details": [
                {"name": s.name, "kind": s.kind, "line": s.line,
                 "doc": s.doc, "signature": s.signature}
                for s in top_5
            ],
            "flows": flows_for_file,
        })
    edges = [{"from": u, "to": v, "weight": d.get("weight", 1)} for u, v, d in graph.edges(data=True)]

    # Compute drift report. Build the per-file symbol set first.
    file_to_symbols: dict[str, set[str]] = {}
    for fi in files:
        file_to_symbols[fi.path] = {s.name.lower() for s in fi.symbols}
    drift = compute_drift_report(files, scores, graph, flow_data or {}, file_to_symbols)

    drift_schema = extract_drift_schema()
    drift_migrations = extract_drift_migrations()
    supabase_migrations = extract_supabase_migrations()
    edge_functions = extract_edge_function_actions()
    anomaly_catalog = extract_anomaly_catalog()
    provider_caches = extract_provider_caches()
    cross_cutting_calls = extract_cross_cutting_calls(files)
    postgres_objects = build_postgres_objects(supabase_migrations)
    env_var_usage = extract_env_var_usage()
    static_data = extract_static_data_maps()

    # Tier-A symbol enrichments (added 2026-04-30 — replace common grep patterns).
    symbol_index    = build_symbol_index(files)
    symbol_callers  = extract_call_graph(files, symbol_index)
    class_hierarchy = extract_class_hierarchy(files)
    class_usage     = build_class_usage(symbol_callers)

    # Tier-A++ extractors (added 2026-04-30, second pass).
    asset_string_index = extract_asset_string_index(files)
    test_pairing       = build_test_pairing(files)
    bug_catalog        = build_bug_catalog_index(files)

    return {
        "generated_at": int(time.time()),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "flow_count": len(flow_index),
        "nodes": nodes,
        "edges": edges,
        "flow_index": flow_index,
        "drift_report": drift,
        "drift_schema": drift_schema,
        "drift_migrations": drift_migrations,
        "supabase_migrations": supabase_migrations,
        "edge_functions": edge_functions,
        "anomaly_catalog": anomaly_catalog,
        "provider_caches": provider_caches,
        "cross_cutting_calls": cross_cutting_calls,
        "postgres_objects": postgres_objects,
        "env_var_usage": env_var_usage,
        "static_data": static_data,
        # Tier-A symbol enrichments (added 2026-04-30).
        "symbol_index": symbol_index,
        "symbol_callers": symbol_callers,
        "class_hierarchy": class_hierarchy,
        "class_usage": class_usage,
        # Tier-A++ (second pass).
        "asset_paths":   asset_string_index["asset_paths"],
        "ui_strings":    asset_string_index["ui_strings"],
        "test_pairing":  test_pairing,
        "bug_catalog":   bug_catalog,
    }


def _append_history_summary(json_data: dict) -> None:
    """
    Append a compact summary line to repo_map_history.jsonl after every build.
    Deduplicates: if the new summary is structurally identical to the previous
    line (same counts, same drift, same validator state, same schema_version),
    we skip the append. This keeps the file from being spammed by real-time
    rebuilds where nothing meaningful changed (e.g., a comment-only edit).

    Use cases the file enables:
      - Trend detection: orphan / broken_deps / undocumented count over time
      - First-appearance forensics: when did a given anomaly type / flow first appear?
      - Build cadence: how often is the index rebuilding?
      - Validation timeline: how long has a flow been broken?

    File: plans/dashboard/data/repo_map_history.jsonl (append-only).
    Each line is a compact JSON object — no nesting beyond two levels — so
    `grep` + `jq` work as well as the dashboard's sparkline renderer.
    """
    drift = json_data.get("drift_report", {}).get("summary", {}) or {}
    flow_index = json_data.get("flow_index", {}) or {}

    # Build the summary record we want to log.
    summary = {
        "ts": json_data.get("generated_at", int(time.time())),
        "node_count":          json_data.get("node_count", 0),
        "edge_count":          json_data.get("edge_count", 0),
        "flow_count":          json_data.get("flow_count", 0),
        # Drift signals
        "orphans":             drift.get("orphaned_high_centrality_files", 0),
        "broken_deps":         drift.get("broken_declared_dependencies", 0),
        "undocumented_pairs":  drift.get("undocumented_cross_flow_pairs", 0),
        "claimed_files_missing": drift.get("claimed_files_missing_in_repo", 0),
        "flows_red":           drift.get("flows_red", 0),
        "flows_amber":         drift.get("flows_amber", 0),
        "flows_info":          drift.get("flows_info", 0),
        "flows_green":         drift.get("flows_green", 0),
        # Auto-extracted field cardinalities (Phase 1 outputs)
        "drift_table_count":      len(json_data.get("drift_schema", {}) or {}),
        "edge_function_count":    len(json_data.get("edge_functions", {}) or {}),
        "anomaly_type_count":     len(json_data.get("anomaly_catalog", {}) or {}),
        "provider_count":         len(json_data.get("provider_caches", {}) or {}),
        "env_var_count":          len(json_data.get("env_var_usage", {}) or {}),
        "schema_version":         (json_data.get("drift_migrations", {}) or {}).get("schema_version"),
        "flows_with_invariants":  sum(1 for f in flow_index.values()
                                       if f.get("invariant_count", 0) > 0),
    }

    # Dedupe vs the last line: if every field except `ts` matches, skip.
    last: Optional[dict] = None
    if OUTPUT_HISTORY_JSONL.is_file():
        try:
            # Read the LAST line efficiently (file is append-only).
            with OUTPUT_HISTORY_JSONL.open("rb") as f:
                f.seek(0, 2)
                size = f.tell()
                if size > 0:
                    # Walk back up to ~2 KB to find the start of the last line.
                    chunk = min(2048, size)
                    f.seek(size - chunk)
                    tail = f.read().decode("utf-8", errors="replace")
                    lines = [ln for ln in tail.splitlines() if ln.strip()]
                    if lines:
                        try:
                            last = json.loads(lines[-1])
                        except Exception:
                            last = None
        except OSError:
            last = None

    if last is not None:
        comp_keys = [k for k in summary if k != "ts"]
        same = all(summary.get(k) == last.get(k) for k in comp_keys)
        if same:
            return  # No-op: nothing meaningful changed since last build.

    # Append the new line.
    OUTPUT_HISTORY_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_HISTORY_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary, separators=(",", ":")) + "\n")


def cmd_build(args) -> int:
    quiet = args.quiet
    if not quiet:
        print("[repo_map] discovering files...", file=sys.stderr)
    files_paths = discover_files()
    if not quiet:
        print(f"[repo_map] {len(files_paths)} files found", file=sys.stderr)

    cache = load_cache() if not args.no_cache else {}
    new_cache: dict = {}
    parsed: list[FileInfo] = []
    n_cached = 0
    n_parsed = 0

    for p in files_paths:
        rel = str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        cached = cache.get(rel)
        if cached and cached.get("mtime") == mtime and not args.include_private:
            fi = fileinfo_from_cache(cached)
            n_cached += 1
        else:
            fi = parse_file(p, args.include_private)
            if not fi:
                continue
            n_parsed += 1
        parsed.append(fi)
        new_cache[rel] = fileinfo_to_cache(fi)

    if not quiet:
        print(f"[repo_map] parsed {n_parsed}, cached {n_cached}", file=sys.stderr)

    save_cache(new_cache)

    if not quiet:
        print("[repo_map] building graph...", file=sys.stderr)
    graph = build_graph(parsed)

    recent = load_recent_edits()
    if not quiet and recent:
        print(f"[repo_map] {len(recent)} recent edits used as PageRank seeds", file=sys.stderr)

    scores = rank_files(graph, recent)
    for fi in parsed:
        fi.score = scores.get(fi.path, 0.0)

    flow_data = load_feature_flows()
    if not quiet:
        flow_index = flow_data.get("flow_index", {})
        file_to_flows = flow_data.get("file_to_flows", {})
        print(f"[repo_map] {len(flow_index)} feature flows loaded; "
              f"{len(file_to_flows)} files have flow membership", file=sys.stderr)

    md_text, included = render_markdown(parsed, scores, args.budget, file_to_flows=flow_data.get("file_to_flows", {}))
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text(md_text, encoding="utf-8")

    json_data = render_json(parsed, scores, graph, flow_data=flow_data)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(json_data, indent=2), encoding="utf-8")

    # Append a compact summary line to repo_map_history.jsonl. Deduplicates
    # internally — only writes if something meaningful changed since last build.
    _append_history_summary(json_data)

    if DIRTY_FLAG.is_file():
        DIRTY_FLAG.unlink()

    if not quiet:
        print(f"[repo_map] wrote {OUTPUT_MD.relative_to(PROJECT_ROOT)} ({len(included)} files in budget)", file=sys.stderr)
        print(f"[repo_map] wrote {OUTPUT_JSON.relative_to(PROJECT_ROOT)} ({json_data['node_count']} nodes, {json_data['edge_count']} edges)", file=sys.stderr)
    return 0


def cmd_status(args) -> int:
    if not OUTPUT_MD.is_file():
        print("repo_map: not yet generated. Run: python scripts/repo_map.py build")
        return 1
    age_s = time.time() - OUTPUT_MD.stat().st_mtime
    age_h = age_s / 3600
    json_ok = OUTPUT_JSON.is_file()
    dirty = DIRTY_FLAG.is_file()
    print(f"repo_map.md   : {OUTPUT_MD} ({age_h:.1f}h old)")
    print(f"repo_map.json : {'present' if json_ok else 'MISSING'}")
    print(f"dirty flag    : {'SET (rebuild needed)' if dirty else 'clear'}")
    if json_ok:
        try:
            data = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
            print(f"node count    : {data.get('node_count', '?')}")
            print(f"edge count    : {data.get('edge_count', '?')}")
        except Exception:
            pass
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Repo Map — Aider-style symbol map")
    sub = p.add_subparsers(dest="command", required=True)

    pb = sub.add_parser("build", help="Build the repo map")
    pb.add_argument("--budget", type=int, default=2000, help="Token budget for repo_map.md (default 2000)")
    # Default ON as of 2026-04-30: private symbols (e.g. `_addColumnIfNotExists`)
    # are valuable in symbol_index for grep-replacement lookups. The markdown
    # token-budgeted output still picks public symbols first via PageRank, so
    # privates don't inflate repo_map.md.
    pb.add_argument("--no-private", dest="include_private", action="store_false",
                    default=True, help="Skip _-prefixed symbols (overrides default-on)")
    pb.add_argument("--no-cache", action="store_true", help="Skip mtime cache and reparse everything")
    pb.add_argument("--quiet", action="store_true")
    pb.set_defaults(func=cmd_build)

    ps = sub.add_parser("status", help="Show generation status")
    ps.set_defaults(func=cmd_status)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
