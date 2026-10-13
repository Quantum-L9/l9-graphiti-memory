# ADR-038: SDK, MCP, CLI, and HTTP Surface

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-038-sdk-mcp-cli-and-http-surface.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-10-13
/L9_META -->


**Date:** 2026-07-21
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2+

## Status

Accepted

## Context

The original monolith accumulated hundreds of routes. The standalone repository needs several access modes without duplicating logic.

## Decision

Python callers use MemoryService or the shipped thin MemorySDK. Agents use MCP. Operators use CLI. HTTP is restricted to MCP transport, health, and readiness. All surfaces share the composition root and server-derived identity. Stdio MCP resolves a repository-scoped local principal or uses explicit local namespace claims; it does not receive wildcard administrator rights by default.

## Alternatives Considered

- Expose one HTTP route per service method
- Require Python SDK for non-Python agents
- Place business logic in command handlers

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Adapters are thin
- Remote HTTP requires authentication by default
- Loopback unauthenticated mode is explicit
- Stdio namespace grants and administrator authority are explicit

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Surface smoke tests
- MCP auth tests
- CLI installed-wheel tests
- Stdio namespace-claim tests

## Rollback Conditions

Retain stdio MCP and CLI while disabling HTTP; core service remains unchanged.

## Supersedes / Superseded By

Adapts SDK-first lessons from L9_Original_Repo.

No later ADR supersedes this decision as of 2026-07-21.

## Amendment — remote agent transport target (2026-10-13)

**Decision date:** 2026-10-13 (operator decision, campaign MEM-HTTP-DOC-01).
**Implementation status:** not implemented. **Proof status:** not proven.
This amendment records a target. It does not describe software that runs
today, and it changes nothing in the 2026-07-21 decision above for the
surfaces that exist.

### Target

Cursor and Claude Code agents consume canonical memory through **one centrally
hosted Memory MCP service**, reached over **authenticated HTTPS using the MCP
Streamable HTTP transport**:

- one `MemoryService` behind that endpoint, with the same canonical semantics
  as every other surface (ADR-002, ADR-082). The HTTP surface remains an
  adapter; it gains no logic, store or authority of its own;
- the caller principal is established **server-side, per request**, with the
  guarantees ADR-083's 2026-10-13 amendment lists. A client never supplies its
  own role, tenant or grant;
- the intended host is the operator's C1 environment, behind a trusted TLS
  reverse proxy. Hosting, deployment and its proof are owned outside this
  repository and are out of scope here;
- the intended canonical store for that deployment is a **new, empty
  PostgreSQL database** (ADR-072). No SQLite ledger, PostgreSQL database,
  Graphiti/Neo4j graph, Redis state or backup is imported, restored or reused.
  Migration law (ADR-072, ADR-077) is untouched and is not invoked;
- no Redis, Graphiti, Neo4j, vector or other subsystem is a prerequisite of
  that basic shared canonical deployment. Those remain optional, separately
  qualified capability families (ADR-097).

Local stdio MCP, the CLI and the SDK stay supported. Stdio stops being the
*target* agent configuration; it is not retired by this amendment, and its
tests and installer proofs (ADR-064) remain valid for what they prove.

### What the 2.6.0 HTTP surface is today

Verified against `src/l9_graphite_memory/server.py` and `version.py` at
`441b741`:

| Property | 2.6.0 behavior | Gap against the target |
|---|---|---|
| Routes | `POST /mcp`, `POST /mcp/`, `GET /healthz`, `GET /readyz` | no `GET`/`DELETE` handler on the MCP endpoint |
| Framing | one JSON-RPC object per POST, JSON response; batches rejected | no `text/event-stream` responses; `Accept` not read |
| Notifications | `notifications/initialized` answered `200 {"status":"ok"}`; any other notification gets a `-32601` error body | Streamable HTTP answers an accepted notification `202` with no body |
| Version | `initialize` always returns `2024-11-05`; the client's requested version is ignored | no negotiation; `MCP-Protocol-Version` header not read |
| Origin | not validated | Streamable HTTP requires `Origin` validation |
| Identity | static `Authorization: Bearer` token mapped to a configured principal (`TokenAuthenticator`, `L9_MEMORY_AUTH_TOKENS_JSON`/`_FILE`) | not equivalent to the signed agent door; see ADR-083 amendment |
| 401 | JSON-RPC `-32001` body | no `WWW-Authenticate` challenge or protected-resource metadata |
| TLS | none in-process (uvicorn host/port only) | TLS terminates at a trusted proxy in the target |
| `--transport sse` | alias for `http`; no SSE exists | — |

The existing invariants hold: remote HTTP requires authentication by default,
and auth-disabled HTTP is refused on a non-loopback bind.

### Protocol revision

The revision is **selected by the implementation campaign, not here.** Facts
recorded on 2026-10-13 from modelcontextprotocol.io: the published revisions
are 2024-11-05, 2025-03-26, 2025-06-18, 2025-11-25 and 2026-07-28, and the
current one is 2026-07-28, which removes the `initialize` handshake and
protocol sessions. Claude Code documents HTTP transport with custom headers
and negotiates 2026-07-28 only on some runtimes, falling back otherwise.
Cursor documents Streamable HTTP with `url` and `headers` but names no
revision. The implementation must pin the revision or revisions it serves
from probes of the installed clients it supports, and record them in
`version.py` and the capability receipt.

### Proof owed before this target is called implemented

1. Streamable HTTP conformance tests for each pinned revision: POST framing,
   notification `202`, `GET`/`DELETE` behavior, `Origin` rejection,
   protocol-version negotiation and header handling.
2. The ADR-083 remote identity negative suite.
3. ADR-082 lifecycle parity over HTTP against an installed wheel.
4. The product-topology question in ADR-094's 2026-10-13 amendment resolved by
   its owner.

Consumer rebinding (Cursor-Governance) and C1 deployment are separate
campaigns in their own repositories and are not proof of any item above.

### Rollback

Unchanged: retain stdio MCP and the CLI while disabling HTTP. Rolling back the
target itself means deleting this amendment; no code depends on it.
