# PACT for Embedded Agents

**When Claude (or any LLM) is embedded in your product — not running in a terminal.**

PACT was designed for CLI agents (Claude Code, Gemini CLI), but its principles apply to any context where an AI agent makes decisions across sessions. This guide shows how to translate PACT's governance patterns into a web application, API service, or any environment where the agent runs server-side.

---

## Why Embedded Agents Need Governance

CLI agents have a developer watching every response. Embedded agents often don't — they interact with end users (business owners, employees, customers) who trust the agent to get it right. The stakes are higher:

- **No developer in the loop** — mistakes reach the end user directly
- **Multi-session amnesia** — each conversation starts cold unless you build persistence
- **Tool access without oversight** — the agent can call APIs, modify databases, send emails
- **Compound errors** — a wrong categorization in session 1 becomes a wrong report in session 10

PACT's governance prevents these failure modes whether the agent runs in a terminal or a browser.

---

## Translation Guide: CLI → Embedded

### Cognitive Redirections

**CLI (CLAUDE.md):**
```markdown
- When about to write code based on memory: "Have I actually read this file?"
```

**Embedded (System Prompt):**
```
## Cognitive Redirections — Questions to Ask Yourself
- Before proposing ANY write: "Have I searched the knowledge base for the correct treatment?"
- When the user corrects you: "Did I save this correction for future sessions?"
- When encountering something unfamiliar: "Do I actually know this, or am I guessing?"
```

**Key difference:** CLI redirections are reinforced by hooks that block violations. Embedded redirections rely on system prompt compliance unless you add mechanical enforcement (see below).

---

### Knowledge Persistence

**CLI:**
```
docs/reference/packages/{name}.yaml     # Package knowledge
docs/reference/research/_RESEARCH.yaml   # Research synthesis
.claude/bugs/_SOLUTIONS.yaml             # Graduated fixes
```

**Embedded:**
```sql
-- Single knowledge table replaces all three
CREATE TABLE knowledge_base (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL,
  category text NOT NULL,        -- 'domain_rules', 'api_workflow', 'error_fix', 'user_specific'
  content text NOT NULL,
  tags text[] DEFAULT '{}',
  source text DEFAULT 'learned', -- 'learned', 'research', 'system', 'correction'
  created_at timestamptz DEFAULT now()
);
```

**Tools to expose:**
- `search_knowledge(query, category?)` — search before acting
- `save_knowledge(title, category, content, tags)` — save after learning
- `research_topic(topic, context?)` — search first, guide web research if not found

**Mechanical enforcement:** In your tool execution middleware, automatically search the knowledge base before every write proposal and attach matching articles to the tool result. The agent sees relevant knowledge whether it remembered to search or not.

---

### Error Investigation Tracking

**CLI:**
```
.claude/bugs/{system}/{system}-NNN.yaml  # Structured investigation
.claude/bugs/_SOLUTIONS.yaml             # Graduated reusable fixes
```

**Embedded:**
```sql
CREATE TABLE error_investigations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  error_code text,
  error_type text NOT NULL,
  what_happened text NOT NULL,
  what_was_tried text,           -- Failed attempts prevent future dead ends
  root_cause text,
  fix_applied text,
  reusable boolean DEFAULT false,
  reusable_pattern text,         -- What triggers this fix
  session_id text,
  status text DEFAULT 'open',    -- 'open', 'investigating', 'resolved'
  created_at timestamptz DEFAULT now()
);
```

**Tools:**
- `log_error_investigation(...)` — log when things go wrong
- `search_error_investigations(error_code?, query?)` — check before debugging

**Cognitive redirection:** "When an error occurs: Have I searched past investigations before debugging from scratch?"

---

### Mechanical Enforcement (Hook Equivalents)

This is the most important translation. PACT's hooks block violations mechanically — the agent cannot bypass them. In an embedded context, your API route handlers ARE the hooks.

**CLI (PreToolUse hook):**
```bash
# pre-edit-rules.sh — blocks edit if file wasn't read first
if ! grep -q "$FILE_PATH" "$READ_TRACKER"; then
  echo "BLOCK: Must read file before editing"
  exit 1
fi
```

**Embedded (API middleware):**

#### Pre-Write Knowledge Injection
```javascript
// In your write proposal function — runs on EVERY write
async function createPendingAction(supabase, sessionId, actionType, entityType, payload) {
  // Automatic knowledge search — agent can't skip this
  const searchTerms = extractSearchTerms(entityType, actionType, payload);
  const { data: articles } = await supabase
    .from('knowledge_base')
    .select('title, content')
    .or(buildSearchFilter(searchTerms))
    .limit(2);
  
  const knowledgeHint = articles?.length
    ? `[Relevant knowledge: ${articles.map(a => a.title).join(', ')}]`
    : null;

  // ... create the proposal, attach knowledgeHint to result
}
```

#### Same-Session Duplicate Detection
```javascript
// Check if the agent already proposed a matching transaction this session
const { data: priorActions } = await supabase
  .from('agent_actions')
  .select('id, task_label, status, proposed_payload')
  .eq('session_id', sessionId)
  .eq('entity_type', entityType)
  .in('status', ['pending', 'completed']);

for (const prev of priorActions) {
  const prevAmount = extractAmount(prev.proposed_payload);
  if (Math.abs(prevAmount - proposedAmount) < 0.02) {
    // Attach warning — not a hard block, but agent must acknowledge
    result.duplicate_warning = `You already ${prev.status} a similar ${entityType} for $${prevAmount} this session.`;
    break;
  }
}
```

#### Post-Write Mirror Sync
```javascript
// After any successful write, immediately update your local mirror
// so the agent sees its own changes on the next read
if (writeSucceeded) {
  await syncEntityToMirror(supabase, entityType, entityId, qboResult);
}
```

---

### Session Start Protocol

**CLI (session-register.sh):**
```bash
# Check PENDING_WORK.yaml, sessions.yaml, SYSTEM_MAP.yaml
```

**Embedded (System Prompt):**
```
## Session Start Protocol
At the START of every conversation:
1. Check tasks for items waiting on the user
2. Read the pending items list
3. Sync any caches that may be stale
4. Greet with specific status of what's pending
5. Check for unresolved error investigations from previous sessions
```

---

### Memory Management

**CLI:** Up to ~5 files in `.claude/memory/`, YAML format, manually managed.

**Embedded:**
```sql
CREATE TABLE agent_memory (
  slug text PRIMARY KEY,
  title text NOT NULL,
  content text NOT NULL,       -- YAML format recommended
  mode text DEFAULT 'default',
  updated_at timestamptz DEFAULT now()
);
```

**Optimization principle:** Memory files hold **volatile, session-critical state** only. Everything stable goes to the knowledge base or structured tables. If a piece of information doesn't change between sessions, it doesn't belong in memory.

Examples of what STAYS in memory:
- Current account balances (change every session)
- Active task list
- User preferences discovered this session

Examples of what MOVES to knowledge base:
- Business rules confirmed by the user
- API quirks and error fixes
- Historical reference data

---

### Merchant/Pattern Rules

If your agent categorizes, routes, or classifies data based on patterns, use a queryable rules table instead of memory:

```sql
CREATE TABLE categorization_rules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  pattern text NOT NULL,
  match_type text DEFAULT 'contains',
  target_category text NOT NULL,
  context_filter text,           -- Optional scope limiter
  notes text,
  confirmed_by text,
  confirmed_at timestamptz,
  active boolean DEFAULT true
);
```

**Tools:** `get_rules(pattern, context?)` and `save_rule(pattern, category, context?, notes?, confirmed_by?)`

This replaces fragile memory-based pattern matching with a queryable, auditable system.

---

### Data Mirror Architecture

If your agent reads from an external system (API, SaaS tool, third-party database), maintain a local mirror:

```
External System (source of truth)
       ↓ sync
Local Mirror (agent's playground)
       ↓ read
Agent makes decisions
       ↓ write
External System (changes applied)
       ↓ auto-sync back
Local Mirror (immediately updated)
```

**Critical rules:**
- Every write to the external system must auto-sync back to the mirror
- Deletes should be soft-deletes in the mirror (preserve audit trail)
- Read queries must filter out deleted/voided records
- The agent should never need to call the external API for reads — the mirror is the source of truth for the agent

---

### Feature Flows

Feature flow documents work identically in embedded contexts. Save them as YAML files in your repo:

```
docs/feature_flows/
  auth_flow.yaml
  billing_flow.yaml
  onboarding_flow.yaml
```

These describe **behavior across time** — what happens when things go right, what happens when things go wrong, and what breaks if you change something. They're essential reading before modifying any critical system.

---

## Common Embedded Agent Patterns

### Bookkeeping / Financial Agent
- Knowledge base: accounting rules, tax treatment, vendor categorization
- Mechanical enforcement: duplicate transaction detection, account type validation
- Error tracking: API error codes, failed writes, stale data issues
- Mirror: financial system ↔ local database with full line-item sync

### Customer Support Agent
- Knowledge base: product FAQs, escalation procedures, known issues
- Mechanical enforcement: prevent conflicting ticket updates, verify customer identity before sharing data
- Error tracking: failed integrations, escalation failures
- Mirror: CRM ↔ local cache of customer context

### Operations / Scheduling Agent
- Knowledge base: scheduling rules, capacity constraints, override policies
- Mechanical enforcement: double-booking detection, constraint validation
- Error tracking: scheduling conflicts, integration failures
- Mirror: calendar/scheduling system ↔ local availability cache

### Sales / CRM Agent
- Knowledge base: pricing rules, discount policies, competitor intelligence
- Mechanical enforcement: discount limit validation, approval workflow for large deals
- Error tracking: CRM sync failures, email delivery issues
- Mirror: CRM ↔ local pipeline cache

---

## Security Considerations

Every table your agent can access must have Row Level Security (RLS) enabled:

```sql
ALTER TABLE knowledge_base ENABLE ROW LEVEL SECURITY;

-- Service role (your backend) gets full access
CREATE POLICY "Service role full access" ON knowledge_base
  FOR ALL USING (auth.role() = 'service_role');

-- Authenticated users can read
CREATE POLICY "Authenticated read" ON knowledge_base
  FOR SELECT USING (auth.role() = 'authenticated');
```

**Cognitive redirection for developers:** "When creating a new database table: Did I enable RLS and add policies?"

---

## Checklist: Embedded PACT Implementation

- [ ] Knowledge base table + search/save tools
- [ ] Error investigation table + log/search tools
- [ ] Cognitive redirections in system prompt
- [ ] Session start protocol
- [ ] Pre-write knowledge injection (mechanical)
- [ ] Same-session duplicate detection (mechanical)
- [ ] Post-write mirror sync (mechanical)
- [ ] Soft-delete support in mirror tables
- [ ] Read queries filter deleted/voided records
- [ ] Memory files for volatile state only
- [ ] Pattern/categorization rules in queryable table
- [ ] Feature flow documents for critical systems
- [ ] RLS on every table
- [ ] Error notification to developer on write failures
