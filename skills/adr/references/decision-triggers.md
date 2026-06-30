# Decision Triggers — When to Write an ADR

Used in the SCOPE phase to classify the decision type and set the appropriate debate depth.

---

## Mandatory ADR Triggers

These always require a DECISIONS.md entry. No exceptions.

| Trigger | Decision Type | Reversal Cost |
|---|---|---|
| New module added to the codebase | Structural | Hard |
| New external dependency added | Dependency | Hard |
| New external API or third-party service integrated | Integration | Hard |
| Data model change (new table, column type, schema change) | Data | Very Hard |
| New authentication or authorization pattern | Security | Very Hard |
| Caching strategy chosen (backend, key design, TTL policy) | Performance | Hard |
| Retry / circuit break policy set | Reliability | Medium |
| Observability strategy chosen (logging structure, metrics) | Observability | Medium |
| Deployment pattern changed (Docker, serverless, VMs) | Infrastructure | Very Hard |
| Prior ADR reversed or significantly modified | Reversal | N/A |
| Technology choice between two real alternatives | Technology | Hard |

---

## Conditional ADR Triggers

These require an ADR entry IF the choice has non-trivial consequences or alternatives
exist. Skip only if the decision is obvious and reversible within a day.

| Trigger | Decision Type | When to Skip |
|---|---|---|
| Test framework chosen | Tooling | Skip if stdlib default (pytest for Python) |
| Linter / formatter chosen | Tooling | Skip if de-facto standard (ruff for Python) |
| File naming or directory convention | Convention | Skip if following existing pattern |
| Error message format | Convention | Skip if following existing pattern |
| Logging format | Observability | Skip if extending existing log structure |
| Concurrency approach (threads vs. async) | Architecture | Always document if non-default |
| Data serialization format (JSON / msgpack / pickle) | Data | Always document if non-JSON |
| Secret management approach | Security | Always document |

---

## Implicit Architectural Decisions (Easy to Miss)

These decisions are made silently by implementation choice. They look like one-line
config changes but each has reversal cost and a stated rationale worth recording.

| Implementation choice | The hidden decision | When to skip |
|---|---|---|
| Setting a UI framework theme (light / dark / system) | Supported rendering environments — forecloses future behavior | Skip only if explicitly temporary |
| Choosing NOT to implement a feature (dark mode, mobile, PDF export) | Deliberate deferral — records the reason so no future session re-debates it | Never skip — deferrals rot silently |
| Using a framework's default behavior vs. overriding it | "We accept this default" — states the assumption explicitly | Skip if default is well-known and reversible in < 1 hour |
| Any `# TODO: revisit` comment added to production code | Deferred decision — if it's worth a comment, it's worth an ADR | Skip only if the todo is trivially mechanical |

Signal to watch: if `/dev-loop` AUDIT phase flags an implicit architectural decision, that
is an ADR trigger regardless of how small the code change looks.

---

## NOT ADR Triggers

These do not require a DECISIONS.md entry. Documenting them would create noise.

- Bug fixes that implement already-decided behavior
- Adding a new endpoint that follows the existing endpoint pattern
- Adding tests
- Updating dependencies to newer versions (unless it's a major version with breaking changes)
- Refactoring within a module without changing its interface
- Copy/text changes in the UI
- Configuration value changes within an already-decided configuration system

---

## Decision Type Reference

### Structural Decisions
Define how the codebase is organized. Hardest to change because everything depends on them.
- Examples: module boundaries, service split, monorepo vs. multi-repo
- Reversal cost: high — touching module structure touches everything that imports it

### Dependency Decisions
What third-party code runs in this project.
- Examples: web framework, ORM, LLM SDK, serialization library
- Reversal cost: high — changing a dependency often requires rewriting the integration layer

### Integration Decisions
How this system communicates with external systems.
- Examples: REST vs. webhook, pull vs. push, sync vs. async
- Reversal cost: hard — external systems often cannot be changed

### Data Decisions
How data is stored, structured, and migrated.
- Examples: SQL schema design, denormalization choices, indexing strategy
- Reversal cost: very hard — data migrations are risky and slow

### Security Decisions
Authentication, authorization, data access patterns.
- Examples: auth mechanism, session storage, what data can a caller see
- Reversal cost: very hard — security changes affect all callers

### Performance Decisions
How the system achieves its latency and throughput targets.
- Examples: caching strategy, connection pooling, query optimization approach
- Reversal cost: medium — can usually swap without interface changes

### Reliability Decisions
How the system behaves under failure.
- Examples: retry policy, circuit breaking, failover strategy
- Reversal cost: medium — usually localized to the failure handling layer

---

## Reversal Cost Reference

| Level | Meaning | Full Debate Required? |
|---|---|---|
| Easy | Change takes < 1 hour, zero downstream impact | No — `quick` mode |
| Medium | Change takes < 1 day, limited downstream impact | Optional — judgment call |
| Hard | Change takes > 1 day or affects multiple callers | Yes — full debate |
| Very Hard | Requires data migration, external coordination, or has irreversible effects | Yes — full debate |

---

## Identifying the Right Question

The most common failure in ADRs is stating the decision too vaguely. A good decision
question is:
- **Specific**: "Should we use in-process LRU caching or Redis for the query cache?"
- **Answerable**: Has a definite answer, not "it depends"
- **Bounded**: Covers one decision, not several

Bad examples:
- "How should we handle caching?" — too vague, multiple decisions bundled
- "What's the best database?" — not bounded, not answerable in this context
- "Should we optimize performance?" — not a decision, it's a goal

Good examples:
- "Should we use Redis or an in-process dict for the query cache given our single-process deployment?"
- "Should data sanitization happen before or after the model context is built?"
- "Should retry logic live in the API client or the calling service?"
