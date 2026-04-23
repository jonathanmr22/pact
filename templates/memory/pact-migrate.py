#!/usr/bin/env python3
"""
PACT Memory Migration — One-time upgrade to v0.7.0 vector search.

Run this ONCE per project to:
  1. Index all existing PACT knowledge files into the vector store
  2. Move pact-ratings.jsonl → bugs/_FEEDBACK.jsonl (if needed)
  3. Verify the index

Non-destructive: YAML files are never modified. This only READS them
and creates the vector index alongside them.

Usage:
  python pact-migrate.py /path/to/your/project

Requirements (one-time install):
  pip install sqlite-vec onnxruntime tokenizers huggingface_hub pyyaml
"""

import os
import sys
import json
import shutil
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print('Usage: python pact-migrate.py /path/to/your/project')
        print()
        print('This upgrades your PACT project to v0.7.0 by:')
        print('  1. Building a vector search index from your existing knowledge files')
        print('  2. Moving task ratings to the new location (bugs/_FEEDBACK.jsonl)')
        print()
        print('Non-destructive — your YAML files are never modified.')
        sys.exit(1)

    project_root = os.path.abspath(sys.argv[1])
    if not os.path.isdir(project_root):
        print(f'Error: {project_root} is not a directory')
        sys.exit(1)

    print(f'PACT Memory Migration v0.7.0')
    print(f'Project: {project_root}')
    print(f'{"=" * 60}')
    print()

    # ── Step 1: Check dependencies ──
    print('[1/4] Checking dependencies...')
    missing = []
    for pkg in ['sqlite_vec', 'onnxruntime', 'tokenizers', 'huggingface_hub', 'yaml']:
        try:
            __import__(pkg)
        except ImportError:
            real_name = 'pyyaml' if pkg == 'yaml' else pkg.replace('_', '-')
            missing.append(real_name)

    if missing:
        print(f'  Missing packages: {", ".join(missing)}')
        print(f'  Run: pip install {" ".join(missing)}')
        sys.exit(1)
    print('  All dependencies installed.')
    print()

    # ── Step 2: Move ratings file ──
    print('[2/4] Checking feedback file location...')
    home_dir = os.path.expanduser('~')
    old_ratings = os.path.join(home_dir, '.claude', 'pact-ratings.jsonl')
    new_feedback = os.path.join(project_root, '.claude', 'bugs', '_FEEDBACK.jsonl')

    if os.path.isfile(old_ratings) and not os.path.isfile(new_feedback):
        os.makedirs(os.path.dirname(new_feedback), exist_ok=True)
        shutil.copy2(old_ratings, new_feedback)
        print(f'  Copied: ~/.claude/pact-ratings.jsonl → bugs/_FEEDBACK.jsonl')
        print(f'  (Original kept at old location for safety. Delete manually when ready.)')
    elif os.path.isfile(new_feedback):
        print(f'  _FEEDBACK.jsonl already exists at new location.')
    elif os.path.isfile(old_ratings):
        print(f'  Ratings exist at old location, feedback already at new location.')
    else:
        print(f'  No ratings file found (fresh project — this is normal).')
    print()

    # ── Step 3: Build vector index ──
    print('[3/4] Building vector search index...')
    print('  (First run downloads the embedding model ~80MB — subsequent runs are instant)')
    print()

    # Import pact-memory from the same directory as this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir)
    import importlib
    pact_memory = importlib.import_module('pact-memory')

    count = pact_memory.reindex(project_root)
    print()
    print(f'  Indexed {count} documents.')
    print()

    # ── Step 4: Verify ──
    print('[4/4] Verifying index...')
    s = pact_memory.stats()
    print(f'  Total documents: {s["total"]}')
    print(f'  By type: {json.dumps(s["by_type"])}')
    if s['by_project']:
        print(f'  By project: {json.dumps(s["by_project"])}')
    print()

    # Test query
    if s['total'] > 0:
        results = pact_memory.query('test query', top_k=1)
        if results:
            print(f'  Test query OK — vector search is working.')
        else:
            print(f'  WARNING: Test query returned no results.')
    print()

    print(f'{"=" * 60}')
    print(f'Migration complete!')
    print()
    print(f'Vector index: ~/.claude/pact-memory.db')
    print(f'Documents indexed: {count}')
    print()
    print(f'What changed:')
    print(f'  - Your YAML files: UNTOUCHED (read-only indexing)')
    print(f'  - New file: ~/.claude/pact-memory.db (vector index)')
    if os.path.isfile(new_feedback):
        print(f'  - New file: bugs/_FEEDBACK.jsonl (task ratings)')
    print()
    print(f'The vector index will be updated automatically as you work.')
    print(f'To re-index manually: python pact-memory.py reindex --project-root {project_root}')


if __name__ == '__main__':
    main()
