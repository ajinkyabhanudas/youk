# Contributing to youk

youk improves through two paths: skills contributed by the community, and the internal
compounding loop (audit → self_heal → proposal → apply). This guide covers the external path.

## Prerequisites

**For skill and docs contributions (no Docker required):**
- Claude Code (Anthropic CLI) — or any Claude agent
- A text editor

Skills (`skills/*/SKILL.md`) and knowledge files are plain markdown — no build step needed to edit them.

**For server code contributions (`servers/`):**
- Docker Desktop 24+
- Claude Code (Anthropic CLI)
- Python 3.11+

No API key is required to install or run youk — `install.sh` wires Claude Code's existing auth into the containers, and youk reads it at runtime.

## Setup

**Skills / docs only:**
```bash
git clone https://github.com/ajinkyabhanudas/youk
cd youk
# Edit skills/ or docs/ directly — no build needed
```

**Server code:**
```bash
git clone https://github.com/ajinkyabhanudas/youk
cd youk
make install   # builds images, registers MCP servers, patches your CLAUDE.md
make test      # verify both MCP servers respond correctly
```

## What you can contribute

### Skills (highest value)

Skills live in `skills/{name}/SKILL.md`. Each skill is a structured prompt that routes_to_skill
loads when Claude Code runs `/done`, `/check`, `/build`, etc.

To add a skill:

1. Read `knowledge/skill-schema.md` — the canonical template and quality bar
2. Create `skills/{name}/SKILL.md` following the schema (phases, quality bars, rules)
3. Add the skill to `docs/doc-map.yaml` under `skills:`
4. Test by calling `route_to_skill("{name}", "describe a task")` in Claude Code
5. Open a PR — include a one-paragraph description of what problem the skill solves

To improve an existing skill: use the proposal workflow rather than editing directly —

```
# Inside a Claude Code session with youk active:
add_proposal(
  title="...",
  rationale="...",
  action="SKILL_EDIT",
  target="{skill-name}",
  content="...",
  target_section="..."
)
```

This keeps the audit trail clean and lets `assess_skill` track the change.

### Server code (`servers/`)

- `servers/core/` — session lifecycle, routing, health, compaction (youk-core container)
- `servers/code/` — skill execution, NFR checks, code review tools (youk-code container)
- `servers/shared/` — shared data models, mounted as a live volume in both containers

After any server change:
```bash
ruff check servers/   # must pass clean
make test             # MCP handshake must succeed on both servers
make build            # rebuild Docker images before testing behavior
```

Note: `servers/shared/` changes take effect immediately without a rebuild (live volume mount).
`servers/core/` and `servers/code/` changes also take effect live — only rebuild when
`requirements.txt` or `Dockerfile` changes.

### Knowledge files (`knowledge/`)

- `knowledge/cross-project.md` — patterns that apply across all projects, feeds `generate_skill`
- `knowledge/skill-graph.yaml` — task routing rules (XS→XL sizing, skill assignments)
- `knowledge/skill-schema.md` — canonical skill template and quality bar

Edit these directly — they're read at runtime, no rebuild needed.

## Code style

- Python: `ruff check servers/` must pass before any PR
- No type: ignore comments without an explanation
- Functions under 40 lines where possible — split at natural boundaries
- No new dependencies without a documented reason in the PR description

## Commit format

One concept per commit. Plain English subject line. Example:

```
feat: add incident-review skill — post-incident structured review

Covers timeline reconstruction, contributing factors, and action items.
Follows the same SCOPE → ANALYZE → VERDICT pattern as code-review.
```

Avoid: "fixed stuff", "WIP", "misc changes", multi-concept commits.

## Observability (optional, maintainer tooling)

youk emits Langfuse traces for drift and repair-quality work. This is **not** part of
using youk. It no-ops unless `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY` and
`LANGFUSE_SECRET_KEY` are all set, so a normal install never touches it and never
needs the stack. You only want this if you are working on repair quality or
release-over-release drift.

```bash
docker compose -f dev/docker-compose.langfuse.yml up -d   # UI on http://localhost:3000
```

Create an account and project in the UI, then put the keys in `.env.langfuse` at the
repo root. It is gitignored via `.env.*`. Source it before running youk:

```bash
set -a && source .env.langfuse && set +a
```

**Before adding anything to a trace, read `docs/adr-011-trace-content-invariant.md`.**
Traces carry derived scalars, enums and hashed identifiers only, never free text from
a session. `_ALLOWED_METADATA_KEYS` in `servers/core/src/observability.py` enforces it
and `tests/test_observability_privacy.py` will fail if the surface widens. The
constraint exists so that pointing `LANGFUSE_HOST` at a shared team instance stays a
config change rather than a privacy incident, and telemetry privacy cannot be
retrofitted once data has left the machine.

## PR expectations

- Small and focused — one skill, one feature, one fix
- Include `make test` output in the PR description
- If your change touches guardrails, security paths, or proposal auto-apply logic:
  tag it with `security` and expect a closer review
- Skills require a real-world test case: describe a task you ran it against

## Questions

Open an issue with the `question` label. For security concerns, use the `security` label
and describe the impact — don't post exploits publicly.
