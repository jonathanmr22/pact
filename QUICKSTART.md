# PACT — Quickstart

**15 minutes from clone to working PACT setup in your project.**

---

## What PACT is, in two sentences

PACT is a governance methodology for AI-assisted software work. It's a set of shell hooks + structured YAML knowledge files that compound your project's self-understanding across sessions, so the agent gets smarter about your codebase the longer you use it.

It is **not** a workflow you follow rigidly. It is invisible infrastructure that keeps the agent honest while you work.

---

## Prerequisites

- A git repository for your project (PACT can `git init` one if you don't have one yet)
- Claude Code (or Gemini CLI — PACT supports both) installed
- Bash shell (Git Bash on Windows, default shell on Linux/macOS)
- Python 3.10+ in your PATH (one PACT script uses it for templating)

---

## Three steps

### Step 1 — Get PACT onto your machine (3 min)

Pick one. Both work; they install PACT to different places.

**Option A — Clone PACT to a sibling directory:**
```bash
cd ~/code   # or wherever you keep projects
git clone https://github.com/jonathanmr22/pact.git
```

**Option B — Install PACT as a Claude Code plugin:**
```bash
# Inside Claude Code:
/install-plugin jonathanmr22/pact
```

Either way, you now have PACT files on your machine. Note the path — you'll point `pact_init.sh` at them in step 2.

### Step 2 — Run `pact_init.sh` in your project (5 min)

```bash
cd ~/code/your-project    # the project you want to put PACT into
bash ~/code/pact/templates/scripts/pact_init.sh
```

The script asks ~5 questions (project name, primary languages, backend type, mobile/no, worktree isolation), then:

1. Generates a customized `CLAUDE.md` from PACT's template — your project name and stack baked in
2. Scaffolds the directory structure (`knowledge/`, `bugs/`, `feature_flows/`, `skills/`, `plans/`, `.claude/`)
3. Copies starter index files (`HANDOFF.yaml`, `KNOWLEDGE_DIRECTORY.yaml`, `_SKILL_INDEX.yaml`, etc.)
4. Copies the default hooks into `.claude/hooks/`
5. Writes a working `.claude/settings.json` with sensible default hook wiring

The script is idempotent — re-running skips files that already exist, so if you change your mind about an answer you can safely re-run.

### Step 3 — Open your project in Claude Code (5 min)

```bash
cd ~/code/your-project
claude
```

On the first session, the **PACT orientation hook** fires automatically. The agent sees a SessionStart context block teaching it:

- What PACT is in two sentences
- Where the key files live in your project
- The core cognitive redirections that always apply
- The session-start protocol

The orientation hook fires for the first 5 sessions, then goes silent (or earlier if your project accumulates real PACT artifacts before then). After that, PACT is invisible infrastructure running in the background.

**Verify it worked:**
- The agent should state *"I have read and will follow all <your project name> rules"* on its first response
- It should reference reading `HANDOFF.yaml` at session start
- It should be using the cognitive redirections from `CLAUDE.md` (verify-before-agreeing, fresh-read-before-edit, etc.)

---

## What you have now

After `pact_init.sh`, your project root has these new files and directories:

| Path | What goes here |
|---|---|
| `CLAUDE.md` | Always-loaded project rules + cognitive redirections. Customize the Project Philosophy section. |
| `HANDOFF.yaml` | Entry pointer — top priorities + last-session summary. Updated as you work. |
| `knowledge/packages/*.yaml` | One YAML per library you use, with verified API + gotchas. **Read before writing package code.** |
| `knowledge/research/*.md` | Synthesis of non-trivial investigations. Save findings here so future sessions don't re-research. |
| `knowledge/KNOWLEDGE_DIRECTORY.yaml` | Tag-based index across all knowledge systems. Scan before researching. |
| `bugs/{system}/{system}-NNN.yaml` | Bug investigations + resolutions. **Create the file BEFORE starting fixes.** |
| `bugs/_SOLUTIONS.yaml` | Reusable solutions across bugs. Check tags here when something breaks. |
| `feature_flows/*.yaml` | Lifecycle docs for critical systems — `participating_files`, `invariants`, `declared_dependencies`. |
| `skills/*.yaml` | Proven multi-step workflows with prerequisites, procedures, quality gates, gotchas. |
| `plans/dashboard/trees/{tree}/streams/*.yaml` | Active task ledger. Single source of truth for current and historical work. |
| `scripts/SCRIPT_CATALOG.yaml` | Every script in your project, with deps, tags, lessons, reusable patterns. |
| `.claude/hooks/*.sh` | Mechanical enforcement. PreToolUse / PostToolUse / SessionStart. |
| `.claude/settings.json` | Wires hooks into Claude Code. |

---

## What to do in your first PACT session

PACT is at its best when you treat it as a *forcing function*, not a checklist. Here's the most common high-value first session:

1. **Customize `CLAUDE.md`** — fill in the Project Philosophy section (core beliefs, decision filters, what this project is NOT). These are the values that govern every product decision. Five minutes of thought here saves hours of misaligned output later.

2. **Add your first feature flow** — pick the most important critical system in your project (auth, payments, sync, encryption — whatever's load-bearing). Run the `feature_flow_authoring` skill. Result: a `feature_flows/{system}_flow.yaml` with `participating_files`, `invariants`, `declared_dependencies`. The next time anyone touches that system, the agent knows what depends on it.

3. **Document one package you actually use** — pick the one that bites the most when its API surprises you. Add `knowledge/packages/{name}.yaml` with verified API + gotchas. Now every code-write that touches that package is correct first try.

That's it. Three things. The rest accumulates organically — every bug you fix becomes `bugs/{system}/{system}-NNN.yaml`. Every workflow you iterate on becomes a skill. Every research session leaves `knowledge/research/{topic}.md` behind. The system gets smarter with use.

---

## Common mistakes

**"I ran `pact_init.sh` but the agent isn't doing anything PACT-y."** — Most likely the orientation hook didn't fire, or the agent ignored CLAUDE.md. Verify: (a) `.claude/settings.json` was created, (b) `CLAUDE.md` exists at project root, (c) the agent's first response mentions reading `CLAUDE.md`. If the hook didn't fire, your `.claude/settings.json` may not be active — Claude Code's settings watcher needs to see the file at session start. Restart Claude Code or run `/hooks` to reload.

**"The CLAUDE.md is too long; I want to trim it."** — Don't trim aggressively. Each cognitive redirection prevents a specific failure mode that downstream projects have hit. If you trim the "verify before agreeing" redirect because it seems redundant, the next session will agree with a wrong correction. Trim only sections clearly inapplicable to your project (e.g. the Flutter-specific subsections if you don't have a mobile app).

**"I have an existing `.claude/` setup that already does what PACT does."** — `pact_init.sh` is idempotent and skips existing files. PACT plays well with other tools (memory plugins, task managers, workflow orchestrators). See `COMPARISON.md` for how it composes.

**"I'm getting hook errors on every command."** — Open `.claude/settings.json`, find the failing hook in the spinner output, and either fix the script (if it's missing a dependency) or remove that one hook entry. PACT hooks are designed to fail gracefully (exit 0 on error) but the underlying scripts may need Python or specific Bash features.

---

## Where to go next

- **`README.md`** — broader feature overview, comparisons to other tools
- **`COMPARISON.md`** — how PACT composes with Superpowers, Taskmaster, memory plugins, etc.
- **`docs/dashboard.md`** — the multi-tree status dashboard + Repo Map view
- **`docs/handoff_architecture.md`** — the HANDOFF.yaml + dashboard streams architecture (replaces the legacy PENDING_WORK.yaml pattern)
- **`templates/CLAUDE.md.template`** — the source of your project's CLAUDE.md, before customization

If you hit a wall, open an issue at <https://github.com/jonathanmr22/pact/issues> with the version (`cat VERSION` in your PACT install) and what you tried.

---

## Versioning

PACT uses Semantic Versioning. Same-day changes share major.minor and increment the patch (so today's three releases would be v0.12.0, v0.12.1, v0.12.2 — not three minor bumps). The CHANGELOG explains what's in each release; the version in `VERSION` matches the latest published release.
