# youk-lite

Zero-dependency memory layer for Claude. Works in any Claude agent that reads `CLAUDE.md` — Claude Code, Claude.ai Projects, Cursor, Windsurf, anything.

No Docker. No MCP servers. No install script.

---

## What it does

- Remembers your working agreements across sessions (contracts)
- Picks up where you left off — resume point per project
- Surfaces what you decided and why, every session
- Upgrades to full youk (compounding skills, self-healing, cross-project patterns) when you're ready

---

## Setup: one copy-paste

Add this block to your `CLAUDE.md` (or create one in your project root):

```markdown
# Working memory

## Contracts (load every session — never paraphrase)
<!-- youk-lite: add working agreements here, one per line -->
<!-- example: - commit format: small logical commits, one concept per commit -->
<!-- example: - always run tests before committing -->

## Resume point
<!-- youk-lite: update this at end of each session — one sentence, where you stopped -->

## Active decisions
<!-- youk-lite: record key architecture/design decisions here with date and rationale -->
<!-- example: ## 2026-07-13: Use SQLite not Postgres — single user, no concurrency needed -->

## Direction gate (M+ tasks only)
Before writing any substantial code or making architecture decisions:
1. State what you're about to do in one sentence
2. Ask: is this the right problem? Is there a simpler version?
3. List what you're assuming — which assumption, if wrong, reverses everything?
Only proceed after step 3. If anything is unresolved, ask one question before starting.
```

That's it. Claude reads this at every session start.

---

## How to use it

**At the start of a session:** Claude loads contracts and resume point automatically — nothing to type.

**When you make a working agreement** ("always run ruff before committing", "never mock the database in tests"):
- Tell Claude: "remember: always run ruff before committing"
- Claude writes it under `## Contracts`

**At the end of a session:** Tell Claude "update the resume point" — one sentence added under `## Resume point`. Next session picks up from there.

**When you make an architecture decision:**
- Tell Claude "log this decision: [what and why]"
- Claude adds a dated entry under `## Active decisions`

---

## The upgrade path

youk-lite gives you memory. [Full youk](https://github.com/ajinkyabhanudas/youk) gives you compounding:

| youk-lite | full youk |
|---|---|
| Contracts load every session | Contracts load + auto-promote cross-project |
| Resume point (manual update) | Resume point (auto-written at session end) |
| Decisions logged manually | Decisions tracked with ADR format + drift detection |
| Works in any Claude agent | Claude Code only (MCP required) |
| Zero setup | `curl -sL .../install.sh \| bash` (~2 min) |
| Static — same quality session 1 and session 100 | Compounding — skills self-patch, patterns promote |

Install full youk when:
- You want sessions to close automatically and capture what was learned
- You're doing serious engineering work (not just notes)
- You want cross-project pattern promotion (what you learn on one project loads on the next)

---

## Template: copy this into your CLAUDE.md

```markdown
# Working memory — youk-lite

## Contracts
<!-- Working agreements — load verbatim every session, never paraphrase -->

## Resume point
<!-- One sentence: where we stopped last session -->

## Active decisions
<!-- Architecture/design decisions with date and rationale -->

## Direction gate (M+ tasks only)
Before writing any substantial code or making architecture decisions:
1. State what you're about to do in one sentence
2. Ask: is this the right problem? Is there a simpler version?
3. List what you're assuming — which assumption, if wrong, reverses everything?
Only proceed after step 3. If anything is unresolved, ask one question before starting.
```
