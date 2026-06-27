# Getting Started with youk

This guide walks through setup from zero to a working youk installation.

---

## Step 1: Prerequisites

You need three things before installing youk:

**Claude Code**
The Anthropic CLI. Install from [claude.ai/code](https://claude.ai/code) or:
```bash
npm install -g @anthropic-ai/claude-code
```
Sign in with `claude` and confirm it works.

**Docker Desktop**
Must be installed and running. Download from [docker.com](https://www.docker.com/products/docker-desktop). After installing, verify:
```bash
docker ps  # should return a header row, not an error
```

**ANTHROPIC_API_KEY**
youk-core and youk-code make API calls for M/L/XL tasks. Add to your shell profile:
```bash
echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.zshrc  # or ~/.bash_profile
source ~/.zshrc
```

---

## Step 2: Clone

```bash
git clone https://github.com/ajinkya-dessai/youk ~/.claude/youk
```

If `~/.claude/` doesn't exist, Claude Code will have created it when you first ran `claude`. It's safe to add the `youk/` subdirectory here.

---

## Step 3: Install

```bash
cd ~/.claude/youk
bash scripts/install.sh
```

This takes about 2 minutes on first run (downloading Python packages for the Docker images). Subsequent runs use Docker's build cache and are much faster.

What the installer does:
1. Creates `~/.claude/youk/state/` (session state files)
2. Creates `~/.claude/briefs/` (task brief scratch space)
3. Symlinks `~/.claude/youk/skills` → `~/.claude/skills/` (if you have Claude skills installed)
4. Builds the `youk-core:latest` Docker image
5. Builds the `youk-code:latest` Docker image
6. Runs `validate.sh` to confirm everything works

If install fails, check the error and run `make build` manually to see Docker build output.

---

## Step 4: Register MCP servers

youk registers as MCP servers in Claude Code so its tools are available in every session.

```bash
# youk-core: session management, routing, self-healing (read-write)
claude mcp add --scope user youk-core --transport stdio -- \
  docker run -i --rm \
  -v "$HOME/.claude:/claude" \
  -v "$HOME/.claude/youk:/youk" \
  -e ANTHROPIC_API_KEY \
  youk-core:latest

# youk-code: skills, NFR checks, commit review (read-only)
claude mcp add --scope user youk-code --transport stdio -- \
  docker run -i --rm \
  -v "$HOME/.claude:/claude:ro" \
  -v "$HOME/.claude/youk:/youk:ro" \
  -e ANTHROPIC_API_KEY \
  youk-code:latest
```

The `--scope user` flag makes these available in all your Claude Code sessions, not just the current project.

Verify:
```bash
claude mcp list
```

Expected output:
```
youk-core: docker run ... - ✔ Connected
youk-code: docker run ... - ✔ Connected
```

---

## Step 5: Add youk identity to CLAUDE.md

Create or update `~/.claude/CLAUDE.md` with the youk instructions. A template is at `docs/claude-md-template.md` — copy it:

```bash
cp ~/.claude/youk/docs/claude-md-template.md ~/.claude/CLAUDE.md
```

If you already have a `CLAUDE.md`, append the youk block to the bottom of it.

---

## Step 6: Open a new Claude Code session

In a new terminal:
```bash
claude
```

youk is now running. No activation needed. When you start a session in a project directory, youk-core loads context from that project automatically.

Try these to verify it's working:
```
> what did we work on last?
> I need to fix a bug in the auth module
> I want to add a new feature — user notifications
```

youk routes silently based on task size. Small tasks get no ceremony. Large tasks get full architecture review suggestions.

---

## Verifying the full setup

Run the built-in validation:
```bash
cd ~/.claude/youk && bash scripts/validate.sh
```

Expected output:
```
Validating youk installation...
  [OK] youk-core image exists
  [OK] youk-code image exists
  [OK] skills directory accessible
  [OK] youk state directory exists
  [OK] knowledge directory exists
  [OK] config files present
  Testing youk-core MCP response...
  [OK] youk-core responds to MCP
  Testing youk-code MCP response...
  [OK] youk-code responds to MCP

All checks passed. youk is ready.
```

---

## Keeping youk updated

```bash
cd ~/.claude/youk
bash scripts/update.sh
```

This pulls the latest version, rebuilds Docker images, and validates the installation. The MCP server registrations don't need to change — Claude Code always starts a fresh container from the image on each session.

---

## What to expect in a session

**Session start:** youk-core loads context from the project you're in. If there are pending improvement proposals, it surfaces them once.

**During the session:** Route_task runs for every non-trivial task. You won't see the routing — it happens silently and shapes how Claude approaches the task.

**Session end:** When you say "done", "stopping", or "that's it", youk-core calls session_end, which validates the session summary and writes structured knowledge entries.

**Every 3 sessions:** A self-health check runs. If it finds patterns (skipped sessions, inconsistent skill usage), it writes proposals to `knowledge/proposals/PENDING.md`. On the next session start, it surfaces these: "youk flagged N proposals — review them?"

---

## Next steps

- [Guard rails guide](guardrails.md) — how hard and soft rules work
- [Building a variant](variants.md) — how to add youk-pm or youk-research
- [PHILOSOPHY.md](../PHILOSOPHY.md) — the design principles behind youk
