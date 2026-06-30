# Project context: youk

project-type: python
first-seen: 2026-06-28
last-seen: 2026-06-30

## What this project is

youk is an ambient AI engineering system built on Claude Code + MCP. Two Docker containers
(youk-core, youk-code) registered as MCP servers via stdio transport. Skills live in
~/.claude/skills/. Knowledge writes to ~/.claude/youk/ only — zero footprint in user repos.

## Gate progress (MLP toward UI developer pilot)

Gate 1 (platform bugs): COMPLETE — 5 commits
  - models.py: Proposal + SessionState extended
  - health.py: apply_proposal two-step diff/write
  - server.py: check_command MCP tool
  - intent.py: API key fallback
  - skill_loader.py + code/server.py: list_skills MCP tool

Gate 2 (install): COMPLETE — 3 commits
  - scripts/install.sh: single-command idempotent wizard
  - scripts/doctor.sh: actionable health check with Fix: lines
  - session.py: project type detection + contracts.md write path

Context system (pre-Gate 6): IN PROGRESS
  - compaction.py: compact_context() tool
  - session_end: explicit_contracts parameter + write path

Gate 3 (routing): PENDING
Gate 4 (workflow UX): PENDING
Gate 5 (UI love moment): PENDING
Gate 6 (session 2 better): IN PROGRESS

## Active decisions

- No headroom integration in youk internals — they are complementary products, not competing
- apply_proposal is two-step: confirmed=False=preview, confirmed=True=write
- Knowledge tier: CONTRACT > DECISION > EXPLORATION > CLARIFICATION
- compact_context generates briefs from structured files, not by summarizing conversation

## Recent commits

See git log for commit history.
