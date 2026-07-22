# ADR-051: Explicit References and Lineage Replay

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-051-explicit-references-and-lineage-replay.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-07-22
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.1+

## Status

Accepted

## Context

Supersession alone cannot explain why a record exists, which sources support it, or whether dependencies are missing. The legacy system contained lineage ideas without a standalone, bounded replay contract.

## Decision

Records carry explicit references in addition to supersedes and conflicts. Lineage replay traverses governed records, detects cycles and missing dependencies, and returns an inspectable replay with issues rather than exposing private model reasoning.

## Alternatives Considered

- Infer lineage from timestamps
- Store private chain-of-thought
- Ignore missing parent records

## Rejected Alternatives

- Timestamp inference is ambiguous
- Private reasoning is not required for provenance
- Missing dependencies silently weaken trust

## Invariants

- References are explicit UUID relationships
- Replay is tenant and namespace authorized
- Cycles and orphans are reported
- Lineage explains evidence relationships without private chain-of-thought

## Consequences

Positive: Provenance and retention become dependency-aware

Negative: Reference graphs require validation and bounded traversal

## Security Impact

Authorized replay prevents cross-tenant graph discovery. Private reasoning text is neither required nor emitted.

## Migration Impact

Legacy parent identifiers are mapped to explicit references when resolvable; unresolved identifiers remain reported migration issues.

## Validation Requirements

- Reference, supersession, cycle, and orphan tests
- Authorization boundary tests
- Retention reference-count tests

## Rollback Conditions

Disable replay while preserving reference fields; references remain inert metadata until the issue is corrected.

## Supersedes / Superseded By

Implements ADR-031 and strengthens ADR-005 and ADR-010.

No later ADR supersedes this decision as of 2026-07-22.
