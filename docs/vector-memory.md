# PACT Vector Memory — Semantic Search Across Knowledge

Local semantic search across bugs, solutions, research, and task feedback using local embeddings. No API keys, no cloud. YAML stays authoritative; vector search finds the right file faster.

---

## How It Works

PACT's knowledge lives in structured YAML files — bug reports, reusable solutions, research synthesis, package knowledge. Vector memory doesn't replace these files. It indexes them so the agent (or you) can find the right one with a natural language query instead of grepping by filename.

**Stack:**
- **Database:** `~/.claude/pact-memory.db` (SQLite + sqlite-vec extension)
- **Embedding model:** `sentence-transformers/all-MiniLM-L6-v2` (ONNX, runs locally)
- **Dimensions:** 384-dimensional vectors
- **Model size:** ~80MB (downloads once to `~/.cache/pact-models/`)
- **Max tokens per document:** 256

---

## Quick Start

```bash
# Index all existing knowledge files
python .claude/memory/pact-memory.py reindex --project-root .

# Search for something
python .claude/memory/pact-memory.py query "entity deleted but still shows in UI" --top 5

# Check what's indexed
python .claude/memory/pact-memory.py stats
```

Or use the `/pact-recall` slash command in Claude Code for inline search.

---

## What Gets Indexed

| Source | Fields Extracted | Type Tag |
|--------|-----------------|----------|
| `bugs/{system}/*.yaml` | title, symptoms, root_cause, resolution, tags | `bug` |
| `bugs/_SOLUTIONS.yaml` | title, symptom, root_cause, fix, tags | `solution` |
| `knowledge/research/*.yaml` | question, synthesis, decision, tags | `research` |
| `_FEEDBACK.jsonl` | task, score, wrong, right, tags | `feedback` |

Each document is stored with its file path, project name, and metadata. Updates re-embed and replace the existing vector.

---

## CLI Commands

### Store a document
```bash
python pact-memory.py store \
  --type bug \
  --id "meld-007" \
  --text "BLE advertising fails when Bluetooth audio is connected" \
  --file "bugs/meld/meld-007.yaml" \
  --project "kensic"
```

### Query (semantic search)
```bash
# Basic search
python pact-memory.py query "stale cache after provider update"

# Filter by type
python pact-memory.py query "encryption key derivation" --type research

# Filter by project
python pact-memory.py query "backup restore" --project kensic

# JSON output (for programmatic use)
python pact-memory.py query "sync conflict" --json --top 10
```

### Reindex all knowledge
```bash
python pact-memory.py reindex --project-root /path/to/project
```

### Index a single file
```bash
python pact-memory.py index-file bugs/sync/sync-003.yaml --project myproject
```

### Stats
```bash
python pact-memory.py stats
# Output: total docs, by type, by project
```

---

## Dashboard Integration

The dashboard server exposes vector search at `GET /recall?q=TEXT&top=5&type=bug`. The sidebar includes a search box that queries this endpoint and displays results inline.

---

## How Subagents Use It

The `pact-researcher` agent checks vector memory before doing external research:
1. Query for matching tags/topics
2. If a relevant document exists, read the source file
3. Only research externally if existing knowledge doesn't answer the question
4. After researching, save findings back (which auto-indexes them)

This creates a compound intelligence loop: each session's research makes future sessions smarter.
