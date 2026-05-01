# Complementary Mechanisms — When Cognitive-Redirect Isn't the Right Tool

**Audience:** Future Claude sessions (or human contributors) considering whether
to add a new pattern to `cognitive_triggers.yaml`. Read this BEFORE adding.
Some failure modes belong in this system; many don't.

**Companion doc:** `COGNITIVE_REDIRECT_DESIGN.md` (the cognitive-redirect
system itself).

**Empirical anchor:** Build B's mining pass against 35 sessions / 31,318 user
messages / 181 correction events surfaced 15 distinct failure-mode categories.
**The cognitive-redirect system structurally cannot exceed ~67% coverage** of
those categories — see `95_PERCENT_HYPOTHESIS_REPORT.md` for the math.
**24% of documented bugs in the `bugs/` corpus have NO assistant-side
language tell at all** — they're invisible to text-pattern detection.

---

## The honest verdict

> The cognitive-redirect system is the right tool for failure modes where
> Claude's *language* signals the failure before the action lands. It is the
> WRONG tool for failure modes that are silent, content-driven, or
> structural.
>
> Stop trying to make every failure mode a redirect trigger. The v2 expansion
> (35 patterns, 0/35 passed validation) was the cost of conflating "should
> catch this" with "regex on assistant text can catch this."

---

## Five mechanisms in the PACT governance ecosystem

Each covers a different failure surface. Pick the one whose signal-to-noise
profile fits your failure mode.

### 1. Cognitive-redirect hook (this system)

**What it sees:** assistant-emitted text + thinking blocks (last turn).
**What it catches:** failure-mode LANGUAGE — hedging, capitulation, premature
commit intent, workaround admissions, "from training data" guessing.
**Latency:** PostToolUse, fires before next thought.
**Best for:**
- Hedge language ("should work", "probably fine") that masks unverified assumptions
- Agreement-capitulation patterns Claude exhibits before acting
- Workaround/band-aid admissions that signal symptom-fixing
- "From memory" / "reconstruct from training" — priors-over-fresh-read tells

**Worst for:**
- Silent failures (no language signal)
- Code antipatterns (the failure is in the file content, not the chat)
- Destructive bash commands (the harm is the command, not the prose around it)
- Structural mismatches (calling a function with wrong types)

**Files:** `.claude/hooks/cognitive-redirect.sh`,
`.claude/hooks/cognitive-outcome-tag.sh`,
`.claude/hooks/lib/{scan_triggers,detect_self_correction,tag_outcomes,validate_triggers,learn_triggers}.py`

---

### 2. Pre-edit content hook (`pre-edit-rules.sh`)

**What it sees:** the actual file content Claude is about to write/edit
(via the tool input, before the write commits).
**What it catches:** code antipatterns at the byte level — `print()` calls,
Hive imports, hardcoded API keys, raw `Color(0x...)`, manual `styleFrom`,
empty catch blocks, hand-built FloatingActionButtons.
**Latency:** PreToolUse, BLOCKS the write.
**Best for:**
- Forbidden patterns in code (banned imports, banned APIs, banned formats)
- Anything where "the rule is `grep -q X file` should return 0"
- Architectural drift that has a syntactic signature

**Worst for:**
- Patterns that need surrounding context (the rule depends on what file we're in)
- Behavioral failures (the code looks fine, behaves wrong)

**Files:** `.claude/hooks/pre-edit-rules.sh`

---

### 3. Bash guard hook (`pre-bash-guard.sh`)

**What it sees:** the bash command Claude is about to execute.
**What it catches:** destructive operations (`git reset --hard`, `rm -rf`),
API-key bypass attempts (curl to LLM endpoints without `pact-delegate`),
multi-Claude conflicts (commit/push when local is behind remote), merge gates
to master.
**Latency:** PreToolUse, BLOCKS the bash call.
**Best for:**
- Destructive operations that have hard reversibility costs
- Bypass patterns (going around the governance system)
- Coordination gates (multi-session safety)

**Worst for:**
- Patterns that depend on the bash command's OUTPUT (you can't see it yet)
- Subtle command misuse (the command is fine, the args are wrong)

**Files:** `.claude/hooks/pre-bash-guard.sh`

---

### 4. PACT checkpoints (XML blocks emitted by Claude)

**What it sees:** Claude's own structured reasoning, emitted in the response.
**What it catches:** decision quality — was a comparison done, was the
solution-space surveyed, was the schema verified.
**Latency:** Claude must self-emit; checkpoint-audit hook detects missing
ones POST-action and warns.
**Best for:**
- Decision-quality gates ("did I compare 2+ options before picking one?")
- Reasoning visibility (forces show-your-work for high-stakes choices)
- Process gates that depend on Claude's awareness, not surface text

**Worst for:**
- Hard guarantees (Claude can skip emitting a checkpoint and the action still happens)
- Real-time blocking (checkpoints are reasoning, not enforcement)

**Files:** `.claude/PACT_CHECKPOINTS.md` (definitions),
`.claude/hooks/post-edit-checkpoint-audit.sh` (audit detector)

---

### 5. Schema-verify / staleness hooks

**What it sees:** live state of databases, package versions, file modification
times.
**What it catches:** drift between what Claude's working from and what's
actually true — stale provider cheatsheets after table changes, stale package
knowledge after upstream releases, missing columns referenced in code.
**Latency:** SessionStart or PreToolUse.
**Best for:**
- Data integrity (column exists, FK matches, RLS is enabled)
- Knowledge staleness (package was last verified X days ago, refresh window is Y)
- Schema-vs-code drift

**Worst for:**
- Behavioral correctness (schema is right, code uses it wrong)
- Patterns that need linguistic interpretation

**Files:** `.claude/hooks/session-package-staleness.sh`,
`.claude/hooks/daily-checks.sh`, `scripts/check_schema_drift.py`

---

## Decision framework — picking the right mechanism

Given a new failure mode you want to prevent, ask in order:

1. **Is the failure in CODE that Claude is about to write?** → Pre-edit content hook (#2)
2. **Is the failure a BASH COMMAND about to execute?** → Bash guard hook (#3)
3. **Is the failure DATA INTEGRITY (schema, FK, RLS, package staleness)?** → Schema-verify / staleness hook (#5)
4. **Is the failure a DECISION-QUALITY skip (no comparison, no verification)?** → PACT checkpoint (#4)
5. **Is the failure visible in Claude's LANGUAGE before the action?** → Cognitive-redirect hook (#1, this system)
6. **Is the failure SILENT** (no language tell, no detectable pattern in code/command)? → **None of these mechanisms can catch it.** Document in `bugs/` and accept it as "Claude has to remember from CLAUDE.md / skills / knowledge."

---

## The 24% gap — failure modes outside ALL mechanisms

From the bug-file analysis (49 bugs, ~12 untouched by any mechanism):

| Bug | Why uncaught | Best alternative |
|-----|-------------|------------------|
| `infra-001` Supabase project ref hardcoded | No language tell; the failure IS the value | Pre-edit content hook (#2) — banlist of project refs |
| `infra-003` sleep-loop polling | Process behavior, no verbal signal | Bash guard hook (#3) — pattern detect on shell loops |
| `auth-001` demo-mode session bypass forgotten | Silent — no hedging language | Schema-verify hook (#5) — invariant check |
| `blueprints-001` Riverpod dispose violation | Caught by hook already (#2) | Existing hook covers |
| `meld-002`, `meld-014` Plugin behavior assumed | Partial — sometimes triggers `from_training_data` | Knowledge file refresh + skill |
| `map-008/013/014` Wrong-metro debugging spirals | Partial coverage via "looks like" | Add UI verification skill |
| `scraper-009` Async blocking I/O | No verbal signal | Pre-edit content hook (#2) — detect blocking calls in async |
| `schema-*` (4 files) Missed column/FK during migration | Schema-verify already catches | Existing mechanism |

**Pattern:** most "uncaught" bugs DO have a mechanism that should catch them
— it's just NOT cognitive-redirect. The right move is to add the rule to the
RIGHT mechanism, not stretch this system to cover everything.

---

## When you're tempted to add a new redirect pattern

Run through this checklist:

1. **Does the failure mode have a recognizable PHRASE that Claude says
   before the failure?** If no → wrong mechanism.
2. **Is the phrase specific enough that legitimate uses are rare?** If no
   → noise, will erode trust.
3. **Have you measured precision against the corpus?** If no → run
   `validate_triggers.py` first.
4. **Does the precision exceed 0.6 weighted (or do you have human-override
   rationale citing specific bugs)?** If no → leave in candidates.
5. **Is there an EXISTING pattern that already covers this?** If yes →
   refine the existing one rather than duplicating.

If you can't say YES to all 5, the new pattern doesn't belong in
`cognitive_triggers.yaml`. Either pick a different mechanism, or accept that
this failure mode lives in CLAUDE.md as a soft-rule.

---

## What this means for the next Claude session

If you're tempted to "improve" this system by adding more redirect patterns,
consider that the RESEARCH says we're already near the structural ceiling
for this mechanism. The leverage is now in:

1. **Better outcome detection** — improving `detect_self_correction.py`'s
   per-category signals to raise the precision floor
2. **Brag citation injection** — closing the recognition loop so existing
   fires become more behaviorally effective
3. **Filling the OTHER mechanism gaps** — particularly pre-edit content
   hooks for the 12-bug uncaught list
4. **Refining the redirection text** — Dumbledore voice, incremental
   framing, implementation intentions

Adding more patterns is the lowest-leverage move at this point. Resist it.

---

## Cross-references

- `COGNITIVE_REDIRECT_DESIGN.md` — full system design + psychology framework
- `95_PERCENT_HYPOTHESIS_REPORT.md` — empirical evidence for the 67% ceiling
- `trigger_candidates_clustered.md` — Build B's clustering of mineable categories
- `validation_report.yaml` — last validation run results
- `cognitive_triggers.yaml` — current live library (10 patterns post-v3)
- `cognitive_trigger_candidates_v3.yaml` — held candidates with measured stats

**Last updated:** 2026-04-30 (post-Phase 3 of cognitive-redirect build)
