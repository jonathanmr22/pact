# PACT — Real-World Examples

These examples demonstrate PACT's governance patterns in action. Each one shows: a failure mode, the PACT mechanism that prevents it, and why it works. They're organized by project type so you can find patterns relevant to your context.

**Jump to:**
- [Mobile App (Flutter/Dart)](#mobile-app-flutterdart) — BLE, encryption, local database, offline-first
- [Embedded AI Agent (Web App)](#embedded-ai-agent-web-app) — LLM embedded in a product, managing external APIs
- [General (Any Project)](#general-any-project) — Patterns that apply everywhere

---

# Mobile App (Flutter/Dart)

---

## The Forbidden Library Hook

**Pattern:** Mechanical enforcement via PreToolUse hook

**The failure:** The project migrated from one database library to another. The agent was told not to use the old one. It added imports for the old library three separate times across three sessions.

**The mechanism:**
```bash
if echo "$NEW_STRING" | grep -qi 'import.*hive'; then
  VIOLATIONS="${VIOLATIONS}BLOCKED: Hive is forbidden. Use Drift.\n"
fi
```

**Why it works:** Telling the agent "don't use X" is a suggestion. A hook that blocks the import is a guarantee. Zero violations since the hook was added.

---

## The Package Knowledge System

**Pattern:** Research-before-code via knowledge files + cognitive redirection

**The failure:** The agent spent 4+ hours debugging a Bluetooth package by guessing at the API from training data. The actual fix was a one-line version bump — the bug had been patched 2 years ago.

**The mechanism:** Per-package knowledge files (`knowledge/packages/{name}.yaml`) where verified research is saved. A cognitive redirection triggers the lookup:

> *"When a package doesn't behave as expected: Do I actually know this package, or am I guessing?"*

**Why it works:** The redirection converts "I think this API works like..." into "Let me check what we actually know." Research compounds — Session B inherits Session A's findings instead of re-discovering them.

---

## Architecture Map Preventing Single-Layer Edits

**Pattern:** Dependency awareness via SYSTEM_MAP.yaml

**The failure:** The agent renamed a database column but didn't update the service, provider, or screen that depend on it. Static analysis passed. The app crashed at runtime.

**The mechanism:**
```yaml
wiring:
  profiles:
    tables: [profiles, profile_tags]
    services: [ProfileService]
    state: ProfileProvider
    screens: [profile_screen, edit_profile_screen]
```

**Why it works:** The agent reads the map before editing and sees the full data flow. A table change triggers updates across all layers in the same session. Without the map, the agent sees one file at a time.

---

## Lifecycle Flow Preventing Initialization Bugs

**Pattern:** Multi-state awareness via feature flow documents

**The failure:** The agent reordered service initialization to fix a bug. The fix worked for normal app opens but broke fresh installs (no encryption key exists yet) and backup restores (key comes from the backup file, not secure storage).

**The mechanism:** A flow document listing every state the feature must survive:
```yaml
states:
  fresh_install:
    encryption_key: "Does not exist yet"
  normal_open:
    order: [read salt, prompt PIN, derive key, open DB]
  backup_restore:
    order: [extract archive, read manifest, prompt PIN, derive key, replace DB]
    danger: "Database overwritten at step 5 — point of no return"
```

**Why it works:** The agent sees all states before touching the code. A fix that works for one state but breaks another is caught before it's written, not after it ships.

---

## Bug Tracker Preventing Re-Investigation

**Pattern:** Compound debugging via structured investigation logs

**The failure:** Session A spent 3 hours finding a platform-specific bug. Session B encountered the same bug. Had no memory of Session A. Spent 2 hours before the developer intervened.

**The mechanism:**
```yaml
investigation:
  - attempt: 1
    tried: "Increase buffer size"
    result: "No effect on target platform"
  - attempt: 2
    tried: "Split into smaller chunks"
    result: "Partial fix — works on most devices, not the target"
  - attempt: 3
    tried: "Switch to notification-based transfer"
    result: "SUCCESS — bypasses the platform limitation entirely"
```

**Why it works:** Failed attempts are as valuable as the fix. Session B skips the 2 dead ends and goes straight to the working solution. Investigation time drops from hours to seconds.

---

## Read-Before-Write Preventing Confident Guessing

**Pattern:** Mechanical enforcement via hook chain (PostToolUse Read → PreToolUse Edit)

**The failure:** The agent edited a file it had never opened. It guessed the class structure from a similar file seen earlier. The guess was wrong.

**The mechanism:** A Read hook logs every file opened. An Edit hook checks the log. If the file wasn't read: blocked.

```
BLOCKED: Read 'lib/services/auth_service.dart' before editing.
```

**Why it works:** The agent can't pattern-match from memory when the hook forces it to read the actual file first. Guessing becomes mechanically impossible for existing files.

---

# Embedded AI Agent (Web App)

*These patterns apply when an LLM is embedded in a product and interacts with end users directly — no developer in the loop during normal operation.*

---

## Mechanical Knowledge Injection Before Writes

**Pattern:** API middleware that searches the knowledge base on every write — agent can't skip it

**The failure:** The agent sent an invalid field name to an external API. The correct field name was documented in the knowledge base from a prior session's research. The agent didn't search before acting.

**The mechanism:** The write proposal function automatically queries the knowledge base using the entity type and action keywords, then attaches matching articles to the tool result:

```javascript
// Runs on EVERY write proposal — not optional
const articles = await searchKnowledge(entityType, actionType);
if (articles.length) {
  result.knowledge_context = articles;
}
```

**Why it works:** The agent sees relevant knowledge whether it remembered to search or not. Past research is surfaced mechanically, not by willpower.

---

## Same-Session Duplicate Detection

**Pattern:** Middleware that checks prior actions in the same session before creating new ones

**The failure:** During a long session processing dozens of transactions, the agent created a record that already existed. Its system prompt said "check before creating." Under cognitive load, it skipped the check.

**The mechanism:**
```javascript
const priorActions = await db.query('agent_actions')
  .where('session_id', sessionId)
  .where('entity_type', entityType)
  .whereIn('status', ['pending', 'completed']);

for (const prev of priorActions) {
  if (Math.abs(prev.amount - proposedAmount) < 0.02) {
    result.duplicate_warning = `You already proposed this.`;
  }
}
```

**Why it works:** System prompt rules are suggestions. Middleware is law. The check runs on every write regardless of the agent's cognitive state.

---

## Auto-Sync Mirror After Every Write

**Pattern:** Post-write hook that immediately updates the local data mirror

**The failure:** The agent wrote to an external system successfully, but the local mirror it reads from wasn't updated. On the next read, the agent couldn't see its own changes — and sometimes re-created the same record.

**The mechanism:**
```javascript
if (writeSucceeded) {
  const fresh = await readFromExternalSystem(entityId);
  const { header, lines } = mapToMirrorFormat(fresh);
  await db.upsert('mirror_table', header);
  await db.replaceLines('mirror_lines', header.id, lines);
}
```

Deletes use soft-delete to preserve audit trail. Read queries filter out deleted/voided records.

**Why it works:** The agent always sees its own changes immediately. No manual sync step to forget.

---

## Memory Optimization via Knowledge Migration

**Pattern:** Moving stable data from memory files to queryable systems

**The failure:** The agent's memory file grew to ~4,000 tokens — mostly stable reference data that never changed between sessions. The file was approaching its size limit and the agent re-read it all every session.

**The mechanism:** Separate volatile state from durable knowledge:

| Volatile (stays in memory) | Durable (moves to knowledge base / rules table) |
|---|---|
| Current balances | Tax treatment rules |
| Active task list | Categorization patterns |
| Pending items | Historical records |
| ~1,500 tokens | Queryable, searchable, unlimited |

**Why it works:** Memory holds what changes. Knowledge base holds what's been learned. The agent searches for specific knowledge instead of re-reading everything.

---

## Recurring Automation Creating Silent Duplicates

**Pattern:** Verification redirection + structured investigation when anomalies are detected

**The failure:** An automation template in an external system was misconfigured — it generated identical records every 2 weeks for 5 months. The AI agent noticed the pattern but deferred, thinking "maybe this is intentional." The duplicates totaled over $48,000 in inflated reporting.

**How it was caught:** A developer queried the data mirror directly and confirmed all entries had identical content on different dates.

**The cognitive redirection added:**
> *"When you find suspected duplicates: verify the data yourself before dismissing or acting."*

**Why it matters:** AI agents are good at noticing anomalies but bad at having conviction about them. A structured verification process (query raw data, compare fields, count occurrences) turns a hunch into a confirmed finding.

---

## Error Notification Closing the Developer Visibility Gap

**Pattern:** Multi-layer error tracking (extract → log → notify → persist)

**The failure:** The agent's write operations occasionally failed. Errors were shown to the end user as "Something went wrong" but the developer had no visibility. Failures accumulated for weeks without investigation.

**The mechanism (four layers):**
1. **Extract** — Parse the error code from the API response into a dedicated column
2. **Log** — Structured console output with action ID, entity type, error code
3. **Notify** — Fire-and-forget email to the developer on every failure
4. **Persist** — Error investigation table where the agent logs what happened, what was tried, and the fix. Future sessions search this before debugging.

**Why it works:** Each layer catches what the others miss. The developer gets immediate awareness. The agent builds a compound library of fixes across sessions.

---

# General (Any Project)

---

## Cognitive Redirection Preventing Premature Agreement

**Pattern:** Verification before agreement

**The failure:** The user said "I think the cache is updating wrong." The agent immediately agreed and rewrote the cache logic. The cache was actually correct — the bug was in the database query.

**The redirection:**
> *"When the user makes a correction: Is this right?"* — verify independently before agreeing. Agreement is a conclusion, not a starting point.

**Why it works:** The question interrupts the agent's default pattern of validating whatever the user says. It forces a verification step between hearing a claim and acting on it.

---

## The Session Oath as Reset Detection

**Pattern:** Canary signal for context loss

**The problem:** Agent sessions reset silently. The developer keeps talking as if the agent remembers. Several confused exchanges pass before anyone realizes the context is gone.

**The mechanism:** A mandatory statement at session start:
```
"I have read and will follow all project rules."
```

When this appears unprompted mid-conversation, the developer knows the session has reset.

**Why it works:** It's a handshake. Presence at the start is normal. Presence mid-conversation is an alarm.

---

## Silent Linter Saving Context

**Pattern:** Output suppression for clean runs

**The problem:** The linter prints "No issues found!" after every successful edit. Over 100 edits, that's 100+ lines of noise consuming the context window.

**The mechanism:**
```bash
OUTPUT=$(dart analyze lib 2>&1)
if echo "$OUTPUT" | grep -q 'error •\|warning •'; then
  echo "$OUTPUT" | grep 'error •\|warning •' >&2
fi
exit 0
```

**Why it works:** Clean runs produce zero output. Only problems surface. Context window space is preserved for code and reasoning.

---

## Verify Before Relaying — The Glass Cannon Problem

**Pattern:** Independent verification before acting on another agent's findings

**The failure:** A developer managed two AI agent contexts. Agent A reported "10 duplicate entries worth $67,000." Agent B (the developer's assistant) relayed this as fact and recommended immediate deletion — without querying the actual data.

**The redirection:**
> *"Before acting on business-critical data: Have I verified this myself, or am I trusting another agent's assessment?"*

**Why it works:** AI agents are not reliable narrators of each other's findings. "Agent A says X" is a hypothesis, not a fact. The receiving context must verify independently. The cost of a wrong deletion on real data is not recoverable.
