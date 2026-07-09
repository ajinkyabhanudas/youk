# Stack: Node.js
detection_key: node

Detected when: JavaScript/TypeScript project without React signal; package.json with express/fastify/koa/hono.
Covers: REST APIs, GraphQL servers, CLI tools, background workers in Node.

---

## Core concepts a developer will encounter

| Concept | What it is (one sentence) | When it appears |
|---|---|---|
| Event loop phases | Node's event loop processes I/O callbacks, timers, and microtasks in a fixed phase order | Timing bugs; `setImmediate` vs `process.nextTick`; Promise ordering |
| Callback pattern vs. Promise vs. async/await | Three generations of async control flow — all still exist in the ecosystem | Reading library docs; mixing callback APIs with async code |
| Stream backpressure | When a readable produces data faster than a writable consumes it, the buffer fills — `pause()`/`resume()` or `pipe()` manage this | File processing; HTTP response streaming; ETL pipelines |
| Worker threads | True parallelism for CPU-bound work in Node — separate V8 isolates with message passing | Image processing; crypto; compute-heavy tasks |
| `process.env` and 12-factor config | Environment variables as the config layer — no config files in production | Secret management; per-environment behavior |
| CommonJS vs. ESM | Two module systems: `require()` (CJS) and `import/export` (ESM) — mixing them causes runtime errors | Dependency compatibility; `"type": "module"` in package.json |
| Error-first callback convention | Node callbacks: `(err, result)` — unchecked `err` is the root cause of most Node bugs | Any callback-based API |
| `cluster` module | Spawns one worker per CPU core, all sharing the same port — master routes incoming connections | Multi-core utilization; PM2 internals |
| `package-lock.json` / `yarn.lock` | Lock files that pin exact dependency versions for reproducible installs | CI/CD reproducibility; `npm ci` vs `npm install` |

---

## Patterns that commonly surprise developers

- **Unhandled Promise rejection crashes in newer Node**: Since Node 15, unhandled rejections crash the process. Silent errors that worked in Node 12 become fatal.
- **`require()` is synchronous and cached**: The first `require()` runs the module and caches it. Subsequent `require()` return the cached export. Mutations to the exported object affect all importers.
- **Event emitter memory leak warning**: Attaching more than 10 listeners to an EventEmitter triggers a warning. This surfaces when routes or handlers are registered in a loop without cleanup.
- **`this` in callbacks**: Arrow functions capture `this` lexically; `function` callbacks don't. In class methods passed as event handlers, `this` is lost unless bound or replaced with an arrow.

---

## Common cross-stack analogies (starting points for MAP phase)

| Concept | Generic analogy | Analogy quality |
|---|---|---|
| Event loop | Single-threaded cooperative multitasking — like Python asyncio but at the runtime level | STRONG |
| Stream backpressure | TCP flow control / network congestion window | PARTIAL |
| Worker threads | OS threads with message passing (no shared heap) ≈ Erlang processes | PARTIAL |
| Cluster module | Pre-fork model (Apache prefork) — one master, N workers, shared port | STRONG |
| ESM vs CJS | Python's `import` vs. `exec` — two module systems that can't always interoperate | PARTIAL |
