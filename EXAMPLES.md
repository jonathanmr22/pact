# PACT — Real-World Examples

These examples are drawn from a mobile app project built over 3 months with an AI coding agent (350+ source files, 70+ database tables, 16 serverless edge functions, BLE peer-to-peer communication, encrypted local database).

---

## Example 1: The Forbidden Library Hook

**The failure:** The project migrated from a key-value store (Hive) to a relational ORM (Drift). The agent was told not to use Hive. It added Hive imports three separate times across three sessions, each time requiring a manual revert.

**The hook:**
```bash
if echo "$NEW_STRING" | grep -qi 'import.*hive'; then
  VIOLATIONS="${VIOLATIONS}BLOCKED: Hive is forbidden. Use Drift.\n"
fi
```

**Result:** Zero Hive imports since the hook was added. The agent sees "BLOCKED: Hive is forbidden" and immediately switches to Drift. No willpower required.

---

## Example 2: The Package Knowledge System

**The failure:** The agent spent 4+ hours debugging a Bluetooth package. It was pattern-matching from training data, guessing at the API, and writing increasingly baroque workarounds. When finally pushed to read the actual documentation, it discovered:

1. The installed version (1.0.0) was 2+ years old
2. The exact bug had been fixed in v1.0.1
3. When asked how the project ended up on v1, the agent fabricated a timeline

**The fix:** A per-package knowledge file (`docs/reference/packages/{name}.yaml`) where research findings are saved. A cognitive redirection was added:

> *"When a package doesn't behave as expected: Do I actually know this package, or am I guessing?"*

**The rule:** The agent must check the knowledge file before writing code. If the file doesn't exist or doesn't cover the question, the agent must research online and save findings before proceeding.

---

## Example 3: Architecture Map Preventing Single-Layer Edits

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

## Example 4: Lifecycle Flow Preventing Initialization Bugs

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

## Example 5: Cognitive Redirection Preventing Premature Agreement

**The failure:** The user said "I think the cache is updating wrong." The agent immediately agreed and rewrote the cache logic. The original cache was actually correct — the bug was in the database query, which returned stale data due to a missing index.

**The redirection:**
> *"When the user makes a correction: Is this right?"* — verify independently before agreeing. Agreement is a conclusion, not a starting point.

---

## Example 6: Bug Tracker Preventing Re-Investigation

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

## Example 7: The Session Oath as Reset Detection

**The problem:** Agent sessions reset silently — either from context compression or unknown triggers. Without a signal, the developer keeps talking as if the agent remembers everything. The responses become confused, and it takes several exchanges to realize the context is gone.

**The fix:** A mandatory recitation at session start:
```
"I have read and will follow all project rules."
```

When this appears unprompted in the middle of a conversation, the developer knows the session has reset. It's a handshake — "I see you, new agent" — that tells the developer to reframe their communication.

---

## Example 8: Silent Linter Saving Context

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

## Example 9: Read-Before-Write Preventing Confident Guessing

**The failure:** The agent edited a service file to add a new method. It had never read the file — it guessed at the class structure based on a similar service it had seen earlier in the session. The guess was wrong (different constructor signature, different import pattern), and the edit broke compilation.

**The fix:** A PostToolUse hook on Read logs every file the agent opens. A PreToolUse hook on Edit checks whether the file was logged. If not: blocked.

```
BLOCKED: Read 'lib/services/auth_service.dart' before editing. You haven't opened this file.
```

The agent is forced to read the actual file before modifying it. Pattern-matching from similar files is no longer possible for existing files.
