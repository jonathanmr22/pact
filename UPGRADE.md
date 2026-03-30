# Upgrading to PACT v0.7.0 — Vector Memory

PACT v0.7.0 adds semantic vector search across your bugs, solutions, research, and task feedback. Your existing YAML files are untouched — the vector index sits alongside them as a fast fuzzy-search layer.

---

## What's New

- **Fuzzy matching**: "BLE write returns null" finds `meld-007.yaml` even if you never tagged it that way
- **Cross-system search**: one query searches bugs, solutions, research, and feedback simultaneously
- **Auto-indexed feedback**: task ratings from the dashboard are automatically added to the vector index
- **`/pact-recall` skill**: ask Claude to search PACT memory by describing what you're looking for
- **Task feedback consolidated**: ratings now live at `.claude/bugs/_FEEDBACK.jsonl` (alongside bugs and solutions)

## Upgrade Steps

### 1. Install dependencies (one time)

```bash
pip install sqlite-vec onnxruntime tokenizers huggingface_hub pyyaml
```

This installs:
- `sqlite-vec` — zero-dependency SQLite vector extension (~1MB)
- `onnxruntime` — runs the embedding model locally (~15MB)
- `tokenizers` — fast text tokenization (~5MB)
- `huggingface_hub` — downloads the model on first run (~1MB)
- `pyyaml` — reads your YAML knowledge files

The embedding model (`all-MiniLM-L6-v2`, ~80MB) downloads automatically on first use. It runs entirely on your CPU — no API keys, no cloud, no GPU needed.

### 2. Run the migration

```bash
python pact-migrate.py /path/to/your/project
```

This will:
1. Read all your bug files, solutions, and research files (read-only — nothing is modified)
2. Copy `~/.claude/pact-ratings.jsonl` → `.claude/bugs/_FEEDBACK.jsonl` (if it exists)
3. Build the vector index at `~/.claude/pact-memory.db`
4. Run a test query to verify everything works

**Output looks like:**
```
PACT Memory Migration v0.7.0
Project: /path/to/your/project
============================================================

[1/4] Checking dependencies...
  All dependencies installed.

[2/4] Checking feedback file location...
  Copied: ~/.claude/pact-ratings.jsonl → .claude/bugs/_FEEDBACK.jsonl

[3/4] Building vector search index...
  Indexed 31 documents.

[4/4] Verifying index...
  Total documents: 31
  By type: {"bug": 21, "solution": 10}
  Test query OK — vector search is working.

============================================================
Migration complete!
```

### 3. Update your hooks (if not using the plugin)

If you installed PACT manually (not via the Claude Code plugin), copy the updated files:

- `templates/hooks/session-register.sh` → `.claude/hooks/session-register.sh`
- `templates/memory/pact-memory.py` → `.claude/hooks/pact-memory.py`
- `templates/dashboard/pact-server.py` → `.claude/hooks/pact-server.py`

### 4. Test it

```bash
python pact-memory.py query "your bug symptom here" --top 5
```

You should see matching bugs and solutions ranked by semantic similarity.

---

## What Didn't Change

- All your YAML files: **untouched**
- SYSTEM_MAP, preflight checks, feature flows, package knowledge: **still YAML, still deterministic**
- The dashboard: **still works** (now also writes feedback to the new location)
- Hooks: **backward compatible** (new features are additive)

## FAQ

**Q: Do I need a GPU?**
No. The embedding model runs on CPU. Embedding 30 documents takes under a second.

**Q: How big is the vector database?**
Tiny. 30 documents ≈ 200KB. Even at 1000 documents it would be under 10MB.

**Q: What if I skip the migration?**
Everything still works. The vector search layer is additive — PACT falls back to tag-based lookup in the Knowledge Directory if the vector index doesn't exist.

**Q: Can I re-run the migration?**
Yes. It's idempotent — existing entries get updated, not duplicated.

**Q: Where does the model get stored?**
`~/.cache/pact-models/` (~80MB). Shared across all projects.
