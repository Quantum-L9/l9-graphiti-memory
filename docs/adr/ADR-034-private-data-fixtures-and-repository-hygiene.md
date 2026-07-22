# ADR-034: Private Data, Fixtures, and Repository Hygiene

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-034-private-data-fixtures-and-repository-hygiene.md
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

A legacy pack included private chat history and operating-system metadata. Such data must not enter a reusable public package.

## Decision

Tests use synthetic fixtures only. Source archives, transcripts, credentials, local databases, state files, caches, and personal paths are excluded. Example identities and tokens are visibly nonfunctional placeholders.

## Alternatives Considered

- Commit sanitized-looking real data
- Rely on .gitignore alone
- Bundle local state for reproducibility

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- No private conversation content in fixtures
- Release inventory excludes caches and databases
- Secret scans run in CI

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Archive inventory scan
- Secret-pattern scan
- Fixture review

## Rollback Conditions

Remove the offending release artifact, rotate exposed credentials, and publish a clean replacement with incident notes.

## Supersedes / Superseded By

Responds to private artifacts found in L9 Repo memory.

No later ADR supersedes this decision as of 2026-07-21.
