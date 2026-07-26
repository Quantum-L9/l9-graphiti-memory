<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/repository-review/projection-control-reconciliation.md
layer: repository_review
owner: memory-control-plane
status: accepted
version: 2.3.0
updated: 2026-07-26
/L9_META -->

# Projection-Control Reconciliation Register

This register extends the merged repository review without replacing or
renumbering its existing `REV-001` through `REV-005` decisions.

## PCR-001 — ADR acceptance and sequencing

### Decision

ADR-063 governs the projection manifest, deterministic compiler, immutable
compiled identity, deterministic rendering, and the compiler-only boundary.
ADR-063 is accepted with Phase 1.

ADR-064 is reserved for future public control-plane mutation surfaces. It must
not be accepted until durable projection state, replay, verification, atomic
alias promotion, rollback, deletion attestation, authenticated control
surfaces, and executable tests exist.

### Result

- Phase 1: unblocked.
- ADR-064: deferred.
- Runtime activation: not authorized.

## PCR-002 — Scalar compatibility versus multi-target compilation

### Decision

Existing scalar projection configuration remains unchanged during Phase 1:

- `none`
- `http`
- `zep`

The compiler may describe multiple provider targets, but compiled targets are
inert data. Phase 1 does not alter `MemorySettings`, `build_projection()`,
runtime construction, startup behavior, or provider delivery.

A later runtime phase must make legacy scalar mode and compiled multi-target
mode mutually exclusive.

### Result

- Offline multi-target compilation: authorized.
- Runtime fan-out: deferred.
- Existing scalar behavior: preserved.

## PCR-003 — Cross-target deletion attestation

### Decision

Delivery criticality and erasure obligation are distinct.

Any target that has durably confirmed storing a record becomes mandatory for
that record's deletion, including targets that were optional for delivery.
The future authoritative deletion target set is therefore every durable
projection link for the record.

Canonical deletion may complete only after every remaining durable target link
has confirmed erasure and the complete deletion attestation is durably
persisted.

Phase 1 only validates declarative deletion requirements. It does not change
the current deletion runtime.

### Result

- Deletion semantics: resolved.
- Phase 1 compiler work: unblocked.
- Target-aware persistence and runtime erasure: deferred.

## PCR-004 — Compiler-only Phase 1

### Decision

Phase 1 is offline, deterministic, and side-effect free.

Authorized areas:

- projection manifest;
- Pydantic manifest contracts;
- strict manifest parsing;
- deterministic compilation;
- deterministic canonical rendering;
- JSON schema resource;
- ADR and reconciliation evidence;
- focused tests;
- existing validation-authority integration.

Prohibited areas:

- runtime composition;
- `MemoryService`;
- `OutboxWorker`;
- `RecordStore`;
- `ProjectionAdapter`;
- adapter factory behavior;
- SQLite schemas;
- network calls;
- provider mutation;
- SDK;
- CLI;
- MCP;
- replay;
- aliases;
- promotion;
- rollback;
- deletion orchestration.

### Result

- Phase 1 implementation: unblocked.
- Runtime changes in Phase 1: prohibited.

## PCR-005 — Validation authority

### Decision

`scripts/validate_release.sh` remains the sole repository release-validation
entry point.

Phase 1 extends it with projection-manifest validation. It does not create a
parallel release authority.

Historical validation files are evidence for their original commit only and
must be regenerated after source changes.

### Result

- Focused tests: required.
- Existing release gate: extended.
- Parallel validation authority: prohibited.

## Residual blockers

The following are intentionally not resolved by Phase 1:

1. acceptance and implementation of ADR-064;
2. target-aware projection-link persistence;
3. multi-target provider delivery;
4. durable replay and partition recovery;
5. D0-D3 verification;
6. transactional promotion and rollback;
7. cross-target deletion-attestation persistence;
8. authenticated public control-plane mutation surfaces;
9. isolated live Graphiti and Zep validation.
