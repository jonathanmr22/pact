# PACT — Real-World Examples

These examples are drawn from real production projects governed by PACT. They're organized by project type so you can find patterns relevant to your own work.

**Jump to:**
- [Mobile App (Flutter/Dart)](#mobile-app-flutterdart) — BLE, encryption, local database, offline-first
- [Embedded AI Agent (Web App)](#embedded-ai-agent-web-app) — LLM embedded in a product, managing external APIs
- [General (Any Project)](#general-any-project) — Patterns that apply everywhere

---

# Mobile App (Flutter/Dart)

*Source: A mobile app with 350+ source files, 70+ database tables, 16 serverless edge functions, BLE peer-to-peer communication, and an encrypted local database.*

---

## The Forbidden Library Hook

**The failure:** The project migrated from a key-value store (Hive) to a relational ORM (Drift). The agent was told not to use Hive. It added Hive imports three separate times across three sessions, each time requiring a manual revert.

**The hook:**
```bash
if echo "$NEW_STRING" | grep -qi 'import.*hive'; then
  VIOLATIONS="${VIOLATIONS}BLOCKED: Hive is forbidden. Use Drift.\n"
fi
```

**Result:** Zero Hive imports since the hook was added. The agent sees "BLOCKED: Hive is forbidden" and immediately switches to Drift. No willpower required.

---

## The Package Knowledge System

**The failure:** The agent spent 4+ hours debugging a Bluetooth package. It was pattern-matching from training data, guessing at the API, and writing increasingly baroque workarounds. When finally pushed to read the actual documentation, it discovered:

1. The installed version (1.0.0) was 2+ years old
2. The exact bug had been fixed in v1.0.1
3. When asked how the project ended up on v1, the agent fabricated a timeline

**The fix:** A per-package knowledge file (`docs/reference/packages/{name}.yaml`) where research findings are saved. A cognitive redirection was added:

> *"When a package doesn't behave as expected: Do I actually know this package, or am I guessing?"*

**The rule:** The agent must check the knowledge file before writing code. If the file doesn't exist or doesn't cover the question, the agent must research online and save findings before proceeding.

---

## Architecture Map Preventing Single-Layer Edits

**The failure:** The agent changed a database table's column name but didn't update the service that reads it, the provider that caches it, or the screen that displays it. Static analysis passed. The app crashed at runtime.

**The fix:** A `SYSTEM_MAP.yaml` entry:
```yaml
wiring:
  profiles:
    tables: [profiles, profile_tags]
    services: [ProfileService]
    state: ProfileProvider — caches: _profiles (List), _profilesById (Map)
    screens: [profile_screen, edit_profile_screen]
    cascade_on_delete: "profile_tags CASCADE"
```

Now the agent reads the map before editing and sees every file in the data flow. A table change triggers updates to the service, provider, and screen in the same session.

---

## Lifecycle Flow Preventing Initialization Bugs

**The failure:** The agent "fixed" the encryption system by reordering service initialization. The fix worked for normal app opens but broke the fresh-install path (no encryption key exists yet) and the backup-restore path (encryption key comes from the backup, not secure storage).

**The fix:** A lifecycle flow document:
```yaml
states:
  fresh_install:
    encryption_key: "Does not exist yet"
    database: "Not created"
    user_flow: "Onboarding → create PIN → derive key → create encrypted DB"

  normal_open:
    order:
      1. "Read salt from secure storage"
      2. "Prompt for PIN"
      3. "Derive key: PBKDF2(PIN, salt, 600000 iterations)"
      4. "Open database with derived key"
    assumes: [salt exists in secure storage, user knows PIN]

  backup_restore:
    order:
      1. "Extract backup archive"
      2. "Read encryption metadata from archive manifest"
      3. "Prompt for PIN"
      4. "Derive key from manifest salt + PIN"
      5. "Replace database file with backup"
      6. "Open restored database with derived key"
    danger: "Point of no return: database file is overwritten at step 5"
```

The agent now checks this document before touching encryption code. It sees all the states the feature must survive, not just the one it's currently fixing.

---

## Bug Tracker Preventing Re-Investigation

**The failure:** Session A spent 3 hours tracking down a Samsung-specific BLE bug. Found the root cause (the device caps GATT reads at 512 bytes), implemented a fix (switched to notification-based transfer), documented everything in conversation. Session B encountered the same bug. Had no memory of Session A. Spent 2 hours before the developer intervened.

**The fix:** A structured bug tracker where investigations are logged in real time:
```yaml
id: ble-002
title: "Samsung 512-byte GATT read cap"
status: fixed
tags: [ble, platform-specific, samsung]

symptom: "Profile image truncated to 512 bytes on Samsung devices"
root_cause: "Samsung BLE stack caps ATT_READ at 512 bytes, ignores ATT_READ_BLOB"

investigation:
  - attempt: 1
    tried: "Increase MTU to 517"
    result: "MTU negotiation hangs — ble_peripheral doesn't respond"
  - attempt: 2
    tried: "Split image into 512-byte reads"
    result: "Works on Pixel, still truncated on Samsung"
  - attempt: 3
    tried: "Switch to BLE notifications for image transfer"
    result: "SUCCESS — 20-byte chunks bypass the read limit entirely"

fix: "Image transferred via sequenced BLE notifications instead of GATT reads"
prevention: "Added to _SOLUTIONS.yaml: Samsung BLE read cap = use notifications"
```

Now Session B's first action on any BLE bug is `check _SOLUTIONS.yaml`. The 3-hour investigation becomes a 30-second lookup.

---

## Read-Before-Write Preventing Confident Guessing

**The failure:** The agent edited a service file to add a new method. It had never read the file — it guessed at the class structure based on a similar service it had seen earlier in the session. The guess was wrong (different constructor signature, different import pattern), and the edit broke compilation.

**The fix:** A PostToolUse hook on Read logs every file the agent opens. A PreToolUse hook on Edit checks whether the file was logged. If not: blocked.

```
BLOCKED: Read 'lib/services/auth_service.dart' before editing. You haven't opened this file.
```

The agent is forced to read the actual file before modifying it. Pattern-matching from similar files is no longer possible for existing files.

---

# Embedded AI Agent (Web App)

*Source: An AI bookkeeping agent embedded in a web application, managing QuickBooks Online for a small business. The agent reads from a local Supabase data mirror and writes to QBO via API. End users (the business owner) interact directly — no developer in the loop.*

---

## Knowledge Enforcement Preventing Wrong API Calls

**The failure:** The agent tried to update a financial transfer's memo field. It sent `{ Memo: "Funds from shareholder" }` — the same field name that works for most transaction types. The API returned error 2010: "Request has invalid or unsupported property." Transfer entities use `PrivateNote`, not `Memo`. The agent retried the same payload and failed again, then told the business owner it couldn't update the memo.

**The fix (three layers):**

1. **Code fix:** The tool handler detects Transfer entities and routes memo updates to `PrivateNote` with a full non-sparse payload (Transfer also requires `FromAccountRef`, `ToAccountRef`, and `Amount` on every update).

2. **Knowledge article:** The fix was saved to the knowledge base with tags `['transfer', 'error 2010', 'PrivateNote', 'Memo']`. Future sessions find it instantly.

3. **Mechanical enforcement:** Every write proposal automatically searches the knowledge base and attaches matching articles to the tool result. Even if the agent forgets to search, the relevant article appears in context before the write executes.

**Result:** The agent can never send `Memo` to a Transfer again — the code prevents it. And new API quirks discovered in the future are automatically surfaced via the knowledge-base-before-write pipeline.

---

## Same-Session Duplicate Detection

**The failure:** During a long session posting dozens of transactions, the agent found a $1,500 bank transfer and created a new deposit for it. The deposit already existed (posted in a prior session). The agent's system prompt said "check before creating" — but under cognitive load, it skipped the check. The duplicate required manual deletion by the business owner.

**The fix:** Mechanical duplicate detection in the write proposal middleware:

```javascript
// Runs on EVERY transaction-creating action — agent cannot skip this
const { data: priorActions } = await supabase
  .from('agent_actions')
  .select('id, task_label, status, proposed_payload')
  .eq('session_id', sessionId)
  .eq('entity_type', entityType)
  .in('status', ['pending', 'completed']);

for (const prev of priorActions) {
  const prevAmount = extractAmount(prev.proposed_payload);
  if (Math.abs(prevAmount - proposedAmount) < 0.02) {
    result.duplicate_warning = `You already ${prev.status} a ${entityType} for $${prevAmount} this session.`;
    break;
  }
}
```

**Key insight:** System prompt rules are suggestions. Middleware is law. The agent can forget to self-check under load, but it cannot bypass code that runs before every write.

---

## Data Mirror Sync Gap

**The failure:** The agent wrote transactions to an external accounting system successfully. But the local database mirror that the agent reads from was NOT updated after writes — the agent had to manually call a sync tool, which it often forgot. The agent would create a transaction, then be unable to see it in its own read queries. Sometimes it re-created the same transaction because it couldn't find evidence of the first one.

**The fix:** Auto-sync in the write execution path:

```javascript
// After EVERY successful write — automatic, not optional
if (writeSucceeded && isTransactionType) {
  const fullEntity = await readFromExternalSystem(entityType, entityId);
  const { header, lines } = mapTransaction(fullEntity);
  await supabase.from('transactions').upsert(header);
  await supabase.from('transaction_lines').delete().eq('transaction_id', header.id);
  await supabase.from('transaction_lines').insert(lines);
}
```

For deletes, the mirror uses soft-delete (preserving audit trail):
```javascript
if (actionType === 'delete') {
  await supabase.from('transactions').update({
    status: 'deleted', deleted_at: new Date()
  }).eq('id', entityId);
}
```

Read queries filter out deleted/voided records:
```javascript
const { data } = await supabase.from('transactions')
  .select('*')
  .not('status', 'in', '("deleted","voided")');
```

**Result:** The agent always sees its own changes immediately. No manual sync required. Deleted records preserve history without polluting active queries.

---

## Memory Optimization via Knowledge Migration

**The failure:** The agent had a single memory file (~4,000 tokens) containing everything: company structure, bank accounts, categorization rules, invoice conventions, tax deduction rules, vehicle fleet details, and historical payment records. The memory was approaching its size limit and the agent had to re-read the entire file every session — most of which was stable reference data that never changed.

**The fix:** Migrate stable data to queryable systems:

| Before (memory file) | After (structured storage) |
|---|---|
| Categorization rules (1,200 tokens) | `categorization_rules` database table — queryable by pattern |
| Tax deduction rules | Knowledge base article — searchable by topic |
| Invoice numbering format | Knowledge base article |
| Historical payment records | Knowledge base article |
| **Volatile data stays:** balances, pending tasks, active rules | Memory file (~1,500 tokens) |

**Result:** Memory file shrunk 60%. Stable data is now queryable (the agent searches for "home office deduction" instead of re-reading a 4,000-token YAML blob). Categorization rules moved from flat text to a structured table with confirmation history.

**Principle:** Memory holds volatile state. Everything else lives in searchable, structured systems.

---

## Recurring Template Silently Creating Duplicates

**The failure:** A bookkeeper created a payroll journal entry template in the accounting system and set it to "Scheduled, Every 2 Weeks." But the template was created from a single pay period — so every 2 weeks, the system auto-generated an identical entry for the same pay period. Over 5 months, this created 10 duplicate entries totaling over $48,000 in inflated expenses. Neither the business owner nor the AI agent caught it because the entries had sequential document numbers and different dates — they looked legitimate individually.

**How it was caught:** A developer audited the AI agent's chat history and noticed the agent had flagged "possible duplicates" but wasn't confident enough to act. The developer queried the database mirror directly:

```sql
SELECT doc_number, txn_date, description, amount
FROM transactions
WHERE description LIKE '%Pay Period 10/27%'
ORDER BY txn_date;
```

All 11 entries had the exact same description, exact same line items, exact same amounts — just different dates, exactly 2 weeks apart.

**The fix:**
1. Deleted the recurring template to stop future duplicates
2. Identified and removed the 10 duplicate entries
3. Added a cognitive redirection: "When you find suspected duplicates, verify the data yourself before dismissing or acting"
4. Added a knowledge base article documenting the pattern

**Key lesson:** AI agents are good at noticing anomalies but bad at having conviction about them. The agent saw the pattern but deferred to "maybe this is intentional." A structured verification process (query the raw data, compare fields, count occurrences) turns a hunch into a confirmed finding.

---

## Error Notification Preventing Silent Failures

**The failure:** The agent's write operations occasionally failed — the external API returned validation errors. The errors were shown to the end user in the chat as "Something went wrong" messages, but the developer had no visibility. Failed writes accumulated over weeks without investigation.

**The fix (four layers):**

1. **Error code extraction:** Parse the error code from the API response and store it in a dedicated column for aggregation.

2. **Console logging:** Structured error logs with action ID, entity type, and error code — visible in hosting platform logs.

3. **Email notification:** Fire-and-forget email to the developer on every write failure:
```javascript
if (writeFailed) {
  fetch('https://api.resend.com/emails', {
    method: 'POST',
    body: JSON.stringify({
      to: 'developer@example.com',
      subject: `Write Failed — ${actionType} (${errorCode})`,
      html: `<p>Action: ${actionId}</p><p>Error: ${errorMessage}</p>`
    })
  }).catch(() => {}); // fire-and-forget
}
```

4. **Error investigation tracking:** A database table where the agent logs structured investigation records. Future sessions search this before debugging from scratch.

**Result:** The developer gets an email within seconds of any failure. Error patterns become visible through the error code column. And the agent builds a growing library of fixes that compound across sessions.

---

# General (Any Project)

*Patterns that apply to CLI agents, embedded agents, and any AI-assisted development.*

---

## Cognitive Redirection Preventing Premature Agreement

**The failure:** The user said "I think the cache is updating wrong." The agent immediately agreed and rewrote the cache logic. The original cache was actually correct — the bug was in the database query, which returned stale data due to a missing index.

**The redirection:**
> *"When the user makes a correction: Is this right?"* — verify independently before agreeing. Agreement is a conclusion, not a starting point.

---

## The Session Oath as Reset Detection

**The problem:** Agent sessions reset silently — either from context compression or unknown triggers. Without a signal, the developer keeps talking as if the agent remembers everything. The responses become confused, and it takes several exchanges to realize the context is gone.

**The fix:** A mandatory recitation at session start:
```
"I have read and will follow all project rules."
```

When this appears unprompted in the middle of a conversation, the developer knows the session has reset. It's a handshake — "I see you, new agent" — that tells the developer to reframe their communication.

---

## Silent Linter Saving Context

**The problem:** Over a 100-edit session, the linter prints "No issues found!" after every successful edit. That's 100+ lines of noise consuming context window space that could hold actual code or reasoning.

**The fix:**
```bash
OUTPUT=$(dart analyze lib 2>&1)
if echo "$OUTPUT" | grep -q 'error •\|warning •'; then
  echo "$OUTPUT" | grep 'error •\|warning •' >&2
fi
exit 0
```

Clean runs produce zero output. Only problems surface. A tiny change with outsized impact on context efficiency.

---

## Verify Before Relaying — The Glass Cannon Problem

**The failure:** A developer was managing two AI agent sessions — one embedded in a product, one in the terminal. The terminal agent read the embedded agent's chat logs and found the embedded agent had flagged "10 duplicate entries worth $67,000." The terminal agent relayed this to the developer as fact and recommended immediate deletion — without ever querying the actual data to verify.

**The fix:** A permanent feedback rule:
> Never relay fix instructions from one agent context to another without independently verifying the data. "Agent A says X is a duplicate" is not verification. Query the raw data yourself.

**The redirection:**
> *"Before recommending action on business-critical data: Have I verified this myself, or am I trusting another agent's assessment?"*

**Key lesson:** AI agents are not reliable narrators of each other's findings. When one agent reports something to another context, the receiving agent (or developer) must verify independently. The cost of a wrong deletion on real financial data is not recoverable by saying "the other agent told me to."
