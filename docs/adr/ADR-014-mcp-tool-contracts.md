# ADR-014: MCP Tool Contracts

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-014-mcp-tool-contracts.md
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

The old local server exposed search/write while its provider client assumed search_facts/add_episode. Local tool drift broke self-compatibility, and the upstream Graphiti MCP surface later evolved to add_memory/search_memory_facts.

## Decision

mcp_tools.py is the single machine-readable local inventory. Canonical names use memory.*. Legacy aliases are generated from canonical definitions and route to the same MCPToolApplication handlers. The agent-facing contract is memory.search, memory.hydrate, memory.write_governed, memory.close, and memory.health. Compatibility aliases graphiti.query and graphiti.write_governed terminate at those handlers and must not call Graphiti directly. Provider-native Graphiti tool discovery remains isolated in the projection transport and cannot redefine local memory law.

## Alternatives Considered

- Maintain separate server and client schemas
- Expose provider-native Graphiti tools directly
- Remove all legacy names immediately

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Every listed tool has exactly one handler
- Aliases cannot change argument semantics
- Tool inventory changes require contract and regression tests

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- tools/list integration test
- Alias equivalence tests
- Unknown-tool error test

## Rollback Conditions

Keep the prior alias set during the deprecation window while reverting canonical additions behind version negotiation.

## Supersedes / Superseded By

Replaces duplicated MCP definitions in server.py and transport.py.

No later ADR supersedes this decision as of 2026-07-21.
