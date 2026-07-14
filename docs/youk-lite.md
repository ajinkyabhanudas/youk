# youk-lite

Zero-dependency memory layer for Claude. Works in any Claude agent that reads `CLAUDE.md` — Claude Code, Claude.ai Projects, Cursor, Windsurf, anything.

No Docker. No MCP servers. No install script.

---

## What it delivers (testable claims)

**A developer using youk-lite loses zero working agreements to session boundaries.** Every "always do X" you state is written to your CLAUDE.md immediately and loaded at the start of every future session — not at end of session, not when you remember to type it.

**Session 10 starts from a one-sentence brief of where session 9 ended** — not from scratch, not from re-reading a transcript. One sentence in, one sentence out, every session.

**Non-trivial work doesn't start until the direction is checked.** The direction gate is a behavioral instruction to Claude, not a checklist. If the gate's questions can't be answered, Claude stops and asks — it doesn't proceed to implementation.

### How to verify (session 2 test)
After your first session:
1. Say "always run tests before committing" — Claude writes it under `## Contracts` in CLAUDE.md now, not later.
2. Update the resume point.
3. Start a new conversation. Without typing anything, Claude should open with the contract and the resume point already loaded.

If step 3 works: youk-lite is delivering. If Claude asks you what the project is: the resume point wasn't saved.

---

## Setup: one copy-paste

Add this block to your `CLAUDE.md` (or create one in your project root):

```markdown
# Working memory

## Contracts
<!-- Load verbatim every session — never paraphrase.
     When the user states a working agreement (always, never, from now on,
     remember to, make sure you): write it here immediately. Do not wait for
     end of session. -->

## Resume point
<!-- One sentence: where we stopped last session.
     If this was written more than 14 days ago: tell the user before loading it.
     First session: type "save resume point: [what you did today]" before closing. -->

## Active decisions
<!-- Architecture/design decisions with date and rationale.
     Format: ## YYYY-MM-DD: Decision — rationale in one sentence -->

## Direction gate (M+ tasks only)

REQUIRED before writing any code or making architecture decisions:
1. State what you're about to do in one sentence.
2. Name the assumption that, if wrong, makes this the wrong thing to do.
3. Name the simpler version of this that achieves 80% of the outcome.

If step 2 or 3 cannot be named: stop and ask the user one question before proceeding.
You MUST NOT proceed to implementation without completing this gate.
```

That's it. Claude reads this at every session start.

---

## How to use it

**At the start of a session:** Claude loads contracts and resume point automatically — nothing to type.

**When you make a working agreement** ("always run ruff before committing", "never mock the database in tests"):
- Just say it. Claude writes it under `## Contracts` immediately — the comment instructs it to.
- No need to say "remember:" first. The instruction is in the template.

**At the end of your first session:** Type: `save resume point: [one sentence about what you did today]`. That seeds session 2. Without it, session 2 starts cold — the template is there but empty.

**At the end of subsequent sessions:** Tell Claude "update the resume point" — one sentence replaces the previous one.

**When you make an architecture decision:**
- Tell Claude "log this decision: [what and why]"
- Claude adds a dated entry: `## YYYY-MM-DD: Decision — rationale`
- Use ISO date format so full youk can detect staleness automatically when you upgrade.

**The direction gate fires automatically** on any non-trivial task — Claude reads the gate instruction from your CLAUDE.md and runs the three questions before writing code. If it skips the gate, say "run the direction gate" and it will.

---

## The upgrade path

youk-lite gives you memory. [Full youk](https://github.com/ajinkyabhanudas/youk) gives you compounding:

| youk-lite | full youk |
|---|---|
| Contracts written immediately on statement | Contracts auto-promoted cross-project |
| Resume point (manual update) | Resume point (auto-written at session end) |
| Direction gate (behavioral instruction) | Direction gate (tool-enforced — `route_task` blocks dev-loop) |
| Staleness detection (14-day warning in template) | Staleness detection + audit trail |
| Decisions logged manually | Decisions tracked with ADR format + drift detection |
| Works in any Claude agent | Claude Code only (MCP required) |
| Zero setup | `curl -sL .../install.sh \| bash` (~2 min) |
| Same quality session 1 and session 100 | Compounding — skills self-patch, patterns promote, org_score tracks |

Install full youk when:
- You want sessions to close automatically and capture what was learned
- You want the direction gate to be tool-enforced (not behavioral)
- You want cross-project pattern promotion (what you learn on one project loads on the next)
- You want to track outcome quality (`prevented_cost_score` shows what skills actually caught)

---

## Template: copy this into your CLAUDE.md

```markdown
# Working memory — youk-lite

## Contracts
<!-- Load verbatim every session — never paraphrase.
     When the user states a working agreement (always, never, from now on,
     remember to, make sure you): write it here immediately. Do not wait for
     end of session. -->

## Resume point
<!-- One sentence: where we stopped last session.
     If this was written more than 14 days ago: tell the user before loading it.
     First session: type "save resume point: [what you did today]" before closing. -->

## Active decisions
<!-- Architecture/design decisions with date and rationale.
     Format: ## YYYY-MM-DD: Decision — rationale in one sentence -->

## Direction gate (M+ tasks only)

REQUIRED before writing any code or making architecture decisions:
1. State what you're about to do in one sentence.
2. Name the assumption that, if wrong, makes this the wrong thing to do.
3. Name the simpler version of this that achieves 80% of the outcome.

If step 2 or 3 cannot be named: stop and ask the user one question before proceeding.
You MUST NOT proceed to implementation without completing this gate.
```

**The one thing that makes session 2 worth having:** Before you close your first session, type `save resume point: [one sentence about what you did today]`. That's the seed. Without it, session 2 opens to an empty template — same as session 1.
