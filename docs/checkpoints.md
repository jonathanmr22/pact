# PACT Checkpoints — Required Reasoning Gates

Checkpoints are structured blocks the agent must output *before acting*. They're visible to the user, verifiable, and much harder to skip than internal questions. When a trigger condition is met, the agent outputs a `<checkpoint>` block — if the reasoning is weak, the user can challenge it before any code is written.

**Why checkpoints exist:** Cognitive redirections (the lighter layer) get skipped under cognitive pressure. A checkpoint converts "think about this" into "show me your thinking in this format." The format requirement is what makes it stick.

**Research basis:** Claude's extended thinking is internal and invisible. Output-level format requirements are the proven mechanism for structured reasoning — visible, verifiable, and resistant to cognitive load.

---

## The Seven Checkpoint Types

### 1. bug_fix

**Trigger:** User reports something broken, wrong, not working, or regressed.

```xml
<checkpoint type="bug_fix">
<symptom>[What the user reported]</symptom>
<causal_chain>[Trace from where the bad state is OBSERVED back to where it is PRODUCED]</causal_chain>
<core_issue>[The line/mechanism that creates the bad state]</core_issue>
<bug_file>[Path to .claude/bugs/ file — create it NOW if it doesn't exist]</bug_file>
</checkpoint>
```

**Why this matters:** The first fix that makes the symptom disappear is almost never the right fix. This checkpoint forces tracing the causal chain *backwards* — from the UI where it's observed to the line of code that produces the bad state. The bug file requirement ensures failed attempts are documented for future sessions.

**Hook integration:** `post-edit-checkpoint-audit.sh` detects when a bug_fix checkpoint should have been used (issue tracker flag active) and logs to the dashboard for adoption tracking.

### 2. solution_compare

**Trigger:** Considering 2+ approaches to solve a problem.

```xml
<checkpoint type="solution_compare">
<options>
  1. [Option A — what it solves, what it costs, what it depends on]
  2. [Option B — same]
  3. [Option C — same]
</options>
<research>[What you looked up to evaluate these. Name sources.]</research>
<decision>[Which option and why]</decision>
</checkpoint>
```

**Why this matters:** Prevents the "spiral" — trying one approach, abandoning it, trying another, abandoning it. A 5-minute comparison table saves hours. The research requirement ensures the agent investigates unknowns before evaluating.

### 3. package_verify

**Trigger:** Writing code that calls a package/library API not verified this session.

```xml
<checkpoint type="package_verify">
<package>[Name and version]</package>
<source>[Where verified: docs, package knowledge file, WebSearch]</source>
<verified_api>[The specific method/pattern confirmed]</verified_api>
</checkpoint>
```

**Why this matters:** AI training data contains stale and incorrect API signatures. 10 minutes reading docs saves hours of debugging workarounds for APIs that don't work like the agent assumed.

### 4. dependency_trace

**Trigger:** About to edit a file that appears in SYSTEM_MAP.yaml or has 3+ downstream dependents.

```xml
<checkpoint type="dependency_trace">
<file>[File being edited]</file>
<upstream>[What this file depends on — 3 hops]</upstream>
<downstream>[What depends on this file — 3 hops]</downstream>
<cache_impact>[Any caches that need updating]</cache_impact>
</checkpoint>
```

**Why this matters:** Single-layer edits are the most common source of regressions. Change a table but not the provider. Change a provider but not the cache map. This checkpoint forces the agent to see the full data flow before touching any file.

### 5. done_check

**Trigger:** About to declare a task complete or say "done."

```xml
<checkpoint type="done_check">
<user_request>[Re-read their exact words — did you do everything they asked?]</user_request>
<stale_artifacts>[What docs/maps/schemas did your changes make stale?]</stale_artifacts>
<untested>[What ripple effects did you not verify?]</untested>
</checkpoint>
```

**Why this matters:** Partial delivery of explicit requests is worse than no delivery — it creates the illusion of progress. `dart analyze` clean does not mean governance clean. This checkpoint forces checking both.

### 6. ui_work

**Trigger:** About to build or significantly modify a UI element.

```xml
<checkpoint type="ui_work">
<task>[What UI element you're building or modifying]</task>
<existing_widgets>[Reusable widgets checked — list what you looked at]</existing_widgets>
<reference_screens>[Existing screens you read for design guidance]</reference_screens>
<design_pattern>[Pattern: matches X screen, extends Y widget, or net-new because Z]</design_pattern>
</checkpoint>
```

**Why this matters:** Every screen should feel like it belongs to the same family. The failure mode: building a bespoke widget from scratch that looks subtly different from the rest of the app, or reinventing something that already exists.

### 7. progress_update

**Trigger:** Completing a logical unit of work during a multi-step operation.

```xml
<checkpoint type="progress_update">
<milestone>[What just completed — be specific]</milestone>
<state_now>[Current state with concrete counts/facts]</state_now>
<pending_work_updated>[yes/no — if no, do it now]</pending_work_updated>
</checkpoint>
```

**Why this matters:** An agent that works for hours without leaving breadcrumbs creates a session that looks like it did nothing. The next session starts from scratch. Hook integration: `post-edit-progress-check.sh` warns after 30 edits or 20 minutes without a PENDING_WORK update.

---

## Promoting Redirections to Checkpoints

When a cognitive redirection is consistently skipped under load, promote it:

1. Identify the failure pattern (what goes wrong when the redirection is skipped)
2. Design a structured output format that forces the reasoning
3. Add the checkpoint type to the instructions file
4. Optionally: add a hook that detects when the checkpoint should have been used (for adoption tracking)

The agent has autonomy to propose new checkpoints when it notices patterns.
