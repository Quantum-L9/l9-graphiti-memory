# ADR-049: Sensitive Profiles and Purpose-Bound Consent

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-049-sensitive-profiles-and-purpose-bound-consent.md
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

Identity, preferences, behavior policy, session context, and domain memory have different authority, retention, and privacy semantics. Treating them as generic facts permits accidental permanence and cross-purpose reuse.

## Decision

Define typed profile contracts and require current, purpose-bound ConsentGrant evidence for identity and preference writes or promotions. Session context and domain memory remain separate models. Consent is persisted with the record and removed during verified deletion.

## Alternatives Considered

- Use one generic profile dictionary
- Treat authenticated submission as implied consent
- Persist all session context indefinitely

## Rejected Alternatives

- Generic dictionaries erase authority and retention distinctions
- Authentication proves caller identity, not subject consent
- Permanent session state violates least-retention principles

## Invariants

- Identity and preference memory require explicit evidence plus valid consent
- Consent is bound to subject, namespace, memory class, purpose, and time
- Revoked or expired consent fails closed
- Profile ingestion uses canonical writes

## Consequences

Positive: Sensitive memory becomes reviewable and purpose-limited

Negative: Callers must supply additional evidence and consent metadata

## Security Impact

This decision creates an enforceable consent boundary and supports verified deletion. It does not claim legal compliance beyond the implemented controls.

## Migration Impact

Legacy preference and identity records without consent import as quarantined or non-sensitive historical evidence, never silently as active profiles.

## Validation Requirements

- Missing, expired, revoked, wrong-subject, and wrong-class consent tests
- CLI and MCP consent contract tests
- Deletion removes embedded consent

## Rollback Conditions

Disable sensitive profile ingestion, preserve non-sensitive records, and export consent receipts for diagnosis.

## Supersedes / Superseded By

Extends ADR-024 and ADR-027.

No later ADR supersedes this decision as of 2026-07-22.
