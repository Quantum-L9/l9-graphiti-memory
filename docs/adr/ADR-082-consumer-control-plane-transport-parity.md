# ADR-082: Consumer Control-Plane Transport Parity

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-082-consumer-control-plane-transport-parity.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-09-05
/L9_META -->


**Date:** 2026-09-05
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.2+ and its consumer `Quantum-L9/Cursor-Governance`

## Status

Accepted

## Context

`MemoryService` is the only production-authorized path into canonical memory
state, and this package already exposes it over three transports: the
`l9-memory` CLI, the MCP server, and `MemorySDK`. Its principal consumer,
Cursor-Governance, does not use any of them for its session lifecycle. Its
hydration searches Graphiti with `search_memory_facts`, its session close
writes provider episodes with `add_memory`, and its resume protocol is a
fuzzy `PICKUP|objective=…|next=…` string parsed back out of provider facts.
Every one of those bytes bypasses admission, authorization, idempotency, the
canonical store, and the receipts. The audit named the state
`CANONICAL_MEMORY_PATH_BYPASSED`.

Part of the reason is that the transports were not at parity. `memory.close`
existed on MCP and `MemoryService.close` existed on the service, but the CLI
that a shell hook can call synchronously had no `close`; the SDK had no
`close`, `conflicts`, `verify_phase_lock`, or `health`; a close replayed
after a crash minted a second close record; and a consumer that wanted to
prove it was bound to a compatible runtime had nothing to bind to except the
presence of individual tools. The governed-candidate ingress could carry a
generated-data fact but not a structured session artifact, and it derived the
namespace from a visibility template that never matched the repository
namespace hydration reads.

## Decision

Every lifecycle operation a consumer needs converges on `MemoryService`
through each transport, and the package tells the consumer what it is bound
to.

**CLI close parity.** `l9-memory close --summary … [--session-id …]
[--capsule-digest …] [--idempotency-key …] [--dry-run]` calls
`MemoryService.close` and prints the canonical `CloseReceipt`. Its exit code
is the canonical verdict: `0` only when a close record is committed, `3`
for a dry run that committed nothing, `2` for a failed or rejected close.
No projection outcome participates in that verdict.

**Idempotent close.** `CloseRequest.idempotency_key` names the retry
identity of a close. A replay under the same key collapses onto the first
close record and returns `CloseReceipt.replayed = True` with the same
`record_id`, so two SessionEnd runs produce exactly one logical close.
Without a key every call is a distinct close, as before.

**SDK parity.** `MemorySDK` gains `write_governed`,
`ingest_governed_candidate`, `conflicts`, `verify_phase_lock`, `close`, and
`health`, so an in-process consumer has no lifecycle operation it can only
reach by going around the service.

**Capability receipt.** `l9-memory capabilities` and `memory.capabilities`
emit one `ControlPlaneCapabilities` receipt: package version, schema
version, `CONTROL_PLANE_CONTRACT_VERSION` (`memory-control-plane/v1`), the
MCP protocol version, the lifecycle operations, and — read from the live CLI
parser and MCP inventory, never hand-listed — the command or tool each
transport exposes for each operation. `HealthReport` carries the same
`contract_version`. A consumer binds to this signal; it does not infer
compatibility from tool presence.

**Continuation candidate contract.** The governed-candidate ingress admits a
Cursor session continuation capsule losslessly. `session_continuation` joins
the supported classes; `knowledge.payload_schema` and
`knowledge.structured_payload` carry a producer-owned structured artifact
that the service stores under record metadata and never interprets; and the
`namespace_local` visibility lets the candidate name the exact namespace it
requests through `source.namespace`. That name is a request. `MemoryService`
authorizes the principal against it like any other write, so a candidate
naming a namespace the principal cannot write is rejected, not admitted
somewhere else.

## Alternatives Considered

- Leave the CLI without `close` and have Cursor hooks drive the MCP stdio
  server themselves
- Have Cursor derive a close idempotency key by convention and accept a
  second close record as harmless
- Let the consumer detect compatibility by probing `tools/list`
- Encode the continuation capsule as a pipe-delimited string inside the
  candidate statement
- Add a dedicated `memory.continuation` tool instead of extending the
  governed-candidate contract

## Rejected Alternatives

- A hook implementing JSON-RPC over stdio duplicates transport logic in the
  consumer and gives a shell hook no exit-code verdict.
- A second close record is not harmless: hydration would surface two closes
  for one session and the consumer would have to pick, which is exactly the
  local truth-making this decision removes.
- Tool presence says nothing about receipt shapes or exit semantics; the
  consumer would be guessing at the contract it depends on.
- A pipe string is the fuzzy protocol being retired; it is lossy and
  unparseable by anything but the producer that wrote it.
- A dedicated tool would be a second admission path for what is, to memory,
  a governed candidate with a structured payload; the existing ingress already
  owns admission, idempotency, and authorization.

## Invariants

- `l9-memory close` exits `0` only when `MemoryService.close` committed a
  record or replayed one already committed
- A close replayed under one `idempotency_key` yields one close record
- Every operation in `LIFECYCLE_OPERATIONS` has a CLI command and an MCP tool,
  and `ControlPlaneCapabilities.missing_operations()` is empty for both
- The capability receipt is built from the live parser and tool inventory
- `namespace_local` is authorized by `MemoryService` on write; the candidate
  cannot grant itself a namespace
- `structured_payload` is stored verbatim and never interpreted by memory

## Consequences

Positive: a consumer can drive hydrate, ingest, close, conflicts, and
phase-lock through one synchronous CLI with exit-code verdicts, prove its
binding before the first call, and store a structured continuation capsule
instead of a provider string.

Negative: the CLI gains two commands and the MCP inventory one tool, which
the Cursor probe's required set does not include and so does not fail on;
consumers pinned to the previous inventory see additive change only.

## Security Impact

No new authority. `close` and the continuation candidate run through the
same admission and namespace policy as every write. The capability receipt
reads no store and carries no secret. `namespace_local` widens what a
candidate may *request* and nothing it may *obtain*.

## Migration Impact

`CloseRequest`, `CloseReceipt`, `HealthReport`, `GovernedCandidateSource`, and
`GovernedCandidateKnowledge` gain optional fields with defaults; existing
callers and persisted records are unchanged. Cursor-Governance's cutover to
these surfaces is its own campaign (its C1–C12), of which this ADR is the
memory-side prerequisite.

## Validation Requirements

- `tests/unit/test_control_plane_transport_parity.py`: CLI close commit,
  dry run, rejection, and replay; capability receipt completeness and its
  refusal to claim absent surfaces; MCP capabilities and idempotent close;
  SDK parity; continuation candidate round trip, duplicate replay,
  unauthorized `namespace_local`, and schema pairing

## Rollback Conditions

Reverting removes the CLI `close` and `capabilities` commands, the
`memory.capabilities` tool, the SDK additions, and the optional contract
fields. Close records written with an `idempotency_key` remain ordinary
close records. Continuation candidates already stored remain records whose
metadata carries a payload the reverted code ignores.

## Supersedes / Superseded By

Extends the close semantics of ADR-030 and the governed-candidate ingress of
ADR-063 with idempotency, a structured payload, and a requested namespace;
the client-instantiation proof of ADR-064 is unchanged.

No later ADR supersedes this decision as of 2026-09-05.
