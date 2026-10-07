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

## 2026-10-06  [G1 baseline battery: no measured benefit from full over bare]
Chose:      Treat G1 as failed by the plan's own rule and make S11 (slim always-on) and S12 (gates as code) the next work. S13 may shrink to test-run-only. Not read as proof that youk does not help: the evidence is inconclusive, not negative.
Over:       Starting S11 and S12 on assumption, and the opposite reading that full is fine because pass rate is not lower.
Because:    28 runs, 14 tasks, bare and full, one repetition, all in canopy, stencil and youk, $25.95 notional on a subscription. pass@1 bare 0.57 (0.29 to 0.86), full 0.64 (0.36 to 0.86). Paired difference +0.07 (+0.00 to +0.21), cost 1.20x (0.91 to 1.64), time 0.97x. The whole difference is one task (youk-12343343: bare fail, full pass). 13 of 14 tasks gave the same outcome in both arms: 7 passed in both, 5 failed in both (four of them youk tasks). The interval's lower bound is exactly 0.00, so the rule `lower bound <= 0` returned FAIL; at 14 tasks that is a boundary case.
Cost:       Two runs were not clean. youk-0313b9b1 bare hit the 900 s timeout after one tool call and shows $0.00 cost, so bare's cost is understated; full also failed that task. youk-f9c1c0c8 full stopped after 8 turns and 1 tool call and failed. Four youk tasks fail in both arms, so they may be unpassable from their prompts and add no signal. k=1 and Python-only. Not measured: compounding across sessions, review time, anything the model has seen. Full costs 20% more with no demonstrated gain, which is the part of G1 that stands.
