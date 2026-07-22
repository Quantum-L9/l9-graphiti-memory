# ADR-016: Secret and Credential Boundaries

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-016-secret-and-credential-boundaries.md
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

Prior config writers persisted Infisical and Zep secrets into desktop JSON files. Legacy hooks loaded local env files and macOS Keychain values.

## Decision

Desktop MCP configuration contains only command and non-secret arguments. Secrets enter the server process through the operator environment or Infisical at runtime. Logs, receipts, and config diagnostics redact credential values.

## Alternatives Considered

- Write secrets into Cursor and Claude config for convenience
- Commit encrypted secrets to the repository
- Require macOS Keychain

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- No generated config contains credential material
- Infisical is optional but never silently partially configured
- Bearer tokens are server-side authorization keys

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Secret-pattern scanner
- Config writer snapshot tests
- Infisical missing/required tests

## Rollback Conditions

Remove generated MCP entries and restore operator-managed environment injection; no credential migration is needed because none are written.

## Supersedes / Superseded By

Supersedes plaintext desktop config generation.

No later ADR supersedes this decision as of 2026-07-21.
