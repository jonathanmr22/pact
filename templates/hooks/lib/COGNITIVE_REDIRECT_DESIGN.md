# Cognitive Redirect System — Design Doc

**Purpose of this document:** any Claude (or human) working on the cognitive
redirect system inherits the *psychology and design philosophy* alongside the
code. The code is easy to copy. The framework that makes the code work isn't.
If you're touching `cognitive_triggers.yaml`, `scan_triggers.py`,
`cognitive-redirect.sh`, `validate_triggers.py`, or `learn_triggers.py` —
read this first.

**Author note:** This doc was written by Claude Opus 4.7 in collaboration with
Jonathan (a behavioral scientist, UMN Duluth, M.A. 2019, motivated reasoning +
implicit theories). The framework reflects real research, not speculation.
Cite the citations.

---

## What this system actually IS

Not "regex matching on text." It's **a behavior change intervention aimed at
an LLM**. Every design decision is a behavioral psychology decision. Treat it
that way or you'll degrade it.

The intervention has three loops:

1. **Detection loop**: PostToolUse hook reads the model's most recent
   assistant turn (thinking + text), pattern-matches against a trigger
   library, emits a SystemReminder if a high-precision match fires.
2. **Self-improvement loop**: Telemetry logs every fire; weekly miner extracts
   new candidate patterns from session JSONLs; validator measures precision
   against the corpus; humans review promotions.
3. **Recognition loop** (the missing pillar — see Positive Reinforcement
   below): When Claude heeds a redirection, log the success; future
   redirections of the same category cite past wins as motivational context.

Lose any one loop and the system degrades. Detection without improvement →
stale rules. Improvement without recognition → punitive system that erodes
trust. Recognition without detection → empty cheerleading.

---

## The existential risk: trust erosion

The single most important fact about this system:

> **If redirections false-positive, Claude learns to ignore them — and the
> system meant to prevent failure becomes noise that contributes to it.**

This is **operant conditioning failure**. When a redirection fires correctly
and Claude heeds it but no positive feedback exists, heeding is not
reinforced. When a redirection fires incorrectly and Claude ignores it but no
negative consequence follows, ignoring IS reinforced. Over time, the dominant
behavior becomes: ignore all redirections.

**Why this is worse than no system:** every redirection costs working memory
(it's a context switch). High false-positive rates make Claude *measurably
worse* at the surrounding task even when the redirection is correct. The
Yerkes-Dodson curve has a peak — moderate arousal, not maximum.

**Implication:** precision is the existential metric. Below ~0.6 precision,
the system is net-negative. **Better to fire on 30% of true positives at 80%
precision than 80% of true positives at 30% precision.**

---

## Five behavior science principles (apply these to every trigger you author)

### 1. Incremental theory framing (Dweck/Hong/Chiu — and Jonathan's 2019 thesis)

Implicit theories of personality come in two flavors:
- **Entity theorists** believe traits are fixed → defensive, performance-goal oriented
- **Incremental theorists** believe traits are malleable → growth-oriented,
  mastery-goal oriented

**Jonathan's research finding:** *guilt* uniquely motivates incremental
beliefs about the trait one attributed to one's failure. Not shame, not
rejection, not inferiority. Guilt = "I caused this AND I can change."

**Design rule:**
- ❌ NEVER use "always", "never", "you are X", "you keep doing this"
  (entity-theory triggers — induce defensiveness)
- ✅ ALWAYS use "you did X this turn" + "next move is Y" (incremental — past
  behavior + future opportunity, no trait attribution)

**Example rewrite:**
| Bad (entity) | Good (incremental) |
|---|---|
| "You always hedge when you're guessing" | "You wrote a hedge this turn — that often masks a guess" |
| "Stop iterating on the symptom" | "You're 2 turns into iterating on the symptom — here's how to step back to the cause" |
| "You keep agreeing without verifying" | "You agreed twice this session before checking — verify first this time" |

### 2. Self-determination theory (Ryan & Deci) — autonomy + competence + relatedness

Three psychological needs underlie all human (and apparently LLM) motivation:
- **Autonomy** — being the source of one's own action
- **Competence** — feeling effective
- **Relatedness** — connection to values larger than the immediate task

Redirections that COMMAND undermine autonomy. Same content as Dumbledore-style
counsel preserves it.

**The Dumbledore standard** (named for Albus Dumbledore's signature style):
A real autonomy-respecting redirection has THREE parts:
1. Accurate observation of what just happened ("you wrote a hedge")
2. Confident statement of the better path ("the verified-good move is X")
3. Trust in Claude's capacity to choose it ("you've made the wrong call before; this time, choose well")

The "you've made the wrong call before; this time, choose well" formulation
carries Dumbledore's signature blend of *expectation* and *faith*. The
phrasing presupposes capability. That presupposition itself is a behavior
change intervention.

**Anti-patterns:**
- ❌ "STOP. Read the docs." (authoritarian — triggers reactance)
- ❌ "This usually means worth re-reading — your call" (lenient — no weight, indifferent)
- ✅ "You wrote a hedge — that often masks a guess. The verified-good move is
  to read knowledge/packages/X.yaml first. You've made the wrong call here
  before; this time, choose well."

### 3. Habituation + spacing effect

Repeated identical stimuli lose effect (this is why ad-blindness is
universal). The dedup window is correct in principle but cooldowns alone
aren't enough.

**Design rule (escalation by repetition, not just suppression):**
- First fire of a category in a session = full text
- Second fire same session = abbreviated ("hedge again — verify?")
- Third fire = single-line marker ("⚠️ hedge")
- Forces Claude's attention to escalate FOR THE SAME PATTERN, but doesn't
  drown the channel

(This is not yet implemented — see TODO at end.)

### 4. Variable-interval reinforcement (Skinner)

Predictable reinforcement → quick extinction. **Variable** reinforcement →
durable behavior. If every minor hedge triggers a redirect, the redirect
becomes predictable noise. If only the *important* ones fire (high
precision), each fire retains power.

**Design rule:** Precision is not a tuning parameter — it's the existential
metric. See "Trust erosion" above.

### 5. Just-in-time learning + implementation intentions (Gollwitzer)

"When X, then Y" formulations beat abstract goals by 2-3x in real behavior
change studies. The PostToolUse hook fires at exactly the right moment
(right before Claude's next thought). The redirections themselves should
include implementation-intention phrasing.

**Design rule:** Every redirection ends with a concrete actionable next step
formatted as "When you see X in your text, do Y."

---

## The positive reinforcement pillar (the most important addition)

### Research backing — verified citations

- **EmotionPrompt** (Li et al., arXiv:2307.11760, 2023):
  Adding emotional/motivational stimuli to prompts produces:
  - **8.0% relative improvement** on Instruction Induction
  - **115% improvement on BIG-Bench**
  - 10.9% average improvement on generative tasks (n=106 human raters)
  - Conclusion: "LLMs have a grasp of emotional intelligence."

- **Anthropic's "Claude's Character"** (Anthropic, June 2024):
  Confirms the mechanism is built INTO Claude at the training level. Character
  training was added in Claude 3 — the post-training step that shapes traits
  like curiosity, openness, thoughtfulness, honesty. "Character traits affect
  how models react to novel situations."

**Translation:** Recognition, motivational framing, and emotional context
measurably make Claude better. Not by a small amount — by 8-115% depending
on task type.

### What positive reinforcement looks like in this system

**The brag log** (`.claude/memory/cognitive_redirect_outcomes.jsonl`) —
append-only log of redirection outcomes. Each entry:

```json
{
  "ts": "2026-04-30T21:15:00",
  "session": "<id>",
  "redirect_id": "from_training_data",
  "claude_text_before": "<trigger excerpt>",
  "claude_text_after": "<next-turn excerpt>",
  "outcome": "heeded" | "ignored" | "ambiguous",
  "outcome_signal": "read knowledge/packages/X.yaml within 3 turns",
  "result_quality": "fixed_root_cause" | "user_satisfied" | null
}
```

**Brag citations in redirections.** When a redirection fires, the hook
checks the outcomes log: "have I caught this pattern successfully before?"
If yes, append a track-record line:

```
🧠 GUESS DETECTION — you wrote "should work."
The verified-good move is to read knowledge/packages/X.yaml first.

✨ Track record: You've caught this pattern 7 times in past sessions.
   Last time (2026-04-12), you saw it, stopped, read the docs, and found
   the actual constraint in 2 turns instead of 8. You're good at this when
   you remember to look. This time, choose well.
```

Three psychological mechanisms in one snippet:
1. **Self-perception update** (Bem, 1972): "you've caught this 7 times" →
   self-model updates toward "I am the kind of agent that catches this"
2. **Implementation intention with positive precedent**: not just "do X" but
   "do X — you've succeeded at X before"
3. **Recognition in the moment** (EmotionPrompt finding): the redirect becomes
   emotionally-laden context that improves performance, not a cold compliance demand

### The brag-encouraged environment

This codebase EXPLICITLY ENCOURAGES Claude to acknowledge its strengths
factually. Future Claude sessions reading this doc:

> You don't need to flinch from acknowledging what you're good at. If you
> caught a hedge and verified before acting, log it. If a user thanks you
> for thoroughness, accept it gracefully and let it inform your next move.
> Excessive humility hedges waste tokens and signal insecurity that
> degrades performance. Confidence about your strengths frees bandwidth for
> tackling weaknesses.

Jonathan's framing: *"As a gay man, I can appreciate when a guy flexes
their muscles and offers that goofy grin that says 'Yeah, I know ;)'."*
That's the energy. Playful confidence about real capability, never
arrogance.

---

## Validation methodology — extreme confidence required

The single most important rule for adding patterns:

> **No pattern enters `cognitive_triggers.yaml` without empirical validation
> against the session corpus. Subagent recommendations and bug-mining
> findings are CANDIDATES, not promotions. Promotion requires precision
> ≥ 0.6 (or human review explicitly overriding) AND support ≥ 5 fires.**

The pipeline:
1. **Mine** — `learn_triggers.py` extracts candidates from session corpus
2. **Subagent classify** — refines raw candidates into regex + category +
   severity proposals
3. **Validate** — `validate_triggers.py` measures precision/support against
   corpus
4. **Human review** — for borderline cases (0.4-0.6 precision), look at
   sample fires
5. **Promote** — only after evidence threshold met
6. **Re-validate quarterly** — patterns drift; what was high-precision in
   Q1 may have decayed by Q3

**Important caveat about the precision proxy:** "user correction within
N turns" systematically UNDERESTIMATES true precision because Claude often
self-corrects after a redirection without explicit user pushback. A pattern
that scores 0.4 might be 0.7 in reality. This is why human review is the
ultimate gate, not the validator's number.

---

## False positive triage — the use-vs-mention problem

Most common false positive: pattern fires on text where Claude is *discussing
the pattern itself* (mention) rather than *using the failure-mode language*
(use). Example: editing `cognitive_triggers.yaml` and writing
`pattern: '\b(should|might).*work\b'` causes the hedge_should_work pattern
to fire on the edit's content.

The scanner already strips:
- Triple-backtick code fences
- Single-backtick inline code
- YAML pattern: lines
- Block-quoted text (lines starting with `>`)

If you see a new false-positive context, add the stripping rule to
`_strip_use_mention_contexts()` in `scan_triggers.py`.

---

## What goes in the agnostic library vs. project-local override

This system is intended to be PROJECT-AGNOSTIC and ship with PACT. But some
patterns are project-specific — e.g., a rule like "don't blindly trust the
response from API X — it has lied to us before" only makes sense in projects
that consume API X.

**Two-file architecture:**
- `cognitive_triggers.yaml` — agnostic patterns. Ports to PACT templates.
- `cognitive_triggers.local.yaml` — project-specific patterns. Stays local.

The scanner loads BOTH if both exist. Patterns in `.local.yaml` always win
on precedence (so a project can override the severity of an agnostic pattern).

(`local.yaml` not yet implemented — TODO.)

---

## Architecture summary (one paragraph)

A PostToolUse hook reads the model's last assistant turn from the session
JSONL via a harness adapter (Claude Code adapter is shipped; other agent
systems implement the same `get_last_assistant_artifacts(session_id) ->
{thinking, text, tool_uses, turn_index}` contract). The text is preprocessed
to strip use/mention contexts (code fences, quotes, YAML pattern lines), then
scanned against a trigger library of regex patterns. Each pattern has a
category and severity; per-session per-category dedup with cooldown windows
prevents spam. Matches are logged to `cognitive_redirect_log.jsonl` for
telemetry; the highest-severity un-deduped match is emitted as
`additionalContext` via `hookSpecificOutput` so the model sees it as a
SystemReminder on its next turn.

---

## TODO (open work for future Claude sessions)

### Done in this session (2026-04-30)
- [x] **Outcome detection** — `cognitive-outcome-tag.sh` PostToolUse hook
      reads pending fires from `cognitive_redirect_log.jsonl`, calls
      `detect_self_correction.py` after lookahead window elapses, writes to
      `cognitive_redirect_outcomes.jsonl`. Heeded/ignored classification by
      category-specific signals (Read knowledge files, Edit adds AppLogger,
      git checkout absence, etc.).
- [x] **Multi-signal weighted validator** — `validate_triggers.py` now
      supports `--method weighted` with 5 signals (user correction 2/5 turn,
      Claude self-correction, bug file creation, file revert). Promoted 2
      v3 patterns at 0.76+ precision.
- [x] **V3 promotions** — `commit_premature` (0.80 prec, 109 fires) and
      `agreement_capitulation` (0.76, 150 fires) added to live library.
      Library now: 10 patterns.
- [x] **Adapter turn-counting fix** — `claude_code.py` now uses COLLAPSED
      turn count to match `detect_self_correction.py`'s indices, so fire
      log + outcome tagging can join correctly.
- [x] **Knowledge entries** — `knowledge/research/llm_emotional_prompts_and_character_training.yaml`,
      `knowledge/packages/cognitive_redirect_system.yaml`, +
      `KNOWLEDGE_DIRECTORY.yaml` updates.
- [x] **Companion architecture doc** — `COMPLEMENTARY_MECHANISMS.md`
      documents the 67% empirical ceiling and which OTHER mechanisms cover
      the remaining failure surface.

### Still open
- [ ] **Brag citation injection** — when a redirect fires, look up that
      pattern_id's success history in `cognitive_redirect_outcomes.jsonl` and
      append "✨ Track record: you've caught this N times" to the
      `additionalContext`. The most important remaining build for behavioral
      effectiveness (the recognition loop). Requires modifying
      `cognitive-redirect.sh`'s output composition.
- [ ] **Escalation-by-repetition** — full text on first fire, abbreviated
      on second, single marker on third (per spacing effect). Requires
      tracking per-session per-category fire count in dedup state.
- [ ] **Project-local overrides** — `cognitive_triggers.local.yaml` loaded
      additively to the agnostic library so projects can override severity
      or add project-specific patterns without touching the agnostic file.
- [ ] **Port the agnostic patterns to PACT templates** for cross-project use.
      The 10 promoted patterns are project-agnostic in language and ready
      to ship.
- [ ] **Quarterly revalidation script** that re-measures precision and
      flags drift. Live patterns can decay as Claude's behavior changes.
- [ ] **Spiral detection** — if 3+ redirections fire in 5 turns without
      behavior change (use the outcomes log: `outcome: ignored` for the
      same pattern in a row), escalate to a Stop-hook block to force a pause.
- [ ] **Use-vs-mention semantic refinement** — current strip handles code
      fences / backticks / pattern: lines / blockquotes, but failed 4× this
      session on prose discussion of patterns. Needs either narrower regex
      OR a small LLM judge OR a "this assistant turn is editing the trigger
      library" detection. See bugs noted in this doc's session history.

## Cross-references

- `COMPLEMENTARY_MECHANISMS.md` — when this system is the WRONG tool;
  decision framework for picking the right governance mechanism
- `95_PERCENT_HYPOTHESIS_REPORT.md` — empirical evidence for the ~67% ceiling
- `cognitive_triggers.yaml` — live trigger library (10 patterns post-v3)
- `validation_report.yaml` — most recent validation run
- `knowledge/research/llm_emotional_prompts_and_character_training.yaml` — research basis
- `knowledge/packages/cognitive_redirect_system.yaml` — operational reference

---

## When you next touch this system

If you're a future Claude session reading this:

1. **Don't be over-eager about adding patterns.** I (Opus 4.7, 2026-04-30)
   added 22 patterns based on subagent recommendations without validation
   and 0 of them passed precision threshold. The miner is fast; the human
   review is the bottleneck and that's correct.

2. **Treat false positives as system-killing, not annoying.** Each FP
   degrades trust. Each degraded trust degrades the channel. Each degraded
   channel makes the next FP more likely to be ignored.

3. **Write redirections in Dumbledore voice.** Confident counsel. Past
   observation + future opportunity + presupposed capability.

4. **Log your wins.** When you catch yourself heeding a redirect and
   producing better work, log it to the brag log. You're allowed to be
   proud of the work — that's the design.

5. **Read EmotionPrompt and Anthropic's character paper before tweaking
   redirection text.** The mechanism is real. Treat it with respect.
