# ADR-098: Remote MCP Transport and Signed-Agent HTTP Identity

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-098-remote-mcp-transport-and-signed-agent-http-identity.md
layer: adr
owner: memory-control-plane
status: active
version: 2.7.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-10-13
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.7+ and remote MCP consumers, first `Quantum-L9/Cursor-Governance`

## Status

Accepted

## Context

ADR-038 restricts HTTP to the MCP transport, health, and readiness, and
requires authentication on a non-loopback bind. At 2.6.0 that HTTP surface
could not serve a standards-conforming remote MCP client, and it could not
carry an agent identity:

- `initialize` always answered `protocolVersion: 2024-11-05`, the stdio
  revision, whatever the client asked for. Streamable HTTP did not exist in
  that revision.
- A notification or a client response got `200 {"status": "ok"}`; Streamable
  HTTP requires `202 Accepted` with no body.
- `GET /mcp` fell through to the framework default; no `Origin` was validated;
  `Accept`, `Content-Type`, `MCP-Protocol-Version` and the JSON-RPC envelope
  were not checked; transport errors carried `"id": null`.
- The only credential was a static bearer token mapped to configured claims
  (`L9_MEMORY_AUTH_TOKENS_JSON`). That is a service principal. It proves
  possession of a long-lived shared string, not that the caller is the agent
  the canonical identity authority resolved, so it is not the signed-agent
  contract that ADR-0031 in Cursor-Governance requires for agent writes.

The stdio agent door already verifies the agent contract: a signed agent
assertion (`agent_id.exp.nonce.HMAC`) under the agent's key, then the sealed
`l9.identity-assertion/v1` evidence and its HMAC under that same key, then a
server-side grant. Its evidence arrives through the process environment, once.
A remote server has no such environment; its evidence must arrive with each
request.

## Decision

**Streamable HTTP, stateless.** `POST /mcp` accepts exactly one JSON-RPC
message. A request gets `application/json`; a notification or a client
response gets `202` with an empty body. `GET` and `DELETE` get `405` with
`Allow: POST`: there is no standalone SSE stream and no `MCP-Session-Id`.

**Per-transport protocol negotiation.** `MCPServer` takes the transport's
supported revisions, newest first, and `initialize` echoes a supported
request or answers the newest. HTTP supports `2025-11-25` and `2025-06-18`
(`HTTP_MCP_PROTOCOL_VERSIONS`). stdio keeps its single
`MCP_PROTOCOL_VERSION = 2024-11-05`, so installed stdio clients and the
`client cursor verify` probe see exactly what they saw before.
`2025-03-26` is not offered: that revision requires receiving JSON-RPC
batches, which this server refuses. A non-`initialize` message without
`MCP-Protocol-Version` is therefore assumed to be `2025-03-26`, as the
specification directs, and refused with `400`.

**Transport refusals.** In order: a present `Origin` outside
`http_allowed_origins` → `403`; a credential-shaped URL query parameter →
`400`; authentication failure → `401` with an RFC 6750
`WWW-Authenticate: Bearer realm="l9-graphite-memory"` challenge
(`error="invalid_token"` when a credential was presented); `Content-Type`
other than `application/json` → `415`; an `Accept` that does not admit both
`application/json` and `text/event-stream` → `406`; a body over 4 MiB →
`413`, enforced while the body streams in; JSON that cannot be decoded
(including excessive nesting or oversized integers) → `400`/`-32700`; a
batch or an invalid envelope →
`400`/`-32600`; an unsupported or absent `MCP-Protocol-Version` → `400` with
`data.supported` and `data.requested`. Every refusal body is a JSON-RPC error
response with no `id`.

**Signed-agent HTTP identity.** `http_auth_mode=signed-agent`
(`L9_MEMORY_HTTP_AUTH_MODE`) verifies, independently on every request:

1. `Authorization: Bearer <agent assertion>` with `verify_assertion` against
   the server-registered key for the named agent, then a lifetime ceiling
   (`http_agent_assertion_max_ttl_seconds`, default 3600, plus 60 s skew):
   the token is reusable until it expires, so its lifetime bounds replay;
2. `L9-Identity-Assertion` (base64url of the sealed JSON object) and
   `L9-Identity-Assertion-HMAC` with `verify_canonical_identity_assertion`
   bound to that agent id and key — digest, HMAC, `resolved` result, product,
   actor equal to the authenticated agent, provenance pinned to the bound
   identity authority revision;
3. the agent's grant, validated at startup from the same
   `L9_MEMORY_AGENT_SIGNING_KEYS_JSON` / `L9_MEMORY_AGENT_GRANTS_JSON` the
   stdio door reads.

The principal is built by `agent_principal`, the one function the stdio door
also uses, so a remote agent holds exactly the claims the same agent holds
locally. Nothing in a request becomes a claim: unknown identity-assertion
members are ignored, request headers are not read for claims, and the
requested namespace remains an address that `MemoryService` checks. The
agent id `human` cannot be registered: the human door
(`L9_MEMORY_HUMAN_DOOR_SECRET`) stays a local stdio tier that HTTP never
consults. There is no fallback from a failed credential to any other
principal.

**Bearer mode is retained as the default** for configured service principals
(the TypeScript client's `client:<id>` namespaces). It is not an agent
identity and is not equivalent to the signed-agent contract.
`signed-agent` with `http_auth_required=false` is a startup error.

**Discovery.** `ControlPlaneCapabilities` gains
`http_mcp_protocol_versions` and `remote_mcp_contract_version`
(`memory-remote-mcp/v1`); both are additive and
`contract_version` stays `memory-control-plane/v1`. The wire contract is
`docs/REMOTE_MCP_CONTRACT.md`.

## Alternatives Considered

- Map one static bearer token per agent to that agent's grant
- Implement OAuth 2.1 protected-resource metadata (RFC 9728) now
- Change the global `MCP_PROTOCOL_VERSION` to `2025-11-25`
- Serve `2025-03-26` for clients that omit `MCP-Protocol-Version`
- Issue `MCP-Session-Id` and authenticate once per session
- Carry the identity assertion as raw JSON in a header
- A second HTTP application or a gateway in front of `MemoryService`

## Rejected Alternatives

- A static per-agent bearer token is a long-lived shared secret with no
  expiry, no identity evidence, and no binding to the actor the identity
  authority resolved; it is the ADR-0031 "per-agent HTTPS bearer" design that
  the signed door superseded.
- RFC 9728 requires naming an authorization server. None exists for L9 agents;
  inventing one would be a second identity system. The HTTP challenge stays
  RFC 6750 and can grow `resource_metadata` when an authority is chosen.
- One global revision would change what installed stdio clients receive and
  what the Cursor probe accepts, to make a different transport pass.
- `2025-03-26` requires batch receipt; claiming it while refusing batches is
  non-conformance.
- Session state would make authentication depend on an earlier request and
  add server-side session storage the stateless design does not need.
- Raw JSON loses non-ASCII members in header transport; base64url does not,
  and the digest is computed over the decoded object.
- A second application or gateway duplicates authority the ADR-002 service
  already owns.

## Invariants

- Every HTTP request is authenticated on its own credentials; no session,
  cookie, or cached principal carries over
- A remote agent principal equals the stdio principal for the same grant,
  except `auth_method`
- Roles, namespaces, tenant, and administrator flags come only from server
  configuration
- No credential is accepted from, or echoed into, a URL, a response body, or
  a refusal header
- stdio answers `MCP_PROTOCOL_VERSION` and is otherwise unchanged
- Tool definitions and tool result envelopes are identical on both transports
- Tool-level authorization stays a JSON-RPC result or error (`-32010`), as on
  stdio; HTTP status codes describe only transport and authentication

## Consequences

Positive: a client that implements the Streamable HTTP wire contract and can
send the three credential headers on every request can reach the one
`MemoryService` over HTTPS as a cryptographically identified agent. The
repository proves that contract with an HTTP client over TCP; interoperability
with the official MCP SDK was observed out of tree (MEM-HTTP-01 evidence) and
with Claude Code `headersHelper` is taken from its documentation — neither is a
release claim of this repository.

Negative: the 2.6.0 HTTP behaviour changes for HTTP callers: a request without
`MCP-Protocol-Version`, without a conforming `Accept`, or as a batch is now
refused, and notifications return `202` without a body. The in-repository
TypeScript client is updated to 3.0.0 (a major version: it requires a 2.7.0+
server) in the same change. The signed-agent
token is bearer-equivalent until it expires and is not audience-bound to one
deployment; per-deployment signing keys and the lifetime ceiling bound that.
Cursor, unlike Claude Code, has no header-refresh hook, so short-lived
credentials there need a refresh outside the IDE or a later OAuth decision.

## Security Impact

The HTTP door accepts exactly the evidence the stdio door accepts, re-verified
per request, with an added lifetime ceiling. Credential shape is validated
before any comparison or arithmetic (decimal `exp` of at most 12 digits,
64 lowercase hex signature, ASCII-only HMAC comparison), so a hostile header is
a `401`, never a server error. An unregistered agent and a bad signature on a
registered one receive the same `401`, so agent ids cannot be enumerated.
Human and agent tiers stay separate, including on auth-disabled loopback HTTP,
which serves the signed agent door or the Tier 3 local principal and never the
human door (closing a gap present at 2.6.0). Origin validation closes DNS rebinding for browser-reachable
deployments. TLS is required for remote deployment and is terminated in front
of the server; the server warns on a non-loopback bind. `/healthz` and
`/readyz` stay unauthenticated probes, as before.

## Migration Impact

Package 2.6.0 is immutable; this ships as 2.7.0. No record, schema, or
receipt shape changes. A bearer deployment keeps working with a conforming
client. A signed-agent deployment sets `L9_MEMORY_HTTP_AUTH_MODE=signed-agent`
and the server-side key and grant registry. Consumer adoption, including the
Cursor-Governance law that currently seals agent HTTP, is a separate,
consumer-owned campaign.

## Validation Requirements

- `tests/integration/test_remote_mcp_http.py`: real uvicorn on TCP, HTTP
  client, known-good and known-bad credentials, protocol and Origin refusals
- `tests/integration/test_installed_wheel_lifecycle.py`: the same contract
  served by the installed wheel's server entry point
- stdio subprocess non-regression in the same suite
- `clients/typescript` `npm run verify:all`

## Rollback Conditions

Set `L9_MEMORY_HTTP_AUTH_MODE=bearer` to return to service-principal HTTP, or
stop the HTTP transport (ADR-038 rollback). stdio and the CLI are unaffected.
Reverting the transport repair requires reverting to 2.6.0 and its
non-conforming HTTP behaviour.

## Supersedes / Superseded By

Extends ADR-038 (HTTP surface) and reuses the stdio door of ADR-083 and the
identity consumption it carries.

No later ADR supersedes this decision as of 2026-10-13.
