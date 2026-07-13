# youk — Engineering Memory System

This file is loaded by AI coding agents (Cursor, Windsurf, GitHub Copilot, Claude Code, and others) to give them working context about how this project operates.

---

## Working agreements (load every session — never paraphrase)

- commit format: small, logical commits with plain-English explanation; one concept per commit
- explain before acting: state what you are about to do and why before every non-trivial change
- gate discipline: complete all items in a gate before moving to the next; run lint after every code change
- no silent fallbacks: if a tool or API call fails, surface the error explicitly

---

## How youk works (for Claude Code users)

youk is a compounding engineering system. Every session, it:

1. Loads working agreements (contracts) from `knowledge/projects/{slug}/contracts.md`
2. Presents a resume point — picks up where you left off
3. Routes tasks by size (XS: respond directly / M+: challenge → nfr_check → dev-loop)
4. Extracts patterns at session end (`/done`) and promotes them to the knowledge base

The longer you use it, the more it adapts to exactly how you build.

**Full youk requires:** Docker Desktop + Claude Code + `make install` (~2 min).
**youk-lite (any agent):** copy the CLAUDE.md template from [docs/youk-lite.md](docs/youk-lite.md) — zero setup.

---

## Project structure

```
servers/core/    — session, health, routing, contracts (MCP server)
servers/code/    — skill routing, code review, NFR check (MCP server)
skills/          — capability skills (learn, challenge, dev-loop, code-review, etc.)
knowledge/       — gitignored: per-project contracts, decisions, domain concepts
plugin/          — Claude Code plugin (hooks: PreCompact, UserPromptSubmit, PostToolUse)
docs/            — guides, templates, architecture docs
tests/           — pytest suite (~530 tests)
```

---

## For agents other than Claude Code

If you are Cursor, Windsurf, GitHub Copilot, or any agent reading this file:

- The working agreements above apply to all sessions on this repo
- Read `knowledge/projects/youk/contracts.md` if it exists — those are active behavioral agreements
- Read `knowledge/projects/youk/decisions.md` if it exists — those are architecture decisions already made
- At session end, offer to update the resume point: "session stopped here — [one sentence]"

youk's full compounding loop (skill routing, self-heal, cross-project promotion) requires Claude Code with MCP. Everything else degrades gracefully to the working agreements above.
