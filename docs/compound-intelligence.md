# PACT Compound Intelligence — Knowledge That Grows With Every Session

A fresh AI session has training data and a context window. A session running PACT has training data + context window + every synthesis every previous session earned. That's compound intelligence — it grows with every session, and no knowledge dies when a context window closes.

---

## Three Systems

### 1. Research Knowledge Base

**Location:** `docs/reference/research/`
**Index:** `docs/reference/research/_RESEARCH.yaml`

When the agent researches something non-trivial — combining project code analysis with online docs, papers, or APIs — the *synthesis* is saved as a structured YAML file. Not the raw facts (those are re-findable) but the reasoning that connected project context to external evidence.

**Depth levels:**
- **shallow** — Quick lookup, single source, may need deepening
- **working** — Sufficient for current task, verified against code
- **deep** — Multiple sources cross-referenced, edge cases covered
- **definitive** — Authoritative, battle-tested in production

**Evolution actions:**
- **deepen** — Add more sources, verify edge cases
- **reframe** — Change the question based on new understanding
- **update** — Incorporate new information (package update, API change)
- **supersede** — Replace with a better synthesis

**Example:** An agent researches BLE advertising on Android. It reads the local `broadcast_service.dart`, searches for known Android BLE bugs, finds that OnePlus 13 has a coexistence check that blocks advertising when Bluetooth audio is connected. The synthesis — connecting the project's specific service code to an OEM-specific hardware bug found via GitHub issues — is the compound knowledge. No future session needs to rediscover this.

### 2. Knowledge Directory

**Location:** `docs/reference/KNOWLEDGE_DIRECTORY.yaml`

A single-file tag index across ALL knowledge systems. One read shows every file that touches a topic without opening them individually.

**Systems indexed:**
- Research files (`docs/reference/research/`)
- Bug investigations (`.claude/bugs/`)
- Reusable solutions (`.claude/bugs/_SOLUTIONS.yaml`)
- Package knowledge (`docs/reference/packages/`)
- Feature flows (`docs/feature_flows/`)

**Hook enforcement:** `pre-bash-guard.sh` blocks commits that include new knowledge files without updating the directory.

**Usage pattern:** Before researching anything, the agent reads the directory and checks for matching tags. If a file exists: read it first. If it answers the question, use it. If it's close, deepen it. If its staleness conditions triggered, update it.

### 3. Capability Baseline

**Location:** `docs/reference/PACT_BASELINE.yaml`

PACT's self-awareness layer. Records what the agent can do natively, what PACT compensates for, and how capabilities change over time.

**Tracks:**
- **Native capabilities** — reasoning, tools, context, collaboration
- **Native limitations** — no persistence, no self-awareness of past sessions, no visual output, no continuous execution
- **PACT compensations** — which PACT feature addresses which limitation, with status (active, enhanced, candidate_retire, retired)
- **PACT enhancements** — how native capabilities make PACT stronger
- **Capability deltas** — append-only log of capability changes over time

**Why it matters:** When the agent provider ships a new feature that makes a PACT rule redundant, this file is how the agent notices. When a new capability makes PACT stronger, this file is how the agent leans into it. Without it, PACT accumulates stale workarounds for problems that no longer exist.

---

## Package Knowledge Files

**Location:** `docs/reference/packages/{name}.yaml`

Per-package research files with verified API knowledge, gotchas, and past mistakes. Mandatory check before writing code that uses a package.

**Contains:**
- Package name, version, what it's used for
- Verified API patterns (confirmed working)
- Gotchas (things that don't work like expected)
- Claude's past mistakes with this package
- Links to docs, changelogs, GitHub issues

**Lifecycle:** Created when the agent first researches a package. Updated when behavior changes or new gotchas are discovered. Checked before every use — a 2-minute read that prevents hours of debugging incorrect API assumptions.

---

## Bug Tracking & Solutions

**Bugs:** `.claude/bugs/{system}/{system}-NNN.yaml`
**Solutions:** `.claude/bugs/_SOLUTIONS.yaml`
**Index:** `.claude/bugs/_INDEX.yaml`

Bug files document investigations in real time — not just the fix, but every failed attempt and the reasoning behind them. This is the knowledge that prevents the next session from repeating dead ends.

**Solutions** are graduated from bug files when a fix proves reusable. They're tagged and searchable via vector memory. Before debugging anything, the agent checks solutions for matching tags — a past session may have already solved the exact problem.

---

## How It All Connects

```
Agent starts session
  → Reads KNOWLEDGE_DIRECTORY (what already exists?)
  → Reads PACT_BASELINE (any capability changes?)
  → Checks package knowledge (before writing code)
  → Checks solutions (before debugging)
  → Checks research (before investigating)
  
Agent finishes work
  → Saves research synthesis (if non-trivial)
  → Updates package knowledge (if learned something new)
  → Closes bug file (if debugging)
  → Graduates solution (if fix is reusable)
  → Updates KNOWLEDGE_DIRECTORY (new entries)
  → Updates PACT_BASELINE (if capabilities changed)
```

Every exit enriches the system. Every entry leverages what came before. That's the compound.
