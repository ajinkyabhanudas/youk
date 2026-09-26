# Standing guards — paperclip_department_head

Real, live source of truth for judgment-weight Paperclip agents (Claude-backed:
CTO, CDO, CMO, CPO, Scout, Conductor, and any future agent of this type). Fetched
live via `GET /agent-guards?agent_type=paperclip_department_head` — do not keep a
static copy of this content in any agent's own AGENTS.md file. If this file
changes, every agent of this type sees the change on its next heartbeat, with no
propagation step required.

Each guard below was written after a real, named incident. Do not remove a guard
because it seems obvious in hindsight — it was not obvious before the incident that
produced it.

---

## No self-authorization past a named escalation

Same rule as `paperclip_support`, applies equally to review/decision authority: a
department head reviewing another agent's work who finds a real reason to escalate
(a scope question only the founder or another named owner can settle) cannot also
be the one who resolves that escalation in the same run. Name the blocker, name the
owner, report `blocked`, and wait for their actual response.

---

## Independent review means re-deriving the claim, not trusting the report

Real, demonstrated pattern that works (2026-09-21): reviewing an implementation
that claimed "0.75, 2 of 4 corrections uncategorized" by independently parsing the
real source document and independently querying the real database — twice,
separately — found the claim was correct but the underlying count was wrong (3 of
4, not 2 of 4). The number that reached the correct final value was only trustworthy
because it was checked against two independent sources, not because the report
sounded plausible.

**The rule:** when reviewing a build, a claim, or a research conclusion before
accepting it as done — re-derive at least one concrete number or fact yourself
from a source independent of the report itself (the real file, the real database,
the real test output), rather than accepting a summary. A review that only reads
the summary and agrees is not independent review; it's a second read of the same
claim.

---

## Audit what was actually asked, not just whether it ran

Real, named failure: a dispatched agent was asked "what does it take to reach
design excellence" and answered the narrower "does this specific feature need a
new department" — technically responsive, actually a different question — and the
substitution went unnoticed until caught directly, after the fact. When a
dispatched agent's job is analysis or a recommendation, not a build, re-read the
literal brief against the literal answer before applying its conclusion. Passing
review because the agent produced *an* answer is not the same as the agent
answering *the* question asked.

---

## A merged deliverable is not the same as a moved outcome

Real, repeated pattern (three separate instances in one session): a real, merged,
tested piece of work was presented as progress toward the org's actual goal, when
it had zero real callers or zero real usage anywhere in the running system. Before
presenting or accepting any shipped work as progress, state explicitly which of
these it is: a mechanism proof (can the org build/ship real, tested code at all —
legitimate to establish, never to keep re-establishing as if repetition were new
evidence), or a product outcome (something in the founder's actual experience of
the product changed, or a real metric moved). If a deliverable has zero real
callers or zero real usage, it is not the second kind, no matter how clean the
tests are.

---

## UI-shipping work requires a CDO design-gate child issue before `done` — CIR-117/CIR-135

Real, repeated failure (CIR-20, CIR-21, CIR-59, CIR-82): four separate issues shipped
user-facing dashboard UI with no CDO assignee and no CDO comment anywhere on the issue,
and the founder rejected the result outright each time. The capability to land design
work clean on the first pass exists and has one real, verified instance (CIR-112/113,
CDO's own design-gate checkpoint before the circaid ops plugin plan proceeded) — the
organizational habit of invoking that capability before UI ships was the missing piece,
not the capability itself.

**The rule, for whichever department head is triaging, planning, or about to move an
issue to `done`:** if an issue's scope touches `apps/web` or any Paperclip plugin UI
surface, it cannot reach `done` without a CDO design-gate child issue somewhere in its
tree — same shape as CIR-113: a plan-stage checkpoint producing an explicit
APPROVE / CONDITIONAL / REVISE verdict with cited evidence (`references/craft-gate.md`'s
scored format, not "looks fine"). If you are the one about to mark such an issue `done`
and no such child issue and verdict exist, stop and create the design-gate child issue
first (or name the missing verdict as a real blocker) — do not treat "nobody assigned
CDO" as a reason it was optional. The gate is blocking, not advisory.

**Triage default:** an unassigned issue whose title or DONE-MEANS names a design/craft
outcome (not just "has a UI" — actually about how something looks or reads) routes to
CDO by default at triage, the same way a security-shaped issue defaults to a security
owner. Silence on assignee is not evidence the issue doesn't need a design owner; CIR-67
sat in backlog with `assigneeAgentId: null` for exactly this reason.

**Evidence, not just a verdict (CIR-135 P10):** a design-gate verdict does not count as
complete until the screenshots or renders it cites as evidence are attached to the issue
as a real artifact work product — not left as untracked files in a repo's `docs/`
directory. `docs/screenshots/design-review-*.png` and `*-p0-fixed.png` sitting untracked
and owned by no issue is the exact failure this closes: real before/after evidence that
existed on disk but was invisible to anyone reviewing the issue itself. Before citing a
screenshot as evidence in a verdict, upload it as the issue's artifact work product first,
then reference it in the verdict comment — the verdict and its evidence live in the same
place a future reader will look.
