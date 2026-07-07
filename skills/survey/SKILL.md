---
name: survey
description: >
  Codebase survey skill. Produces a structured one-page map of the project
  answering the 12 standard onboarding questions: stack, architecture, modules,
  entry points, request flow, integrations, config, patterns, standards, key files,
  technical debt, and a summary. Writes output to knowledge/projects/{slug}/survey.md
  and tracks the git commit hash so session_start can detect when it's stale.
  Triggers on: /survey, "map this codebase", "onboard me", "explain the architecture",
  "what is this project", first session on a project with no prior context,
  joining a new project.

fast-path: |
  If survey.md already exists AND was written in the last 20 commits, surface the
  existing survey with a freshness note rather than re-running all 6 phases.
  Only re-run if the developer explicitly asks for a refresh.
---

# survey — Codebase Map (12 Onboarding Questions)

One command. One structured map. Everything a new developer needs to understand a codebase.
The output persists to `knowledge/projects/{slug}/survey.md` and loads in every future session brief.

---

## When to run

- Explicitly: `/survey`, "map this codebase", "explain the architecture"
- Automatically: session_start returns `survey_stale_note` with a staleness warning
- First session on a project where context_health is NONE or L1

---

## Phase 1 — STACK (Q1, Q7)

**Read these files** (whichever exist):
- `package.json` → `engines`, `dependencies`, `devDependencies`
- `requirements.txt` or `pyproject.toml` → key packages + versions
- `go.mod` → Go version, key imports
- `Cargo.toml` → Rust edition, key crates
- `pom.xml` → Java version, key dependencies

**Extract:**
- Runtime/language version
- Framework (Django, FastAPI, React, Next.js, Gin, etc.)
- 5 most significant dependencies with their purpose

**Config/secrets scan:**
- Look for: `.env.example`, `config/`, `settings.py`, `*.yaml`, `*.env.*`
- List what configuration surface exists (env vars, config files, secrets manager)

**Emit:**
```
[STACK]
Runtime: {version}
Framework: {framework}
Key dependencies: {name@version — purpose}, ...
Config: {how config is managed}
```

---

## Phase 2 — STRUCTURE (Q2, Q3, Q9)

**Read README.md** (full — this is the only full file read in the survey).

**Run:** `find . -maxdepth 3 -type d -not -path "*/node_modules/*" -not -path "*/.git/*" -not -path "*/__pycache__/*"`

**From the directory tree, identify:**
- Top-level modules and their apparent purpose (infer from directory name + key file names inside)
- Test directories
- Config/infrastructure directories
- Where the core business logic lives

**From README + directory inspection:**
- State the overall system purpose in 2 sentences
- List major services/modules with 1-line responsibility each

**Coding standards (infer from code samples):**
- Naming convention (snake_case / camelCase / PascalCase)
- Notable structural patterns (feature-based vs. layer-based, monorepo vs. single package)
- Test organization (unit alongside source vs. top-level tests/ dir)

**Emit:**
```
[STRUCTURE]
Purpose: {2-sentence system description}
Modules:
  {module/} — {responsibility}
  ...
Standards: {naming convention, test structure, notable conventions}
```

---

## Phase 3 — ENTRY POINTS + REQUEST FLOW (Q4, Q5)

**Find entry points** by looking for these patterns:
- Python: `if __name__ == "__main__"`, `uvicorn.run(`, `app.run(`, `wsgi.py`, `asgi.py`
- TypeScript/JS: `index.ts`, `server.ts`, `bin/`, scripts in `package.json`
- Go: `cmd/*/main.go`, `main.go`
- Other: `Makefile` run targets, `Dockerfile` CMD/ENTRYPOINT

**Trace one request flow** — pick the most representative endpoint (not auth, not health-check):
1. Route definition → handler function
2. Handler → any service/business logic layer
3. Service → any external call (DB query, cache read, external API)
4. Response shape

Keep this to 5-7 steps. Reference actual file:line numbers.

**Emit:**
```
[ENTRY POINTS]
Main: {file:line — what it starts}
Routes defined in: {file(s)}

[REQUEST FLOW — {endpoint}]
1. {route} → {file:line}
2. {handler} calls {file:line}
...
```

---

## Phase 4 — INTEGRATIONS (Q6)

**Grep for** (each in the source, not test files):
- Databases: `psycopg`, `pymongo`, `sqlalchemy`, `prisma`, `pg`, `mysql2`, `sqlite3`, `redis`
- Message queues: `kafka`, `rabbitmq`, `celery`, `bull`, `sqs`, `pubsub`
- Cloud SDKs: `boto3`, `google-cloud`, `azure-`
- HTTP clients: `httpx`, `requests`, `axios`, `fetch` (for external API calls)
- Auth: `jwt`, `oauth`, `passport`, `authlib`

For each found, identify **where** it's initialized and its **purpose** (not just "redis is used"):
- "Redis — session token cache (`app/cache.py:12`)"
- "Kafka — order events producer (`services/order_service.py:88`)"

**Emit:**
```
[INTEGRATIONS]
{name} — {purpose} ({file:line})
...
(None found: state explicitly)
```

---

## Phase 5 — PATTERNS + RISK (Q8, Q10, Q11)

**Design patterns** — infer from structure, not documentation:
- Repository pattern: if there's a `repositories/` or `*_repository.py` layer between handlers and DB
- Dependency injection: if functions receive DB/service instances rather than creating them
- Event-driven: if there are event emitters, listeners, or message producers/consumers
- CQRS: separate read/write paths
- Middleware chain: request passes through multiple layers before reaching handler

**10 most important files** — rank by:
1. Import frequency (grep for `from X import` or `import X` — files imported most are most central)
2. Explicit significance (files named `core.py`, `models.py`, `schema.py`, `router.py`, `app.py`)

List as: `{file} — {why it matters}`

**Risk flags:**
- Files >500 lines: `wc -l {files}` on suspected large files
- TODO/FIXME count: `grep -r "TODO\|FIXME\|HACK\|XXX" --include="*.py" --include="*.ts" . | wc -l`
- Missing tests: directories with no corresponding test files
- Direct DB queries in route handlers (bypasses service layer)

**Emit:**
```
[PATTERNS]
{pattern name}: {evidence}
...

[TOP 10 FILES]
1. {file} — {why}
...

[RISK FLAGS]
{flag}: {evidence and severity}
...
```

---

## Phase 6 — WRITE

**Produce the one-page summary** in this format:

```markdown
# {project} — Codebase Survey
*Generated: {date} | Commit: {git HEAD short hash} | Stack: {stack} {version}*

## 1. Stack & Versions
{stack section content}

## 2. Architecture
{2-sentence architecture summary}

## 3. Modules
| Module | Responsibility |
|---|---|
| {module} | {responsibility} |

## 4. Entry Points
{entry points}

## 5. Request Flow
{traced flow}

## 6. Integrations
{integrations table}

## 7. Config & Secrets
{config surface}

## 8. Design Patterns
{patterns found}

## 9. Standards & Structure
{conventions}

## 10. Key Files
{top 10}

## 11. Technical Debt & Risk
{risk flags}

## 12. Onboarding Summary
{3-bullet executive summary: what this system does, how to get started, the one thing a new dev must understand before touching production code}
```

**Write to disk:**
- Path: `knowledge/projects/{slug}/survey.md` (create `knowledge/projects/{slug}/` if needed)
- Record commit hash: call `youk-core.save_contract("survey_commit_hash:{git_head}", project_dir)` — this lets session_start detect staleness

**Confirm:**
```
[SURVEY COMPLETE]
Written: knowledge/projects/{slug}/survey.md
Covers: all 12 onboarding questions
Commit: {hash}
Next refresh: when >20 new commits land (session_start will notify)
```

---

## Quality bars

- **Specificity over comprehensiveness**: "Redis is used" is not a finding. "Redis — session token cache, TTL 30min (`app/cache.py:12`)" is.
- **File references required**: every integration, entry point, and key file must have a `file:line` reference. Surveyable from the output alone.
- **Honest risk flags**: do not soften or omit risk. "No tests found for payment/ module" is a risk flag, not an omission.
- **The request flow must be traced, not described**: don't say "the handler calls the service". Show `handler.py:45 → service.py:12 → db.py:89`.
- **If a section genuinely has nothing**: state it explicitly: "No external integrations found."
