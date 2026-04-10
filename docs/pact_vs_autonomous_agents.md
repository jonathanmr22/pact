# PACT vs Autonomous Agent Frameworks: A Comparison

**Last updated:** 2026-04-10

## The Two Schools of AI-Assisted Development

The AI coding tool ecosystem has split into two philosophical camps:

1. **Maximum autonomy** — spawn many agents, let them work independently, merge results
2. **Governed autonomy** — one orchestrator makes decisions, cheap workers grind, infrastructure prevents mistakes

PACT is firmly in camp 2. This document explains why, when each approach wins, and where they might converge.

---

## Comparison Table

| Dimension | Swarm Agents (OpenClaw, etc.) | Multi-Agent Harness (Claw Code, etc.) | PACT |
|---|---|---|---|
| **Philosophy** | Maximum autonomy — agents decide and act | Replicate Claude Code's architecture for any LLM | Constrained autonomy — infrastructure makes "correct" the default |
| **Agent model** | Many autonomous agents, each with full decision-making | Multi-agent orchestration with tool permissions | One frontier orchestrator + cheap specialized workers |
| **Enforcement** | Trust the agent's judgment | Tool permission gates (19+ tools) | Hooks mechanically block mistakes before they happen |
| **Memory** | Session-based, ephemeral | Session persistence | Structured cross-session knowledge (bugs, research, packages, feature flows, scripts) |
| **Cost model** | All tokens hit the same model | Provider-agnostic, but typically one model | Frontier model for thinking ($15/M), cheap models for grinding ($0.40-0.99/M) |
| **Coordination** | Agents coordinate via shared state or message passing | Built-in orchestration layer | No coordination needed — one mind holds the full picture |
| **What it optimizes** | "What can AI do?" (capability) | "How do we make Claude Code open-source?" (access) | "How do we make AI reliable?" (consistency) |
| **Cross-session learning** | Starts fresh each time | Session persistence helps | Every session inherits and extends structured knowledge |

---

## Where Swarm Approaches Win

Swarm agents excel at **embarrassingly parallel tasks** where subtasks are independent:

- Running tests across 20 files simultaneously
- Searching a large codebase for all instances of a pattern
- Generating boilerplate code for multiple modules at once
- Web research across many topics in parallel
- Processing large datasets where each item is independent

The key characteristic: **each agent's work doesn't affect any other agent's work.** No shared state, no sequential dependencies, no architectural decisions that ripple downstream.

## Where PACT Wins

PACT excels at **chain-dependent work** where decisions compound:

- Bug fixes that require tracing causal chains across multiple files
- Feature implementation touching database → service → state → UI layers
- Architecture decisions that affect every downstream consumer
- Security work where one wrong assumption compromises the entire system
- Long-running projects where consistency across sessions matters more than speed within one

The key characteristic: **every decision narrows or widens the solution space for every subsequent decision.** A name-based lookup in one Edge Function breaks 7 downstream consumers. A wrong migration cascade behavior corrupts the entire database. These chains require one mind that sees the full path.

### The Chain Problem in Detail

Consider a real-world bug: a map overlay shows "Welcome to Minneapolis" when the user is in Miami.

**Swarm approach:** Multiple agents investigate independently.
- Agent A patches the overlay text display
- Agent B adds a fallback city name check
- Agent C special-cases Miami in the Edge Function
- Result: 3 band-aids, root cause still alive. Next city with an ambiguous name hits the same bug.

**PACT approach:** One orchestrator traces the full causal chain.
- Edge Function returns metro by name → name parsing extracts "Miami" → matches Miami, OK instead of Miami, FL → all 7 downstream consumers inherit the wrong city
- Fix: replace name-based lookup with ID-based lookup across all 7 files
- Result: root cause eliminated. Every metro resolves correctly. The fix, the causal chain, and the anti-pattern are documented so no future session repeats it.

The orchestrator's advantage isn't speed — it's **coherence**. It holds the full dependency chain in context and makes one decision that fixes everything, instead of N agents each fixing their own symptom.

---

## The Cost Argument

In a real production session, PACT's delegation model produced:

| Task | PACT Cost | If Orchestrator Did Everything |
|---|---|---|
| 3,434 metro descriptions | ~$0.60 (Trinity) | ~$20 (Claude) |
| 275+ photo evaluations | ~$0.11 (Pixel/Gemini Flash) | Not possible (no vision) |
| Architecture decisions, bug fixes, governance | ~$3 (Claude) | ~$3 (same) |
| **Total** | **~$3.71** | **~$23+** |

The orchestrator spent tokens on **reasoning** (tracing the getCityMeta bug, designing the Voronoi pipeline, writing governance hooks). Workers spent tokens on **grinding** (generating descriptions, evaluating photos, classifying content).

This is ~6x more efficient than having the frontier model do everything. And the swarm alternative would be even more expensive — each autonomous agent loads its own context, reasons independently, and most of that reasoning is redundant because they're solving overlapping problems without shared understanding.

---

## The Cross-Session Compound Effect

The deepest difference isn't within a single session — it's across sessions.

**Swarm agents** start fresh. Each session rediscovers the architecture, re-reads the same files, re-learns the same gotchas. Session N is no faster than session 1.

**PACT agents** inherit a growing knowledge base:
- **SYSTEM_MAP.yaml** — file wiring traced once, available to every future session in 5 seconds
- **Feature flows** — lifecycle state machines that prevent the "fix one thing, break initialization" pattern
- **Bug tracker** — failed debugging attempts documented so no session repeats dead ends
- **Package knowledge** — verified API behavior that prevents "it doesn't work like I expected"
- **Script catalog** — reusable patterns and hard-won lessons from every script ever written
- **PENDING_WORK.yaml** — exact state handoff so the next session picks up, not starts over

Session N is dramatically faster than session 1, because every previous session left the project smarter. This is PACT's real thesis: **governance compounds.** Every hook added, every bug documented, every pattern cataloged makes the next session better. Autonomous agents can't compound because they have nothing to inherit.

---

## Could They Converge?

Yes. The architectures are complementary:

- **Swarm agents for parallel grinding** — web research, test execution, boilerplate generation — tasks where independence is the feature
- **PACT governance for decision-making** — which agent works on what, what the architectural constraints are, what patterns to follow, what mistakes to avoid
- **Structured knowledge as shared context** — instead of agents coordinating via message passing, they all read from the same SYSTEM_MAP, feature flows, and script catalog

The ideal system might be: PACT's orchestrator decides what to do and how, spawns swarm agents for parallelizable subtasks, reviews their output through PACT's checkpoint system, and memorializes the results in the knowledge base. The governance layer wraps the capability layer.

But today, for projects where architectural coherence matters — which is most real software — one governed orchestrator with cheap delegation outperforms a swarm of autonomous agents. Not because it's faster, but because it's right.

---

## Referenced Projects

- **OpenClaw** (github.com/open-claw/open-claw) — Open-source autonomous AI agent. Originally "Clawdbot" by Peter Steinberger. 100K+ stars. General-purpose (coding, web browsing, data extraction). Runs locally, connects via messaging platforms.
- **Claw Code** (claw-code.codes) — Clean-room Rust+Python rewrite of Claude Code's agent harness. Multi-agent orchestration, tool-calling, multiple LLM providers. Built after March 2026 source code leak.
- **PACT** (github.com/jonathanmr22/pact) — Programmatic Agent Constraint Toolkit. Governance framework for AI coding agents. Hooks, checkpoints, cognitive redirections, structured knowledge, multi-model delegation.
