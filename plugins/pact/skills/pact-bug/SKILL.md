---
description: Log a bug investigation using PACT's structured bug tracker
disable-model-invocation: false
---

Create or update a PACT bug tracking file. Follow this protocol:

**Step 1: Check existing solutions first.**
Read `bugs/_SOLUTIONS.yaml` and search for matching tags. If a previous session already solved this class of bug, report the existing solution instead of re-investigating.

**Step 2: Create the bug file.**
If no existing solution matches, create `bugs/{system}/{system}-NNN.yaml` with:
- `id`, `title`, `status: investigating`, `severity`, `system`, `tags`
- `symptom` — what was observed
- `expected` — what should happen
- `investigation` — log every attempt in real time (attempt number, what was tried, result)

**Step 3: Update as you investigate.**
Add each attempt to the investigation log as you try things. Failed attempts are as valuable as successes — they prevent the next session from wasting hours on dead ends.

**Step 4: When fixed, complete the record.**
Update `status: fixed`, add `root_cause`, `fix`, `files_changed`, and `prevention`.

**Step 5: Graduate reusable solutions.**
If the fix applies to a class of bugs (not just this specific instance), add an entry to `bugs/_SOLUTIONS.yaml` with tags for future matching.
