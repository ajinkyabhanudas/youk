# Information governance

youk treats links, imports, and document-map references as discovery evidence, not
authority. Authority is explicit and local to the project.

## Registry

Create `docs/information-governance.yaml` when a project needs lifecycle checks:

```yaml
version: 1
files:
  - path: docs/source.md
    role: source_of_truth
  - path: docs/derived.md
    role: derived
    authority: docs/source.md
    lifecycle: maintained
```

Roles are `source_of_truth`, `derived`, and `reference_only`. A derived file has one
declared source of truth. Registry paths must be relative to the project, exist, and
form an acyclic authority graph. Invalid metadata blocks registry publication rather
than silently producing an empty authority graph.

## Freshness and retrieval

Staleness uses authority content hashes. A derived file is stale when its recorded
authority hash differs from the current authority hash. Timestamps, Markdown links,
imports, and `doc-map.yaml` edges never make a file stale by themselves.

BM25 retrieval is local, deterministic, and provider-neutral. Queries, result counts,
graph expansion, and estimated context tokens have fixed bounds. Responses distinguish
`absent`, `invalid`, `failed`, and `ready`; they never create an empty index during a
read. The operator-facing `get_information_governance_health(project_slug)` exposes
counts only: declared, derived, stale, and unknown. It does not retain raw documents,
queries, prompts, or responses.

An absent registry is reported as `unmanaged`/`unknown`, not healthy. This is deliberate:
the system can say what was declared, but cannot claim governance coverage that was not
declared.
