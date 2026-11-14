<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/REMOTE_MCP_CONTRACT.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.7.0
updated: 2026-11-13
/L9_META -->

# Remote MCP Contract — `memory-remote-mcp/v1`

Describes the HTTP contract of ADR-098 as carried by the `l9-graphite-memory`
3.0.0 release candidate (source version **3.0.0**; first introduced at
source 2.7.0 in PR #94). It binds a release only once that release is
validated on its exact bytes, and stays in force until the contract version
changes. Decision record: [ADR-098](adr/ADR-098-remote-mcp-transport-and-signed-agent-http-identity.md).
Constants: `l9_graphite_memory.version.REMOTE_MCP_CONTRACT_VERSION` and
`HTTP_MCP_PROTOCOL_VERSIONS`, also reported by `memory.capabilities` as
`remote_mcp_contract_version` and `http_mcp_protocol_versions`.

This document describes what the Memory server guarantees. It does not install
or authorize any consumer; a consumer's configuration is unverified until that
consumer proves it in its own campaign.

**Status (2026-10-26).** "2.7.0" was the source version identifier of the
ADR-098 candidate (PR #94). That candidate is integrated into the Memory
3.0.0 release candidate (source version 3.0.0), which is on the default branch
but untagged and not an accepted release; the contract binds a release only
once that release is admitted on its exact bytes (ADR-094). The hosted
carrier (`Dockerfile`, `.l9/deployment.yaml`,
`.github/workflows/release-container.yml`) is a candidate too: no image is
published and no deployment of it exists.

**Hosted carrier door (2026-11-13; supersedes the 2026-11-02 paragraph).**
ADR-100 (*Native OAuth MCP Full Cutover*,
[ADR-100](adr/ADR-100-native-oauth-mcp-full-cutover.md)) makes the hosted
service Auth0 OAuth only: the signed-agent authentication of §2 and the bearer
mode below are not hosted doors and not fallbacks. The hosted carrier
(`Dockerfile`, `.l9/deployment.yaml`) serves the OAuth resource-server mode of
§2a ([ADR-102](adr/ADR-102-oauth-resource-server-for-streamable-http.md)), with
actors bound by the operator
([ADR-103](adr/ADR-103-oauth-actor-binding-and-user-subjects.md)):

- The profile pins `L9_MEMORY_HTTP_AUTH_MODE=oauth` and
  `L9_MEMORY_HTTP_OAUTH_ISSUER` (the Auth0 tenant's issuer, with its trailing
  slash) in `runtime.environment`, where a rendered runtime.env entry cannot
  override them. The image bakes in no mode.
- The image entrypoint (`l9-memory-carrier`) starts the server only for
  `oauth` with an issuer. It refuses unset, `signed-agent`, `bearer` and every
  other value by name, before the server starts. The server then refuses an
  issuer that is not `https`, a missing grant map, an administrator grant and a
  malformed actor map.
- `L9_MEMORY_OAUTH_GRANTS_JSON` and `L9_MEMORY_OAUTH_ACTORS_JSON` are operator
  data in the rendered runtime.env, never in the profile.
- The reverse proxy must pass both `/mcp` and
  `/.well-known/oauth-protected-resource/mcp` to the service (§2a).

The carrier proof (`tests/deployment/carrier/test_container_carrier.py`, run in
full and with no skip by `.github/workflows/release-container.yml`) drives the
built image against PostgreSQL 16 and a local TLS issuer: an audience-bound
token is admitted, a bound subject writes and another reads; wrong issuer,
wrong audience, wrong resource, expired, foreign-signed and client-credentials
tokens, a signed-agent credential and a static bearer token are each refused
with `401`. That issuer is not the live tenant. The live PKCE receipt ADR-100
requires is recorded on
[issue #108](https://github.com/Quantum-L9/l9-graphiti-memory/issues/108#issuecomment-6862806068)
(2026-11-13T19:25:56Z, six of six checks passed, `receipt_sha256`
`sha256:8e0eeb4ed9cb8853b71e448cc38b0ea0fd801372eddc04b2d3f39e6f671b02ad`).
No image is published and no deployment of it exists yet. §2 and the bearer
mode remain the contract of the package's HTTP transport outside the hosted
carrier until the change that removes them.

## 1. Transport

| Item | Contract |
|---|---|
| Endpoint | `POST https://<host>/mcp` (also `/mcp/`, except in OAuth mode, §2a). TLS is terminated in front of the server. |
| Revisions | `2025-11-25`, `2025-06-18` (Streamable HTTP). stdio stays `2024-11-05`. |
| Negotiation | `initialize.params.protocolVersion` is echoed when supported, otherwise the server answers `2025-11-25`. A client that cannot speak the answer must disconnect. |
| Version header | `MCP-Protocol-Version: <negotiated>` on every request after `initialize` (notifications included). Absent ⇒ assumed `2025-03-26` ⇒ `400`. |
| Body | One JSON-RPC 2.0 message. Batches are refused. `id` is a string or integer, never `null`. |
| Headers | `Content-Type: application/json`; `Accept` admitting both `application/json` and `text/event-stream` (`*/*` qualifies). |
| Request response | `200`, `Content-Type: application/json`, one JSON-RPC response with the request `id`. No SSE. |
| Notification / client response | `202`, empty body. |
| `GET`, `DELETE` | `405`, `Allow: POST`. No standalone stream, no session. |
| Session | None. No `MCP-Session-Id` is issued or read. |
| Probes | `GET /healthz`, `GET /readyz` (unauthenticated, as in 2.6.0; public body since 3.0.0, see §1a). FastAPI's default `/docs`, `/redoc` and `/openapi.json` are also served unauthenticated; their exposure is a deployment decision. |

### 1a. Probe bodies are public (3.0.0, U-011)

`/healthz` and `/readyz` carry no credential, so their bodies are public and
are built by allowlist (`src/l9_graphite_memory/public_probe.py`), never by
dumping the internal health report. Status codes are unchanged: `/healthz`
answers `503` when `status` is `failed`, `/readyz` answers `200` only when
`readiness.ready`, and a canonical store that becomes unreachable is a `503`
on both (before 3.0.0 a dropped PostgreSQL connection could surface as `500`).

| Field | Public body |
|---|---|
| top level | `status`, `package_version`, `schema_version`, `contract_version`, `degraded_reasons`, `checked_at` |
| `store`, `projection`, `gate` | `name`, the booleans `configured`/`enabled`/`selected`/`required`/`healthy`/`ready` that the component reports, and `reason` when it is a stable code (`store_unavailable`) |
| `graph` (`/readyz`, when a graph service exists) | `enabled`, `healthy`, `required`, `ready` |
| `active_memory.store`, `active_memory.bus`, `readiness.families[]` | `name`, `selected`, `required`, `healthy`, `ready`, `reasons`, and `detail` reduced to `shared_store` |
| `readiness` | `status`, `ready`, `full_capability`, `package_version`, `schema_version`, `contract_version`, `families`, `degraded_reasons`, `checked_at` |

**Removed from the unauthenticated bodies (breaking):** `store.records`,
`store.schema_version`, `store.path`, `store.error`, `outbox_backlog`,
projection `targets`/`runtime_mode`/tool lists, the graph capability report
beyond its four booleans, and every family's adapter `detail` except
`shared_store`. No count, no path, no URL, and nothing derived from an
exception's text is published. Every consumer in this repository reads only
fields that remain (`status`, `package_version`, `store.name`,
`store.healthy`, `graph.ready`, `active_memory.{store,bus}.{healthy,ready}`,
`readiness.{ready,status,families[].name,families[].healthy}`,
`families[canonical].detail.shared_store`).

The full report stays available to an authenticated caller through the
`memory.health` MCP tool (behind the `/mcp` door). The detail of a store
failure goes to the server log through the one redaction path
(`src/l9_graphite_memory/redaction.py`), which strips passwords, URI userinfo,
secret query parameters and the DSN's own host, port, user and database. A
server that cannot open its store exits non-zero with a message naming
`L9_MEMORY_POSTGRES_DSN` and the class of failure, never its value.

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
| `L9_MEMORY_AGENT_GRANTS_JSON` | `{agent_id: AgentDoorGrant}` — `principal_id`, `user_id`, `roles`, `read_namespaces`, `write_namespaces`, `promote_namespaces`; `is_admin` must be absent or `false` |
| `L9_MEMORY_HTTP_AGENT_ASSERTION_MAX_TTL_SECONDS` | lifetime ceiling, default `3600` (plus 60 s clock skew) |
| `L9_MEMORY_HTTP_ALLOWED_ORIGINS` | comma list of browser origins; a request with any other `Origin` gets `403` |

Every registered agent must have a valid grant, no grant may set `is_admin`,
and `human` cannot be registered; otherwise the server refuses to start.
No signed-agent principal is ever an administrator, in signed-agent mode or on
auth-disabled loopback HTTP serving the agent door. (Bearer-mode token
principals and the auth-disabled Tier 3 local principal keep their configured
`is_admin` / `is_global_admin`; this refusal does not cover them.) Tenant, organization, and
workspace come from `L9_MEMORY_LOCAL_*_ID` on the server.

**Refresh.** The assertion is reusable until it expires: it is not single-use,
and there is no replay ledger. Clients mint a new one before then:

- Claude Code: its documentation describes a `headersHelper` that runs at
  session start, on reconnect, and after a `401`/`403`, so a helper that mints
  the three headers would keep them fresh; static `headers` with `${VAR}`
  expansion do not refresh. Documented client functionality, not demonstrated
  here or accepted by any consumer.
- Official MCP SDKs: static headers through `requestInit`, or per-request
  minting through a custom `fetch`. Observed in an out-of-tree interoperability
  run (MCP TypeScript SDK 1.20.2 and 1.32.1) recorded in the MEM-HTTP-01
  evidence bundle; it is **not** part of this repository's executable release
  validation, which proves the wire contract with an HTTP client over TCP.
- Cursor: static `headers` with `${env:VAR}` expansion; there is no refresh
  hook, so the variable must be refreshed outside the IDE. Not proven here.

**Bearer mode** (`L9_MEMORY_HTTP_AUTH_MODE=bearer`, the default) maps a static
token to configured service-principal claims (`L9_MEMORY_AUTH_TOKENS_JSON` /
`_FILE`). It is not an agent identity.

## 2a. OAuth resource-server mode (`L9_MEMORY_HTTP_AUTH_MODE=oauth`)

Decision records: [ADR-102](adr/ADR-102-oauth-resource-server-for-streamable-http.md),
[ADR-103](adr/ADR-103-oauth-actor-binding-and-user-subjects.md) (actor binding).
The mode is additive to `memory-remote-mcp/v1`; §1, §2 and the bearer mode are
unchanged by it.

Sent on **every** request:

| Header | Value |
|---|---|
| `Authorization` | `Bearer <access token>`: a JWT the configured issuer signed for the Memory resource |

The server requires all of:

| Check | Rule |
|---|---|
| Algorithm | `RS256`, `PS256` or `ES256`. `none` and HMAC algorithms are refused. |
| Key | `kid` present and published in the configured issuer's key set. A key carried in the token is never used. |
| Signature | Valid under that key; RSA keys of at least 2048 bits. |
| `iss` | Equal to `L9_MEMORY_HTTP_OAUTH_ISSUER`, character for character. |
| `aud` | Contains `https://memory.quantumaipartners.com/mcp` (`MEMORY_RESOURCE_IDENTIFIER`). |
| `exp`, `nbf`, `iat` | Enforced with 30 s of clock skew. `exp` and `sub` are required. |
| End user | The token stands for a person. Refused when `gty` or `grant_type` names client credentials, `sub` ends in `@clients`, `sub` equals the `azp` or `client_id` the token names, or `sub_profile` is present and is not `user`. |

Server-side only:

| Variable | Content |
|---|---|
| `L9_MEMORY_HTTP_OAUTH_ISSUER` | The issuer URL, `https`, exactly as in the `iss` claim. No default. Missing or not `https` ⇒ the server refuses to start. |
| `L9_MEMORY_OAUTH_GRANTS_JSON` | `{subject: {roles, read_namespaces, write_namespaces, promote_namespaces}}`, keyed by the token `sub`. Required; `{}` grants nobody. `is_admin` ⇒ the server refuses to start. |
| `L9_MEMORY_OAUTH_ACTORS_JSON` | `{subject: {client_id: {actor_ref, surface_ref?}}}`: the actor the operator binds to one verified (`sub`, `azp`/`client_id`) pair, as `l9.actor-registry/global@1#<id>` and optionally `l9.surface-registry/global@1#<id>`. Optional; absent or `{}` binds nobody. A malformed binding, an actor equal to the client or the subject, or an `@clients` subject ⇒ the server refuses to start. |

Behaviour:

- **One endpoint.** Only `POST /mcp` is served. `/mcp/` answers `404` for
  every method and is not redirected, so the service has one resource string.
- **Challenge.** A `401` carries
  `WWW-Authenticate: Bearer realm="l9-graphite-memory", resource_metadata="https://memory.quantumaipartners.com/.well-known/oauth-protected-resource/mcp"`,
  plus `error="invalid_token"` when a credential was presented.
- **Metadata.** `GET /.well-known/oauth-protected-resource/mcp` is
  unauthenticated and returns the RFC 9728 document: `resource`,
  `authorization_servers` (the configured issuer) and
  `bearer_methods_supported`. The host-root well-known path is not served.
  A deployment must route this path to the server as well as `/mcp`.
- **Issuer keys.** Read from the `jwks_uri` of the issuer's
  `/.well-known/openid-configuration`, over `https`, without redirects,
  cached for 10 minutes. If they cannot be obtained the request gets `401`.
  No other credential is consulted in this mode.
- **Principal.** The token subject, with the namespaces of its grant,
  `auth_method` `oauth`, and the token's client id as `oauth_client_id`. It
  names an agent only when `L9_MEMORY_OAUTH_ACTORS_JSON` binds that exact
  (subject, client id) pair; then `agent_id` is the actor id and the server
  records a reference to the binding. A subject without a grant is
  authenticated and holds no namespace. Token scopes and other claims,
  including `agent_id` and `act`, grant nothing.
- **Writes.** Every tool that is not read-only is refused for an OAuth
  principal without a bound actor (`-32010`, `AuthorizationError`), because
  a subject is not an actor and a client id is never one (ADR-100). With a
  bound actor, writes go through ordinary admission and are attributed to
  that actor.
- **Explicit evidence.** Purpose-bound `consent` whose `subject_id` equals
  the token subject is explicit evidence the server adds itself, so an
  identity or preference write about the authenticated person can admit.
  Any other consent adds nothing; a caller's own `kind: explicit` stays a
  claim and is quarantined.
- **Probes.** `/healthz` and `/readyz` stay unauthenticated and do not depend
  on the issuer.

The operator tool `tools/assurance/oauth_pkce_receipt.py` produces the live
PKCE receipt for this mode. No receipt exists in this repository.

## 3. Refusals

All refusal bodies are `{"jsonrpc": "2.0", "error": {"code", "message", "data"?}}`
with **no** `id`. Credentials are never echoed.

| Condition | Status | JSON-RPC code |
|---|---|---|
| `Origin` present and not allowed | 403 | -32600 |
| credential-shaped URL query parameter | 400 | -32600 |
| missing / malformed / expired / over-ceiling / tampered / unknown-agent / other-actor credential (an unknown agent and a bad signature share one message) | 401 + `WWW-Authenticate: Bearer realm="l9-graphite-memory"[, error="invalid_token"]` | -32001 |
| OAuth mode: missing token, or wrong issuer, wrong audience, expired, not yet valid, disallowed algorithm, missing or unknown `kid`, bad signature, malformed token, issuer keys unavailable, token without an end user (client credentials) | 401 + `WWW-Authenticate: Bearer realm="l9-graphite-memory", resource_metadata="…"[, error="invalid_token"]` | -32001 |
| OAuth mode: any request to `/mcp/` | 404 | -32600 |
| `Content-Type` not `application/json` | 415 | -32600 |
| `Accept` lacks either media type | 406 | -32600 |
| body over 4 MiB (checked while streaming, chunked included) | 413 | -32600 |
| undecodable JSON (syntax, encoding, excessive nesting, oversized integers) | 400 | -32700 |
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
| Health and capabilities | Binds `memory-control-plane/v1` and package version from `l9-memory capabilities` | Same receipt plus additive `http_mcp_protocol_versions`, `remote_mcp_contract_version` | Yes, additive | Pin the validated release that carries `memory-remote-mcp/v1` (the Memory 3.0.0 target), not the candidate |
| MCP initialize | Stdio test sends `2024-11-05` and checks only that a version is returned | stdio unchanged (`2024-11-05`); HTTP answers `2025-11-25` or `2025-06-18` | Yes | An HTTP client must speak one of the HTTP revisions |
| `tools/list`, `tools/call` | Dotted names; Claude maps `.` to `_` | Identical definitions on both transports | Yes | None |
| Error semantics | Ungranted write: `-32001`/`-32010` or a `rejected` receipt | Same JSON-RPC codes; transport refusals add HTTP statuses | Yes | Handle `401` (re-mint) and `400`/`406`/`415` (client defect) |
| Transport policy | CANONICAL_LAW §8.5.4 and ADR-0031 seal agent HTTP; launcher is stdio only | Remote transport implemented in the candidate; not released or deployed | **No — consumer law** | A Cursor-Governance ADR is required before any adapter may select HTTP |

## 5. Not covered by this contract

- Deployment of a shared server, PostgreSQL as its canonical store, and TLS
  termination. The carrier that deploys one is described by
  `.l9/deployment.yaml` and owned by l9-deploy's contract, not by this one.
- An authorization server. The package is a resource server only (§2a); it
  issues no token, registers no client and proxies no authorization request.
  Token lifetime, revocation, scopes and who may obtain a token for the
  Memory audience are authorization-server settings.
- A proven OAuth deployment. §2a describes source behaviour and the hosted
  carrier pins it; the live PKCE receipt proves the tenant against a local
  server, not a deployed service.
- Audience binding of the agent assertion to one deployment. Use
  per-deployment keys.
- Admission of any running server. The classification is settled (ADR-094,
  2026-10-15): the topology claims the admitted hosted-Memory exception and
  declares the service's own runtime identity, never Constellation identity;
  service admission is still a separate target-class decision.
- In-window replay prevention (ADR-083, 2026-10-14).
- Administrator authority for bearer-mode token principals and the
  auth-disabled Tier-3 local principal; signed-agent grants carrying
  `is_admin` are refused at startup.
- MCP revision `2026-07-28`, which drops `initialize`: a client that speaks
  only that revision is refused with `400`. The served revisions were chosen
  from the specification, not from probes of installed Cursor or Claude Code
  builds; such probes are consumer proof.

## 6. Memory-owned client (2026-10-16)

The package ships the client side of this contract. Decision:
[ADR-082, 2026-10-16 amendment](adr/ADR-082-consumer-control-plane-transport-parity.md).

| Surface | Use |
|---|---|
| `l9_graphite_memory.remote_client.RemoteMemoryClient` | Python consumers. Typed lifecycle methods return the same receipt models as `MemoryService`; `write_agent` and `write_governed` are included. Credentials are fixed `AgentCredentials` or a provider called per request. |
| `l9-memory --remote-url URL <command>` or `L9_MEMORY_REMOTE_URL=URL l9-memory <command>` | Hooks and operators. Covers `health`, `capabilities`, `hydrate`, `search`, `get`, `write` (as `memory.ingest`), `ingest-governed-candidate`, `close`, `conflicts`, `phase-lock` and `verify-phase-lock`, plus local `resolve`. Same argv, stdout receipt and exit codes as the local command. |

Client inputs, all on the consumer side:

| Variable | Content |
|---|---|
| `L9_MEMORY_REMOTE_URL` | `https://host[/path]`; `/mcp` is appended when absent. `http://` is accepted only for a loopback host. A URL with user information, a query or a fragment is refused. |
| `L9_MEMORY_AGENT_ASSERTION` | the minted agent assertion, the same value the stdio door reads |
| `L9_MEMORY_IDENTITY_ASSERTION_JSON` | the sealed identity assertion as JSON; the client base64url-encodes it |
| `L9_MEMORY_IDENTITY_ASSERTION_HMAC` | its HMAC |
| `L9_MEMORY_REMOTE_TIMEOUT_SECONDS` | per-request timeout, default `30` |

Behaviour:

- The client binds the server before the first operation. It negotiates the
  revision, sends `notifications/initialized`, and requires
  `memory.capabilities` to report `memory-control-plane/v1`,
  `memory-remote-mcp/v1`, the negotiated revision and every operation above.
- An assertion within 5 s of expiry is refused without a request.
- Redirects are refused.
- A failure exits `1` with `{"error", "message", "remote": {"failure_kind",
  "http_status", "rpc_code", "remote_type"}}` on stderr. `error` is the type
  a local run raises for the same outcome, so type-based classification
  carries over.
  - **Failure kinds:** `configuration`, `credential_expired`, `unreachable`,
    `timeout`, `authentication`, `authorization`, `protocol`,
    `contract_mismatch`, `invalid_request`, `tool_failure` and
    `unsupported_remotely`.
- With a remote URL selected, no local store is opened, and every other
  command is refused (`unsupported_remotely`), including `distill` and
  `bootstrap`. Those tools require administrator authority that this
  contract never grants a signed agent, and they read server-side paths.
- `memory.search` has no `token_budget` and `memory.hydrate` has no
  `valid_at`. A request that sets either is refused, never silently
  narrowed.

Consumer adoption is outside this document. That covers selecting the remote
URL, provisioning keys and grants, and refreshing assertions, which is
consumer law in Cursor-Governance, where agent HTTP is sealed today.
