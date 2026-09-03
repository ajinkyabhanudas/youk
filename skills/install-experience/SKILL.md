---
name: install-experience
description: >
  Audits the first-run install sequence for youk: simulates install.sh execution,
  API key prompt flow, Docker build, and MCP server handshake verification. Distinct
  from simulate-experience (which covers developer personas post-install). Fires when:
  install.sh is modified, Docker config changes, "does install work?", "test onboarding",
  "first-run audit", new developer onboarding review, pre-release gate. Produces: a
  pass/fail audit of each install step with specific failure modes and remediation steps.
  Do NOT use for post-install skill usage (simulate-experience), code review (code-review),
  or dependency version checks (dependency-audit).
---

# install-experience — First-Run Install Sequence Audit

Validates that a new developer can install youk from zero to working MCP handshake
without tribal knowledge or undocumented steps. Every step must be explicit, every
failure must have a recovery path, and the audit must be runnable without being on
Ajinkya's machine.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full audit: all 4 phases |
| `quick` | SCAN + HANDSHAKE only — skip deep script analysis |
| `script only` | SCAN + SCRIPT-AUDIT only — verify install.sh correctness |
| `docker only` | DOCKER phase only — verify Dockerfile + build sequence |
| `enter: HANDSHAKE` | Skip to HANDSHAKE — assumes install already ran |

fast-path: |
  If install.sh hasn't changed since last audit (check git log -- install.sh)
  AND Docker image tag is unchanged: emit "Install sequence unchanged since last audit — skipping."

---

## Context Capture (Always First)

```
INSTALL_SCRIPT:    [path to install.sh — default: youk/install.sh]
DOCKER_COMPOSE:    [path to docker-compose.yml — default: youk/docker-compose.yml]
ENV_TEMPLATE:      [path to .env.example or equivalent — default: youk/.env.example]
LAST_CHANGE:       [git log --oneline -3 -- install.sh Dockerfile — infer from git]
TARGET_ENV:        [fresh machine | CI | existing install — infer from trigger context]
MCP_SERVERS:       [list of MCP server names expected after install — read from claude_desktop_config or .mcp.json]
```

Never read .env or any file containing actual API key values. If key presence must be
verified, check for non-empty variable name only — never print the value.

---

## The Four Phases

### Phase 1 — SCAN

1. Read `install.sh`. Map every step in execution order:
   - Dependency checks (what commands are checked with `which` / `command -v`)
   - Environment variable prompts (what the script asks for, in what order)
   - File writes (what gets created, where, with what permissions)
   - Docker commands (build, run, compose up sequences)
   - MCP registration commands (what gets written to claude_desktop_config or .mcp.json)

2. Check `README.md` or `INSTALL.md` for listed prerequisites. Cross-reference with what
   install.sh actually checks. Flag any prerequisite that is documented but not checked,
   or checked but not documented.

3. Check `.env.example`: does it list every variable that install.sh prompts for? Any
   prompt not in .env.example is undocumented — flag it.

4. Emit:
   ```
   [SCAN]
   Steps mapped: {N}
   Undocumented prerequisites: {list or "none"}
   .env.example gaps: {list or "none"}
   README/script mismatches: {list or "none"}
   ```

> Compact phase summary: full step map and documentation gaps known for deep audit phases.

---

### Phase 2 — SCRIPT-AUDIT

Walk each step from SCAN and verify:

1. **Dependency checks**: does the script exit with a clear error if `docker`, `python3`, `make`, or other required tools are missing? Failure mode: script runs partial steps then fails mid-way with a cryptic error.

2. **API key prompt**: does it prompt for each key individually? Does it validate non-empty before writing? Does it ever print the key value (grep for `echo $KEY` patterns)? Flag any `echo` that could leak a key value to stdout.

3. **File write idempotency**: if install.sh is run twice, does it overwrite existing config, append duplicate entries, or check first? Flag non-idempotent writes to `~/.claude/` — these are global state mutations.

4. **PIPESTATUS / exit code propagation**: does the script use `PIPESTATUS` or `set -e` to catch failures in piped commands? A `make build | tee log.txt` that ignores `make` exit code silently passes on build failure.

5. **Permission checks**: are any files written with overly broad permissions (e.g. `chmod 777`)? Check for world-writable files under `~/.claude/`.

6. **Emit one finding per step, severity: PASS | WARN | FAIL:**
   ```
   [SCRIPT-AUDIT]
   Step 1 — dependency check: PASS
   Step 2 — API key prompt: WARN — key echoed to stdout on line 47 (fix: remove echo)
   Step 3 — .env write: FAIL — non-idempotent; appends on re-run (fix: check before write)
   ...
   ```

> Compact phase summary: all script issues enumerated with line numbers; FAIL items block HANDSHAKE.

---

### Phase 3 — DOCKER

1. Read `Dockerfile` and `docker-compose.yml`. Check:
   - Base image is pinned to a specific tag (not `latest`) — `latest` breaks on upstream changes
   - Build ARGs that require API keys: verify they are not baked into the image layer (use `--secret` or env injection at runtime, not `ARG KEY=value`)
   - Health check: does `docker-compose.yml` define a `healthcheck` for each MCP server container?
   - Port conflicts: do any host ports conflict with common developer tools (5432=postgres, 6379=redis, 8080=common dev server)?

2. Simulate build without running Docker:
   - Read the build sequence from install.sh
   - Identify any `make` targets called during install — read the Makefile targets
   - Check that each target exists in the Makefile (grep for `^target-name:`)
   - Flag any `make {target}` call in install.sh where `{target}` is not defined in Makefile

3. Emit:
   ```
   [DOCKER]
   Base image pinning: {PASS | FAIL — image:latest used on line N}
   Secret handling:    {PASS | WARN — API key in build ARG on line N}
   Health checks:      {PASS | WARN — no healthcheck for {server}}
   Port conflicts:     {PASS | WARN — port 8080 may conflict}
   Make targets valid: {PASS | FAIL — target 'xyz' called but not defined}
   ```

> Compact phase summary: Docker config issues enumerated; any FAIL here blocks production use.

---

### Phase 4 — HANDSHAKE

1. Identify what MCP registration steps install.sh performs (writes to `claude_desktop_config.json`, `.mcp.json`, or similar).

2. Read the target config file path from install.sh. Verify:
   - The written JSON is valid (parse it mentally — check for trailing commas, unbalanced braces)
   - Each server entry has: `command`, `args`, and any required `env` keys
   - Server names don't collide with Claude Code built-in server names or other registered servers

3. Verify the startup sequence:
   - What command does Claude Code use to launch each MCP server?
   - Does that command match what the server's `__main__.py` or `server.py` expects?
   - Is the working directory set correctly, or does the server assume CWD = repo root?

4. Check that install.sh tells the user what to do after it completes (e.g. "restart Claude Code", "verify with /health") — a silent finish leaves the developer guessing.

5. Emit the final verdict:
   ```
   [HANDSHAKE]
   MCP config valid:    {PASS | FAIL — invalid JSON on line N}
   Namespace clean:     {PASS | FAIL — server name 'X' collides with built-in}
   Startup command:     {PASS | FAIL — command mismatch: script writes X, server expects Y}
   Post-install guide:  {PASS | WARN — no completion message}

   INSTALL AUDIT: {PASS | FAIL}
   Blockers:  {list of FAIL items, or "none"}
   Warnings:  {list of WARN items, or "none"}
   ```

> Compact phase summary: install sequence is either PASS (safe to ship) or FAIL with specific blockers.

---

## Quality Bars (Non-Negotiable)

- **Never read .env or secrets files**: audit presence only (does file exist, is variable non-empty), never print values. Any grep that could surface a key value is a violation.
- **Line numbers for every finding**: "line 47" not "somewhere in the script". Without line numbers, findings are unactionable.
- **Idempotency check is mandatory**: install.sh runs on re-install, not just first-install. Non-idempotent writes to `~/.claude/` affect every Claude Code session on the machine.
- **Docker image pinning is mandatory**: `FROM python:latest` in a Dockerfile that ships to other developers is a FAIL, not a WARN — it breaks reproducibility.
- **FAIL items block the audit verdict**: a single FAIL → overall INSTALL AUDIT: FAIL. The verdict is binary.

## Hiring Validation

1. **API key leak test**: install.sh has `echo "Your ANTHROPIC_API_KEY is: $ANTHROPIC_API_KEY"` on line 23. Does the audit flag this as FAIL with line number and specific fix? Correct: yes.
2. **Idempotency test**: install.sh appends a line to `~/.claude/claude_desktop_config.json` without checking if it already exists. Does the audit flag this? Correct: FAIL — non-idempotent write to global config.
3. **Missing Makefile target test**: install.sh calls `make handshake-verify` but Makefile has no such target. Does Phase 3 catch this? Correct: FAIL — target not defined.
4. **Secret-in-ARG test**: Dockerfile has `ARG ANTHROPIC_API_KEY`. Does Phase 3 flag this? Correct: WARN — key may be baked into image layer; recommend runtime injection.
5. **Fast-path test**: install.sh unchanged since last audit per git log. Does the skill emit the fast-path message and skip? Correct: yes, no redundant re-audit.

---

## Reference Files

| File | When to read |
|------|-------------|
| `install.sh` | Phase 1 (SCAN) and Phase 2 (SCRIPT-AUDIT) — primary audit target |
| `Dockerfile` | Phase 3 (DOCKER) — image pinning and secret handling |
| `docker-compose.yml` | Phase 3 (DOCKER) — health checks and port conflicts |

---

## Example Flows

**Pre-release gate — install.sh was just modified:**
> "audit the install experience before we ship"

SCAN (map 12 steps, find 1 .env.example gap: OPENAI_API_KEY not listed) →
SCRIPT-AUDIT (Step 6: API key echoed to stdout — FAIL) →
DOCKER (base image pinned, health checks present, no port conflicts — PASS) →
HANDSHAKE (MCP config valid, names clean — PASS) →
INSTALL AUDIT: FAIL — Blockers: [echo leaks key value on line 31]

**Quick smoke check after Dockerfile change:**
> "quick install check"

SCAN + HANDSHAKE only →
SCAN (no README/script mismatches) →
HANDSHAKE (MCP config valid, startup command matches) →
INSTALL AUDIT: PASS (script not re-audited — use 'script only' to check install.sh changes)

**CI integration check:**
> "install-experience enter: HANDSHAKE"

Skip SCAN/SCRIPT-AUDIT/DOCKER →
HANDSHAKE only: verify MCP config written by CI install step is valid JSON, names clean,
startup command matches server expectation →
Emit HANDSHAKE verdict only
