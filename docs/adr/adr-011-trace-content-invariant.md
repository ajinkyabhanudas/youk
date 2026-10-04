# ADR-011: Traces carry derived scalars, never session content

**Date:** 2026-08-27 (session 93)
**Status:** Accepted

## Decision

Langfuse traces emitted by youk carry only derived scalars, enums, and hashed
identifiers. They never carry free text originating in a session.

Allowed: counts, rates, durations, enum outcomes, hashed identifiers, version strings.
Not allowed: task descriptions, file paths, project names, finding text, prompts,
usernames, hostnames, or anything reconstructible into them.

`_ALLOWED_METADATA_KEYS` in `servers/core/src/observability.py` is the enforcement
point. `tests/test_observability_privacy.py` is the drift sentinel.

## Context

Langfuse instrumentation shipped in #85 sending `project_dir` as raw trace metadata.
That is an absolute path containing the user's home directory name, so it identifies
both the person and their filesystem layout. The session slug, a project name, was
sent raw alongside it.

On a local single-user instance this is harmless, which is exactly why it survived
review. The cost only appears if `LANGFUSE_HOST` is ever pointed at a shared server.

Observability is currently maintainer tooling: it no-ops unless all three Langfuse
env vars are set, and a normal install never reaches it. But a plausible future use
is a team lead running a shared instance to see whether skill invocation rates are
improving across a team. That is a config change, one env var, which is precisely
what makes it dangerous. Nothing about pointing at a shared host forces a review of
what the traces contain.

## Why the constraint is adopted now rather than when the feature is built

Telemetry privacy cannot be retrofitted. Once identifying data reaches a shared
server it is on that server, in backups, and in anything downstream of it. Removing
the field afterwards does not undo the disclosure. The only point at which this is
free is before any shared instance exists.

The same reasoning applies to `install_id`. An anonymous per-install identifier is
useless today, since a local instance has exactly one install. But without a stable
grouping key, a shared instance cannot distinguish ten developers from one developer
with ten times the sessions, and that distinction cannot be reconstructed from
historical data after the fact. Generating it now costs one file in `state/` and
keeps team aggregation a config change instead of a redesign.

## Rejected alternatives

**Send raw values, scrub later if youk ever goes multi-user.** This is the retrofit
that does not work, for the reasons above. It also assumes someone remembers to scrub
before the first shared instance, when the failure mode is precisely that no review is
triggered by changing an env var.

**Send nothing but scores, no metadata at all.** Loses the ability to group by project
or compare across youk versions, which is most of the diagnostic value. Hashing keeps
the grouping power and drops only the identity.

**Make it a runtime config flag, "privacy mode on/off".** A flag defaulting to safe is
equivalent to this ADR but with an off switch, and a flag defaulting to unsafe is worse
than the current state. The off switch has no legitimate use: no youk diagnostic needs
the raw path rather than a stable hash of it.

**Collect population-level telemetry across developers.** Explicitly rejected. Its
value is speculative and it cuts directly against youk's existing secrets and privacy
contracts. This ADR deliberately leaves it *possible* without making it easy: a shared
instance works, but it can only ever receive non-identifying data.

## Consequences

Adding a metadata key is now a deliberate act. It requires editing
`_ALLOWED_METADATA_KEYS` and the pinned assertion in the sentinel test, so the trace
surface cannot widen as a silent side effect of an unrelated change.

`build_trace_metadata()` is the single construction point, so the allowlist has one
thing to guard rather than every call site.

The invariant is stated in the `observability.py` module docstring as well as here,
because the module is where someone about to add a field is actually looking.
