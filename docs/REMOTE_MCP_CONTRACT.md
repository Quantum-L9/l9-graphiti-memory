<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/REMOTE_MCP_CONTRACT.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.7.0
updated: 2026-07-22
/L9_META -->

# Remote MCP Contract — `memory-remote-mcp/v1`

Binding for `l9-graphite-memory` **2.7.0** and later until the contract version
changes. Decision record: [ADR-098](adr/ADR-098-remote-mcp-transport-and-signed-agent-http-identity.md).
Constants: `l9_graphite_memory.version.REMOTE_MCP_CONTRACT_VERSION` and
`HTTP_MCP_PROTOCOL_VERSIONS`, also reported by `memory.capabilities` as
`remote_mcp_contract_version` and `http_mcp_protocol_versions`.

This document describes what the Memory server guarantees. It does not install
or authorize any consumer; a consumer's configuration is unverified until that
consumer proves it in its own campaign.

## 1. Transport

| Item | Contract |
|---|---|
| Endpoint | `POST https://<host>/mcp` (also `/mcp/`). TLS is terminated in front of the server. |
| Revisions | `2025-11-25`, `2025-06-18` (Streamable HTTP). stdio stays `2024-11-05`. |
| Negotiation | `initialize.params.protocolVersion` is echoed when supported, otherwise the server answers `2025-11-25`. A client that cannot speak the answer must disconnect. |
| Version header | `MCP-Protocol-Version: <negotiated>` on every request after `initialize` (notifications included). Absent ⇒ assumed `2025-03-26` ⇒ `400`. |
| Body | One JSON-RPC 2.0 message. Batches are refused. `id` is a string or integer, never `null`. |
| Headers | `Content-Type: application/json`; `Accept` admitting both `application/json` and `text/event-stream` (`*/*` qualifies). |
| Request response | `200`, `Content-Type: application/json`, one JSON-RPC response with the request `id`. No SSE. |
| Notification / client response | `202`, empty body. |
| `GET`, `DELETE` | `405`, `Allow: POST`. No standalone stream, no session. |
| Session | None. No `MCP-Session-Id` is issued or read. |
| Probes | `GET /healthz`, `GET /readyz` (unauthenticated, as in 2.6.0). |

## 2. Signed-agent authentication (`L9_MEMORY_HTTP_AUTH_MODE=signed-agent`)

Sent on **every** request:

| Header | Value | Minted with |
|---|---|---|
| `Authorization` | `Bearer <agent_id>.<exp_unix>.<nonce_hex>.<hmac_hex>` | `mint_assertion(agent_id, key, ttl_seconds=…)`: HMAC-SHA256 under the agent key over `agent_id\|exp\|nonce` |
| `L9-Identity-Assertion` | base64url (padding optional) of the sealed `l9.identity-assertion/v1` JSON object | the resolver output, sealed with `assertion_digest = local_assertion_digest(body)` |
| `L9-Identity-Assertion-HMAC` | lowercase hex | `identity_assertion_hmac(assertion_digest, key)` |

These are the values the stdio door reads from `L9_MEMORY_AGENT_ASSERTION`,
`L9_MEMORY_IDENTITY_ASSERTION_JSON`, and `L9_MEMORY_IDENTITY_ASSERTION_HMAC`;
only the carrier differs.

Server-side only — never sent by a client:

| Variable | Content |
|---|---|
| `L9_MEMORY_AGENT_SIGNING_KEYS_JSON` | `{agent_id: key}` for every agent this deployment admits |
| `L9_MEMORY_AGENT_GRANTS_JSON` | `{agent_id: AgentDoorGrant}` — `principal_id`, `user_id`, `roles`, `read_namespaces`, `write_namespaces`, `promote_namespaces`, `is_admin` |
| `L9_MEMORY_HTTP_AGENT_ASSERTION_MAX_TTL_SECONDS` | lifetime ceiling, default `3600` (plus 60 s clock skew) |
| `L9_MEMORY_HTTP_ALLOWED_ORIGINS` | comma list of browser origins; a request with any other `Origin` gets `403` |

Every registered agent must have a valid grant, and `human` cannot be
registered; otherwise the server refuses to start. Tenant, organization, and
workspace come from `L9_MEMORY_LOCAL_*_ID` on the server.

**Refresh.** The assertion is reusable until it expires. Clients mint a new one
before then:

- Claude Code: `headersHelper` runs at session start, on reconnect, and after a
  `401`/`403`, so a helper that mints the three headers keeps them fresh.
  Static `headers` with `${VAR}` expansion also work but do not refresh.
- Official MCP SDKs: static headers through `requestInit`, or per-request
  minting through a custom `fetch` (both proven in the 2.7.0 evidence).
- Cursor: static `headers` with `${env:VAR}` expansion; there is no refresh
  hook, so the variable must be refreshed outside the IDE. Not proven here.

**Bearer mode** (`L9_MEMORY_HTTP_AUTH_MODE=bearer`, the default) maps a static
token to configured service-principal claims (`L9_MEMORY_AUTH_TOKENS_JSON` /
`_FILE`). It is not an agent identity.

## 3. Refusals

All refusal bodies are `{"jsonrpc": "2.0", "error": {"code", "message", "data"?}}`
with **no** `id`. Credentials are never echoed.

| Condition | Status | JSON-RPC code |
|---|---|---|
| `Origin` present and not allowed | 403 | -32600 |
| credential-shaped URL query parameter | 400 | -32600 |
| missing / malformed / expired / over-ceiling / tampered / unknown-agent / other-actor credential | 401 + `WWW-Authenticate: Bearer realm="l9-graphite-memory"[, error="invalid_token"]` | -32001 |
| `Content-Type` not `application/json` | 415 | -32600 |
| `Accept` lacks either media type | 406 | -32600 |
| body over 4 MiB | 413 | -32600 |
| unparseable JSON | 400 | -32700 |
| batch, missing/invalid `jsonrpc`, `id`, or `method` | 400 | -32600 |
| unsupported or absent `MCP-Protocol-Version` | 400, `data: {supported, requested}` | -32600 |

JSON-RPC-level outcomes keep the request `id` and HTTP `200`, exactly as stdio:
unknown method or tool `-32601`, invalid params `-32602`, authentication inside
a tool `-32001`, memory errors `-32010` with `data.type` (for example
`AuthorizationError` for an ungranted read), unhandled failure `-32603`. An
ungranted write returns a `rejected` receipt with `record_id: null`.

## 4. Cursor-Governance compatibility matrix

Read-only inspection of Cursor-Governance at the time of 2.7.0. "Consumer
change" is work for the successor campaign; nothing here was changed in
Cursor-Governance.

| Area | Cursor-Governance today | Remote server (2.7.0) | Compatible | Consumer change |
|---|---|---|---|---|
| Agent authentication | `ops/memory/agent_assertion.py` mints `agent_id.exp.nonce.hmac` (TTL 3600) into `L9_MEMORY_AGENT_ASSERTION` | Same token in `Authorization: Bearer` | Yes: same format and verifier | Carry the token in a header (e.g. a `headersHelper`) |
| Identity assertion | `print_agent_assertion_env.py` seals `l9.identity-assertion/v1`; same digest rule and HMAC | Same object, base64url in `L9-Identity-Assertion`; HMAC in `L9-Identity-Assertion-HMAC` | Yes: same `verify_canonical_identity_assertion` | base64url-encode the sealed JSON |
| Signing keys | Per agent; hosted containers mint ephemeral `token_hex(32)` keys | Server-side `L9_MEMORY_AGENT_SIGNING_KEYS_JSON` registry | Only with keys shared by agent and server | Provision durable per-agent keys to both sides; ephemeral container keys cannot reach a remote server |
| Namespace authorization | Grants from `agent_registry.yaml` `assigned_groups`, trimmed to `AgentDoorGrant` | Same grant model, server-side `L9_MEMORY_AGENT_GRANTS_JSON`; `MemoryService` authorizes | Yes | Render the grant map for the server deployment, not the agent process |
| `memory.write_agent`, `memory.write_governed` | Arguments built by `ops/memory/agent_write.py`; result read from `content[0].text` | Same tools, schemas, receipts | Yes | None |
| `memory.search`, `memory.hydrate`, `memory.close` | Same tools via stdio; hook lane uses the CLI | Same tools and receipts over HTTP | Yes | None for MCP; the CLI hook lane is not affected |
| Phase locks and receipts | `phase_lock` → `write_governed`; receipt fields per `memory-receipt-contract.json` | Same `lock_id`, `granted`, `expires_at`; write `receipt_id`, `status`, `namespace`, `record_id` | Yes | None |
| Health and capabilities | Binds `memory-control-plane/v1` and package version from `l9-memory capabilities` | Same receipt plus additive `http_mcp_protocol_versions`, `remote_mcp_contract_version` | Yes, additive | Pin `2.7.0` and, for HTTP, `memory-remote-mcp/v1` |
| MCP initialize | Stdio test sends `2024-11-05` and checks only that a version is returned | stdio unchanged (`2024-11-05`); HTTP answers `2025-11-25` or `2025-06-18` | Yes | An HTTP client must speak one of the HTTP revisions |
| `tools/list`, `tools/call` | Dotted names; Claude maps `.` to `_` | Identical definitions on both transports | Yes | None |
| Error semantics | Ungranted write: `-32001`/`-32010` or a `rejected` receipt | Same JSON-RPC codes; transport refusals add HTTP statuses | Yes | Handle `401` (re-mint) and `400`/`406`/`415` (client defect) |
| Transport policy | CANONICAL_LAW §8.5.4 and ADR-0031 seal agent HTTP; launcher is stdio only | Remote transport available | **No — consumer law** | A Cursor-Governance ADR is required before any adapter may select HTTP |

## 5. Not covered by this contract

- Deployment of a shared server, PostgreSQL as its canonical store, and TLS
  termination.
- OAuth 2.1 / RFC 9728 discovery. No L9 authorization server exists; when one
  is chosen, `WWW-Authenticate` can add `resource_metadata` in a new contract
  version.
- Audience binding of the agent assertion to one deployment. Use
  per-deployment keys.
- The product topology's `kind: dependency` declares no independent runtime
  identity; an independently hosted server is a topology decision for the
  deployment campaign (see the 2.7.0 evidence).
