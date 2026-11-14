<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: SECURITY.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-10-14
/L9_META -->

# Security

## Threat model

The system defends against:

- caller identity spoofing
- cross-tenant and cross-namespace access
- duplicate writes (idempotency) and replayed writes; credential replay is bounded by expiry only (see "Credential replay")
- credential persistence or logging
- prompt-injection-like content entering active retrieval without review
- PII leakage
- direct-store or provider write bypasses
- silent backend failure
- stale or malicious schema versions

## Controls

- server-side MemoryPrincipal
- separate read, write, promote, archive, and admin claims
- tenant predicates in every store operation
- explicit authentication for HTTP; unauthenticated HTTP refused on a non-loopback bind
- repository-scoped local/stdio claims with administrator authority disabled by default
- deterministic normalization and digests
- admission quarantine
- PII redaction with original source digest retention
- schema upcasting and validation
- atomic receipts and outbox
- CI bypass, config-drift, ADR, and wiring checks

## Remote HTTP: Memory 3.0.0 trust boundary

The target is one `MemoryService` hosted on the operator's C1 environment and
reached by multiple agents over native MCP Streamable HTTP protected by Auth0
OAuth (ADR-100, accepted 2026-10-27). It is not deployed. The released
2.5.0/2.6.0 HTTP server does not meet this boundary and must not be exposed to
remote agents.

### Hosted door (ADR-100)

- The hosted credential is an Auth0 access token for the one Memory resource
  (RFC 8707 `resource`, Auth0 audience); the resource identifier is
  `MEMORY_RESOURCE_IDENTIFIER` in `src/l9_graphite_memory/version.py`. A token
  with the wrong resource, issuer or audience is a failed authentication.
- Signed-agent HMAC, static bearer and Memory stdio are not hosted doors and
  are not fallbacks. Restoring any of them as a hosted door needs a new ADR.
- A verified OAuth principal is not an actor and not a surface; consequential
  actor attribution fails closed when the actor is unproved.
- Not implemented yet: `main` (source version 3.0.0, no `v3.0.0` tag, not a
  release) has the Streamable HTTP transport (ADR-098) but `http_auth_mode`
  admits only `bearer` and `signed-agent`, and no live PKCE receipt exists.
  The hosted carrier image therefore refuses every auth mode and does not
  start (`Dockerfile`, `.l9/deployment.yaml`, issue #108). Nothing in this
  document claims that OAuth works.

The subsections below through "Transport and default-deny" describe the
`signed-agent` and `bearer` code that is still in the tree. Since ADR-100 it
is legacy code, not the hosted contract; its presence does not close or
authorize any listener.

### Signed-agent identity chain (legacy code, not a hosted door)

1. Each agent holds its own securely provisioned signing key.
2. On every request it sends a short-lived signed agent assertion
   (`Authorization: Bearer`) and the sealed `l9.identity-assertion/v1` object
   with its HMAC under the same key.
3. The server verifies signature, expiry, lifetime ceiling, identity digest,
   HMAC, `resolved` result, product, actor equal to the agent, and pinned
   provenance, on that request alone; there is no session or cached
   principal.
4. The server takes the principal's roles, namespaces and flags only from its
   own grant map, and tenant, organization and workspace from its own
   settings. No header, query, body, MCP `_meta` or assertion field adds a
   claim.
5. `MemoryService` enforces tenant and namespace authorization on the
   operation itself (ADR-006); a requested namespace is an address, never a
   claim.
6. Receipts and records carry the authenticated agent and record provenance.

### Key separation

One key per agent, never shared between independently authorized agents.
Credentials are not audience-bound, so each deployment needs its own keys: a
key shared with another deployment or with a local stdio door makes its
credentials valid there too. Keys are not provisioned by this repository.
Per-agent keys and a grant map are inputs of `signed-agent` mode only; since
ADR-100 they are not prerequisites of the hosted 3.0.0 deployment.

### Credential replay

A signed agent credential is reusable until it expires. There is no nonce or
`jti` ledger, so it is **not** single-use, and replay within the validity
window is **not** prevented. Exposure is bounded by expiry checked on every
request, the lifetime ceiling (`http_agent_assertion_max_ttl_seconds`,
default 3600, plus 60 s skew), deployment-specific keys, and TLS on every hop
that carries the credential (ADR-083 and ADR-098, 2026-10-14).

### Administrator authority

In `signed-agent` mode ordinary remote agent grants do not set `is_admin` and
administrative operations are separately governed. The 3.0.0 source enforces it for signed agents: a grant
with `is_admin` stops the server at startup in `signed-agent` mode and on
auth-disabled loopback HTTP serving the agent door (ADR-098;
`test_remote_mcp_http.py`, `test_installed_wheel_lifecycle.py`). Bearer-mode
token principals can still carry `is_admin` and `is_global_admin`, so bearer
mode is not for agents. The human door is unreachable over HTTP.
Auth-disabled loopback serves the signed agent door when
`L9_MEMORY_AGENTS_DOOR_SECRET` is set (never as administrator), otherwise the
Tier-3 local principal, which is an administrator when
`L9_MEMORY_LOCAL_IS_ADMIN` or `L9_MEMORY_LOCAL_IS_GLOBAL_ADMIN` is true.

### Transport and default-deny

- TLS terminates at a trusted reverse proxy; the service listens where only
  that proxy reaches it. The server has no in-process TLS.
- A request without valid credentials gets `401`; an unknown agent and a bad
  signature get the same answer, so agent ids cannot be enumerated. There is
  no anonymous or local-operator fallback on an authenticated server, and
  `signed-agent` mode with authentication disabled refuses to start.
- A present `Origin` outside `http_allowed_origins` gets `403`; credentials in
  a URL get `400` and are never echoed.
- `/healthz`, `/readyz` and FastAPI's default `/docs`, `/redoc` and
  `/openapi.json` are unauthenticated in every version, including the
  3.0.0 source. Their exposure beyond the host is a deployment decision that has
  not been made.

### Gaps on 2.5.0 and 2.6.0

The HTTP server there authenticates only by static bearer tokens (not an
agent identity, and able to carry administrator flags), has no `Origin`
validation, protocol negotiation or `WWW-Authenticate` challenge, and with
authentication disabled serves the stdio principal on loopback, which is the
administrator when `L9_MEMORY_HUMAN_DOOR_SECRET` is set. Use it on loopback
for development only.

## Secret handling

Generated MCP config files contain only executable and argument data. Tokens, Zep keys, Graphiti credentials, and Infisical machine identity values remain in the runtime environment or external secret manager.

For the hosted 3.0.0 deployment the runtime secret this source defines is the PostgreSQL connection string (`L9_MEMORY_POSTGRES_DSN`), which the carrier requires. The Auth0 issuer and audience settings of the OAuth resource server are not defined in this source yet (issue #108). The agent signing-key map (`L9_MEMORY_AGENT_SIGNING_KEYS_JSON`) and the grant map (`L9_MEMORY_AGENT_GRANTS_JSON`, not secret in content but integrity-critical) are inputs of the legacy `signed-agent` mode, not of the hosted service (ADR-100). Secrets are delivered through the operator's existing secret path, owned by the deployment campaign; this repository defines the inputs and holds none of the values.

## Reporting

Report vulnerabilities privately to the repository owner. Do not open a public issue containing credentials, personal memory data, tenant identifiers, or exploit details.

## Security non-goals

The default SQLite adapter does not provide database-at-rest encryption. Operators needing encrypted storage must use encrypted volumes or implement a conforming encrypted RecordStore adapter.
