# ADR-024: Memory Privacy, Consent, and Deletion

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-024-memory-privacy-consent-and-deletion.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-07-21
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2+

## Status

Accepted

## Context

Identity and preference memory can be sensitive. PII redaction alone does not satisfy consent, access, or deletion obligations.

## Decision

Identity and preference classes require explicit evidence by default. Tenant isolation applies to every access. Routine retention archives records; verified deletion is a separate administrative workflow that must produce a tombstone receipt and remove projections.

## Alternatives Considered

- Treat all memories as anonymous technical data
- Delete records automatically on TTL
- Rely only on provider deletion

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Private classes have stronger admission rules
- Deletion authority is separate from write authority
- Deletion does not leave searchable projections

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Identity/preference admission tests
- Cross-tenant isolation tests
- Projection deletion conformance

## Rollback Conditions

Suspend deletion workers and export tombstone intents for later processing; do not restore deleted personal data automatically.

## Supersedes / Superseded By

Adds explicit privacy law absent from the v0.2 contract.

No later ADR supersedes this decision as of 2026-07-21.
