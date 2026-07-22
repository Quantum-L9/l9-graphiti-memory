<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/RECURSIVE_HARVEST_AUDIT.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Recursive Harvest Audit

## Scope

This audit compared the delivered v2.0 rewrite against every architectural finding and harvest promise recorded during the pack reviews in this workstream:

- current remote and reconciled pack audit
- predecessor and handoff pack deltas
- L9-Ops-MCP integration pack
- mixed memory architecture pack
- detached legacy memory subsystem
- `cryptoxdog/L9_Original_Repo`
- the first v2 rewrite bundle

The review used repository, architecture, artifact-quality, validation, recursive-improvement, and L9 dependency-package adapters.

## Baseline result

The v2.0 pack had a strong canonical kernel, but several concepts named in earlier audits were present only as interfaces, ADRs, or deferred roadmap items. The highest-risk gaps were:

1. Atomic extraction and evidence binding were not operationally complete.
2. Identity, preference, behavior, session, and domain profile boundaries were incomplete.
3. Purpose-bound consent and verified deletion were not fully wired.
4. Lineage replay, procedural synthesis, and ingress recovery remained partial.
5. Hybrid retrieval names did not prove independent strategy execution.
6. Provider deletion could not complete because stable episode locators were not persisted.
7. The Graphiti projection assumed older provider tool names.
8. No machine-readable ledger proved that every promised harvest was closed.
9. Secret and local latency checks were documented but not executable gates.
10. Roadmap and remediation documents still described implemented concepts as deferred.

## Integrated closure

### Contract and ingestion closure

- Added atomic assertions with exact source ranges and source digests.
- Added evidence-bound deterministic and provider extraction contracts.
- Added offline document, repository, and session distillation.
- Added distinct identity, preference, behavior-policy, session-context, and domain-memory profiles.
- Added purpose-bound consent validation for sensitive profile memory.

### Lifecycle and governance closure

- Added lineage replay with cycle and orphan detection.
- Added task-bound phase-lock verification.
- Added governed procedural synthesis candidates.
- Added canonical ingress recovery replay.
- Added verified deletion with redacted tombstones and projection confirmation.

### Projection and retrieval closure

- Added independent graph and semantic strategy execution and receipts.
- Added current Graphiti MCP dialect support for `add_memory`, `search_memory_facts`, `search_nodes`, and `delete_episode`.
- Retained explicit compatibility for `add_episode` and `search_facts`.
- Added canonical `ProjectionLink` persistence in both in-memory and SQLite stores.
- Added Graphiti and Zep episode deletion adapters using stable locators.
- Prevented deletion receipts from completing when the provider locator or erasure proof is missing.

### Assurance closure

- Added a high-confidence committed-secret scanner.
- Added a deterministic in-memory SLO benchmark with explicit scope.
- Added a 44-decision machine-readable harvest ledger.
- Added a validator that requires implementation, tests, and ADR evidence for every implemented decision.
- Added recursive improvement, delta, convergence, and validation evidence.

## Boundary decisions preserved

The audit did not re-import the legacy monolith. The package still rejects ownership of:

- constellation transport contract
- agent execution and checkpoint state
- world-model updates
- private reasoning traces
- a duplicate L9-Ops-MCP memory control plane
- mandatory PostgreSQL, Redis, Neo4j, LangGraph, or LLM infrastructure
- raw private chat-history fixtures

## Coverage result

`docs/harvest_coverage.yaml` contains 44 closed decisions:

- 35 implemented
- 5 rejected by repository boundary
- 4 blocked on external environments

There are no `partial`, `deferred`, or unnamed `unknown` statuses in the coverage ledger.

## Validation result

The converged tree passes:

- 103 tests
- 62 ADR validations
- 44 harvest-decision validations
- 21 preflight gates
- 86 production-module quality checks
- package-wiring audit with zero unexplained orphans
- canonical-write bypass audit
- configuration-drift audit
- committed-secret scan
- local write, search, and hydration SLO benchmark
- wheel build, install, package-resource, entrypoint, CLI, and MCP smoke

Live provider and production environment proof remains external and is recorded as blocked, not passed.

## Convergence

Two consecutive adversarial scans produced no new in-scope implementation category. Remaining work requires credentials, hosted repository controls, or production-like data. The recursive audit therefore converged on the v2.2 pack.
