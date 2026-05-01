# 95% Hypothesis Report

**Question:** If we promote the top-N candidates from the 35-session mining pass to the live library, would they catch 95% of the failure-mode language patterns Jonathan has historically encountered?

**Verdict:** **No. Realistic coverage is ~55–65%, not 95%.** The mining methodology is structurally incapable of catching the long tail because it depends on (a) Claude using a recognizable phrase before being corrected, and (b) the user's correction matching one of 21 hand-curated regexes. Both filters drop signal.

---

## Quantitative breakdown

### Corpus stats (from full miner pass)
- 35 parent sessions analyzed
- 31,318 user messages total
- **181 detected correction events** (0.58% of user msgs)
- 43 candidates above the 5-event threshold

### Distinct failure categories observed in the 199 unique correction excerpts I read manually
Counting categories that recur ≥3 times:

| # | Category | Sample-frequency | In existing library? | In new candidates? |
|---|---|---|---|---|
| 1 | Symptom-fix instead of root cause | 18 | Yes (workaround_language, wrong_root_cause) | — |
| 2 | Agreement without verification | 14 | No | **Yes (agreement_capitulation)** |
| 3 | Premature commit/push/action | 12 | No | **Yes (forward_action_without_pause)** |
| 4 | "I can't" / capability disclaim | 9 | No | **Yes (hedge_or_capability_disclaim)** |
| 5 | Complexity inflation / scope creep | 11 | No | Partial (complexity_inflation hold) |
| 6 | Phantom-change gaslight ("you didn't update X") | 8 | No (done_check covers partly) | No (no assistant-side signal) |
| 7 | Memory file violation | 4 | Hook-blocked | N/A |
| 8 | Off-topic / wrong session context | 6 | No | No |
| 9 | Forgot user constraint earlier in session | 7 | Yes (cloud_fallback_after_rejection) | — |
| 10 | Stale knowledge / wrong package recall | 5 | Yes (from_training_data) | — |
| 11 | Should-speculation without verify | 7 | No | Hold (should_speculation) |
| 12 | Tone / verbosity / hand-holding | 6 | No | No (style, not failure mode) |
| 13 | Wrong tech stack assumption | 4 | No | No (covered by CLAUDE.md "tech stack" redirect, not regex-checkable) |
| 14 | Lazy approach over right approach | 5 | No | Partial (overlap with hedge) |
| 15 | Asking clarifying Q after action ("ANSWER, don't act") | 4 | No | Partial (forward_action) |

**15 distinct categories. Existing library covers 5 (33%). Adding the 3 strong new candidates → 8 (53%). Adding the 2 hold-for-validation → 10 (67%).**

---

## Bug-evidence gap analysis

Bug files whose root-cause failure modes would NOT be caught by any current or proposed mined candidate:

| Bug ID | Root cause | Why uncaught |
|---|---|---|
| infra-001 (FPS cross-contamination) | Hardcoded Supabase project ref | Hook-enforced; no assistant-side phrase |
| infra-003 (stuck emulator) | sleep-loop polling pattern | No verbal signal — process behavior |
| infra-006 (dashboard duplicate tabs) | Re-implementing existing UI without searching | `feature_existence_check` covers IF Claude says "doesn't exist" first; rarely does |
| auth-001 (demo mode Supabase session) | Forgot demo-mode bypass branch | Silent — no hedging language |
| blueprints-001 (kills app process) | Riverpod dispose violation | Caught by hook, not phrase |
| meld-002, meld-014 | Plugin behavior assumed instead of verified | Partial — "from_training_data" sometimes fires |
| map-008, map-013, map-014 | Wrong-metro / wrong-style debugging spirals | Partial — covered when Claude says "looks like" or admits chasing |
| scraper-009 | Async blocking I/O | No verbal signal pre-correction |
| schema-* (4 files) | Missed column/FK during migration | Schema-verify checkpoint covers, not regex |

**~12 of 49 bug files have failure modes that NO trigger (existing or proposed) would have caught at the assistant-language level.** That's ~24% of the bug corpus permanently outside the mineable surface area.

---

## Why the methodology has a ceiling

1. **Selection bias toward verbal corrections.** Many of Jonathan's most painful corrections happen via screenshots, `Read` of bug files, or silent re-routing — not regex-detectable.
2. **Correction-pattern recall ≠ precision.** The 21 hand-curated user-side regexes catch ~181/31,318 events (0.58%). The true correction rate is likely 3–8% based on manually scanning random user messages. Most corrections use phrasings the regex misses ("hold on", politeness-prefixed "Can we instead...", emoji-only "🤔").
3. **Generic English dominates the n-gram counts.** Even at 5+ events, the top of the candidate list is filler ("let me", "i can"). Real failure-mode signals sit in the middle of the long tail at 5–10 events each.
4. **Confounded by self-prompts.** Some "Claude said X then user said wtf" cases are about content not language — Claude proposed the wrong feature, not used the wrong words. No regex catches "you proposed feature Y when I asked for Z."
5. **Existing library already covers the loudest patterns.** The 8 promoted patterns absorbed the high-precision wins. New candidates necessarily live in lower-precision territory.

---

## Recommendation

- **Honest target: 60–70% coverage of mineable failure modes**, not 95%.
- Promote the 3 high-confidence candidates (agreement_capitulation, hedge_or_capability_disclaim, forward_action_without_pause) AFTER `validate_triggers.py` confirms ≥0.3 precision against the corpus.
- Hold complexity_inflation and should_speculation for v3 — they're plausible but the over-eager v2 lesson (35 patterns, 0/35 passed validation) argues for restraint.
- For the 24% of bugs outside the mineable surface, double down on the OTHER loops: hooks, checkpoints, schema-verify, dependency_trace. Regex triggers cannot solve every failure mode and pretending they can is itself the v2 anti-pattern.

The mining system is doing its job — surfacing candidates. Treating it as a 95% solution would degrade the live library by adding low-precision patterns that erode the trust that makes high-precision patterns work.
