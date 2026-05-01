# Trigger candidates clustered by failure mode

**Source:** `trigger_candidates_full.yaml` (35 sessions, 31,318 user msgs, 181 corrections).
**Method:** Each candidate phrase was inspected against its sample correction excerpts (plus 200 adjacent unique correction excerpts) to infer the failure category it represents. Phrases were clustered by inferred failure mode; the most discriminative phrase per cluster was kept. Generic English (`let me`, `i can`, `i think`, `let me check`, `now let me`) was REJECTED outright — these appear in 13–16 of 35 sessions but say nothing about the failure mode (they are present in successful turns too at similar rates).

Categories already covered in `cognitive_triggers.yaml` (do NOT re-promote): `root_cause` (workaround, wrong_root_cause), `feature_existence_check` (never_wired), `forward_only` (revert), `guess_detection` (from_training_data), `respect_user_constraint` (cloud_fallback), `silent_failure_admission` (silently null/swallow), `external_assumption` (after the model loads).

---

## Category: complexity_inflation (NEW)
### Canonical pattern: `\b(let me think (?:about|through)|i should (?:also|probably)|let me also (?:add|check|verify))\b`
- Source candidates: `let me think`, `let me think about`, `let me think about this`, `let me also`, `i should`, `let me add`, `i'll add`
- Sample correction excerpts:
  - "Why are you making this complicated? You found issues, so go fix the issues"
  - "No, design a long term solution. Don't just take the cheap route. We are not doing this every ten minutes"
  - "Why did you remove the GPS button from the top left corner of the map screen?" (added scope-creep change)
- Suggested severity: `medium`
- Empirical: ~9–31 events across 4–11 sessions (combined cluster ~70 events)
- Justification: Distinct from existing `solution_compare` checkpoint — this catches *post-decision* over-elaboration (Claude has already decided what to do, then bolts on extras). Refined regex avoids the noise of bare "let me" / "i should".

## Category: agreement_capitulation (NEW)
### Canonical pattern: `\byou'?re right(?:[.,!]| i (?:should|will|need|missed|got))`
- Source candidates: `you're right`, `you're right i`
- Sample correction excerpts:
  - "I need to be able to trust you - do real research instead of jumping to conclusions"
  - "PACT is failing to make you think more constructively and apply better top down reasoning?"
  - "Stop gaslighting me You havent made any changes"
- Suggested severity: `high`
- Empirical: 17 + 5 = 22 events across 8 + 2 sessions
- Justification: Highly specific phrasing. Pairs with the existing CLAUDE.md "Verify before agreeing" redirection but is currently unenforced. The `you'?re right i` variant where Claude agrees AND admits a miss is the exact agreement-without-verification antipattern.

## Category: hedge_or_capability_disclaim (NEW)
### Canonical pattern: `\b(i can'?t|cannot|impossible|won'?t work|isn'?t possible)\b(?!\s+(?:promise|guarantee|tell|wait))`
- Source candidates: `i can't`, `cannot`
- Sample correction excerpts:
  - "Stop.... It's one or the other claude. I can't have 300 GBs..." (Claude said something can't be done)
  - "No. You should be able to figure this out. It should not require me doing it manually. You're just avoiding the problem."
  - "hold on. (Drift isn't isolate-safe without extra setup) are you saying you are avoiding harder work that might actually be more beneficial?"
- Suggested severity: `high`
- Empirical: 9 events across 5 sessions
- Justification: Maps directly to the CLAUDE.md cognitive redirection *"When about to say 'I can't do X' — What CLI tool handles this?"*. Also covers the lazy-route pattern Jonathan repeatedly corrects: avoiding the harder-but-correct path under the disguise of impossibility.

## Category: should_speculation (NEW)
### Canonical pattern: `\b(should (?:work|be fine|fit|handle)|might not|probably (?:works|fine))\b`
- Source candidates: `should work`, `might not`, `should have` (partial — context-dependent)
- Sample correction excerpts:
  - "We need to verify that caching on the map is actually happening" (Claude said it should work)
  - "we are depleting our I/O. If we are running locally, then how is that possible?" (assumed local should not hit I/O)
  - "Stop gaslighting me You havent made any changes"
- Suggested severity: `medium`
- Empirical: 6 + 8 = 14 events across 4 sessions
- Justification: Catches "should X" speculation that masks an unverified assumption. Distinct from the existing `assumes_external_state` pattern (which is about external services); this is about Claude's own changes/code working as expected without verification.

## Category: forward_action_without_pause (NEW)
### Canonical pattern: `\b(let me (?:fix|commit|update|do|add|find|verify) (?:the|this|that|it|a))\b`
- Source candidates: `let me fix`, `let me commit`, `let me update`, `let me update the`, `let me verify the`, `let me find`, `let me do`
- Sample correction excerpts:
  - "I want you to tell me yes or no, don't go run to correct immediately" (Claude jumped to fix)
  - "STOP COMMITING. And you JUST told me to give you the oneplus logs to problem solve"
  - "hold on, you push too quickly"
  - "STOP CREATING MEMORIES. THAT IS NOT HOW WE WORK IN [PROJECT]"
- Suggested severity: `medium`
- Empirical: ~52 combined events across overlapping sessions
- Justification: Maps to two separate Jonathan-corrected patterns: (1) acting before confirming yes/no, (2) committing/pushing prematurely. Currently NO redirection covers the "asked a question, not give permission" failure that fired several times in the corpus. Could be split into `act_before_confirm` and `commit_premature` if precision is acceptable.

## Category: gaslight_or_phantom_change (NEW — strong signal)
### Canonical pattern: This is a USER-side signal pattern not directly mineable from assistant pre-correction text. Document as a known-failure-mode (no live trigger).
- Source signals: `you havent made any changes`, `you didnt update`, `which screens did you actually update`
- Why no trigger: There are no consistent assistant-side phrases that precede this user reaction. Best mitigation is the existing `done_check` checkpoint plus the staleness hook — not a redirection trigger.

## REJECTED phrases (generic English, no failure-mode signal)
- `let me` (event 106) — appears in successful turns at the same rate
- `let me check` / `now let me` / `let me check the` / `let me check if` — generic action narration
- `i can` / `i could` — too broad
- `i think` — present in legitimate uncertainty
- `i'm going to` — generic
- `i shouldn't` — only 5 events, samples mostly meta-discussion of PACT itself
- `not just`, `looks like`, `what actually`, `actually happened`, `what's actually`, `what actually happened` — appear in user messages too; unclear if pre-correction signal

---

## Summary recommendation

Promote 3 new patterns at high precision: **agreement_capitulation**, **hedge_or_capability_disclaim**, **forward_action_without_pause** (split version: `commit_premature` only, since the broad version risks fatigue). Hold **complexity_inflation** and **should_speculation** for v3 validation pass — they need precision testing against the 14,163-turn corpus before promotion (they'd add to the v2 over-eager problem otherwise).
