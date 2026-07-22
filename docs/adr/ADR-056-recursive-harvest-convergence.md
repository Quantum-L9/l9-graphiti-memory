# ADR-056: Recursive Harvest Convergence

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-056-recursive-harvest-convergence.md
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

The v2 rewrite was assembled from several iterative packs and a legacy monolith. Earlier documentation listed promised concepts as partial or deferred, creating a risk that the package looked complete while implementation seams remained unwired.

## Decision

Maintain an explicit harvest coverage matrix that maps every accepted concept to implementation, tests, ADRs, and disposition. Recursive improvement stops only after two passes produce no material unowned gaps, all local hard gates pass, and external Unknowns are isolated as blocked validation rather than hidden omissions.

## Alternatives Considered

- Rely on narrative audit summaries
- Import every legacy module
- Continue adding features without convergence criteria

## Rejected Alternatives

- Narrative summaries drift
- Wholesale import recreates the monolith
- Unbounded improvement prevents release decisions

## Invariants

- Every harvested concept has an adopt, adapt, reject, or external disposition
- Rejected scope has an ADR rationale
- Implemented concepts have executable wiring and tests
- Blocked external checks remain explicit

## Consequences

Positive: The rewrite becomes traceable and bounded

Negative: Coverage documentation must be maintained with future harvests

## Security Impact

Recursive review prioritizes authorization, privacy, evidence, and failure semantics before optional sophistication.

## Migration Impact

This ADR governs the v2.1 closure pack and future source-pack reconciliation.

## Validation Requirements

- Harvest coverage validator
- Package wiring audit
- Recursive audit and convergence reports
- Full release validation

## Rollback Conditions

Return to the last validated release and preserve the failed improvement log for diagnosis.

## Supersedes / Superseded By

Records the convergence decision following ADR-033.

No later ADR supersedes this decision as of 2026-07-22.
