# Decision log

## 2026-08-27  [Langfuse trace granularity]
Chose:      One trace per run (session_start → session_end). Repairs are spans within.
Over:       One trace per repair.
Because:    A run is the atomic unit of user value — session context, routing, repairs, close. Per-repair traces lose the session frame and make aggregating cost/latency across a run impossible without a join.
Cost:       A long session with many repairs produces one large trace. Individual repair latency is visible as a span, not independently queryable without filtering.

## 2026-08-27  [Langfuse data handling]
Chose:      Self-host via Docker Compose (docker-compose.langfuse.yml).
Over:       Langfuse cloud free tier.
Because:    Stored context contains project contracts, skill gaps, and decision history — project-specific detail that shouldn't leave the machine. Self-host keeps all trace data local.
Cost:       Requires Docker running locally. No Langfuse cloud UI features (SSO, managed infra). One more service to keep up.

## 2026-08-27  [Proxy score definition]
Chose:      patch_cycle_rate: ratio of patch_cycle=True candidates to total candidates in run_health_check. 0.0 when no repairs queued.
Over:       Token cost per run, human-judged score.
Because:    Already computable from existing audit data on every run. No API call. Directly maps to the cheap proxy defined in EVAL.md.
Cost:       Zero candidates produces 0.0 which is indistinguishable from "all repairs stuck". Filter: only attach score when candidate count > 0.
