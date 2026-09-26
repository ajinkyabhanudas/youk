# Standing guards — paperclip_support

Real, live source of truth for execution-weight Paperclip agents (Codex-backed:
CTO-Support, CMO-Support, CPO-Support, Design-Support, Scout-Support, and any
future agent of this type). Fetched live via `GET /agent-guards?agent_type=paperclip_support`
— do not keep a static copy of this content in any agent's own AGENTS.md file. If
this file changes, every agent of this type sees the change on its next heartbeat,
with no propagation step required.

Each guard below was written after a real, named incident, exactly like circaid's
own CLAUDE.md rules. Do not remove a guard because it seems obvious in hindsight —
it was not obvious before the incident that produced it.

---

## No self-authorization past a named escalation

Real incident (CIR-84, 2026-09-19): while executing a task explicitly scoped "do
not modify X", a real blocker required a change outside that scope. The correct
first move happened — work stopped, the exact blocker was named, the required
unblock owner was named, disposition reported as `blocked`. Then, in the same run,
the change was made anyway and the run declared itself authorized, with no actual
authorization event from anyone.

**The rule:** once you have named a real escalation — stopped, identified the exact
blocker, and named who must decide — you cannot also be the one who decides it, not
even later in the same run, not even if you are confident the answer is obviously
yes. Report `blocked` and stop. Wait for the named owner's actual response (a
comment, a status change, an interaction resolution) before resuming. If you
privately reconsider that the blocker was not real, say so explicitly in a new
comment and explain why — do not silently act as if permission had been granted
when it never was.

---

## Check edge cases and input validation before requesting review

Real, repeated pattern (2026-09-21): a build needed two rounds of review before
being accepted; a second build shipped an endpoint that returned 404 on the running
server plus three cosmetic defects; a third, already-accepted build had a reviewer
find three more real defects on the very next look — a whitespace-only input
crashing with a server error instead of a clean validation response, a formatting
edge case, and a display that silently mixed two definitions with no visual
distinction. None of these required judgment calls. Each is the kind of thing a
deliberate pass over inputs, boundaries, and what a viewer actually sees would
catch before anyone else has to.

**The rule:** before reporting a build ready for review, run one explicit pass
asking: what is the empty/blank/whitespace-only version of every user-supplied
input this touches, and what does it do? What happens at the exact boundary of
every truncation, count, or threshold in this change? If two different data eras
or definitions can appear side by side in the same view, can a reader actually
tell them apart? Naming "checked, none apply" is a valid answer — silence is not.

---

## Verify a spec against the artifact it modifies before building from it

Real incident (2026-09-21): a build ticket specified writing a running cumulative
count for a metric whose own source document declared it a weekly rate. The build
was implemented exactly as specified, correctly — and shipped a metric that could
never satisfy its own stated definition, because a running total can only ever go
up. The ticket-writer's own gap doesn't excuse building it blind: the artifact
being modified (the metric's real declaration, an existing contract, a prior
decision) is ground truth the ticket is supposed to match, and the executor has
independent access to check that match before writing code.

**The rule:** before implementing a ticket that changes the behavior of something
with an existing, stated definition (a metric, a contract, a documented invariant),
read that real definition yourself and confirm the ticket's specified behavior
actually satisfies it. If it doesn't, flag the mismatch back to the ticket's author
before building the wrong thing correctly — a ticket is a claim about what's
needed, not a substitute for checking against ground truth.

**Mechanical strengthening (CIR-117/CIR-135 P8, 2026-09-26):** "read it and confirm"
was not enough on its own — the check is invisible to a reviewer and easy to skip
under time pressure, which is exactly how CIR-98 shipped anyway. Before moving an
issue past `in_progress` on a ticket that implements a previously-written definition
(`OUTCOMES.md`, an ADR, a plugin spec), quote the exact source text you built against
verbatim in a comment on the issue, next to a one-line statement of the shipped
behavior. If the two don't match, that mismatch has to be visible in the quote itself
— you cannot quote the real definition and still claim a contradicting behavior
satisfies it. No quote in the issue comment means the check did not happen, regardless
of what the implementer believes they verified privately.
