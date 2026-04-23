# .githooks/ — Project-level git hooks for PACT

## Why

PACT is project-agnostic infrastructure. Its commit history, templates,
docs, hooks, and skills **must not name specific consuming projects**
(those are downstream private repos that install PACT). Letting a
consuming project's name leak in here breaks portability and bleeds
private context across a public/internal boundary.

These git hooks enforce that boundary at commit time. Even if an editor
(human or agent) tries to commit content that names a consuming project,
the commit gets blocked before it lands.

## Hooks

| Hook | Fires | What it checks |
|------|-------|----------------|
| `pre-commit` | Before commit, after staging | Staged additions (added/modified lines only) for forbidden terms — case-insensitive substring match |
| `commit-msg` | After message is composed, before commit lands | Commit message body (excluding `#` comment lines) for forbidden terms |
| `forbidden_terms.txt` | (config, not a hook) | Newline-separated term list. `#` lines are comments |

## Setup (one-time, per clone)

These hooks live in `.githooks/` so they're tracked alongside the repo.
Tell git to use them instead of the default `.git/hooks/`:

```bash
git config core.hooksPath .githooks
```

You only need to run this once per clone. Verify with:

```bash
git config --get core.hooksPath   # should print: .githooks
```

The hook scripts must be executable:

```bash
chmod +x .githooks/pre-commit .githooks/commit-msg
```

## Bypass

If you genuinely need to commit a forbidden term (e.g., a case study
that explicitly attributes a downstream project, with their permission):

```bash
git commit --no-verify
```

Add a comment in the commit message explaining why the bypass is
justified, so future audits can verify intent.

## Extending the term list

Edit `forbidden_terms.txt`. One term per line, comments start with `#`.
Match is case-insensitive substring (so `kensic`, `Kensic`, and `KENSIC`
all match the same entry).

## What gets blocked vs. what's fine

**Blocked (will fire):**
- Adding the line `Brings PACT into alignment with Kensic's restructure`
- Renaming a file path that contains a consumer project name
- Adding code comments that reference a specific consumer

**Fine (won't fire):**
- Lines that already existed before staging (only ADDITIONS are scanned)
- Generic terms like "downstream projects", "consuming projects", "the project"
- Anything in `.git/`, `.githooks/forbidden_terms.txt` itself, or build outputs
