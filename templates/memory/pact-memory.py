#!/usr/bin/env python3
"""
PACT Memory — Vector search layer for compound intelligence.

Provides fuzzy semantic search across PACT's knowledge systems:
  - Bug symptoms and resolutions
  - Research synthesis
  - Task feedback (rated user experiences)
  - Graduated solutions

Uses sqlite-vec (zero-dep SQLite extension) + all-MiniLM-L6-v2 (ONNX, local, no API key).
Single file: ~/.claude/pact-memory.db

Usage:
  # Store a document
  python pact-memory.py store --type bug --id meld-007 --text "BLE write values null" --file "bugs/meld/meld-007.yaml"

  # Query for similar documents
  python pact-memory.py query "entity deleted but still shows in UI" --top 5

  # Index all PACT knowledge files (run by pact-migrate.py)
  python pact-memory.py reindex --project-root /path/to/project

  # Show stats
  python pact-memory.py stats
"""

import argparse
import json
import os
import sys
import sqlite3
import struct
import time
from pathlib import Path

# ─── Configuration ───
PACT_DIR = os.path.join(os.path.expanduser('~'), '.claude')
DB_PATH = os.path.join(PACT_DIR, 'pact-memory.db')
MODEL_ID = 'sentence-transformers/all-MiniLM-L6-v2'
EMBEDDING_DIM = 384
MAX_TOKENS = 256

# ─── Lazy-loaded globals ───
_tokenizer = None
_session = None
_model_dir = None


def get_model_dir():
    """Find or download the ONNX model."""
    global _model_dir
    if _model_dir:
        return _model_dir

    cache_dir = os.path.join(os.path.expanduser('~'), '.cache', 'pact-models')

    # Check if already downloaded
    from huggingface_hub import hf_hub_download
    try:
        model_path = hf_hub_download(MODEL_ID, 'onnx/model.onnx', cache_dir=cache_dir, local_files_only=True)
        _model_dir = str(Path(model_path).parent.parent)
        return _model_dir
    except Exception:
        pass

    # Download
    print('[PACT Memory] Downloading embedding model (one-time, ~80MB)...', file=sys.stderr)
    for f in ['onnx/model.onnx', 'tokenizer.json', 'tokenizer_config.json']:
        hf_hub_download(MODEL_ID, f, cache_dir=cache_dir)

    model_path = hf_hub_download(MODEL_ID, 'onnx/model.onnx', cache_dir=cache_dir, local_files_only=True)
    _model_dir = str(Path(model_path).parent.parent)
    print('[PACT Memory] Model ready.', file=sys.stderr)
    return _model_dir


def embed(texts):
    """Embed a list of strings into normalized vectors. Returns numpy array (N, 384)."""
    global _tokenizer, _session
    import numpy as np

    if _tokenizer is None:
        from tokenizers import Tokenizer
        import onnxruntime as ort

        model_dir = get_model_dir()
        _tokenizer = Tokenizer.from_file(os.path.join(model_dir, 'tokenizer.json'))
        _tokenizer.enable_padding(pad_id=0, pad_token='[PAD]')
        _tokenizer.enable_truncation(max_length=MAX_TOKENS)
        _session = ort.InferenceSession(
            os.path.join(model_dir, 'onnx', 'model.onnx'),
            providers=['CPUExecutionProvider'],
        )

    encodings = _tokenizer.encode_batch(texts)
    input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
    attention = np.array([e.attention_mask for e in encodings], dtype=np.int64)
    token_types = np.zeros_like(input_ids)

    outputs = _session.run(None, {
        'input_ids': input_ids,
        'attention_mask': attention,
        'token_type_ids': token_types,
    })

    # Mean pooling + L2 normalize
    token_emb = outputs[0]
    mask_exp = attention[:, :, np.newaxis].astype(np.float32)
    pooled = np.sum(token_emb * mask_exp, axis=1) / np.clip(mask_exp.sum(axis=1), 1e-9, None)
    norms = np.linalg.norm(pooled, axis=1, keepdims=True)
    return (pooled / norms).astype(np.float32)


def serialize_f32(vector):
    """Pack a float32 vector into bytes for sqlite-vec."""
    return struct.pack(f'{len(vector)}f', *vector)


def get_db():
    """Open the pact-memory database, creating tables if needed."""
    os.makedirs(PACT_DIR, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.enable_load_extension(True)
    import sqlite_vec
    sqlite_vec.load(db)

    db.executescript(f'''
        CREATE TABLE IF NOT EXISTS pact_docs (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,        -- bug, solution, research, feedback
            text TEXT NOT NULL,         -- the searchable content
            file TEXT,                  -- source file path (relative)
            project TEXT,              -- project folder name
            metadata TEXT,             -- JSON blob for extra fields
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS pact_vec USING vec0(
            id TEXT PRIMARY KEY,
            embedding float[{EMBEDDING_DIM}]
        );
    ''')
    return db


def store(doc_id, doc_type, text, file=None, project=None, metadata=None):
    """Store or update a document with its embedding."""
    import numpy as np
    db = get_db()
    vec = embed([text])[0]

    # Upsert document
    db.execute('''
        INSERT INTO pact_docs (id, type, text, file, project, metadata, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            type=excluded.type, text=excluded.text, file=excluded.file,
            project=excluded.project, metadata=excluded.metadata,
            updated_at=datetime('now')
    ''', (doc_id, doc_type, text, file, project, json.dumps(metadata) if metadata else None))

    # Upsert vector
    db.execute('DELETE FROM pact_vec WHERE id = ?', (doc_id,))
    db.execute('INSERT INTO pact_vec (id, embedding) VALUES (?, ?)',
               (doc_id, serialize_f32(vec)))

    db.commit()
    db.close()


def query(text, top_k=5, doc_type=None, project=None):
    """Query for similar documents. Returns list of {id, type, text, file, score, metadata}."""
    db = get_db()
    vec = embed([text])[0]

    # KNN search via sqlite-vec
    rows = db.execute('''
        SELECT v.id, v.distance
        FROM pact_vec v
        WHERE v.embedding MATCH ?
        ORDER BY v.distance
        LIMIT ?
    ''', (serialize_f32(vec), top_k * 3)).fetchall()  # over-fetch for filtering

    if not rows:
        db.close()
        return []

    # Fetch full docs and filter
    results = []
    for row_id, distance in rows:
        doc = db.execute(
            'SELECT id, type, text, file, project, metadata FROM pact_docs WHERE id = ?',
            (row_id,)
        ).fetchone()
        if not doc:
            continue

        d_id, d_type, d_text, d_file, d_project, d_meta = doc

        # Apply filters
        if doc_type and d_type != doc_type:
            continue
        if project and d_project and d_project != project:
            continue

        results.append({
            'id': d_id,
            'type': d_type,
            'text': d_text[:300],
            'file': d_file,
            'project': d_project,
            'score': round(1.0 - (distance ** 2 / 2), 4),  # L2 distance to cosine similarity for normalized vectors
            'metadata': json.loads(d_meta) if d_meta else None,
        })

        if len(results) >= top_k:
            break

    db.close()
    return results


def stats():
    """Return database statistics."""
    db = get_db()
    total = db.execute('SELECT COUNT(*) FROM pact_docs').fetchone()[0]
    by_type = db.execute('SELECT type, COUNT(*) FROM pact_docs GROUP BY type ORDER BY COUNT(*) DESC').fetchall()
    by_project = db.execute('SELECT project, COUNT(*) FROM pact_docs WHERE project IS NOT NULL GROUP BY project ORDER BY COUNT(*) DESC').fetchall()
    db.close()
    return {'total': total, 'by_type': dict(by_type), 'by_project': dict(by_project)}


def reindex(project_root):
    """Re-index all PACT knowledge files from a project."""
    import yaml

    project_name = os.path.basename(os.path.abspath(project_root))
    indexed = 0

    # ── Bugs ──
    bugs_dir = os.path.join(project_root, '.claude', 'bugs')
    if os.path.isdir(bugs_dir):
        for root, dirs, files in os.walk(bugs_dir):
            for f in files:
                if f.startswith('_') or not f.endswith('.yaml'):
                    continue
                path = os.path.join(root, f)
                rel_path = os.path.relpath(path, project_root).replace('\\', '/')
                try:
                    with open(path, 'r', encoding='utf-8') as fh:
                        content = fh.read()
                    # Extract searchable fields — handle various bug file structures
                    try:
                        data = yaml.safe_load(content)
                        parts = []
                        # Title
                        if data.get('title'):
                            parts.append(str(data['title']))
                        # Symptoms (can be string or list)
                        symptoms = data.get('symptoms', data.get('symptom', ''))
                        if isinstance(symptoms, list):
                            parts.extend(str(s) for s in symptoms)
                        elif symptoms:
                            parts.append(str(symptoms))
                        # Root cause
                        if data.get('root_cause'):
                            parts.append(str(data['root_cause'])[:200])
                        # Resolution/fix
                        resolution = data.get('resolution', data.get('fix', ''))
                        if isinstance(resolution, dict):
                            parts.append(str(resolution.get('summary', '')))
                        elif resolution:
                            parts.append(str(resolution)[:200])
                        # Tags
                        tags = data.get('tags', [])
                        if isinstance(tags, list):
                            parts.append(' '.join(str(t) for t in tags))
                        text = ' '.join(parts).strip()
                    except Exception:
                        text = content[:500]

                    if text:
                        doc_id = f"bug:{project_name}:{f.replace('.yaml', '')}"
                        store(doc_id, 'bug', text, file=rel_path, project=project_name)
                        indexed += 1
                except Exception as e:
                    print(f'  SKIP {rel_path}: {e}', file=sys.stderr)

    # ── Solutions ──
    solutions_file = os.path.join(project_root, '.claude', 'bugs', '_SOLUTIONS.yaml')
    if os.path.isfile(solutions_file):
        try:
            with open(solutions_file, 'r', encoding='utf-8') as fh:
                data = yaml.safe_load(fh.read())
            for sol in data.get('solutions', []):
                sol_id = sol.get('id', 'unknown')
                text = f"{sol.get('title', '')} {sol.get('symptom', '')} {sol.get('root_cause', '')} {sol.get('fix', '')} {' '.join(sol.get('tags', []))}"
                doc_id = f"solution:{project_name}:{sol_id}"
                store(doc_id, 'solution', text.strip(),
                      file='bugs/_SOLUTIONS.yaml', project=project_name,
                      metadata={'sol_id': sol_id, 'title': sol.get('title', '')})
                indexed += 1
        except Exception as e:
            print(f'  SKIP _SOLUTIONS.yaml: {e}', file=sys.stderr)

    # ── Research ──
    research_dir = os.path.join(project_root, 'docs', 'reference', 'research')
    if os.path.isdir(research_dir):
        for f in os.listdir(research_dir):
            if f.startswith('_') or not f.endswith('.yaml'):
                continue
            path = os.path.join(research_dir, f)
            rel_path = os.path.relpath(path, project_root).replace('\\', '/')
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    data = yaml.safe_load(fh.read())
                question = data.get('question', '')
                synthesis = data.get('synthesis', '')
                decision = data.get('decision', '')
                tags = ' '.join(data.get('tags', []))
                text = f"{question} {synthesis} {decision} {tags}".strip()
                if text:
                    doc_id = f"research:{project_name}:{f.replace('.yaml', '')}"
                    store(doc_id, 'research', text, file=rel_path, project=project_name)
                    indexed += 1
            except Exception as e:
                print(f'  SKIP {rel_path}: {e}', file=sys.stderr)

    # ── Feedback ──
    feedback_file = os.path.join(bugs_dir, '_FEEDBACK.jsonl')
    if not os.path.isfile(feedback_file):
        # Check old location
        feedback_file = os.path.join(PACT_DIR, 'pact-ratings.jsonl')
    if os.path.isfile(feedback_file):
        try:
            with open(feedback_file, 'r', encoding='utf-8') as fh:
                for i, line in enumerate(fh):
                    line = line.strip()
                    if not line:
                        continue
                    rating = json.loads(line)
                    task = rating.get('task', '')
                    wrong = rating.get('wrong', '')
                    right = rating.get('right', '')
                    tags = ' '.join(rating.get('tags', []))
                    score = rating.get('score', 0)
                    text = f"Task: {task}. Score: {score}/5. Wrong: {wrong}. Right: {right}. Tags: {tags}".strip()
                    doc_id = f"feedback:{project_name}:{i}"
                    store(doc_id, 'feedback', text,
                          file='bugs/_FEEDBACK.jsonl', project=project_name,
                          metadata={'score': score, 'task': task})
                    indexed += 1
        except Exception as e:
            print(f'  SKIP feedback: {e}', file=sys.stderr)

    return indexed


def index_single_file(filepath, project=None):
    """Index a single YAML knowledge file with proper field extraction."""
    import yaml

    filepath = os.path.abspath(filepath)
    if not os.path.isfile(filepath):
        print(f'File not found: {filepath}', file=sys.stderr)
        return

    filename = os.path.basename(filepath).replace('.yaml', '')
    rel_path = filepath  # will be relative if caller provides relative

    # Detect type from path
    path_lower = filepath.replace('\\', '/').lower()
    if '_solutions' in path_lower:
        doc_type = 'solution'
    elif '_feedback' in path_lower:
        doc_type = 'feedback'
    elif '/research/' in path_lower:
        doc_type = 'research'
    else:
        doc_type = 'bug'

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            data = {}

        parts = []

        if doc_type == 'research':
            for field in ['question', 'synthesis', 'decision']:
                if data.get(field):
                    parts.append(str(data[field]))
            tags = data.get('tags', [])
            if isinstance(tags, list):
                parts.append(' '.join(str(t) for t in tags))

        elif doc_type == 'solution':
            # Solutions file has a list — index each entry
            for sol in data.get('solutions', []):
                sol_id = sol.get('id', 'unknown')
                text = f"{sol.get('title', '')} {sol.get('symptom', '')} {sol.get('root_cause', '')} {sol.get('fix', '')} {' '.join(sol.get('tags', []))}"
                doc_id = f"solution:{project or 'unknown'}:{sol_id}"
                store(doc_id, 'solution', text.strip(), file=rel_path, project=project,
                      metadata={'sol_id': sol_id, 'title': sol.get('title', '')})
            print(f'Indexed {len(data.get("solutions", []))} solutions from {filename}')
            return

        else:  # bug
            if data.get('title'):
                parts.append(str(data['title']))
            symptoms = data.get('symptoms', data.get('symptom', ''))
            if isinstance(symptoms, list):
                parts.extend(str(s) for s in symptoms)
            elif symptoms:
                parts.append(str(symptoms))
            if data.get('root_cause'):
                parts.append(str(data['root_cause'])[:200])
            resolution = data.get('resolution', data.get('fix', ''))
            if isinstance(resolution, dict):
                parts.append(str(resolution.get('summary', '')))
            elif resolution:
                parts.append(str(resolution)[:200])
            tags = data.get('tags', [])
            if isinstance(tags, list):
                parts.append(' '.join(str(t) for t in tags))

        text = ' '.join(parts).strip()
        if text:
            doc_id = f"{doc_type}:{project or 'unknown'}:{filename}"
            store(doc_id, doc_type, text, file=rel_path, project=project)
            print(f'Indexed: {doc_id}')
        else:
            print(f'No searchable content in {filename}', file=sys.stderr)

    except Exception as e:
        print(f'Error indexing {filepath}: {e}', file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description='PACT Memory — vector search for compound intelligence')
    sub = parser.add_subparsers(dest='command')

    # store
    p_store = sub.add_parser('store', help='Store a document')
    p_store.add_argument('--type', required=True, choices=['bug', 'solution', 'research', 'feedback'])
    p_store.add_argument('--id', required=True)
    p_store.add_argument('--text', required=True)
    p_store.add_argument('--file', default=None)
    p_store.add_argument('--project', default=None)

    # query
    p_query = sub.add_parser('query', help='Search for similar documents')
    p_query.add_argument('text', help='Search query')
    p_query.add_argument('--top', type=int, default=5)
    p_query.add_argument('--type', default=None, choices=['bug', 'solution', 'research', 'feedback'])
    p_query.add_argument('--project', default=None)
    p_query.add_argument('--json', action='store_true', help='Output as JSON')

    # reindex
    p_reindex = sub.add_parser('reindex', help='Re-index all PACT knowledge files')
    p_reindex.add_argument('--project-root', required=True)

    # index-file
    p_index = sub.add_parser('index-file', help='Index a single PACT knowledge file')
    p_index.add_argument('filepath', help='Path to the YAML file')
    p_index.add_argument('--project', default=None)

    # stats
    sub.add_parser('stats', help='Show database statistics')

    args = parser.parse_args()

    if args.command == 'store':
        store(args.id, args.type, args.text, file=args.file, project=args.project)
        print(f'Stored: {args.id}')

    elif args.command == 'index-file':
        index_single_file(args.filepath, project=args.project)

    elif args.command == 'query':
        results = query(args.text, top_k=args.top, doc_type=args.type, project=args.project)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            if not results:
                print('No results found.')
            else:
                for r in results:
                    score_pct = int(r['score'] * 100)
                    print(f"  [{score_pct}%] [{r['type']}] {r['id']}")
                    print(f"       {r['text'][:120]}")
                    if r['file']:
                        print(f"       -> {r['file']}")
                    print()

    elif args.command == 'reindex':
        count = reindex(args.project_root)
        s = stats()
        print(f'Indexed {count} documents. Total: {s["total"]}')
        print(f'By type: {s["by_type"]}')

    elif args.command == 'stats':
        s = stats()
        print(f'Total documents: {s["total"]}')
        print(f'By type: {s["by_type"]}')
        if s['by_project']:
            print(f'By project: {s["by_project"]}')

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
