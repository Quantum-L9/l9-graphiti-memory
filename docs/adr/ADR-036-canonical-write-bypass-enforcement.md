# ADR-036: Canonical Write Bypass Enforcement

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-036-canonical-write-bypass-enforcement.md
layer: adr
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-09-04
/L9_META -->


**Date:** 2026-07-21
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2+

## Status

Accepted

## Context

Direct SQL, provider calls, and subprocess writes repeatedly bypassed validation and governance in older systems.

## Decision

A release-blocking assurance scanner detects direct commit, SQL mutation, and provider write patterns outside approved storage and service modules. Exceptions require an explicit reviewed manifest entry with rationale and expiry.

In addition to the static scanner, every canonical-mutation method on a `RecordStore` (`commit_write`, `commit_deletion`, `commit_archive`, `save_phase_lock`) requires a `ServiceWriteCapability` issued by the `MemoryService` control plane. Store adapters reject any canonical mutation that does not present the single process-wide capability, so the storage side effect is technically dependent on a service-issued capability rather than merely governed by repository-source review. The scanner additionally forbids referencing or forwarding that capability outside the control plane.

Trust boundary (stated explicitly to avoid overclaiming): within a single trusted operating-system process, arbitrary Python can reach any in-memory object through introspection. The capability, the scanner, and the layering rules are therefore a defense-in-depth control that raises the bar against accidental and casual bypass and makes the canonical-write dependency inspectable — not an operating-system privilege boundary. A deployment that must resist hostile in-process code has to place canonical persistence behind a real process or database privilege boundary; this repository's guarantee is that first-party production source cannot bypass the service, enforced at build time by the scanner and at run time by the capability.

## Alternatives Considered

- Rely on reviewer memory
- Allow inline bypass comments anywhere
- Ban all SQL including migrations

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Public adapters never call RecordStore.commit_write
- Canonical store mutations require a MemoryService-issued write capability at run time
- The service write capability is never referenced or forwarded outside the control plane
- Migrations are isolated from runtime code
- Exceptions are visible and temporary

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Run check_memory_write_bypass.py
- Negative fixture test
- Direct-store canonical mutation without the capability is rejected at run time
- Review approved_bypasses.yaml

## Rollback Conditions

Disable a false-positive rule with a narrow manifest entry; do not delete the enforcement gate.

## Supersedes / Superseded By

Harvests GMP-129 bypass detection and strengthens it.

No later ADR supersedes this decision as of 2026-07-21.

## Amendments

**2026-09-04 — the capability covers every canonical mutation.**

The forensic codebase audit (finding F-05) found that `RecordStore.transition_state`
mutated a record's lifecycle state without presenting the capability, and that
the bypass scanner allowed the maintenance package to call it. Both gaps are
closed: `transition_state` and the new `commit_lifecycle` take the
`ServiceWriteCapability` like every other mutation, the scanner guards both
names, and the only callers it permits are `MemoryService` and the three store
adapters. The list of guarded methods in the Decision above therefore reads
`commit_write`, `commit_deletion`, `commit_archive`, `commit_lifecycle`,
`transition_state`, `save_phase_lock`.
