# Feature Type → NFR Routing Matrix

Used in the CLASSIFY phase. Determines which NFR categories are mandatory, conditional,
or optional for each feature type.

**Legend:** M = Mandatory (cannot defer without explicit reasoning), C = Conditional
(mandatory if the feature has the stated property), O = Optional (may skip with a note)

---

## Feature Types

### New Module / Service
A standalone unit of functionality with its own lifecycle.

| NFR Category | Status | Condition for Mandatory |
|---|---|---|
| Caching | M | Always — new modules must decide cache strategy upfront |
| Retry + Timeout | M | Always |
| Observability | M | Always — logging + timing baseline |
| Auth / Authz | M | Always — even "internal only" is a decision |
| Idempotency | M | Always — new modules are called by others |
| Consistency | C | If module owns data |
| Rate Limiting | C | If public-facing or has external I/O cost |
| Data Volume | C | If module reads/writes a database |
| Error Propagation | M | Always — what does the caller receive on failure? |

---

### New API Endpoint
A new HTTP/gRPC/MCP endpoint exposed to callers.

| NFR Category | Status | Condition for Mandatory |
|---|---|---|
| Caching | M | Always — even "read-only, no caching needed" is a decision |
| Retry + Timeout | M | Always |
| Observability | M | Always — at minimum: request/response timing + status code |
| Auth / Authz | M | Always |
| Idempotency | M | For POST/PUT/DELETE; inferred safe-to-skip for GET |
| Rate Limiting | M | Always |
| Data Volume | C | If endpoint returns variable-size results |
| Error Response Format | M | Always — 4xx/5xx shape must be decided |

---

### LLM / External API Integration
Any code path that calls an LLM, external REST API, or third-party service.

| NFR Category | Status | Condition for Mandatory |
|---|---|---|
| Caching | **CRITICAL** | Always — cost-bearing paths must cache. No exceptions. |
| Retry + Timeout | **CRITICAL** | Always — external APIs fail transiently |
| Observability | M | Always — latency + cost tracking |
| Rate Limiting | M | Always — external APIs have rate limits; protect against thundering herd |
| Idempotency | M | Always — retries must be safe |
| Circuit Breaking | C | If external API is unreliable or business-critical |
| Fallback Strategy | C | What happens when the external API is unavailable? |
| Cost Budget | C | For LLM calls — what's the per-query token budget? |

---

### Background Job / Worker
An asynchronous process that runs outside the request lifecycle.

| NFR Category | Status | Condition for Mandatory |
|---|---|---|
| Retry + Timeout | M | Always |
| Idempotency | M | Always — jobs can be retried by the scheduler |
| Observability | M | Always — jobs must be observable without user-initiated tracing |
| Failure Alerting | M | Always — no user to observe silent failures |
| Concurrency | C | If multiple instances can run |
| Data Volume | C | If job processes variable-size datasets |
| Caching | O | Usually not applicable; include if job has repeated reads |

---

### UI Component / User-Facing Feature
A new Gradio component, page, or interaction pattern visible to end users.

| NFR Category | Status | Condition for Mandatory |
|---|---|---|
| Loading States | M | Always — every async operation must show progress |
| Error States | M | Always — every failure must show a user-readable message |
| Empty States | M | Always — zero results must be explicit, not blank |
| Observability | C | Log user-facing errors; timing if slow operations |
| Accessibility | C | WCAG 2.1 AA compliance for any field input or output |
| Caching | C | If UI triggers expensive backend calls |
| Responsive Layout | O | Decide if mobile/tablet use is in scope |

---

### Data Pipeline / ETL
A process that reads, transforms, or writes data at volume.

| NFR Category | Status | Condition for Mandatory |
|---|---|---|
| Idempotency | M | Always — pipelines re-run on failure |
| Data Volume | M | Always — row counts, batch sizes, memory constraints |
| Error Propagation | M | Always — partial failure handling |
| Observability | M | Always — row count, duration, error rate per run |
| Consistency | M | Always — what's the atomicity guarantee? |
| Retry + Timeout | M | Always |
| Caching | O | Useful for expensive lookups in transformations |

---

### Infrastructure / Config Change
Changes to Dockerfile, env vars, deployment config, CI/CD.

| NFR Category | Status | Condition for Mandatory |
|---|---|---|
| Backward Compatibility | M | Always — can existing deployments migrate safely? |
| Secret Management | M | Always — new env vars must follow secret hygiene rules |
| Rollback Plan | M | Always — how do we undo this change? |
| Observability | C | Does this change affect what gets logged or monitored? |
| Security Surface | C | Does this change expose new ports, permissions, or data? |

---

### Hotfix
A small, targeted change to correct a defect in production.

| NFR Category | Status | Condition |
|---|---|---|
| Does not regress existing NFRs | M | Always — check affected NFR blocks |
| Risk of unintended side effects | M | Always — state scope of impact |
| All others | O | Skip unless the hotfix itself introduces new I/O or logic paths |

> **Hotfix rule:** Run `/nfr-check quick` mode. If the fix is > 20 lines or touches
> a module boundary, escalate to full check.
