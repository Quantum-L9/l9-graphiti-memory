# ADR-082: Consumer Control-Plane Transport Parity

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-082-consumer-control-plane-transport-parity.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-10-14
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

## Amendment — 2.3.0 (campaign stage M2)

Release `2.3.0` is the `MEMORY_TARGET_VERSION` the consumer binds. Beyond the
M1 surface above it adds the tag selector on search and hydrate (the consumer's
typed continuation retrieval), `client cursor verify --path` probing the entry
as installed rather than as generated, the installed-wheel lifecycle proof, and
the shared fixture under `tests/fixtures/control_plane/`. None of these change
`CONTROL_PLANE_CONTRACT_VERSION`: every addition is optional on the request
side and additive on the receipt side.

## Amendment — refinement supersession and replay forensics (audit closure, 2026-09-06)

The paired-release audit of Cursor-Governance#509 and this PR found two
lifecycle defects at the new seam, both closed here without changing
`CONTROL_PLANE_CONTRACT_VERSION` (request side optional, receipt side additive).

**Governed-candidate supersession (P1-03).** `GovernedMemoryCandidate` gains
an optional `supersedes: [record_id, …]`. A producer that refines a
continuation (Cursor's Phase B over its Phase A capsule) names the prior
canonical record instead of leaving two ACTIVE continuations behind and
relying on retrieval order. Memory owns the validation — same tenant,
authorized namespace, target exists, lifecycle transition legal — and applies
the transition transactionally through the existing
`MemoryWriteRequest.supersedes` path; the ingestion result reports
`superseded_record_ids`. A supersession memory refuses rejects the candidate
before anything is committed and leaves the targets untouched, so a failed
refinement keeps the Phase A record ACTIVE. The refinement keeps its own
candidate id and idempotency key: the payload genuinely changed, and reusing
the prior key would make memory keep the original body and hide the
refinement as a duplicate.

**Close replay forensics (P2-01).** `CloseReceipt` gains
`replay_payload_matched`, `stored_digest`, `replay_digest` and `warnings`.
A close replayed under an existing idempotency key still collapses onto the
first close record, but the receipt now says whether the replay carried the
same normalized payload; a drifted replay surfaces the write path's
"replay payload differs" warning instead of reading as a clean `replayed`.
The consumer's retry path replays the exact original close request from its
local obligation and treats a mismatch as a finding.

Tests: `tests/unit/test_control_plane_transport_parity.py` — refined
continuation supersedes the prior record and is the only one tag-selected
search returns; refused supersession rejects the refinement and keeps the
prior ACTIVE; the CLI carries `supersedes`; close replay reports a matched
payload and a drifted one.

## Amendment — semantic parity is not protocol conformance (2026-10-13)

**Decision date:** 2026-10-13 (campaign MEM-HTTP-DOC-01).
**Implementation status:** the remote HTTP contract below is required and
not implemented. **Proof status:** not proven.

This ADR's parity is **semantic**: every lifecycle operation reaches the same
`MemoryService` handler with the same receipts, whatever adapter carries it.
Three other properties are separate and are not implied by it:

| Property | Owner | What proves it |
|---|---|---|
| Semantic operation parity | this ADR | `tests/unit/test_control_plane_transport_parity.py`; the capability receipt built from the live parser and tool inventory |
| MCP transport/protocol conformance | ADR-038 | conformance tests for each pinned protocol revision (none exist for the HTTP server today) |
| Remote authentication and identity | ADR-083 | the remote identity negative suite (does not exist today) |

A green parity suite says nothing about whether the current HTTP endpoint is a
conforming Streamable HTTP server, or whether its principal is the right
agent.

### Remote HTTP consumer contract (required, unverified)

When ADR-038's remote target is implemented, a remote consumer binds to the
following, and each item needs its own evidence over the real HTTP endpoint
of an installed wheel before anyone claims it:

1. **Negotiation.** The protocol revision or revisions the server pins, how a
   client learns them, and how a mismatch is refused.
2. **Discovery.** `tools/list` returns the same inventory `mcp_tools.py`
   defines for stdio.
3. **Invocation.** `tools/call` for every operation in `LIFECYCLE_OPERATIONS`
   (`health`, `capabilities`, `hydrate`, `search`, `get`, `ingest`,
   `ingest_governed_candidate`, `close`, `conflicts`, `phase_lock`,
   `verify_phase_lock`) and for both agent write tools, `memory.write_agent`
   and `memory.write_governed`.
4. **Receipts.** The receipt shapes this ADR and ADR-083 document, unchanged.
5. **Version handshake.** `memory.capabilities` reports package version,
   schema version, `CONTROL_PLANE_CONTRACT_VERSION` and the MCP protocol
   revision actually served, and a consumer binds to that receipt, not to tool
   presence.

Whether a remote HTTP surface keeps `memory-control-plane/v1` or needs a
contract bump is **undetermined**. It can keep `v1` only if the operation set
and every receipt shape are unchanged and a consumer's binding proof still
holds over the new transport. No document may claim `memory-control-plane/v1`
compatibility for remote HTTP until that is validated. The capability receipt
today reports `mcp_protocol_version` `2024-11-05`, which describes what the
server advertises, not a conformance result.

## Amendment — proof obligations over the ADR-098 candidate (2026-10-14)

**Decision date:** 2026-10-14 (campaign MEM-DOC-3.0, documentation only).
**Effect:** records what the ADR-098 candidate (PR #94) proves against the
2026-10-13 list, whose "not implemented" status line and "none exist today" /
"does not exist today" notes described `441b741` and are superseded for the
candidate by the evidence column below. The five
properties are separate proof obligations; a pass on one is never evidence
for another.

| Obligation | Owner | Candidate evidence (PR #94) | Owed for 3.0.0 |
|---|---|---|---|
| MCP protocol conformance | ADR-038, ADR-098 | `tests/integration/test_remote_mcp_http.py` over real TCP: negotiation of `2025-11-25`/`2025-06-18`, `MCP-Protocol-Version`, framing, `202`, `405`, `Origin`, `Accept`, `Content-Type`, size and envelope refusals | the same suite on the 3.0.0 bytes |
| Authentication and identity | ADR-083, ADR-098 | same suite: missing, expired, over-ceiling, tampered, unknown-agent and other-actor credentials; smuggled claims; human door unreachable; startup refusal of an administrator agent grant | the same suite on 3.0.0 bytes |
| Lifecycle | this ADR | over HTTP the suite calls `health`, `capabilities`, `hydrate`, `search`, `get`, `close`, `phase_lock`, `write_agent` and `write_governed`; the installed wheel's HTTP proof calls `initialize`, `tools/list`, `capabilities`, `write_agent` and `search` | `ingest`, `ingest_governed_candidate`, `conflicts` and `verify_phase_lock` are not exercised over HTTP; installed-wheel coverage of the full set |
| Receipts | this ADR, ADR-083 | `test_capability_and_lifecycle_receipts_keep_their_control_plane_shapes` | the receipt-shape test on a PostgreSQL-backed service; `tests/integration/test_remote_mcp_postgres_multiprocess.py` checks write and read receipts (status, record id, authorization, provenance) across processes on PostgreSQL, but the shape test still runs in-memory and the wheel proof on SQLite |
| Semantic parity | this ADR | unchanged: `tests/unit/test_control_plane_transport_parity.py`; both transports dispatch the same tool definitions to the same `MemoryService` | — |

**Contract version.** The 2026-10-13 amendment left open whether remote HTTP
keeps `memory-control-plane/v1`. ADR-098 decides it for the candidate: the
operation set, tool definitions and receipt shapes are unchanged, so
`contract_version` stays `memory-control-plane/v1`, and the transport is
versioned separately as `memory-remote-mcp/v1` (`docs/REMOTE_MCP_CONTRACT.md`),
reported additively by `memory.capabilities` as `remote_mcp_contract_version`
and `http_mcp_protocol_versions`. A remote consumer may claim
`memory-control-plane/v1` compatibility over HTTP only for the operations it
has proven over HTTP; the lifecycle row above lists the gaps.
`mcp_protocol_version` in the receipt remains the stdio revision.

The capability receipt reports which HTTP revisions the package supports. It
does not report whether an HTTP server is running or which `http_auth_mode`
it uses; a consumer learns those from its own deployment evidence.

## Amendment — Memory-owned remote consumer (2026-10-16)

**Decision date:** 2026-10-16 (campaign MEMORY-C1-REMOTE-CONSUMER-CLOSURE).
**Effect:** adds the consumer half of `memory-remote-mcp/v1`. No contract
version, tool definition, receipt shape, capability receipt or server
behaviour changes.

**Context.** ADR-098 gave the hosted `MemoryService` a conforming Streamable
HTTP door with signed-agent identity, but the package shipped no client for
it. A consumer that wanted the hosted service had to implement JSON-RPC over
HTTP, credential carriage, contract binding and failure classification
itself. That is the transport duplication this ADR rejected for stdio in
2026-09-05, and it would put Memory transport ownership in the consumer.
Cursor-Governance drives memory only through `l9-memory` argv, stdout
receipts, exit codes and stderr error types.

**Decision.**

1. `l9_graphite_memory.remote_client.RemoteMemoryClient` is the
   Memory-owned client of `memory-remote-mcp/v1`. It negotiates
   `2025-11-25`/`2025-06-18`, sends `notifications/initialized`, and then
   binds the server's `memory.capabilities` receipt. The receipt must name
   `memory-control-plane/v1` and `memory-remote-mcp/v1`, advertise the
   negotiated revision, and expose every lifecycle operation plus
   `write_agent` and `write_governed` on the MCP transport. Otherwise the
   client refuses with `contract_mismatch` before any lifecycle call. Every
   receipt is validated into the same pydantic model the in-process service
   returns, so a drifted receipt is also a `contract_mismatch`, never a
   partial read.
2. **Identity is the stdio agent door's, carried per request.** The client
   reads `L9_MEMORY_AGENT_ASSERTION`, `L9_MEMORY_IDENTITY_ASSERTION_JSON` and
   `L9_MEMORY_IDENTITY_ASSERTION_HMAC` (or takes a credential provider) and
   sends them as the three ADR-098 headers on every request. It never holds
   or sends a signing key, grant, role, tenant or namespace claim. No new
   credential class exists.
   - **Expiry.** An assertion within 5 s of expiry is refused locally
     (`credential_expired`).
   - **Refresh.** A callable provider is consulted per request, and one
     `401` is retried with freshly minted evidence. A `401` means nothing was
     served, so the retry cannot duplicate a write.
3. **The CLI is the hook-lane carrier.** `l9-memory --remote-url URL …` or
   `L9_MEMORY_REMOTE_URL` runs the following commands against the hosted
   service, with the argv, stdout receipt and exit codes of the local
   commands:
   - `health`, `capabilities`, `hydrate`, `search`, `get`, `write`,
     `ingest-governed-candidate`, `close`, `conflicts`, `phase-lock`,
     `verify-phase-lock` — the ADR-082 lifecycle set, where `write` is the
     operator form of `ingest`;
   - `resolve`, which is local namespace computation.

   A failure prints `{"error", "message", "remote": {failure_kind,
   http_status, rpc_code, remote_type}}` on stderr and exits `1`. `error` is
   the type a local run raises for the same outcome:
   - `AuthorizationError`, `AuthenticationError`, `ConfigurationError`,
     `ValueError`;
   - `ConnectionError` for an unreachable server;
   - the server's own `data.type` for a tool failure.

   A consumer's type-based classification therefore holds unchanged.
4. **No fallback.** With a remote URL selected, no local runtime or store is
   constructed. Every other command is refused with `unsupported_remotely`
   before any request is sent, and an unreachable, stalled or redirecting
   server is a typed failure:
   - plain `http://` is accepted only to a loopback host;
   - a URL carrying user information, a query or a fragment is refused;
   - redirects are refused, so credentials reach one endpoint only.
5. **Distillation is blocked remotely.** `memory.distill` (and
   `memory.bootstrap`) require `principal.is_admin`. ADR-098 refuses to start
   a server that would give a signed agent an administrator grant, and the
   tool reads a path on the server's filesystem, so a client's local excerpt
   is unreachable. Serving it would need a new tool, credential class or
   authority. None is defined, and inventing one is outside this decision.
   `l9-memory distill` under a remote URL is refused with the reason, and
   local distillation is unchanged. `REMOTE_BLOCKED_OPERATIONS` records the
   block.
6. **Remote provenance is server-derived.** On `write`, the CLI's `--source`
   label and the session id are not sent: the remote contract carries no
   field for them. The record's provenance is the verified agent's, with
   `source=mcp` and `tool=memory.ingest`.

**Also corrected.** `write --kind` and `import --memory-class` defaulted to
the enum member, which argparse passed through `str()` as
`"MemoryClass.OBSERVATION"` and refused. `l9-memory write` without `--kind`
had never parsed. Both defaults are now the string value.

**Proof obligations from 2026-10-14, updated.**

| Obligation | Evidence added |
|---|---|
| Lifecycle over HTTP | `tests/integration/test_remote_consumer.py` runs every lifecycle command through the shipped CLI against a real signed-agent server on TCP, including the four owed operations (`ingest`, `ingest_governed_candidate`, `conflicts`, `verify_phase_lock`), plus both agent write doors through the client |
| Receipts on PostgreSQL | `tests/integration/test_remote_consumer_postgres.py`, run from the source tree and from the installed wheel alone: candidate admission, hydration, close, close replay, phase lock and verification, grant refusals and `get` — each a separate CLI process, across separate server processes on one PostgreSQL schema and across a full restart, with receipts validated into their models by the client |
| No local fallback | both suites assert that no SQLite ledger appears beside the consumer, and that a stopped, unreachable or stalled server is a typed failure |

**Not covered.**
- TLS to a real deployment and any non-loopback path.
- Consumer adoption. Cursor-Governance's CANONICAL_LAW §8.5.4 and ADR-0031
  seal agent HTTP, and its `ops/config/memory-binding.json` pins 2.6.0. Both
  are consumer-owned and unchanged here.
- Remote distillation, blocked as above.
- In-window replay, as in ADR-098.

**Rollback.** Unset `L9_MEMORY_REMOTE_URL` (or omit `--remote-url`): every
command runs locally exactly as before. Reverting removes the client module
and the flag, and no record, receipt or server behaviour depends on them.
