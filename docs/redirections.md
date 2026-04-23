# PACT Cognitive Redirections — Self-Check Questions

Cognitive redirections are questions the agent asks itself at decision points. They're the lightest enforcement layer — guidance, not gates. They work well for routine decisions but can be skipped under cognitive pressure (which is why the heaviest patterns were upgraded to checkpoints).

**The agent has autonomy to add new redirections** based on observed failure patterns. Future sessions inherit the awareness.

---

## The Catalog

### Before Editing

> **"What depends on this, and what does this depend on?"**

Trace 3 hops in both directions. Table → service → provider → screen. Screen → provider → service → table. Use SYSTEM_MAP. Stop expanding when the next hop no longer serves the user's intention.

> **"Have I actually read this file, or am I guessing?"**

Pattern-matching from other files is not the same as knowing this file. Read it. (Hook-enforced via read-before-write, but the redirection catches conceptual guessing even after reading.)

> **"Why does this code exist?"**

Read the comments above, inline, and surrounding code you're about to delete. Comments document intent. If there's a comment explaining WHY, understand that reason and confirm it no longer applies. If there are no comments, check git blame or ask.

### Before Writing Code

> **"Do I actually know this package, or am I guessing?"**

If you haven't verified this package's behavior in this session, you do not know it. Training data is stale. Lookup order: (1) `knowledge/packages/{name}.yaml`, (2) if not sufficient, WebSearch/WebFetch, (3) save findings to the package knowledge file.

> **"Can I delegate this?"**

Before spending 5,000 tokens reading a changelog: would Trinity do this? Before writing 20 boilerplate test cases: would M2.5 handle this with a pattern file? The orchestrator's job is to think, decide, and verify — not to grind.

> **"Does this need project understanding, online research, or both?"**

Project-level research answers "how does THIS codebase do it?" Online research answers "how does the WORLD do it?" Default to both. Skipping either means building on half an understanding.

### Security & Architecture

> **"Have I researched what exists, or am I inventing from scratch?"**

The security community has spent decades building battle-tested patterns. Search for how Signal, Matrix, Keybase, age, and academic systems solve the same problem. Starting from the best existing work and adapting it is both proven and tailored.

### During Bug Fixes

> **"Am I treating a symptom or the core issue?"**

The first fix that makes the symptom disappear is almost never the right fix. Trace the causal chain back to where the bad state is PRODUCED, not where it's OBSERVED. Ask: "If I remove this fix, does the problem come back?"

> **"Can I fix this forward?"**

Never revert from git history unless the user specifically asks. "Broken" means "fix the current code." Reverting destroys the work in the new approach and teaches nothing.

### During Evaluation

> **"Is this objection real, or am I folding?"**

When you find a potential problem during review, stress-test the objection. (1) Does this actually occur in practice? (2) Does the underlying system already handle it? (3) Can you verify with code/docs? The failure pattern: propose correct solution → find hypothetical concern → immediately abandon it.

> **"Have I compared them, or am I just iterating?"**

If you're trying approaches sequentially (try → fail → try different → fail), STOP. List the top 3 options. For each: what it solves, what it doesn't, what it costs. A 5-minute comparison table saves hours of spiraling.

### Before Declaring Done

> **"Did I do everything the user asked?"**

Re-read their message word by word. If they asked for 3 things and you did 1, you're not done.

> **"What did my changes just make stale?"**

Added a table → SYSTEM_MAP stale. Added a provider → cheatsheet stale. Changed a service → feature flow may be stale. `dart analyze` clean does not equal governance clean.

> **"Am I the user right now?"**

Walk through the entire user journey for the feature you just built. What do you see first? Tap the thing. What happens? Try edge cases at zero. This mental walkthrough catches what code review can't.

### Capability Awareness

> **"What can't I do? What CLI tool handles this?"**

You have Bash and the entire CLI ecosystem. Check for ffmpeg, imagemagick, python, etc. The correct response to "can you do X with file type Y" is "let me find the right tool."

> **"Is something about my capabilities different?"**

If you notice a tool you don't recognize or a capability that wasn't there at baseline, check `PACT_BASELINE.yaml`. Add a `capability_deltas[]` entry. This is how PACT evolves with you.

---

## Adding New Redirections

When you notice a moment where a question would have led to a better outcome:

1. Phrase it as a question the agent asks itself
2. Include the context trigger ("When about to...")
3. Add it to the cognitive redirections section of CLAUDE.md
4. If you find it being skipped under load repeatedly, promote it to a checkpoint
