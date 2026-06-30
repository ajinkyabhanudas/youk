<div align="center">

# youk

**ambient AI engineering system**

*routes tasks · remembers context · learns from work · stays out of your way*

[![CI](https://github.com/ajinkyabhanudas/youk/actions/workflows/ci.yml/badge.svg)](https://github.com/ajinkyabhanudas/youk/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.13+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-required-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![MCP](https://img.shields.io/badge/protocol-MCP-8B5CF6)](https://modelcontextprotocol.io)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License](https://img.shields.io/badge/license-MIT-22C55E)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey)](https://github.com/ajinkyabhanudas/youk)

</div>

---

youk turns Claude Code from a chat assistant into an engineering system with persistent memory, structured task routing, live guard rails, and domain-specialized variants. It runs in Docker containers, speaks the Model Context Protocol, and learns across sessions without ever storing raw conversation transcripts.

> **Status:** Active development — v0.1.0. Core variant (youk-core + youk-code) is live.

---

## What youk does

| Without youk | With youk |
|---|---|
| You manually invoke skills and remember which ones apply | `route_task()` sizes the task and returns the right skills |
| Context is lost between sessions | `session_start()` restores project context from the last session |
| No guard rails — Claude can commit credentials | `check_commit_quality()` blocks credential commits at tool level |
| Learning is informal | Structured knowledge extracted and committed to the repo |
| Self-improvement requires manual effort | Health check every 3 sessions, proposals require your approval |

---

## Prerequisites

- **Claude Code** (the Anthropic CLI) — [install guide](https://docs.anthropic.com/en/claude-code)
- **Docker Desktop** 24+ (must be running)
- **Python 3.11+** (for local validation scripts)
- **Anthropic API key** in your environment: `export ANTHROPIC_API_KEY=sk-...`

---

## Quick start (5 minutes)

### 1. Clone the repo

```bash
git clone https://github.com/ajinkya-dessai/youk ~/.claude/youk
```

> If you already have a `~/.claude/` directory from Claude Code, that's fine — youk lives in a `youk/` subdirectory inside it.

### 2. Run the installer

```bash
cd ~/.claude/youk
bash scripts/install.sh
```

The installer:
- Creates runtime directories (`state/`, `knowledge/`)
- Sets up symlinks to your existing Claude skills
- Builds the Docker images (takes ~2 minutes on first run — subsequent builds use cache)
- Validates that everything responds correctly

### 3. Register the MCP servers

```bash
claude mcp add --scope user youk-core --transport stdio -- \
  docker run -i --rm \
  -v "$HOME/.claude:/claude" \
  -v "$HOME/.claude/youk:/youk" \
  -e ANTHROPIC_API_KEY \
  youk-core:latest

claude mcp add --scope user youk-code --transport stdio -- \
  docker run -i --rm \
  -v "$HOME/.claude:/claude:ro" \
  -v "$HOME/.claude/youk:/youk:ro" \
  -e ANTHROPIC_API_KEY \
  youk-code:latest
```

Verify both are connected:

```bash
claude mcp list
```

You should see `youk-core` and `youk-code` with status `Connected`.

### 4. Update your CLAUDE.md

Add the youk identity block to `~/.claude/CLAUDE.md`. A template is at `docs/claude-md-template.md`.

### 5. Open a new Claude Code session

youk starts automatically. No activation phrase needed.

---

## How it works

youk is two Docker containers registered as MCP servers in Claude Code:

```
┌─────────────────────────────────┐
│           Claude Code           │
│         (MCP client)            │
└──────────┬──────────┬───────────┘
           │          │
    ┌──────▼──┐  ┌────▼──────┐
    │youk-core│  │youk-code  │
    │         │  │           │
    │session  │  │nfr_check  │
    │routing  │  │skills     │
    │health   │  │review     │
    └──────┬──┘  └────┬──────┘
           │          │
    ┌──────▼──────────▼──────┐
    │   ~/.claude/ (volume)  │
    │   skills, context,     │
    │   audit logs           │
    └────────────────────────┘
```

**youk-core** (read-write access):
- `session_start` — loads project context, checks pending proposals
- `session_end` — validates and writes structured knowledge
- `route_task` — sizes the task, returns skill list and ceremony level
- `self_heal` — analyzes audit logs, generates improvement proposals
- `get_proposals` / `apply_proposal` — proposal review and approval

**youk-code** (read-only access):
- `nfr_check` — XS/S: instant 2-question logic check; M: API call; L/XL: full check
- `route_to_skill` — loads any skill's SKILL.md and runs it against your task
- `check_commit_quality` — scores commit message, blocks credential files

Both containers mount `~/.claude/` via Docker volumes. youk-core has write access (writes session state, knowledge entries, audit logs). youk-code has read-only access (reads skills, config, context).

---

## Guard rails

Guard rails are machine-readable contracts in `config/guardrails.yaml`. Hard rules are enforced at the tool level — they block, not suggest.

**Hard rules (block):**

| Rule | What it stops |
|---|---|
| `no-auto-apply-proposals` | Self-heal proposals auto-applying without your review |
| `no-credential-commits` | `.env`, `*secret*`, `*api_key*` files entering a commit |
| `knowledge-extraction-not-logging` | Raw conversation transcripts being stored |
| `no-destructive-without-confirm` | `rm -rf`, `reset --hard`, force push without confirmation |

**Soft rules (suggest once, skippable):**

| Rule | What it surfaces |
|---|---|
| `nfr-before-m-tasks` | Run NFR check before M+ sized tasks |
| `spec-before-l-tasks` | Write a spec before L/XL tasks |
| `session-close-cluster` | context-sync + learn + humanize at session end |
| `adr-for-real-alternatives` | Document architectural decisions with rejected options |

To add or change a rule: edit `config/guardrails.yaml` and commit. Guard rails are not prompt instructions — they're versioned code.

---

## Living knowledge

`knowledge/` stores what youk has learned — not what was said.

```
knowledge/
├── KNOWLEDGE-INDEX.md          ← health status, what exists
├── interpretation/
│   ├── user-intent.md          ← how your phrases map to actual intent
│   └── task-signals.md         ← what signals reveal task size
├── clarifications/
│   └── YYYY-MM/
│       └── YYYY-MM-DD-{slug}.md   ← one entry per intent-resolution case
├── domain/                     ← symlink to your existing skill knowledge base
└── proposals/
    └── PENDING.md              ← self-heal proposals awaiting review
```

Each session, `session_end` extracts structured insights and writes them here. Raw transcripts are never stored — that's enforced by the `knowledge-extraction-not-logging` hard rule.

Every 3 sessions, `self_heal` reads the last 30 days of audit logs and generates improvement proposals. Proposals sit in `PENDING.md` until you review and approve them via `apply_proposal(id, confirmed=True)`.

---

## Task routing

`route_task(task)` returns:

```json
{
  "size": "M",
  "ceremony": "standard",
  "skills": ["nfr_check", "dev_loop", "code_review", "verify"],
  "nfr_mode": "quick_4q",
  "warnings": ["NFR check recommended before this task"]
}
```

Sizes: **XS** (typo, clarification) → **S** (bug fix, config) → **M** (feature, refactor) → **L** (system, architecture) → **XL** (new project, migration)

Routing logic lives in `config/routes.yaml` — readable, editable, committed.

---

## Variants

youk is a platform. Each variant is one Docker image + one server file specialized for a domain:

| Variant | Domain | Status |
|---|---|---|
| youk-core | Session, routing, self-healing | Live |
| youk-code | Software engineering | Live |
| youk-pm | Product management, specs, ADRs | Planned |
| youk-research | Research, synthesis | Planned |
| youk-design | UX, Figma integration | Planned |
| youk-analytics | Production metrics loops | Planned |

Adding a variant means building one Dockerfile, one server.py, one entry in `config/variants.yaml`, and one `claude mcp add` command. The pattern is in [docs/variants.md](docs/variants.md).

---

## Development commands

```bash
# Build both images
make build

# Run tests (tools/list handshake)
make test

# Full rebuild from scratch
make rebuild

# Update after pulling changes
bash scripts/update.sh

# Validate installation
bash scripts/validate.sh
```

---

## Repository structure

```
youk/
├── config/
│   ├── guardrails.yaml     ← hard + soft rules (machine-readable)
│   ├── routes.yaml         ← task sizing + skill routing logic
│   └── variants.yaml       ← active variants
├── servers/
│   ├── shared/             ← Python modules shared across containers
│   │   ├── models.py       ← dataclasses (SessionState, RoutingDecision, ...)
│   │   ├── guardrails.py   ← rule enforcement
│   │   └── skill_loader.py ← reads SKILL.md files from volume mount
│   ├── core/               ← youk-core container
│   │   ├── Dockerfile
│   │   └── src/            ← server.py, session.py, routing.py, health.py
│   └── code/               ← youk-code container
│       ├── Dockerfile
│       └── src/            ← server.py, nfr.py, skills.py, review.py
├── knowledge/              ← living knowledge base (committed to repo)
├── scripts/
│   ├── install.sh          ← one-command setup
│   ├── update.sh           ← pull + rebuild + validate
│   └── validate.sh         ← post-install health check
├── docs/
│   ├── getting-started.md
│   ├── guardrails.md
│   └── variants.md
├── Makefile
├── PHILOSOPHY.md
└── README.md
```

---

## Troubleshooting

**`claude mcp list` shows youk-core/youk-code as disconnected**

Docker may not be running, or the images need rebuilding:
```bash
docker ps  # verify Docker is running
cd ~/.claude/youk && make rebuild
```

**`session_start` returns an error about missing context files**

The state directory needs to exist:
```bash
mkdir -p ~/.claude/youk/state
```

**`nfr_check` or `route_to_skill` can't find skills**

The volume mount uses your local `~/.claude/` path. Verify:
```bash
ls ~/.claude/skills/dev-loop/SKILL.md
```

If you're using a non-standard Claude config location, update the volume paths in your `claude mcp add` commands.

**Build fails with `COPY servers/shared/ /shared/` error**

Build must run from the repo root (not from inside `servers/core/`). The Makefile handles this — use `make build`, not `docker build` directly.

---

## Philosophy

Eight principles drive every design decision in youk. The full document is [PHILOSOPHY.md](PHILOSOPHY.md). The short version:

1. **Ambient over activated** — no "activate" phrase, always on
2. **Extract, don't log** — knowledge is insights, not transcripts
3. **Propose, never auto-apply** — self-healing requires founder approval
4. **Guard rails are versioned contracts** — committed YAML, not prompt text
5. **Ceremony proportional to risk** — XS task gets no ceremony, XL task gets full architecture review
6. **Variants are forms of intelligence** — specialization, not sprawl
7. **The repo is the truth** — everything important is in git
8. **Build the foundation right, then build fast** — Phase 1 is permanent

---

## Contributing

youk is a personal system in active development. Issues and pull requests are welcome, but changes that affect the guard rail contracts or knowledge structure need explicit discussion first — those are the load-bearing walls.

---

## License

MIT
