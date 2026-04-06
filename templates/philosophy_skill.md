---
description: "Project philosophy and core beliefs. USE THIS whenever making product decisions, designing features, choosing defaults, writing user-facing copy, or evaluating trade-offs. If you are deciding what the product SHOULD DO (not just how it looks), this skill is active."
user-invocable: false
---

# {Project Name} Philosophy — Core Beliefs

<!--
PACT Template: Create this file at .claude/skills/{project}-philosophy.md

This is the product counterpart to the aesthetic skill. While the aesthetic
skill governs HOW things look, this skill governs WHY things exist and
WHAT the product believes about its users.

Every product decision is a values decision. "Should we track this?" is a
privacy question. "Should we require sign-up?" is an accessibility question.
"Should we gamify this?" is a motivation question. This skill makes those
values explicit so Claude doesn't default to industry norms that may
contradict your project's beliefs.

The aesthetic skill answers: "What does it look like?"
This skill answers: "What does it believe?"

PreFlight integration: The preflight-checks.yaml "philosophy_engagement"
check will remind the agent to consult this skill when making product
decisions — feature design, default values, data collection, user flows,
and trade-off resolution.
-->

## The Why

<!-- Why does this project exist? Not what it does — why it matters.
     This is the North Star that every feature decision should serve. -->

{Describe the core purpose in 2-3 sentences. What problem are you solving
and WHY does that problem matter to you personally?}

## Core Beliefs

<!-- These are non-negotiable. They should NEVER be compromised, even
     when they make implementation harder. Write them as declarative
     statements about what you believe about your users and your domain.

     Good examples:
       - "Users own their data. Period."
       - "Privacy is a right, not a feature."
       - "Play, not homework — if using this feels tedious, we failed."
       - "Accommodate everyone — age, gender, language, ability, budget."
       - "Mastery over performance — no leaderboards, no streaks as primary reward."

     Bad examples (too vague):
       - "We care about users" (every product says this)
       - "Quality matters" (means nothing specific)
       - "Be innovative" (not a belief, it's a buzzword) -->

### Belief 1: {Name}
{What you believe and WHY. Include the reasoning — it helps Claude
apply this correctly in edge cases.}

### Belief 2: {Name}
{What you believe and WHY.}

### Belief 3: {Name}
{What you believe and WHY.}

<!-- Add as many beliefs as are genuinely non-negotiable. 3-7 is typical.
     If you have more than 10, some are probably preferences, not beliefs. -->

## Decision Filters

<!-- When Claude faces a product trade-off, these filters resolve it.
     Write them as questions Claude should ask itself. -->

### When choosing what data to collect:
<!-- Example: "Is this data necessary for the feature, or just nice to have?
     If nice to have, don't collect it. The user's trust is worth more
     than our analytics." -->

{Your filter for data collection decisions.}

### When choosing defaults:
<!-- Example: "The default should protect the user, not optimize for
     engagement. Opt-in for sharing, opt-out for exposure." -->

{Your filter for default value decisions.}

### When choosing between convenience and principle:
<!-- Example: "If the convenient path compromises a Core Belief, take the
     harder path. The inconvenience is temporary; the compromise is
     permanent." -->

{Your filter for convenience-vs-principle trade-offs.}

## Who This Product Is For

<!-- Be specific. Not "everyone." Who are the primary users, and what
     matters to THEM? This shapes feature priorities and communication
     tone. -->

{Describe your users — their context, their needs, what they value,
what frustrates them about existing alternatives.}

## What This Product Is NOT

<!-- Equally important as what it is. What should Claude actively
     resist building, even if it seems like a good idea? -->

- Not {anti-pattern 1 — e.g., "a social media platform optimizing for engagement"}
- Not {anti-pattern 2 — e.g., "a data broker disguised as a free service"}
- Not {anti-pattern 3 — e.g., "a gamification engine using streaks and FOMO"}

## The Gut Check

<!-- Your version of "does this feel right?" When Claude is unsure whether
     a decision aligns with the philosophy, this is the final test. -->

{Describe the intuitive test for whether a product decision is right.
Example: "Would I be comfortable explaining this decision to a user
who asked 'why does it work this way?' If the honest answer involves
our benefit over theirs, it's wrong."}
