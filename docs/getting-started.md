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

---

## Step 2: Clone

```bash
git clone https://github.com/ajinkyabhanudas/youk ~/.claude/youk
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
2. Creates `~/.claude/audit/` (session audit logs)
3. Builds the `youk-core:latest` Docker image
4. Builds the `youk-code:latest` Docker image
5. Registers both as MCP servers in Claude Code
6. Writes `state/path-map.env` so containers can resolve your host paths
7. Runs `doctor.sh` to confirm everything works

If install fails, run `make doctor` to see specific Fix: lines for each failure.

---

## Steps 4–5: Register MCP servers + patch CLAUDE.md

`install.sh` handles both of these automatically. If you need to run them manually:

```bash
# MCP server registration
claude mcp add --scope user youk-core --transport stdio -- \
  docker run -i --rm \
  -v "$HOME/.claude:/claude" \
  -v "$HOME/.claude/youk:/youk" \
  youk-core:latest

claude mcp add --scope user youk-code --transport stdio -- \
  docker run -i --rm \
  -v "$HOME/.claude:/claude:ro" \
  -v "$HOME/.claude/youk:/youk:ro" \
  youk-code:latest
```

Verify with `claude mcp list` — both should show `✔ Connected`.

`install.sh` also patches `~/.claude/CLAUDE.md` with the youk identity block. If you already have a CLAUDE.md, it appends without overwriting existing content.

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

```bash
bash ~/.claude/youk/scripts/doctor.sh
```

Every check prints `PASS`, `WARN`, or `FAIL`. Every `FAIL` has a `Fix:` line. Re-run after fixing until all checks pass.

---

## Keeping youk updated

```bash
cd ~/.claude/youk && make update
```

This pulls the latest code and rebuilds Docker images. Restart Claude Code afterward to pick up the new images.

---

## What to expect in a session

**Session start:** youk-core loads contracts, resume point, and session plan from the project you're in. Pending improvement proposals surface once: "youk flagged N proposals — review them?"

**During the session:** `route_task` runs silently for every non-trivial task. Small tasks get no ceremony. M+ tasks get an nfr_check before implementation starts. If a skill fails mid-session, youk patches it immediately rather than deferring to the next session.

**Session end — type `/done`:** This is the most important habit. `/done` runs code-review + verify, saves contracts, and writes a `CloseCluster: yes` audit entry. That entry feeds org_score. Without it, the self-improvement loop can detect what happened but not confirm quality — and org_score stays capped.

If you close the tab without `/done`: youk detects the stale session at next open and writes a recovery entry. You won't lose context entirely, but the session won't count toward the quality score.

**Checking system health:** Type `/health` at any point. It returns `org_score` (0–10) and `loop_verdict` (IMPROVING / STALLED / etc.). The single biggest factor in score: did `/done` fire? Three consecutive `/done` sessions move the needle visibly.

---

## Next steps

- [Guard rails guide](guardrails.md) — how hard and soft rules work
- [Building a variant](variants.md) — how to add youk-pm or youk-research
- [PHILOSOPHY.md](../PHILOSOPHY.md) — the design principles behind youk
