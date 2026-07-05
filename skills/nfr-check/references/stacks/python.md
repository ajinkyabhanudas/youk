# Python — NFR Probe Additions

Layer these questions on top of the base NFR check for the applicable categories.
Answer from session context; only ask the user if the answer is genuinely unknowable.

---

## Concurrency + GIL

Applies when: task uses `threading`, `multiprocessing`, `asyncio`, or background workers.

1. **GIL impact**: Is this computation CPU-bound? If yes, `threading` will not parallelize it — `multiprocessing` or async I/O is required.
2. **Async blocking**: Does any `async def` function call a sync library function that blocks (e.g., `requests`, `time.sleep`, `open` without `aiofiles`)? If yes, the entire event loop blocks.
3. **Shared state**: Is any mutable object (list, dict, counter) accessed from multiple threads or coroutines without a lock or `asyncio.Lock`?
4. **Task cancellation**: Are `asyncio.Task` objects properly cancelled and awaited on shutdown? Uncancelled tasks leak resources.

**Decision criteria:**
- CPU-bound parallel work → `multiprocessing` or `concurrent.futures.ProcessPoolExecutor`
- I/O-bound parallel work → `asyncio` with async libraries
- Blocking call inside async → must wrap in `asyncio.to_thread()` or `loop.run_in_executor()`

---

## Memory + Resource management

Applies when: task loads large datasets, streams files, or processes records in loops.

1. **Generator vs. list**: Does the task build a large list in memory before processing? Could a generator or iterator replace it?
2. **Reference cycles**: Does the code create objects that reference each other? Python's GC handles this, but large cycles cause GC pauses.
3. **File handles**: Are all file handles, DB connections, and network sockets closed in a `finally` block or via `with` statement?
4. **ORM queryset size**: Does any queryset call `.all()` on a table that could have > 10k rows? Use `.iterator()` for large result sets.

---

## Startup + cold start

Applies when: task runs in a Lambda, Docker container, or CLI tool.

1. **Import cost**: Does the module import heavy libraries (`torch`, `transformers`, `pandas`) at the top level? Lazy imports reduce cold start time.
2. **Connection pool**: Is a DB or HTTP connection pool initialized at startup? Re-initializing per-request is expensive.
3. **Environment variables**: Are required environment variables validated at startup, not at first use?

---

## Dependency + packaging

Applies when: task adds a new `pip` package.

1. Is the package pinned to a specific version in `requirements.txt` or `pyproject.toml`?
2. Is the package actively maintained (last release within 12 months)?
3. Does the package have any known CVEs? (check PyPI safety advisory or `pip-audit`)
4. Does the package pull in large transitive dependencies that increase image/build size significantly?
5. For youk: does the package need to be added to both `servers/core/requirements.txt` and `servers/code/requirements.txt`, or only one?

---

## Django-specific additions

Applies when: stack is Django.

1. **Migrations**: Does this task add or alter a model field? Is a migration generated and included?
2. **Migration safety on live table**: Does the migration add a NOT NULL column without a default? That blocks the table lock — must use a multi-step migration.
3. **N+1 on admin**: Does any `ModelAdmin.list_display` include a related field without `list_select_related = True`?
4. **Signals**: Are Django signals used? Signals are implicit, hard to trace, and bypass the ORM transaction boundary — flag for discussion.
5. **CSRF**: Is the view exempt from CSRF (`@csrf_exempt`)? State why.

---

## FastAPI-specific additions

Applies when: framework is FastAPI.

1. **Pydantic validation**: Are all request bodies modelled as Pydantic models? Unvalidated `Request.body()` is a security surface.
2. **Dependency injection**: Are database sessions injected via `Depends()` and closed properly in the dependency cleanup?
3. **Background tasks**: Does `BackgroundTasks.add_task()` run a function that might fail silently? Background task errors are not surfaced to the caller.
4. **Response model**: Is `response_model` set on endpoints returning sensitive data? Without it, all model fields are returned.
