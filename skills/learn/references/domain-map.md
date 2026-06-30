# Domain Map — Ajinkya's Background to CS/Engineering Concepts

Used in the MAP phase. Maps Ajinkya's existing domain knowledge to patterns and
concepts that appear in engineering work. When a new concept is encountered, look
for the closest analogy here first.

This file should be updated as new analogies are discovered.

---

## Domain 1: AWS Cloud

**Ajinkya's depth:** Deep — production experience with core services.

| CS/Engineering Concept | AWS Analogy | Analogy Quality | Where It Breaks |
|---|---|---|---|
| LRU cache eviction | Redis maxmemory-policy (ElastiCache) | STRONG | In-process cache is ephemeral, not distributed |
| Cache TTL | CloudFront invalidation TTL / S3 lifecycle | STRONG | Object storage TTL is file-level, not query-level |
| Retry with backoff | SQS visibility timeout + dead letter queue | PARTIAL | SQS manages retries at infrastructure level; code-level retry is application-managed |
| Circuit breaker | API Gateway throttling + fallback | PARTIAL | Circuit breaker is application-pattern; AG throttling is infrastructure |
| Rate limiting | API Gateway usage plans / Lambda concurrency limits | STRONG | Cloud limits are per-account/region; app-level limits are per-request |
| Event-driven architecture | Lambda + EventBridge + SQS | STRONG | Cloud event bus is persistent; in-process queues are ephemeral |
| Read replica / read-only | RDS read replica | STRONG | RDS replica is async replication; psycopg2 readonly=True is a session-level constraint |
| Config management | Systems Manager Parameter Store / Secrets Manager | STRONG | SSM centralizes config; .env is local file |
| Container deployment | ECS / Fargate | STRONG | ECS manages orchestration; Docker Compose is single-host |
| Health check endpoint | ELB health check | STRONG | ELB uses the check to route traffic; Gradio health is for local readiness only |
| IAM / least privilege | read-only DB user | PARTIAL | IAM is fine-grained per-resource; DB readonly=True is session-level |
| Content-addressed storage | S3 object key = sha256(content) | STRONG | S3 is immutable-by-key; our cache entries can be evicted |
| Idempotency keys | SQS message deduplication ID | STRONG | SQS deduplicates at queue level; application idempotency is per-operation |

---

## Domain 2: Azure IoT

**Ajinkya's depth:** Production experience with device management and telemetry.

| CS/Engineering Concept | Azure IoT Analogy | Analogy Quality | Where It Breaks |
|---|---|---|---|
| Message queue (thread+queue pattern) | IoT Hub message routing → Service Bus | PARTIAL | IoT Hub routes between services; in-process queue is within one process |
| Streaming / generator pattern | IoT Hub streaming ingest | PARTIAL | IoT streams are continuous from devices; Gradio generator yields discrete chunks |
| Device twin / state sync | Session state sync | WEAK | Device twin is bidirectional device/cloud state; session state is one-directional |
| Telemetry timestamp | Event time vs. processing time distinction | STRONG | Same concept: when did it happen vs. when did we see it |
| Edge processing | In-process computation before sending | PARTIAL | Edge computing reduces cloud calls; our pre-processing reduces LLM calls |
| Connection string / credentials | Database connection string | STRONG | Same concept, same risks (don't hardcode, use env vars) |
| Protocol (MQTT, AMQP) | API protocol choice (REST, GraphQL, WebSocket) | PARTIAL | IoT protocols are device-optimized; web APIs are request-optimized |

---

## Domain 3: Data Science / ML

**Ajinkya's depth:** Working knowledge — Python data stack, statistical reasoning, some ML ops.

| CS/Engineering Concept | Data Science Analogy | Analogy Quality | Where It Breaks |
|---|---|---|---|
| LLM token budget | Memory/compute budget in ML training | PARTIAL | Tokens are per-inference, not per-training-run |
| Prompt as feature engineering | Feature engineering for model input | STRONG | Both optimize input representation for model performance |
| Cache hit rate | Precision (exact match ratio) | PARTIAL | Hit rate is a performance metric, not a classification metric |
| Evaluation / eval scripts | Model evaluation metrics | STRONG | Same concept: measure how well the system does on representative inputs |
| Schema drift | Data drift in production | STRONG | Both: the data distribution changes from what the model/system expected |
| Semantic caching | Embedding-based similarity search | STRONG | Semantic cache IS an embedding similarity search — same math |
| SQL query as data retrieval | DataFrame query / pandas filtering | STRONG | SQL is more expressive; pandas is in-memory; both are declarative |
| System prompt as model configuration | Hyperparameter tuning | WEAK | Hyperparameters are numerical; prompts are semantic |
| RAG (Retrieval Augmented Generation) | k-NN lookup + model inference | STRONG | RAG retrieves context; k-NN retrieves neighbors — same pattern |

---

## Domain 4: Python (Server-side)

**Ajinkya's depth:** Strong — production Python, data pipelines, scripting.

| CS/Engineering Concept | Python Analogy | Analogy Quality | Notes |
|---|---|---|---|
| Abstract base class (ABC) | Python's `abc.ABC` | N/A — direct knowledge | |
| Dataclass / frozen dataclass | Python `@dataclass(frozen=True)` | N/A — direct knowledge | |
| Context manager | Python `with` statement | N/A — direct knowledge | |
| Generator function | Python `yield` | N/A — direct knowledge | |
| Module-level constants | Python module-level `SCREAMING_SNAKE_CASE` | N/A — direct knowledge | |
| Monkey patching in tests | Python `monkeypatch` fixture | N/A — direct knowledge | |
| Thread + queue | `threading.Thread` + `queue.Queue` | N/A — direct knowledge | Key: thread runs in background, queue is the channel |

---

## Domain 5: React / Frontend

**Ajinkya's depth:** Moderate — can build and modify, less familiar with deep patterns.

| CS/Engineering Concept | React Analogy | Analogy Quality | Where It Breaks |
|---|---|---|---|
| State management | React state / useState | STRONG | React state is component-local; application state is global |
| Streaming UI updates | React useEffect watching a changing value | PARTIAL | React re-renders on state change; Gradio generators yield chunks |
| Loading states | React loading spinner pattern | STRONG | Same concept — UI should indicate activity |
| Error boundaries | React error boundaries | STRONG | Same concept — catch errors at UI layer, show graceful message |
| Component props → function params | Python function arguments | STRONG | Same concept — explicit inputs produce deterministic outputs |

---

## Domain 6: MCP (Model Context Protocol)

**Ajinkya's depth:** Working knowledge — understands protocol, has built with it.

| CS/Engineering Concept | MCP Analogy | Analogy Quality | Where It Breaks |
|---|---|---|---|
| Tool use / function calling | MCP tool invocation | STRONG | MCP standardizes tool protocol; native tool use is vendor-specific |
| Tool result format | MCP tool response schema | STRONG | Both: structured response that the model can parse |
| Multi-step agentic loop | MCP multi-turn conversation | STRONG | MCP is stateless; our loop holds state in Python |
| Context window management | MCP context injection | PARTIAL | MCP injects context at protocol level; we manage context manually |

---

## Domain 7: MBA / Business

**Ajinkya's depth:** Formal training — prioritization, trade-off reasoning, stakeholder communication.

| Engineering Concept | MBA Analogy | Analogy Quality | Notes |
|---|---|---|---|
| Technical debt | Financial debt with interest | STRONG | Both accumulate cost over time; both need to be paid down |
| MVP (minimum viable product) | MBAs invented this term | N/A — direct knowledge | |
| P0/P1/P2 prioritization | Eisenhower matrix / strategic planning | STRONG | Same urgency/importance framework |
| ADR (architecture decision record) | Board meeting minutes with decision rationale | STRONG | Both document decisions and rejection reasoning for future reference |
| NFR check | Due diligence checklist | STRONG | Both: systematic check of non-obvious requirements before committing |
| Caching as cost reduction | Operational efficiency | STRONG | Every cache hit = cost saved = margin improvement |
| Monitoring / observability | KPI dashboard | STRONG | Both: measure what matters to know if the system is working |

---

## Concepts With No Strong Analogy (Known Gaps)

These are areas where Ajinkya's background doesn't provide a direct analogy.
Study these explicitly rather than force-fitting an analogy.

| Concept | Why No Strong Analogy | Recommended Approach |
|---|---|---|
| Semantic / embedding-based caching | Not in AWS standard services; data science knows embeddings but not this specific application | Build it in a project to learn by doing |
| Distributed consensus (Raft, Paxos) | AWS hides this in managed services | Conceptual reading: "Designing Data-Intensive Applications" Ch 9 |
| Database transaction isolation levels | Used RDS but not at this depth | Postgres docs on isolation levels + MVCC |
| Compiler design / AST parsing | Not in background | Not needed unless building DSLs |
| GPU programming / CUDA | Data science but not GPU computing | Not needed for current projects |

---

## CTO-Track Concept Map

Concepts that are specifically relevant to the transition from senior engineer to CTO:

| Engineering Concept | CTO Skill It Builds |
|---|---|
| ADR / decision documentation | Making defensible decisions; team alignment |
| NFR check | Systems thinking; non-functional requirements as product requirements |
| Stress testing / red team | Pressure-testing ideas before committing; intellectual honesty |
| PM review | Product thinking with technical depth; prioritization under constraints |
| Context management | Team knowledge management; documentation culture |
| Trade-off documentation | Strategic decision-making; communicating constraints |
| Technical debt tracking | Long-horizon thinking; technical strategy |
| Cross-project patterns | Platform thinking; reusable architecture |
