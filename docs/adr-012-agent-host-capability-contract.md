# ADR-012: Agent-host capabilities are explicit and vendor-neutral

**Date:** 2026-09-23
**Status:** Accepted

## Decision

Core code evaluates a versioned `HostCapabilities` declaration. It does not branch
on an LLM or vendor name. Host-specific adapters translate only at their boundary.

Each capability is classified as either safety-critical or advisory. A missing or
unknown safety capability returns `blocked`; a missing advisory capability returns
`degraded`; declared capabilities return `available`. These outcomes are pure,
deterministic, and require no network, LLM, credential, or conversation data.
An unsupported schema version or an unclassified declared capability also blocks.
Runtime boundaries call `require_capability` before using safety-required host
features, so this policy is enforced rather than merely described by an adapter.

The first adapters are Claude Code and Codex. Codex's `SessionStart` envelope is now
rendered by its adapter rather than constructed in core server code.

## Context

youk historically embedded Claude Code assumptions in path names, plugin hooks,
installation, and runtime documentation. The Codex integration added a correct hook
adapter, but another per-vendor branch would repeat the same coupling. Future features
need one core policy path even when agent hosts expose different lifecycle events.

## Rejected alternatives

**Copy a new adapter for every host.** This duplicates policy and lets safety behavior
drift between integrations.

**Use one lowest-common-denominator hook API.** Hosts do not provide equivalent
lifecycle events. Pretending they do would silently remove safeguards.

**Allow unknown capabilities by default.** A future host could then appear supported
while omitting a safety control. Unknown values must fail closed.

## Consequences

The capability vocabulary is now an additive, versioned public boundary. Adding a
capability requires classifying it as safety or advisory and adding contract tests.

This first slice does not rewrite installers, plugins, or every historical
`CLAUDE_ROOT` reference. Those migrations follow after the capability policy is proven
against the current two adapters.

Revisit this decision if a third host needs a capability that cannot be represented by
the current vocabulary without vendor-specific policy in core.
