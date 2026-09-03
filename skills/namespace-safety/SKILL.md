---
name: namespace-safety
description: >
  Gate that checks for naming collisions before new skill names, MCP tool names, config
  keys, or server names are written. Scans SKILL-REGISTRY.md, server.py tool registrations,
  and ~/.claude/skills/ directories for conflicts. Fires when: Track A confirmation gate
  runs (before any generate_skill call), new MCP tool being added to a server, new server
  name proposed, new config key written to global Claude config. Produces: CLEAR or
  COLLISION verdict with specific conflict details and rename suggestions. Do NOT use for
  skill content review (code-review), dependency checks (dependency-audit), or install
  sequence verification (install-experience).
---

# namespace-safety — Naming Collision Gate

Checks names before they're written. A collision in `~/.claude/skills/` or in an MCP
server's tool registration shadows an existing capability globally — affecting every
Claude Code session on the machine, not just the current project.

Built on the observation that skill names, MCP tool names, and config keys all share a
flat namespace within their respective scopes — and a silent shadow is harder to debug
than a pre-write collision check.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full check: all 3 namespaces (skills, MCP tools, config keys) |
| `quick` | Skills namespace only — for Track A confirmation gate |
| `mcp only` | MCP tool names only — for new tool addition review |
| `config only` | Config key namespace only — for new config entries |
| `check: {name}` | Single name check across all namespaces |

fast-path: |
  If the candidate name contains no alpha characters (e.g. empty string): COLLISION immediately.
  If the candidate name exactly matches an existing entry: COLLISION without scanning.

---

## Context Capture (Always First)

```
CANDIDATE_NAMES:   [list of names to check — from Track A confirmation gate or explicit ask]
CANDIDATE_TYPE:    [skill | mcp_tool | mcp_server | config_key — determines which namespaces scan]
SCOPE:             [global (~/.claude/skills/) | project (youk/skills/) | server (which server)]
PROJECT_DIR:       [infer from session context]
```

If `CANDIDATE_TYPE` is ambiguous: check all three namespaces. Over-checking is safer than under-checking.

---

## The Three Phases

### Phase 1 — SKILL NAMESPACE

1. Read `knowledge/SKILL-REGISTRY.md`. Extract all registered skill names (lines starting with `| `).
2. List all directories under `~/.claude/skills/` and `{PROJECT_DIR}/skills/` — each directory name is a registered skill name.
3. For each candidate name:
   a. Exact match check: does the name appear in SKILL-REGISTRY.md or as a directory name? → COLLISION
   b. Semantic overlap check: does any existing skill's description cover the same trigger conditions or output type as the candidate? → OVERLAP WARNING (not a hard block, but surfaces the overlap)
   c. Shadow risk check: would this name shadow a Claude Code built-in skill or workflow command (`/done`, `/build`, `/start`, `/review`, etc.)? → SHADOW COLLISION

4. Emit per candidate:
   ```
   [SKILL NAMESPACE]
   {name}: CLEAR | COLLISION ({existing name}, reason) | OVERLAP ({existing skill}, degree: partial/full)
   ```

> Compact phase summary: skill namespace verdict known. COLLISION or SHADOW COLLISION blocks; OVERLAP warns.

---

### Phase 2 — MCP TOOL NAMESPACE

1. Read `servers/core/src/server.py` — extract all `@mcp.tool()` decorated function names and their `name=` parameter values.
2. Read `servers/code/src/server.py` — same extraction.
3. If any other `servers/*/src/server.py` files exist, read them too.
4. Check Claude Code's documented built-in MCP tool names (Read, Write, Edit, Bash, etc.) — these are fixed namespace entries.

5. For each candidate MCP tool name:
   a. Exact match in any server's tool registry → COLLISION (specify: which server, which line)
   b. Name resembles a built-in tool name (e.g. `read_file` vs built-in `Read`) → SHADOW WARNING

6. Emit per candidate:
   ```
   [MCP TOOL NAMESPACE]
   {name}: CLEAR | COLLISION (servers/core/src/server.py line 47, tool 'session_start') | SHADOW ({built-in name})
   ```

> Compact phase summary: MCP tool namespace verdict known. COLLISION blocks; SHADOW warns.

---

### Phase 3 — CONFIG KEY NAMESPACE

1. If candidate type is `config_key` or `mcp_server`:
   a. Read `~/.claude/claude_desktop_config.json` or `.mcp.json` if accessible — extract all server names under `mcpServers`.
   b. For `mcp_server` candidates: check for exact name match in existing `mcpServers` entries.
   c. For `config_key` candidates: check if the key already exists anywhere in the config JSON.

2. Check for OS-level conflicts: does the proposed server name conflict with any common tool name that might appear in PATH (e.g. naming an MCP server `git` or `python`)?

3. Emit:
   ```
   [CONFIG NAMESPACE]
   {name}: CLEAR | COLLISION (mcpServers.{name} already registered) | PATH_SHADOW (conflicts with system tool)
   ```

4. Emit the final verdict:
   ```
   [NAMESPACE SAFETY VERDICT]
   Candidates checked: {N}
   CLEAR:     {list}
   COLLISION: {list — each with specific conflict and suggested rename}
   OVERLAP:   {list — each with existing skill and overlap degree}
   SHADOW:    {list — each with shadowed name}

   Suggested renames for collisions:
     {name} → {name}-{qualifier} (e.g. "audit" → "install-audit" to avoid collision with "audit" skill)
   ```

> Compact phase summary: full namespace verdict with collision details and rename suggestions ready.

---

## Quality Bars (Non-Negotiable)

- **Exact match is always a hard block**: no exceptions. An exact name collision in any namespace is COLLISION, not a warning.
- **Shadow collisions are hard blocks**: a skill named `done` or `build` shadows youk's workflow commands globally — every session on this machine is affected. These are COLLISION, not OVERLAP.
- **Semantic overlap is a warning, not a block**: the user decides whether two skills are truly distinct. Provide the overlap degree (partial: different trigger conditions, full: same triggers + same output type) so the decision is informed.
- **Rename suggestions must be concrete**: "rename it" is not a suggestion. `"{name}" → "{name}-{qualifier}"` with the specific qualifier is a suggestion.
- **Scope annotation on every finding**: `~/.claude/skills/done` (global, all sessions) vs `youk/skills/done` (project-local). The blast radius changes the urgency.

## Hiring Validation

1. **Exact collision test**: Candidate name "code-review" is checked. SKILL-REGISTRY.md has an entry for "code-review". Does the skill return COLLISION with the existing skill name? Correct: yes, not OVERLAP.
2. **Shadow collision test**: Candidate name "done" is proposed as a skill. Does the skill return SHADOW COLLISION referencing `/done` workflow command? Correct: yes — this is a hard block.
3. **Semantic overlap test**: Candidate "python-review" is checked. Existing skill "code-review" has description "fires on code review requests for any language". Does the skill return OVERLAP (full) with a note that code-review already covers Python? Correct: yes with overlap degree specified.
4. **MCP tool collision test**: Candidate MCP tool name "route_task" is proposed. servers/core/src/server.py has `@mcp.tool(name="route_task")`. Does the skill return COLLISION with line number? Correct: yes.
5. **Rename suggestion test**: COLLISION found for candidate "audit". Does the skill suggest `"audit" → "install-audit"` or similar concrete rename? Correct: yes — not "rename it".

---

## Reference Files

| File | When to read |
|------|-------------|
| `knowledge/SKILL-REGISTRY.md` | Phase 1 — registered skill names and descriptions |
| `servers/core/src/server.py` | Phase 2 — core server tool registrations |
| `servers/code/src/server.py` | Phase 2 — code server tool registrations |

---

## Example Flows

**Track A confirmation gate — 3 candidates before generation:**
> Triggered automatically when Track A gate runs with candidates: ["self-heal", "install-experience", "done"]

Phase 1 only (quick mode from Track A):
SKILL NAMESPACE:
  self-heal: CLEAR (no existing entry, no semantic overlap with existing skills)
  install-experience: CLEAR
  done: SHADOW COLLISION (shadows /done workflow command — global, all sessions)

Verdict: 2/3 CLEAR. "done" → blocked. Present to user: "Cannot generate skill named 'done' — shadows /done workflow command. Suggest: 'install-done-gate' or 'close-gate'. Proceed with other 2?"

**MCP tool addition review:**
> "Adding a new tool called 'session_start' to the code server"

MCP TOOL NAMESPACE only:
  session_start: COLLISION — servers/core/src/server.py line 12, tool already registered as 'session_start' in core server.
  Suggested rename: `code_session_start` or `code_server_start`

**Config key check before writing new MCP server:**
> New server name "youk-browser" being registered

CONFIG NAMESPACE:
  youk-browser: CLEAR (not in mcpServers, no PATH conflict)
  → NAMESPACE SAFETY VERDICT: CLEAR — safe to register
