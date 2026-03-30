---
description: Search PACT's vector memory for relevant bugs, solutions, research, and feedback
disable-model-invocation: false
---

Search the PACT vector memory for knowledge relevant to the user's query. This uses semantic similarity to find matching bugs, graduated solutions, research synthesis, and task feedback across all indexed projects.

**How to use:** The user provides a description of what they're looking for — a symptom, a question, a topic. You run the query and present the results.

Run this command to search:

```bash
python ~/.claude/hooks/pact-memory.py query "{user's query}" --top 5 --json
```

If pact-memory.py isn't at that path, check:
- `.claude/hooks/pact-memory.py` (project-local)
- The PACT templates/memory directory

Present the results to the user as:

```
## PACT Recall: "{query}"

Found {N} relevant results:

1. **[{score}%] [{type}] {id}**
   {text preview}
   → {file path}

2. ...
```

If the score is above 40%, the result is likely relevant. Below 30% is weak — mention it's a loose match.

If no results are found, suggest the user run `python pact-migrate.py /path/to/project` to index their knowledge files, or note that the vector index may not have been built yet.
