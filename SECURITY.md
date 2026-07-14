# Security

## Threat model

youk is a local developer tool. It runs two Docker containers on your machine, communicates via MCP (stdio), and writes to `~/.claude/`. It does not have a network-facing surface, does not phone home, and does not transmit session data anywhere.

The threat surface is:
1. **API key exposure** — the Anthropic API key used by `optimize_intent`
2. **Audit log content** — session audit logs may contain fragments of code, architecture decisions, or working agreements from your projects
3. **Cross-project knowledge promotion** — patterns extracted by `/learn` may be promoted across projects; proprietary patterns from one project could surface in another

## Credential handling

**What youk does:**
- Reads `ANTHROPIC_API_KEY` from environment variable
- Falls back to `~/.claude/.anthropic/api_key` (mounted read-only into the container)
- Uses the key only for `optimize_intent` API calls (intent compression)

**What youk never does:**
- Never reads `.env` files or any secrets file directly
- Never prints, logs, or surfaces API key values in output, tool results, or responses
- Never commits API keys — `ANTHROPIC_API_KEY` is an env var, not a file in the repo
- Never transmits session content, audit logs, or contracts to any external service

**Sourcing `.env` for scripts:** allowed — the key value is loaded into the shell environment, not read by youk directly.

## Audit log content

Audit logs are written to `~/.claude/audit/YYYY-MM.md`. They contain:
- Session metadata: project name, skills invoked, close cluster status
- Working agreements (contracts) stated during the session
- Task labels passed to `task_checkpoint`
- NFR gaps flagged during sessions

They do not contain: full conversation transcripts, code content, file contents, or user messages verbatim.

**If your audit logs contain sensitive project names or task labels:** the audit directory is local to your machine. It is not synced, not shared, and not read by any external service.

## Cross-project knowledge promotion

`/learn` extracts patterns from the current session and may promote them to cross-project knowledge in `knowledge/global/`. Promoted patterns are behavioral — commit conventions, routing preferences, skill gaps — not code or architecture specifics.

**If you work on proprietary projects:** review `knowledge/global/` periodically. Patterns promoted from a client project will appear in future sessions on other projects. Remove any that shouldn't cross project boundaries.

## Reporting a vulnerability

If you find a credential exposure, data leak, or other security issue:

1. Do not open a public GitHub issue
2. Email: ajinkya.dessai25@imperial.ac.uk with subject `[youk security]`
3. Include: description, reproduction steps, potential impact
4. Expected response: within 48 hours

## Key rotation

If your `ANTHROPIC_API_KEY` is compromised:

1. Rotate the key at console.anthropic.com immediately
2. Update your shell profile or `~/.claude/.anthropic/api_key`
3. Restart Docker containers: `docker restart $(docker ps -q --filter name=youk)`
4. Verify the new key is live: `make doctor`

youk holds no persistent copy of your API key — rotation is effective immediately after updating the source.
