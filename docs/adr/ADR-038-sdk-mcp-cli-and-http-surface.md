# ADR-038: SDK, MCP, CLI, and HTTP Surface

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-038-sdk-mcp-cli-and-http-surface.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-10-14
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

No later ADR supersedes this decision as of 2026-07-21. ADR-098 extends the HTTP surface with Streamable HTTP conformance and signed-agent HTTP identity without changing this decision.

## Amendment — remote agent transport target (2026-10-13)

**Decision date:** 2026-10-13 (operator decision, campaign MEM-HTTP-DOC-01).
**Implementation status:** not implemented. **Proof status:** not proven.
This amendment records a target. It does not describe software that runs
today, and it changes nothing in the 2026-07-21 decision above for the
surfaces that exist.

**Release status (operator statement, 2026-10-13):** 2.5 is the current
release; 2.6 is the version to be released and deployed. "Current" in this
document means the code on `main` at `441b741` (package version 2.6.0), not a
released or deployed artifact. This document does not state what the 2.6
release will contain: the remote target counts as shipped only when the proof
listed below passes on the exact released bytes.

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

### What the HTTP surface on current `main` is

Verified against `src/l9_graphite_memory/server.py` and `version.py` at
`441b741`:

| Property | Behavior at `441b741` (package 2.6.0) | Gap against the target |
|---|---|---|
| Routes | `POST /mcp`, `POST /mcp/`; unauthenticated `GET /healthz`, `GET /readyz`, and FastAPI's default `/docs`, `/redoc`, `/openapi.json` | no `GET`/`DELETE` handler on the MCP endpoint; the unauthenticated documentation and readiness routes need an explicit exposure decision |
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

Unchanged: retain stdio MCP and the CLI while disabling HTTP. Withdrawing the
target itself is a later dated amendment that says so; this one is not
deleted. No code depends on it.

## Amendment — Memory 3.0.0 target convergence (2026-10-14)

**Decision date:** 2026-10-14 (campaign MEM-DOC-3.0, documentation only).
**Effect:** reconciles the 2026-10-13 amendment above with ADR-098 and the
operator's release identity. No code, configuration, topology or release
changes with it.

### Release identity (supersedes the 2026-10-13 release statement)

The 2026-10-13 amendment recorded "2.6 is the version to be released and
deployed". That statement is superseded by the following separate facts; the
2026-10-13 text stays as the record of what was said that day.

| State | Identity | Meaning |
|---|---|---|
| Current operational release | 2.5.0 | operator-designated |
| Package release line | 2.6.0 | a `v2.6.0` Git tag and a published 2.6.0 artifact exist; neither is operator acceptance or a deployment |
| Candidate | ADR-098 implementation, PR #94, source version identifier 2.7.0 | unmerged at 2026-10-14; not an accepted or live release |
| Target | Memory **3.0.0** | first live release of the consolidated remote architecture; not built, not released, not deployed |

Tag existence, published package identity, active deployment and operator
release acceptance are distinct facts and are never inferred from one another.
3.0.0 is bound to exact source and built-artifact identities only after the
candidate is integrated and validated; renumbering the candidate's version
identifier is a release-preparation step this amendment does not take.

### Target, restated for 3.0.0

The target of the 2026-10-13 amendment is unchanged and is now the 3.0.0
target: one logical `MemoryService`, hosted on the operator-controlled Hetzner
C1 environment, reached by Cursor, Claude Code and other authorized agents on
different machines through MCP Streamable HTTP behind a trusted TLS reverse
proxy, backed by one new, empty PostgreSQL database. HTTP stays an adapter.
Process lifecycle, recovery, availability, health and readiness belong to the
hosting/deployment boundary, and the runtime does not depend on the operator's
Mac being online. Exact hostname, address, certificate, process supervisor and
operating-system configuration are unverified until deployment evidence
exists. C1 is not deployed.

### What the 2026-10-13 "open" items became

| 2026-10-13 statement | Disposition (2026-10-14) |
|---|---|
| Implementation status: not implemented | Superseded for the transport: ADR-098 is a candidate implementation (PR #94). The 3.0.0 deployment remains unimplemented and unproven. |
| Protocol revision selected by the implementation campaign | Settled by ADR-098: HTTP serves `2025-11-25` and `2025-06-18` (`HTTP_MCP_PROTOCOL_VERSIONS`); stdio keeps `2024-11-05` (`MCP_PROTOCOL_VERSION`). `2026-07-28`, which drops `initialize`, is not served: a client speaking only it is refused. The 2026-10-13 requirement to pin from probes of installed clients is not met in this repository; those probes are consumer proof. |
| HTTP gap table at `441b741` | Remains a correct description of `441b741`. In the candidate, framing, `202` notifications, `GET`/`DELETE` `405`, negotiation, `MCP-Protocol-Version`, `Origin` and the `WWW-Authenticate` challenge are closed by ADR-098. Still open: FastAPI's default `/docs`, `/redoc` and `/openapi.json` are served unauthenticated (no exposure decision is recorded), and TLS is out of process by design. |
| Proof item 1, Streamable HTTP conformance | Candidate evidence: `tests/integration/test_remote_mcp_http.py` and the installed-wheel HTTP proof in `tests/integration/test_installed_wheel_lifecycle.py`, run on the candidate; not yet run on 3.0.0 bytes. |
| Proof item 2, ADR-083 remote identity suite | Candidate evidence in the same suite; the administrator-grant case is not covered (ADR-083, 2026-10-14). |
| Proof item 3, ADR-082 lifecycle parity over HTTP | Partial; see ADR-082, 2026-10-14. |
| Proof item 4, product topology | Open; see ADR-094, 2026-10-14. |

### Proof still owed before 3.0.0 is called deployed

1. The candidate integrated, versioned 3.0.0, and validated on the exact
   release bytes (`scripts/validate_release.sh` in publication mode).
2. The HTTP suite run against a PostgreSQL canonical store; the candidate's HTTP suite uses an in-memory store and its installed-wheel HTTP proof the default SQLite store.
3. The ADR-083 administrator-grant decision implemented or recorded as a
   deployment-only control, with its negative test.
4. ADR-094's classification resolved by its owner.
5. C1 deployment evidence: TLS, process supervision, readiness, backup and
   restore, owned by the deployment campaign.
6. Consumer acceptance by each consumer in its own repository.

Rollback is unchanged.
