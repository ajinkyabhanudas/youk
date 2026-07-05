# Python — Code Review Additions

Layer these checks on top of the base ANALYZE and SECURITY phases.
Skip any row where the surface is clearly not present in the diff.

---

## Python-specific ANALYZE additions

| Check | Severity |
|---|---|
| Mutable default argument: `def f(x=[])` or `def f(d={})` | HIGH — shared across all calls |
| Bare `except:` or `except Exception:` without re-raise or explicit handling | MEDIUM |
| `eval()` or `exec()` on any non-literal input | CRITICAL |
| Late binding in closures inside loops: `[lambda: i for i in range(n)]` | HIGH |
| `is` used for value equality (`x is "string"`, `x is 0`) | MEDIUM |
| Async function called without `await` — coroutine silently discarded | HIGH |
| `asyncio.get_event_loop()` used in async context (deprecated, use `asyncio.get_running_loop()`) | MEDIUM |
| Blocking call inside `async def` — `time.sleep`, `open()`, `requests.get()` without async equivalent | HIGH |
| Missing `__init__.py` in new package directory | MEDIUM |
| `global` or `nonlocal` used in new code without documented reason | MEDIUM |
| Catching `BaseException` or `KeyboardInterrupt` (swallows signals/exits) | HIGH |

---

## Python ORM / database additions (when Django/SQLAlchemy present)

| Check | Severity |
|---|---|
| `.all()` or `.filter()` inside a loop without prefetch → N+1 query | HIGH |
| Django: `select_related` / `prefetch_related` missing for FK/M2M accessed in template or loop | HIGH |
| Raw SQL via `cursor.execute()` with f-string or % formatting (not parameterised) | CRITICAL |
| QuerySet evaluated multiple times in same scope (not cached in variable) | MEDIUM |
| `objects.all()` without `.only()` or `.values()` on large tables | MEDIUM |
| Missing `db_index=True` on fields used in `.filter()` on high-volume tables | MEDIUM |
| Django: missing `select_for_update()` in a read-modify-write pattern | HIGH |

---

## Python type annotation additions

| Check | Severity |
|---|---|
| Public function missing return type annotation | LOW |
| Public function parameter missing type annotation | LOW |
| `Optional[X]` used where `X | None` is preferred (Python 3.10+) | INFO |
| `Any` used in a type position without a comment explaining why | MEDIUM |
| `cast()` used to work around a real type mismatch (masking an error) | MEDIUM |

---

## Python security additions (appends to base SECURITY phase)

| Check | Severity |
|---|---|
| `yaml.load()` without `Loader=yaml.SafeLoader` | CRITICAL — arbitrary code execution |
| `pickle.loads()` on untrusted data | CRITICAL — arbitrary code execution |
| `subprocess` with `shell=True` and any variable input | CRITICAL |
| `os.system()` with any variable input | CRITICAL |
| `tempfile.mktemp()` used instead of `tempfile.mkstemp()` (race condition) | HIGH |
| File opened with user-controlled path without `os.path.realpath()` check | HIGH |
| Secret read via `os.environ["KEY"]` — hard crash if missing; use `.get()` with documented fallback | MEDIUM |
