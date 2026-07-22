# ADR-028: Agent Checkpointing Boundary

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-028-agent-checkpointing-boundary.md
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

The legacy monolith treated agent checkpoints as a mandatory memory DAG node, coupling memory writes to runtime state restoration.

## Decision

Agent checkpointing is outside this repository. Agents may store checkpoint references or summaries as memory records, but checkpoint serialization, restore, scheduling, and runtime state are owned by the agent runtime.

## Alternatives Considered

- Port the full checkpoint manager
- Make every critical memory write trigger a checkpoint
- Store arbitrary pickled agent state

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Memory writes do not depend on agent runtime availability
- No pickle serialization
- Checkpoint references require provenance

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Dependency boundary scan
- No checkpoint service exports
- Reference-record tests

## Rollback Conditions

Consumers may keep their existing checkpoint service while migrating memory references independently.

## Supersedes / Superseded By

Rejects checkpoint ownership harvested from L9 Repo memory.

No later ADR supersedes this decision as of 2026-07-21.
