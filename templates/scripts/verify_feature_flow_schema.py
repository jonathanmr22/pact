#!/usr/bin/env python3
"""
Feature Flow Schema Validator — phase 1 of the Codebase Intent Map unification.

Checks every feature_flows/*.yaml file against the schema introduced on
2026-04-29 (participating_files, declared_dependencies, invariant_anchors).
Anchors flow claims to plans/dashboard/data/repo_map.json so we can verify
mechanically that the intent layer matches structural reality.

Usage:
  python scripts/verify_feature_flow_schema.py                    # all flows
  python scripts/verify_feature_flow_schema.py --flow encryption  # single flow
  python scripts/verify_feature_flow_schema.py --warn-only        # exit 0 on errors (phase-1 mode)
  python scripts/verify_feature_flow_schema.py --json             # JSON output

Exit codes:
  0 = clean (or --warn-only and no fatal parse errors)
  1 = at least one violation (when not --warn-only)
  2 = system error (missing repo_map.json, etc.)

Phase rollout:
  Phase 1: --warn-only by default in the pre-commit hook.
  Phase 2 (after backfill): becomes blocking by default.

See plans/codebase_intent_map_unification_plan.yaml for the larger context.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

# Make stdout/stderr UTF-8 so em-dashes, arrows, box-drawing in flow text don't crash output
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FLOWS_DIR = PROJECT_ROOT / "feature_flows"
REPO_MAP_JSON = PROJECT_ROOT / "plans" / "dashboard" / "data" / "repo_map.json"

REQUIRED_TOP_KEYS = ["purpose"]                       # universally required
REQUIRED_INTENT_KEYS = ["participating_files"]        # required by the new schema
RECOMMENDED_KEYS = ["invariants", "declared_dependencies"]
ALLOWED_KIND = {"depends_on", "communicates_with", "uses_utility", "consumes_event"}
ALLOWED_FLOW_KIND = {"feature", "cross_cutting_concern", "infrastructure"}
ALLOWED_ANCHOR_TYPE = {"exclusive_locality", "single_caller", "gates_caller", "presence"}

# Subsystem stubs that are valid declared_dependencies targets even though they
# don't have their own feature_flow file (yet). Add to this list as needed.
RECOGNIZED_SUBSYSTEM_STUBS = {
    "supabase",      # Postgres + Edge Functions + Storage as a black-box dependency
    "drift",         # Local SQLite/Drift database
    "platform",      # iOS/Android/web platform channels
    "sentry",        # External logging + crash reporting
    "stadia",        # Stadia Maps (geocoding + static maps)
    "overture",      # Overture Maps Foundation data
    "freerasp",      # Runtime app shielding
    "stripe",        # Payments
    "google_play",   # Billing + sign-in
}


@dataclass
class Violation:
    flow: str
    severity: str             # "error" | "warning" | "info"
    code: str                 # short identifier for filtering
    message: str
    suggested_fix: Optional[str] = None


@dataclass
class FlowReport:
    flow_name: str
    file: str
    violations: list[Violation] = field(default_factory=list)


def load_repo_map() -> dict:
    if not REPO_MAP_JSON.is_file():
        print(f"ERROR: repo_map.json not found at {REPO_MAP_JSON}", file=sys.stderr)
        print("Run: python scripts/repo_map.py build", file=sys.stderr)
        sys.exit(2)
    with open(REPO_MAP_JSON, encoding="utf-8") as f:
        return json.load(f)


def load_flow(path: Path) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError as e:
        print(f"YAML parse error in {path}: {e}", file=sys.stderr)
        return None


def discover_flows() -> list[Path]:
    if not FLOWS_DIR.is_dir():
        return []
    return sorted(p for p in FLOWS_DIR.glob("*.yaml") if not p.name.startswith("_"))


def flow_name_from_path(path: Path) -> str:
    return re.sub(r"_flow$", "", path.stem)


def index_repo_map(repo_map: dict) -> tuple[set[str], dict[str, set[str]]]:
    """
    Returns (path_set, path_to_symbols_map):
      - path_set: every node id (relative path) that exists in the codebase
      - path_to_symbols_map: per-file lowercase-set of symbol names
        (only top_symbols are stored in repo_map.json; that's our oracle)
    """
    nodes = repo_map.get("nodes", []) or []
    path_set: set[str] = set()
    path_to_symbols: dict[str, set[str]] = {}
    for n in nodes:
        nid = (n.get("id") or "").replace("\\", "/")
        if not nid:
            continue
        path_set.add(nid)
        syms = {s.lower() for s in (n.get("top_symbols") or []) if isinstance(s, str)}
        path_to_symbols[nid] = syms
    return path_set, path_to_symbols


def index_flow_files() -> dict[str, str]:
    """Map flow_name → flow_file_path (relative). Used to resolve declared_dependencies references."""
    out: dict[str, str] = {}
    for p in discover_flows():
        name = flow_name_from_path(p)
        out[name] = str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
    return out


def validate_flow(
    path: Path,
    data: dict,
    repo_paths: set[str],
    path_to_symbols: dict[str, set[str]],
    flow_index: dict[str, str],
) -> FlowReport:
    name = flow_name_from_path(path)
    rep = FlowReport(flow_name=name, file=str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))

    if not isinstance(data, dict):
        rep.violations.append(Violation(name, "error", "not_yaml_mapping",
            "Flow file does not parse to a YAML mapping (top-level must be key:value)"))
        return rep

    # ── Required top keys ──
    for k in REQUIRED_TOP_KEYS:
        if k not in data:
            rep.violations.append(Violation(name, "error", f"missing_{k}",
                f"Required key '{k}' is missing",
                suggested_fix=f"Add: '{k}: \"...\"' at the top level"))

    # ── Required intent-layer keys ──
    for k in REQUIRED_INTENT_KEYS:
        if k not in data or not data[k]:
            rep.violations.append(Violation(name, "warning", f"missing_intent_{k}",
                f"Intent-layer key '{k}' is missing or empty (required after phase-2 backfill)",
                suggested_fix=f"Run: python scripts/suggest_flow_participants.py {name}"))

    # ── flow_kind enum ──
    fk = data.get("flow_kind")
    if fk is not None and fk not in ALLOWED_FLOW_KIND:
        rep.violations.append(Violation(name, "error", "bad_flow_kind",
            f"flow_kind '{fk}' is not in {sorted(ALLOWED_FLOW_KIND)}",
            suggested_fix="Use one of: feature, cross_cutting_concern, infrastructure"))

    # ── participating_files ──
    pfs = data.get("participating_files") or []
    if pfs and not isinstance(pfs, list):
        rep.violations.append(Violation(name, "error", "participating_files_not_list",
            "participating_files must be a list",
            suggested_fix="Reformat as a YAML list of strings"))
        pfs = []

    # Normalize Windows separators just in case
    pfs_norm = [str(p).replace("\\", "/") for p in pfs if p]
    seen: set[str] = set()
    for p in pfs_norm:
        if p in seen:
            rep.violations.append(Violation(name, "warning", "duplicate_participant",
                f"participating_files contains duplicate: {p}",
                suggested_fix=f"Remove the duplicate '{p}' entry"))
        seen.add(p)
        if p not in repo_paths:
            # Heuristic: was it a generated file?
            if any(p.endswith(suf) for suf in (".g.dart", ".freezed.dart", ".mocks.dart", ".gr.dart")):
                rep.violations.append(Violation(name, "error", "participant_is_generated",
                    f"participating_files references a generated file: {p}",
                    suggested_fix="Remove generated files; list only source files"))
            else:
                rep.violations.append(Violation(name, "error", "participant_not_in_repo_map",
                    f"participating_files references a path not present in repo_map.json: {p}",
                    suggested_fix=f"Either fix the path or remove it. Run: python scripts/repo_map.py build && grep -l '{Path(p).name}' to find the correct path"))

    # ── declared_dependencies ──
    deps = data.get("declared_dependencies") or []
    if deps and not isinstance(deps, list):
        rep.violations.append(Violation(name, "error", "declared_dependencies_not_list",
            "declared_dependencies must be a list",
            suggested_fix="Reformat as a YAML list of objects"))
        deps = []

    for i, dep in enumerate(deps):
        if not isinstance(dep, dict):
            rep.violations.append(Violation(name, "error", "declared_dep_not_object",
                f"declared_dependencies[{i}] is not an object",
                suggested_fix="Each entry must be a YAML mapping with depends_on/communicates_with/consumes + via + purpose + kind"))
            continue

        # Resolve the target — exactly one of depends_on/communicates_with/consumes
        target_keys = [k for k in ("depends_on", "communicates_with", "consumes") if k in dep]
        if len(target_keys) == 0:
            rep.violations.append(Violation(name, "error", "declared_dep_no_target",
                f"declared_dependencies[{i}] has no target (depends_on/communicates_with/consumes)",
                suggested_fix="Add 'depends_on: <other_flow_name>'"))
            continue
        if len(target_keys) > 1:
            rep.violations.append(Violation(name, "error", "declared_dep_multiple_targets",
                f"declared_dependencies[{i}] has multiple target keys: {target_keys}",
                suggested_fix="Keep only one of depends_on/communicates_with/consumes"))
            continue
        target = dep[target_keys[0]]

        if not isinstance(target, str) or not target:
            rep.violations.append(Violation(name, "error", "declared_dep_bad_target",
                f"declared_dependencies[{i}].{target_keys[0]} is not a string",
                suggested_fix="Use a flow name (e.g. 'auth_flow' or 'auth') or recognized subsystem stub"))
            continue

        # Try to resolve target to a flow file or subsystem stub
        target_canon = re.sub(r"_flow$", "", target.strip())
        if target_canon not in flow_index and target_canon not in RECOGNIZED_SUBSYSTEM_STUBS:
            rep.violations.append(Violation(name, "warning", "declared_dep_unknown_target",
                f"declared_dependencies[{i}] target '{target}' resolves to neither an existing feature_flow nor a recognized subsystem stub",
                suggested_fix=f"Either create feature_flows/{target_canon}_flow.yaml or add '{target_canon}' to RECOGNIZED_SUBSYSTEM_STUBS in this validator"))

        # Validate via
        via = dep.get("via") or []
        if not isinstance(via, list):
            rep.violations.append(Violation(name, "error", "declared_dep_via_not_list",
                f"declared_dependencies[{i}].via must be a list of strings",
                suggested_fix="via: [SymbolA, SymbolB]"))
        else:
            # If target is a flow we know, verify each via symbol exists in that flow's
            # participating_files' symbol set per repo_map.json. Skip for subsystem stubs.
            if target_canon in flow_index:
                target_path = PROJECT_ROOT / flow_index[target_canon]
                target_data = load_flow(target_path)
                if isinstance(target_data, dict):
                    target_pfs = [str(p).replace("\\", "/") for p in (target_data.get("participating_files") or [])]
                    target_symbols: set[str] = set()
                    for tp in target_pfs:
                        target_symbols.update(path_to_symbols.get(tp, set()))
                    for sym in via:
                        if not isinstance(sym, str):
                            continue
                        if sym.lower() not in target_symbols and target_symbols:
                            rep.violations.append(Violation(name, "warning", "declared_dep_via_symbol_not_found",
                                f"declared_dependencies[{i}].via symbol '{sym}' not found in {target_canon}_flow's top_symbols",
                                suggested_fix=f"Either fix the symbol name or add the actual implementing file to {target_canon}_flow.participating_files"))

        # Validate purpose
        if not dep.get("purpose"):
            rep.violations.append(Violation(name, "warning", "declared_dep_no_purpose",
                f"declared_dependencies[{i}] is missing 'purpose'",
                suggested_fix="Add a one-sentence 'purpose:' explaining why this dependency exists"))

        # Validate kind
        kind = dep.get("kind")
        if kind is None:
            rep.violations.append(Violation(name, "warning", "declared_dep_no_kind",
                f"declared_dependencies[{i}] is missing 'kind'",
                suggested_fix=f"Add 'kind:' (one of {sorted(ALLOWED_KIND)})"))
        elif kind not in ALLOWED_KIND:
            rep.violations.append(Violation(name, "error", "declared_dep_bad_kind",
                f"declared_dependencies[{i}].kind '{kind}' is not in {sorted(ALLOWED_KIND)}",
                suggested_fix=f"Use one of: {', '.join(sorted(ALLOWED_KIND))}"))

    # ── invariant_anchors ──
    invariants = data.get("invariants") or []
    anchors = data.get("invariant_anchors") or []
    if anchors:
        if not isinstance(anchors, list):
            rep.violations.append(Violation(name, "error", "invariant_anchors_not_list",
                "invariant_anchors must be a list of objects"))
        else:
            for i, anc in enumerate(anchors):
                if not isinstance(anc, dict):
                    rep.violations.append(Violation(name, "error", "invariant_anchor_not_object",
                        f"invariant_anchors[{i}] is not an object"))
                    continue
                idx = anc.get("invariant_index")
                if not isinstance(idx, int):
                    rep.violations.append(Violation(name, "error", "invariant_anchor_bad_index",
                        f"invariant_anchors[{i}].invariant_index must be an integer"))
                    continue
                if not (0 <= idx < len(invariants)):
                    rep.violations.append(Violation(name, "error", "invariant_anchor_index_oor",
                        f"invariant_anchors[{i}].invariant_index={idx} is out of range; invariants[] has {len(invariants)} entries"))

                anchored_by = anc.get("anchored_by") or []
                if not isinstance(anchored_by, list):
                    rep.violations.append(Violation(name, "error", "invariant_anchor_not_list",
                        f"invariant_anchors[{i}].anchored_by must be a list"))
                    continue

                anchor_type = anc.get("anchor_type")
                if anchor_type is not None and anchor_type not in ALLOWED_ANCHOR_TYPE:
                    rep.violations.append(Violation(name, "error", "invariant_anchor_bad_type",
                        f"invariant_anchors[{i}].anchor_type '{anchor_type}' is not in {sorted(ALLOWED_ANCHOR_TYPE)}"))

                # For anchored_by entries of form "file::Symbol", check the file exists
                for ent in anchored_by:
                    if not isinstance(ent, str):
                        continue
                    if "::" in ent:
                        f_part = ent.split("::", 1)[0].strip().replace("\\", "/")
                        # f_part may be just a basename — try loose match
                        if f_part not in repo_paths:
                            matches = [p for p in repo_paths if p.endswith("/" + f_part) or p.endswith(f_part)]
                            if not matches:
                                rep.violations.append(Violation(name, "warning", "invariant_anchor_file_unknown",
                                    f"invariant_anchors[{i}].anchored_by '{ent}' references a file not found in repo_map: {f_part}"))

    return rep


def render_text(reports: list[FlowReport], summary_only: bool = False) -> str:
    out: list[str] = []
    total_errors = 0
    total_warnings = 0
    flows_with_errors = 0
    flows_with_warnings = 0
    flows_clean = 0

    for rep in reports:
        errs = [v for v in rep.violations if v.severity == "error"]
        warns = [v for v in rep.violations if v.severity == "warning"]
        if errs:
            flows_with_errors += 1
        elif warns:
            flows_with_warnings += 1
        else:
            flows_clean += 1
        total_errors += len(errs)
        total_warnings += len(warns)

    out.append("-" * 72)
    out.append(f"Feature Flow Schema Validator -- checked {len(reports)} flow(s)")
    out.append(f"  clean:      {flows_clean}")
    out.append(f"  warnings:   {flows_with_warnings}  ({total_warnings} total)")
    out.append(f"  errors:     {flows_with_errors}  ({total_errors} total)")
    out.append("-" * 72)

    if summary_only:
        return "\n".join(out)

    for rep in reports:
        if not rep.violations:
            continue
        out.append("")
        out.append(f"╭─ {rep.flow_name}  ({rep.file})")
        for v in rep.violations:
            sev_tag = "ERROR  " if v.severity == "error" else ("WARN   " if v.severity == "warning" else "INFO   ")
            out.append(f"│  [{sev_tag}] {v.code}: {v.message}")
            if v.suggested_fix:
                out.append(f"│     → {v.suggested_fix}")
        out.append("╰─")

    return "\n".join(out)


def render_json(reports: list[FlowReport]) -> str:
    return json.dumps([
        {
            "flow_name": r.flow_name,
            "file": r.file,
            "violations": [
                {"severity": v.severity, "code": v.code, "message": v.message, "suggested_fix": v.suggested_fix}
                for v in r.violations
            ],
        }
        for r in reports
    ], indent=2)


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate feature_flow YAMLs against the intent-map schema")
    ap.add_argument("--flow", help="Validate a single flow by name (e.g. 'encryption' or 'auth_flow')")
    ap.add_argument("--warn-only", action="store_true", help="Exit 0 even when errors are present (phase-1 mode)")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    ap.add_argument("--summary", action="store_true", help="Emit only the summary header")
    args = ap.parse_args()

    repo_map = load_repo_map()
    repo_paths, path_to_symbols = index_repo_map(repo_map)
    flow_index = index_flow_files()

    if args.flow:
        target = re.sub(r"_flow$", "", args.flow)
        if target not in flow_index:
            print(f"ERROR: flow '{args.flow}' not found in feature_flows/", file=sys.stderr)
            return 2
        flows = [PROJECT_ROOT / flow_index[target]]
    else:
        flows = discover_flows()

    reports: list[FlowReport] = []
    for path in flows:
        data = load_flow(path)
        if data is None:
            rep = FlowReport(flow_name=flow_name_from_path(path), file=str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
            rep.violations.append(Violation(rep.flow_name, "error", "yaml_parse_error",
                "YAML parse error — see stderr"))
            reports.append(rep)
            continue
        reports.append(validate_flow(path, data, repo_paths, path_to_symbols, flow_index))

    if args.json:
        print(render_json(reports))
    else:
        print(render_text(reports, summary_only=args.summary))

    has_errors = any(any(v.severity == "error" for v in r.violations) for r in reports)
    if has_errors and not args.warn_only:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
