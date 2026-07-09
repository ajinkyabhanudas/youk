# Stack: Python
detection_key: python

Detected when: Python project without a strong DB signal (no psycopg2/SQLAlchemy/postgres).
Covers: Flask, FastAPI, CLI tools, data pipelines, ML inference services, scripts.

---

## Core concepts a developer will encounter

| Concept | What it is (one sentence) | When it appears |
|---|---|---|
| GIL (Global Interpreter Lock) | CPython allows only one thread to execute Python bytecode at a time | Threading for CPU-bound work (doesn't parallelize); IO-bound threading (does work) |
| Asyncio event loop | Single-threaded cooperative concurrency — tasks yield at `await` points | FastAPI handlers; async HTTP clients; async DB drivers |
| Generator / iterator protocol | Functions that produce values lazily on demand via `yield` | Streaming responses; large dataset processing; memory efficiency |
| Context manager (`with` statement) | Protocol for setup/teardown — guarantees cleanup even on exception | File handles, DB connections, locks, temp state |
| Decorator pattern | Functions that wrap other functions to add behavior | Auth, logging, retry, caching, rate limiting |
| `__slots__` / dataclass / frozen | Memory and attribute control on class instances | High-frequency object creation; immutable value objects |
| Module import side effects | Code that runs at import time can cause test pollution and circular imports | Test isolation; mock patching; startup time |
| `functools.lru_cache` / `cache` | In-process memoization with bounded or unbounded size | Pure function results that are expensive to recompute |
| Subprocess / shell invocation | Running external commands from Python (`subprocess.run`, `Popen`) | Build tools; docker commands; CLI wrappers |
| Virtual environment isolation | Project-scoped dependency sets that don't bleed between projects | Dependency conflicts; reproducible installs |
| Type hints + mypy/pyright | Static type annotations checked by a separate tool (not enforced at runtime) | Larger codebases; API contracts; IDE assistance |
| `__main__` guard | `if __name__ == "__main__":` prevents code from running when the module is imported | Script + library dual-use; test safety |

---

## Patterns that commonly surprise developers

- **Thread safety ≠ process safety**: `threading.Lock` protects within one process. Multiple Gunicorn workers (separate processes) share nothing in memory — shared state needs a DB or Redis.
- **Mutable default arguments**: `def f(x=[])` — the list is created once at function definition, not at call time. Classic Python gotcha that causes state to leak between calls.
- **`asyncio.run()` vs event loop reuse**: Calling `asyncio.run()` inside an already-running event loop raises `RuntimeError`. FastAPI manages the loop; don't create your own.
- **Import order matters for mocking**: `from module import func` binds `func` at import time. Patching `module.func` after the fact won't affect callers that already imported `func` directly. Patch where it's used, not where it's defined.
- **`lru_cache` holds references**: Cached results are never garbage collected while the cache lives. On a long-running server, this can cause memory growth if cached values are large.

---

## Common cross-stack analogies (starting points for MAP phase)

| Concept | Generic analogy | Analogy quality |
|---|---|---|
| GIL | Single-core processor — threads run but don't actually parallelize CPU work | STRONG |
| Asyncio event loop | Event loop in JavaScript (Node.js) / browser — single thread, non-blocking IO | STRONG |
| Generator | Lazy sequence / stream — values produced on demand, not upfront | STRONG |
| Context manager | try/finally with a cleaner syntax — guaranteed teardown | STRONG |
| Decorator | Middleware / interceptor pattern — wraps behavior without modifying core | STRONG |
| lru_cache | Memoization table / CDN edge cache for function results | STRONG |
| Virtual environment | Docker container for dependencies — isolated, reproducible | PARTIAL |
| Type hints + mypy | Compile-time type checking in a dynamically-typed language | STRONG |
