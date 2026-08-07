# Getting Started with youk

Two paths: **youk-lite** (zero dependencies, any Claude agent, 60 seconds) or **full youk** (Claude Code + Docker, compounding skills). Start with lite if you're evaluating. Upgrade to full when you want the compounding loop.

---

## Path A — youk-lite (no install required)

Add this block to your project's `CLAUDE.md` (or `~/.claude/CLAUDE.md` for global use):

```markdown
# Working memory — youk-lite

## Contracts
<!-- Load verbatim every session — never paraphrase.
     When the user states a working agreement (always, never, from now on,
     remember to, make sure you): write it here immediately. Do not wait for
     end of session. -->

## Resume point
<!-- One sentence: where we stopped last session.
     If this was written more than 14 days ago: tell the user before loading it. -->

## Active decisions
<!-- Architecture/design decisions with date and rationale -->

## Direction gate (M+ tasks only)

REQUIRED before writing any code or making architecture decisions:
1. State what you're about to do in one sentence.
2. Name the assumption that, if wrong, makes this the wrong thing to do.
3. Name the simpler version of this that achieves 80% of the outcome.

If step 2 or 3 cannot be named: stop and ask the user one question before proceeding.
You MUST NOT proceed to implementation without completing this gate.
```

Just say a working agreement aloud — Claude writes it immediately (no "remember:" prefix needed). Tell Claude "update the resume point" at session end. Works in Claude Code, Claude.ai Projects, Cursor, Windsurf — anything that reads `CLAUDE.md`.

→ [Full youk-lite guide](youk-lite.md)

---

## Path B — full youk (Claude Code + Docker)

### No `make`? Use these equivalents

Every `make` target has a direct shell equivalent. Pick whichever works on your machine.

| Task | `make` | bash / Git Bash / WSL2 | PowerShell |
|------|--------|------------------------|------------|
| First install | `make install` | `bash scripts/install.sh` | `.\scripts\install.ps1` |
| Update + rebuild | `make update` | `git pull --rebase && bash scripts/install.sh` | `git pull --rebase; .\scripts\install.ps1` |
| Uninstall / revert | `make uninstall` | `bash scripts/uninstall.sh` | `.\scripts\uninstall.ps1` |
| Fast checkup | `make checkup-fast` | `python3 -m pytest tests/integration/test_l0_environment.py tests/integration/test_l1_infrastructure.py -v --tb=short -m integration --no-cov` | same (in Git Bash or WSL2) |
| Build images | `make build` | `docker build -t youk-core:latest -f servers/core/Dockerfile . && docker build -t youk-code:latest -f servers/code/Dockerfile .` | same |
| Unit tests | `make test-unit` | `python3 -m pytest tests/ -v -m "not integration"` | same |
| MCP handshake | `make verify-mcp` | `bash scripts/doctor.sh` | `wsl bash scripts/doctor.sh` |

### Step 1: Prerequisites

You need three things before installing youk:

**Claude Code**
The Anthropic CLI. Install from [claude.ai/code](https://claude.ai/code) or:
```bash
npm install -g @anthropic-ai/claude-code
```
Sign in with `claude` and confirm it works.

> **API key:** Signing in with `claude` writes your key to `~/.claude/.anthropic/api_key`. youk reads it from there automatically — no `ANTHROPIC_API_KEY` export required. If you're using the Claude Code desktop app, the signin flow handles this for you.

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

**macOS / Linux (bash):**
```bash
cd ~/.claude/youk
bash scripts/install.sh
# or, if you have make:
make install
```

**Windows — Git Bash (VS Code terminal) or WSL2:**
```bash
cd ~/.claude/youk
bash scripts/install.sh
```
Docker Desktop must be installed with **"Use WSL 2 based engine"** enabled (Settings → General). Git Bash users: Docker Desktop for Windows handles the bridge automatically.

**Windows — PowerShell:**
```powershell
cd ~\.claude\youk
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\install.ps1
```
Run as Administrator (or with Developer Mode enabled) for symlinks. The script creates directory junctions as fallback if symlinks fail.

> `make` is optional on all platforms. `bash scripts/install.sh` is the canonical install command — `make install` just calls it.

---

## Uninstalling / reverting

To return Claude Code to its pre-youk state:

**macOS / Linux / Git Bash / WSL2:**
```bash
cd ~/.claude/youk
bash scripts/uninstall.sh      # or: make uninstall
```

**Windows — PowerShell:**
```powershell
cd "$HOME\.claude\youk"
.\scripts\uninstall.ps1
```

This reverses everything the installer added — MCP servers, skill symlinks, the hooks
plugin, the `CLAUDE.md` block, and the scheduled jobs — and removes the Docker images.
It restores `CLAUDE.md` from a snapshot the installer took **before** its first change
(kept at `~/.claude/youk-restore/`), so any content you had before youk comes back
byte-for-byte.

Your accumulated knowledge is **preserved by default** (`~/.claude/youk/knowledge`,
`state/`, and `~/.claude/audit`), so re-installing later resumes with full history. To
remove that too:

```bash
bash scripts/uninstall.sh --purge
```

Other flags: `--keep-images` (leave the Docker images), `--dry-run` (print every action
without changing anything). On PowerShell these are `-Purge`, `-KeepImages`, `-DryRun`.
The youk repo itself is left in place — delete it with `rm -rf ~/.claude/youk` (or
`Remove-Item -Recurse -Force "$HOME\.claude\youk"`) when you no longer want it.

> Note: the PowerShell installer currently appends the `CLAUDE.md` block unfenced, so on
> Windows `uninstall.ps1` will ask you to remove that one section by hand (everything else
> reverts automatically). Fence/snapshot parity for `install.ps1` is a tracked follow-up.

---

This takes about 2 minutes on first run (downloading Python packages for the Docker images). Subsequent runs use Docker's build cache and are much faster.

What the installer does:
1. Creates `~/.claude/youk/state/` (session state files)
2. Creates `~/.claude/audit/` (session audit logs)
3. Builds the `youk-core:latest` Docker image
4. Builds the `youk-code:latest` Docker image
5. Registers both as MCP servers in Claude Code
6. Writes `state/path-map.env` so containers can resolve your host paths
7. Runs `make checkup-fast` (L0+L1) to confirm environment and Docker images are healthy

If install fails, run `make checkup-fast` (or the direct equivalent from the table above) to see specific failure lines for each check.

---

## Steps 4–5: Register MCP servers + patch CLAUDE.md

`install.sh` handles both of these automatically. If you need to run them manually:

```bash
# MCP server registration
claude mcp add --scope user youk-core --transport stdio -- \
  docker run -i --rm \
  -v "$HOME/.claude:/claude" \
  -v "$HOME/.claude/youk:/youk" \
  -v "$HOME/.claude/youk/servers/shared:/shared" \
  youk-core:latest

claude mcp add --scope user youk-code --transport stdio -- \
  docker run -i --rm \
  -v "$HOME/.claude:/claude:ro" \
  -v "$HOME/.claude/youk:/youk:ro" \
  -v "$HOME/.claude/youk/servers/shared:/shared" \
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

youk has a hierarchical checkup suite — each layer must pass before the next runs. Run the command that matches how much you want to verify:

```bash
# Fast: environment + Docker images + MCP handshake (< 20s, no state touched)
make checkup-fast

# Static: registry, YAML integrity, doc-map — no Docker required
make checkup-static

# Full body checkup L0–L6 (requires built images, ~60s)
make checkup
```

**Layer overview:**

| Layer | What it checks | Docker? |
|-------|---------------|---------|
| L0 Environment | Python ≥3.11, docker CLI, PyYAML, model imports | No |
| L1 Infrastructure | Docker daemon, image existence, MCP handshake, critical tool list | Yes |
| L2 Route Reachability | `route_task` sizing, session lifecycle, slug correlation | Yes |
| L3 Skill Completeness | SKILL-REGISTRY.md vs SKILL.md files, `route_to_skill` for all 52 capability skills | Yes |
| L4 Integrity | YAML validity, doc-map authority paths, stale state detection | No (static) / Yes (dynamic) |
| L5 Gates | NFR gate, challenge gate, task contract gate, guardrails, proposal lifecycle | No |
| L6 End-to-End | Full session round-trip: `session_start → route_task → route_to_skill → self_heal → session_end` | Yes |

If a layer fails, subsequent layers are skipped — their results would be meaningless on a broken foundation. Fix the failing layer and re-run.

`make checkup` is the full body check. `make health-check` is the org_score / improvement proposals command (separate — runs `self_heal()` autonomously via Docker, safe for cron).

---

## Keeping youk updated

```bash
cd ~/.claude/youk && make update
```

This pulls the latest code and rebuilds Docker images. Restart Claude Code afterward to pick up the new images.

### Picking up code changes without a full rebuild

youk mounts its source code as a live Docker volume (`-v ~/.claude/youk:/youk`). Most Python changes take effect without rebuilding the image — just restart Claude Code to get a fresh container.

**Two tiers:**

| Change type | What to do | Example |
|-------------|-----------|---------|
| Code only (`.py` files inside `servers/`) | Restart Claude Code | Bug fix in `session.py`, new skill signal logic |
| Dependency or shared model change | Rebuild + restart: `make build` then restart Claude Code | New package in `requirements.txt`, new field in `servers/shared/models.py` |

**How to tell which tier:** If `requirements.txt` or `servers/shared/` changed, rebuild. Otherwise, restart only.

```bash
# Code-only change — restart Claude Code (close and reopen the terminal)
# Then verify:
make checkup-fast

# Dependency change — rebuild first:
make build         # or: docker build -t youk-core:latest -f servers/core/Dockerfile .
# Then restart Claude Code, then verify:
make checkup-fast
```

**Windows (PowerShell equivalent):**
```powershell
# Rebuild:
docker build -t youk-core:latest -f servers/core/Dockerfile .
docker build -t youk-code:latest -f servers/code/Dockerfile .
# Then restart Claude Code.
```

---

## What to expect in a session

**Session start:** youk-core loads contracts, resume point, and session plan from the project you're in. Pending improvement proposals surface once: "youk flagged N proposals — review them?"

**During the session:** `route_task` runs silently for every non-trivial task. Small tasks get no ceremony. For M+ tasks (features, new modules, anything non-trivial), three gates run in sequence before implementation starts:
1. `optimize_intent` — runs two checks: (a) scope ambiguity — if the implementation forks, models both paths and asks the one question that collapses it; (b) intent opacity — if the goal contains quality words ("better", "right") or mindset language ("discover the pattern"), surfaces a goal-translation question before proceeding. Both checks block until resolved. You answer once; implementation proceeds on the resolved scope and intent.
2. `nfr_check` — four questions (performance, reliability, security, observability) answered in-session. Takes seconds, produces an NFR Decision Block that anchors the implementation.
3. `check_nfr_gate` — confirms the NFR block is present before code is written. Blocked = re-run nfr_check. Passed = dev-loop starts.

If a skill fails mid-session, youk patches it immediately rather than deferring to the next session.

**Session end:** Type `/done` when you finish — or any natural closing phrase: "done", "ship it", "commit", "ok thanks", "that's all", "looks good", "we're done", "wrap it up", "let's call it", "perfect", "good enough". This runs code-review + verify + learn, writes the resume point for next session, saves contracts, and sets `CloseCluster: yes` for org_score.

If you close the tab without `/done`: the next session opens with `⚠ [BLOCKED] Last session closed without /done — Run /learn NOW` as the first item in the session plan, not a nudge. `session_start` returns `force_learn: true` and writes `state/pending-action.json` durably — the block persists across tab-closes until `/learn` fires. When `route_to_skill("learn")` runs, the pending-action file is cleared and the session proceeds normally. The only thing permanently lost on tab-close is `CloseCluster: yes` for org_score — everything else is recovered.

**Skill self-improvement (automatic):** After each `/done`, `session_end` silently runs the signal detector — a deterministic scanner that reads `[EXAMINATION SURFACE]` blocks from skill output and compares what each skill examined against what was mandatory for the task type.

- `state/skill-signals.jsonl` accumulates one entry per skill per session.
- After 3 sessions with the same skill-dimension gap: a proposal is ready to generate.
- To act on it: run `generate_skill_improvement_proposal('skill-name')` from inside a Claude Code session — it produces a 5-part evaluable proposal queued in `PENDING.md`.
- Proposals require your approval before `apply_proposal` can modify anything.
- After a proposal is applied, the falsifier monitor watches it for 3 sessions and surfaces an alert if the signal didn't improve.

No activation needed. It runs automatically starting from the next session end.

**Context management:** youk manages context automatically via three hooks installed at setup:
- `PreCompact` — fires before Claude auto-compacts, injects a structured preservation brief so contracts and active task survive the summarizer verbatim.
- `UserPromptSubmit` — injects an intent-gated brief (~100-150 tokens) before each turn. When context pressure exceeds 40% of the window, it signals Claude to run `/compact` proactively — before auto-compaction fires at 70%.
- `PostToolUse` — captures active task state (file being edited, last error, current intent) after every tool call so post-compact resume is accurate.

No manual compaction needed. Context stays lean; auto-compaction rarely fires.

**Checking system health:** Type `/health` at any point. It returns `org_score` (0–10) and `loop_verdict` (IMPROVING / STALLED / etc.). The primary factor in score is capability skill invocation — did `/build`, `/review`, or `/done` fire this session? Close rate matters but doesn't dominate.

---

## Next steps

- [Guard rails guide](guardrails.md) — how hard and soft rules work
- [Building a variant](variants.md) — how to add youk-pm or youk-research
- [PHILOSOPHY.md](../PHILOSOPHY.md) — the design principles behind youk
