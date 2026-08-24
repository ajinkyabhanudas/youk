# youk v1.0 — Release Definition

*Authority: ADR-010 (2026-08-08). This document is the committed form of that decision.*

youk v1.0 ships when all three floors hold. All three held as of 2026-08-24.

---

## Floor A — Capability (L1-L6, each with a passing exit-1 test)

| Level | What it means | Test |
|---|---|---|
| L1 Routed | Tasks route to the correct skill via `route_task` | `test_route_task.py` |
| L2 Context-loaded | Contracts and decisions survive compaction | `test_compaction.py` |
| L3 Gate-enforced | NFR and challenge gates block M+ tasks when unfired | `test_nfr_gate.py`, `test_challenge_gate.py` |
| L4 Done | `/done` closes the loop: code-review + learn + session_end | `test_session.py` |
| L5 Learning | Corrections persist and surface next session | `test_health.py`, `test_session.py` |
| L6 Self-healing | `self_heal` finds gaps; self-revision meta-loop revises judgment-sets | `test_health.py` |

L7 (compaction by intent) and L8 (skill handoff) are built and ship with v1.0 as bonus capability, not blockers.

---

## Floor B — Safety (three gates, not discipline)

| Guarantee | Enforcement |
|---|---|
| No personal-data leak in committed files | `personal_data_pulse.py` — pre-commit gate + health vital |
| All built capabilities wired into the live loop | `wiring_pulse.py` — 0 orphans at ship |
| No capability ships without a test | Pre-commit hook blocks commits missing test coverage |

---

## Floor C — North-star metric instrumented

`developer_autonomy_rate` — the fraction of sessions where the developer pre-empts a gate unprompted — is the headline v1 metric.

- Computed by `_compute_autonomy_rate` in `health.py`
- Surfaced at `session_start` and in `self_heal` output
- Target: rising trend across a developer's first ~20 sessions

**v1.0 ships this metric instrumented and visible. Proof of the thesis is deferred to post-release real-user data.** README and marketing must not overclaim: youk is measured-and-capable at v1, not proven.

---

## What v1.0 is not

- Not a proof that youk compounds developer judgment. That is the thesis being tested, not the bar for release.
- Not complete at L7/L8. Those levels are built and functional but not the ship gate.
- Not safe for multi-user deployment. v1.0 is a single-developer local system. No multi-tenancy, no shared state management.

---

## Reversal conditions

Revisit this definition if:
- A real user + "prove before ship" mandate appears → switch to proven-over-20-sessions bar
- `developer_autonomy_rate` proves undetectable reliably → metric C changes to a proxy
- A personal-data leak class the pulse cannot catch causes an incident → Floor B tightens before any future release
