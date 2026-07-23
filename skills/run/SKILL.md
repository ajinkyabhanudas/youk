---
name: run
description: >
  DevOps skill. Start the project for manual verification — resolves the correct
  run command for the current project type, executes it, and surfaces any
  startup errors. Use before any "does this work?" question in a session.
---

# run — Project Start Gate

Resolves and executes the correct start command for this project. Eliminates
"what's the run command again?" and surfaces startup failures before manual testing.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Detect project type, run with defaults |
| `docker` | Force Docker compose up |
| `dev` | Force dev server (npm run dev, uvicorn --reload, etc.) |
| `test` | Run test suite instead of starting the server |
| `background` | Start in background, surface the URL |

---

## Execution Sequence

**Phase 1 — DETECT**

Determine project type and run command:

| Signal | Command |
|--------|---------|
| `docker-compose.yml` present | `docker compose up` |
| `Makefile` with `run` target | `make run` |
| `package.json` with `dev` script | `npm run dev` |
| `pyproject.toml` with `[tool.scripts]` | use the defined script |
| FastAPI / Flask app file | `uvicorn {app}:app --reload` |
| Plain Python | `python {entry_point}` |
| Fallback | surface the ambiguity, ask for the command |

Read `Makefile` and `package.json` first — project-defined commands always win
over inferred defaults.

**Phase 2 — RUN**

Execute the resolved command. Capture:
- Exit code (non-zero = startup failure)
- First 50 lines of stdout/stderr (surface startup errors, not full logs)
- Port the server is listening on (from log output: "Running on http://0.0.0.0:{port}")

**Phase 3 — VERIFY**

If a port was detected: output `Server ready at http://localhost:{port}`

If startup failed: output the first error line and the probable cause.

Common startup failure patterns:
- `Address already in use` → another process on the port: `lsof -i :{port} | grep LISTEN`
- `ModuleNotFoundError` → missing dependency: run install command first
- `Permission denied` → Docker socket: check `docker info`
- Database connection error → dependent service not running

---

## Output Contract

```
[DETECT] Command: {resolved command}
[RUN] Starting...
[READY] Server ready at http://localhost:{port}
```

Or on failure:
```
[DETECT] Command: {resolved command}
[FAIL] Startup error at line {n}: {error message}
[FIX] Probable cause: {one sentence}. Try: {concrete command}
```

---

## Quality Bar

- Never guess a port — read it from startup output.
- Never run `rm`, `drop`, or any destructive command as part of startup.
- If the project has no clear run command: surface the ambiguity in one sentence,
  ask for the correct command rather than guessing.
- Background mode must surface the PID so the process can be killed: `PID: {n}`
