# ADR-063: Projection Manifest, Compiler, and Control-Plane Boundaries
<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-063-projection-manifest-compiler-and-control-plane-boundaries.md
layer: adr
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-07-26
/L9_META -->

**Date:** 2026-07-26
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.3+

## Status

Accepted.

Phase 1 accepts only the manifest, deterministic compiler, rendering contract,
and control-plane boundaries described here. Runtime fan-out, replay,
verification, promotion, rollback, deletion attestation, and public mutation
surfaces remain deferred.

## Context

The repository currently constructs one optional projection backend selected
from `none`, `http`, or `zep`. That scalar configuration is sufficient for the
existing runtime but cannot describe versioned projection definitions,
simultaneous provider targets, deterministic render identity, shadow builds,
target-aware replay, or target-complete deletion evidence.

Graphiti and Zep remain derived, disposable projections. `MemoryService` and
`RecordStore` remain authoritative for canonical memory, lifecycle state,
receipts, outbox state, and durable projection links.

A new compiler must not silently activate a second runtime path or weaken the
existing scalar configuration contract.

## Decision

Introduce a strict `Projection` manifest and an offline compiler that produces
an immutable `CompiledProjection`.

The compiler validates:

- canonical record-store authority;
- non-authoritative vector and provider state;
- explicit tenant and namespace scope;
- fail-closed scope behavior;
- deterministic render fields and normalization;
- provider target identity;
- pinned embedding model revision;
- dimensional and similarity-space identity;
- replay side-effect prohibition;
- deletion propagation and attestation requirements;
- unique provider-target identities;
- deterministic structural and render digests.

A target identity is:

```text
projection-name : projection-version : provider-type : target
```

Example:

```text
facts:v8:graphiti_mcp:primary
```

Compiled targets are inert data during Phase 1.

Existing scalar projection configuration remains supported without behavioral
change. Phase 1 does not modify runtime composition, provider construction,
outbox delivery, deletion execution, persistence, SDK, CLI, or MCP.

## Alternatives Considered

**Replace scalar configuration immediately.**
Rejected because it would combine contract introduction with runtime migration,
fan-out, persistence, provider behavior, and operational cutover.

**Store manifests without compilation.**
Rejected because raw configuration does not provide a stable compiled identity,
canonical digest, or deterministic compatibility boundary.

**Treat external provider state as authoritative.**
Rejected because it violates the repository's canonical-memory architecture and
verified-deletion model.

**Add public projection controls in Phase 1.**
Rejected because mutation authorization, durable state, replay recovery,
verification, atomic promotion, rollback, and deletion evidence do not yet
exist.

## Rejected Alternatives

- Runtime fan-out during Phase 1.
- SQLite schema changes during Phase 1.
- Provider network calls during compilation.
- Environment-dependent compiler output.
- Current-time or random-value compiler output.
- Alias mutation during compilation.
- Automatic promotion after compilation.
- A second release-validation entry point.

## Invariants

1. `MemoryService` remains the canonical memory control plane.
2. `RecordStore` remains the canonical durable source of truth.
3. External projections remain disposable and rebuildable.
4. Compilation performs no network, database, provider, alias, or canonical
   memory mutation.
5. Identical manifest inputs produce identical compiled JSON and digests.
6. Rendered projection text depends only on declared canonical fields and the
   immutable render contract.
7. Tenant and namespace scope are mandatory and fail closed.
8. Provider and vector state are never authoritative.
9. Existing scalar `none`, `http`, and `zep` runtime behavior is unchanged.
10. Runtime fan-out requires a later governed phase.
11. Any durable provider link created in a later phase becomes part of that
    record's mandatory deletion set.
12. `scripts/validate_release.sh` remains the release-validation authority.

## Consequences

Phase 1 gains a deterministic, reviewable projection definition without
changing production behavior.

Later phases may consume `CompiledProjection`, but they must separately
implement and validate:

- durable registration;
- target-aware links;
- fan-out;
- replay;
- verification;
- promotion and rollback;
- deletion attestation;
- authenticated public controls.

Projection-version changes are required when immutable derivation inputs
change, including render fields, normalization, embedding model revision,
dimensions, distance metric, similarity space, scope, replay semantics, or
deletion semantics.

## Security Impact

The manifest requires tenant and namespace scope and requires fail-closed scope
behavior.

Compilation rejects authoritative vector state, unpinned embedding models,
missing scope, duplicate target identities, unsafe replay side effects, and
deletion definitions without attestation.

The compiler does not accept credentials and does not perform network access.

## Migration Impact

Phase 1 is additive.

No existing configuration key changes.

No SQLite migration is introduced.

No provider data migration is introduced.

No active alias or runtime projection changes.

The JSON schema resource must be included in built distributions.

A future multi-target runtime mode must be explicitly configured and mutually
exclusive with legacy scalar mode.

## Validation Requirements

The following are mandatory:

- strict parsing of the example manifest;
- rejection of unknown fields;
- rejection of missing tenant or namespace scope;
- rejection of authoritative vector state;
- rejection of duplicate target identities;
- rejection of unpinned embedding models;
- deterministic compilation;
- deterministic canonical rendering;
- render-field presence validation;
- packaged JSON-schema validation;
- ADR index and contiguous-number validation;
- execution through the existing release-validation script.

Unknown or unexecuted validation is not a pass.

## Rollback Conditions

Before runtime wiring, rollback consists of removing:

- the projection compiler package;
- manifest resources;
- the example manifest;
- Phase 1 tests;
- the ADR and reconciliation additions;
- the projection-manifest release-validation step.

No database downgrade is required because Phase 1 introduces no schema change.

## Supersedes / Superseded By

This ADR does not supersede an existing ADR.

It extends ADR-013, ADR-018, ADR-020, ADR-021, ADR-022, ADR-025, ADR-037,
ADR-043, ADR-046, ADR-053, and ADR-057 without changing their canonical
authority conclusions.

ADR-064 is reserved for future public projection-control mutation surfaces and
does not become accepted through this decision.
