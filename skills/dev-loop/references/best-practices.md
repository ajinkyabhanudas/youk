# Best Practices Reference

Used in WRITE and REFACTOR phases of dev-loop. Apply the relevant section for
the detected language and framework.

---

## Universal (All Languages)

- **Single Responsibility**: each function/method does one thing.
- **Fail fast**: validate inputs at the boundary; don't propagate invalid state deep.
- **Explicit over implicit**: prefer clarity to cleverness.
- **Smallest public surface**: expose only what callers need.
- **No premature optimisation**: make it correct first, fast second.
- **Constants over magic values**: name every non-obvious literal.
- **Consistent error handling strategy**: pick one pattern and use it everywhere.

---

## TypeScript / JavaScript

### General
- Prefer `const` over `let`; avoid `var`.
- Enable `strict` mode in `tsconfig.json`.
- Use `unknown` instead of `any` for external data; narrow with type guards.
- Avoid `as` casts; prefer user-defined type guards or `satisfies`.
- Use optional chaining (`?.`) and nullish coalescing (`??`) over manual null checks.
- Prefer `structuredClone` over spread for deep copies.

### Async
- Always `await` Promises in async functions; never float a Promise.
- Use `Promise.all` / `Promise.allSettled` for concurrent independent operations.
- Wrap `async` event handlers in try/catch or use a central error boundary.

### React / Next.js
- Colocate state with the component that owns it; lift only when needed.
- Use `useCallback` / `useMemo` only after profiling; don't optimise by default.
- Prefer server components in Next.js 13+; client components for interactivity only.
- Keep effects minimal; prefer derived state over `useEffect` for synchronisation.

### Modules
- Use named exports; avoid default exports for maintainability.
- Barrel files (`index.ts`) are fine for public API; avoid deep barrel chains.

---

## Python

### Style
- Follow PEP 8; use `ruff` for formatting and linting.
- Use type hints everywhere; run `mypy` in strict mode.
- Prefer dataclasses or Pydantic models over plain dicts for structured data.
- Use f-strings for formatting; avoid `%` and `.format()` in new code.

### Patterns
- Use `pathlib.Path` over `os.path`.
- Context managers (`with`) for all resources: files, DB connections, locks.
- Generator expressions over list comprehensions when the full list isn't needed.
- Raise specific exception types; never `raise Exception("message")`.
- Use `logging` module — never `print()` in production code.

### Async (asyncio)
- Use `asyncio.gather` for concurrent coroutines.
- Avoid blocking calls inside `async` functions; use `asyncio.to_thread` for CPU work.
- Set timeouts explicitly with `asyncio.wait_for`.

### FastAPI
- Define request/response models with Pydantic v2.
- Use dependency injection for DB sessions, auth, config.
- Return typed responses; use `response_model` on every endpoint.
- Handle expected errors with `HTTPException`; unexpected errors via global handler.

---

## Go

### Style
- `gofmt` and `golangci-lint` are non-negotiable.
- Accept interfaces, return concrete types.
- Keep interfaces small (1–3 methods is ideal).
- Use table-driven tests.

### Error Handling
- Always check errors; wrap with `fmt.Errorf("context: %w", err)`.
- Define sentinel errors with `errors.New`; use `errors.Is` / `errors.As` for checks.
- Do not use `panic` in library code; reserve for truly unrecoverable states.

### Concurrency
- Prefer channels for communication; prefer mutexes for state.
- Always cancel goroutines via `context.Context`; no goroutine without an exit path.
- Use `sync.WaitGroup` for fan-out; `errgroup` when any error should cancel all.
- Race detector: `go test -race` must pass before ship.

### Packages
- Flat package structure for small projects; domain packages for larger ones.
- `internal/` for packages not meant for external use.
- Avoid `init()` functions; initialise explicitly.

---

## Rust

### Ownership & Borrowing
- Prefer borrowing (`&`) over cloning unless ownership transfer is needed.
- Use `Arc<Mutex<T>>` for shared mutable state; `Arc<RwLock<T>>` for read-heavy.
- Prefer `Rc`/`RefCell` only in single-threaded code.

### Error Handling
- Use `Result<T, E>` everywhere; never `unwrap()` in non-test code without a comment.
- Define domain errors with `thiserror`; propagate with `?`.
- Use `anyhow` for application-level error chains.

### Style
- `clippy` must pass with no warnings (`#![deny(clippy::all)]`).
- Use `derive` macros liberally (`Debug`, `Clone`, `PartialEq`) for boilerplate.
- Prefer iterators and combinators over explicit loops.
- Document public items with `///` rustdoc; include at least one example.

### Async (Tokio)
- Avoid `block_on` inside async contexts.
- Use `tokio::spawn` for concurrent tasks; hold `JoinHandle`s or detach deliberately.
- Prefer `tokio::select!` for racing futures over nested awaits.

---

## SQL / Database

- Always use parameterised queries or an ORM; never concatenate user input.
- Index: every foreign key and every column used in `WHERE` / `ORDER BY` / `JOIN`.
- Transactions: wrap multi-step mutations in a single transaction.
- Prefer explicit column lists over `SELECT *`.
- Use `EXPLAIN ANALYZE` to verify query plans on large tables.
- Keep migrations additive; avoid destructive changes in non-breaking releases.
- Store timestamps in UTC; convert at the presentation layer.

---

## REST API Design

- Use nouns for resources, HTTP verbs for actions.
- `GET` is idempotent and safe; `POST` creates; `PUT`/`PATCH` updates; `DELETE` removes.
- Return meaningful HTTP status codes; never 200 with an error body.
- Paginate unbounded list endpoints; document page size limits.
- Version via path prefix (`/v1/`) for breaking changes.
- Return errors as structured JSON: `{ "error": { "code": "...", "message": "..." } }`.
- Validate all inputs at the edge; reject unknown fields in strict mode.

---

## Testing Best Practices

→ See `references/test-strategies.md` for framework patterns.

Universal:
- Tests must be deterministic; no random seeds, no wall-clock dependencies.
- Tests must be independent; no shared mutable state between cases.
- Name tests descriptively: `test_<unit>_<condition>_<expected_result>`.
- Arrange–Act–Assert structure in every test body.
- Mock at the boundary (I/O, network, time); don't mock your own domain logic.
- Test behaviour, not implementation — avoid asserting on private internals.
