# ADR-102: OAuth Resource Server for the Streamable HTTP Transport

**Date:** 2026-11-13
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** the HTTP transport of `l9-memory-server` in `Quantum-L9/l9-graphiti-memory`

This record implements part of ADR-100. It does not change ADR-100, and
identity meanings stay in `Quantum-L9/.github`.

## Status

Proposed

The author of this change does not accept its own decision record. Merging
this record on the default branch by the decision owner accepts it; the index
status changes in that same merge.

## Context

ADR-100 makes the hosted Memory service one OAuth-protected MCP Streamable
HTTP endpoint with Auth0 as the issuer and
`https://memory.quantumaipartners.com/mcp` as the resource. Until this change
the source had no code that could serve it: `http_auth_mode` admitted only
`bearer` and `signed-agent`, nothing consumed `MEMORY_RESOURCE_IDENTIFIER`,
and nothing produced a principal with `auth_method="oauth"`. The hosted
carrier therefore refuses to start on every mode.

Issue #108 names two start conditions for pinning OAuth in the carrier:
resource-server code on the default branch, and a live PKCE receipt. This
record is the first, and adds the tool that produces the second.

The transport serves MCP revisions `2025-11-25` and `2025-06-18`. The
`2025-11-25` authorization specification requires an MCP server to implement
OAuth 2.0 Protected Resource Metadata (RFC 9728) with at least one
`authorization_servers` entry, to offer either the `resource_metadata`
challenge parameter or the well-known URI, to validate that a token was
issued for it as the audience (RFC 8707), and to answer an invalid or expired
token with `401`. It recommends a canonical server URI without a trailing
slash.

## Decision

**Mode.** `http_auth_mode` gains the value `oauth`
(`L9_MEMORY_HTTP_AUTH_MODE=oauth`). The literal has one owner,
`contracts.identity.OAUTH_AUTH_METHOD`, which is also the `auth_method` of
the principal the mode produces. `bearer` and `signed-agent` are unchanged.

**Issuer.** The issuer is configuration: `L9_MEMORY_HTTP_OAUTH_ISSUER`
(`http_oauth_issuer`). It has no default and is never derived. It is compared
with the token's `iss` claim character for character and is not normalised;
an Auth0 issuer ends with a slash. OAuth mode refuses to start when the
issuer is unset, is not an `https` URL, or carries user information, a query
or a fragment, and when `http_auth_required` is false.

**Token validation.** Each request carries `Authorization: Bearer <JWT>`. The
server requires, in this order:

1. a JWT header whose `alg` is on the allow-list `RS256`, `PS256`, `ES256`.
   `none` and every HMAC algorithm are refused before any key is read;
2. a `kid`;
3. a verification key with that `kid` published by the configured issuer;
4. a valid signature under that key, with the key's own algorithm and an RSA
   key of at least 2048 bits;
5. `iss` equal to the configured issuer, `aud` containing
   `MEMORY_RESOURCE_IDENTIFIER`, `exp` and `sub` present, and `exp`, `nbf`
   and `iat` within 30 seconds of the server clock.

A key carried in the token (`jwk`) or located by it (`jku`, `x5u`) is never
used. Scopes, permissions, roles and any other claim are not read.

**Issuer keys.** The key set location is the `jwks_uri` of the issuer's
`/.well-known/openid-configuration`, which must itself name the configured
issuer and an `https` location. Reads are `https` only, follow no redirect,
time out after 5 seconds and are capped at 256 KiB. Symmetric keys, keys with
private members, keys not marked for signing and duplicated key ids are not
used. Keys are cached for 10 minutes. A token naming an unknown `kid` causes
at most one re-read per 60 seconds. After a failed read the issuer is left
alone for 5 seconds. When keys cannot be obtained, or the cache has expired
and cannot be refreshed, the request is refused with `401`. Nothing is read
at startup, and `/readyz` does not depend on the issuer.

**No other door.** In OAuth mode a refusal is final. The signed-agent
verifier and the static bearer map are not consulted, whatever is configured.

**Principal.** The principal is the verified subject: `principal_id` is the
token's `sub`, `auth_method` is `oauth`, and `agent_id` and `user_id` are
unset. The client id in the token is not copied onto the principal. Tenant,
organization and workspace come from `L9_MEMORY_LOCAL_*_ID`, as for a signed
agent. `is_admin` is never set.

**Grants.** Namespaces come from server-side configuration,
`L9_MEMORY_OAUTH_GRANTS_JSON`: a JSON object mapping a token subject to
`roles`, `read_namespaces`, `write_namespaces` and `promote_namespaces`. The
variable is required in OAuth mode; `{}` grants nobody. A malformed grant or
a grant with `is_admin` stops startup. A subject without a grant is
authenticated and holds no namespace. `MemoryService` remains the only
authorization decision.

**Actor.** Nothing here binds an actor. `MCPToolApplication.call` still
refuses every tool that is not on the read-only allow-list for an OAuth
principal, so an OAuth caller can read what its grant allows and can write
nothing. Admitting a write with a proven actor is issue #108 section 3.

**One resource string.** The canonical resource is
`MEMORY_RESOURCE_IDENTIFIER`, without a trailing slash. In OAuth mode the
server serves `POST /mcp` only. `/mcp/` answers `404` with a message naming
the canonical endpoint, for every method, and is not redirected. The other
modes keep serving both paths.

**Discovery.** In OAuth mode a `401` carries
`WWW-Authenticate: Bearer realm="l9-graphite-memory", resource_metadata="https://memory.quantumaipartners.com/.well-known/oauth-protected-resource/mcp"`,
followed by `error="invalid_token"` when a credential was presented. The same
document is served unauthenticated at
`GET /.well-known/oauth-protected-resource/mcp`: `resource`,
`authorization_servers` with the configured issuer, and
`bearer_methods_supported: ["header"]`. The host-root well-known path is not
served. No `scope` is challenged because the server defines no scope.

**Contract version.** `REMOTE_MCP_CONTRACT_VERSION` stays
`memory-remote-mcp/v1`. The mode is additive: the v1 carriers, status codes
and negotiation are unchanged, and the shipped `RemoteMemoryClient` binds v1.
The version changes when a hosted contract is admitted, not here.

**Dependencies.** `PyJWT` and `cryptography` join the `server` and `all`
extras. They are imported only when OAuth mode starts.

**PKCE receipt tool.** `tools/assurance/oauth_pkce_receipt.py` runs
authorization code with PKCE as a public client over a loopback redirect,
names the resource with the RFC 8707 `resource` parameter on both requests,
and writes a receipt of digests and claim metadata. It checks that the Memory
endpoint refuses an unauthenticated request, that the token is audience-bound
and admitted, that an altered token is refused, and that a mismatched
resource is refused by the authorization server or by the resource server.

**What this record does not do.** It does not pin OAuth in `Dockerfile` or
`.l9/deployment.yaml`; the carrier still refuses to start. It contains no
live PKCE receipt, and no test fixture here is one. It does not remove the
stdio server, the signed-agent door, the bearer mode or SQLite. It does not
name the issuer domain or a client id.

## Alternatives Considered

### Option A: Use the JWT library's key-set client

- Pros: less code
- Cons: it re-reads the key set for every unknown `kid` with no interval, so
  invented key ids become requests to the issuer; it follows redirects

### Option B: Take namespaces from token claims (scopes or permissions)

- Pros: no server-side grant map; the issuer administers access
- Cons: it defines a claim-to-namespace mapping no accepted record specifies,
  and moves an authorization input out of server-side configuration

### Option C: Keep serving `/mcp/` and accept either audience

- Pros: a client configured with a trailing slash keeps working
- Cons: two resource strings for one service; RFC 9728 requires a client to
  reject metadata whose `resource` differs from the URL it used

### Option D: A validator owned by this package, grants keyed by subject, one endpoint

- Pros: bounded key retrieval, the existing grant pattern, one audience
- Cons: more code to own; the grant map is operator-maintained

## Rejected Alternatives

Option A is rejected for its unbounded refresh. Option B is rejected until a
record defines such a mapping. Option C is rejected: one canonical resource
string is what issue #108 asks for. Option D is the decision.

## Invariants

- OAuth mode validates every request and consults no other credential.
- Only an asymmetric signature by a key the configured issuer publishes
  verifies a token.
- `iss` equals the configured issuer exactly. `aud` contains
  `MEMORY_RESOURCE_IDENTIFIER`.
- Unobtainable or expired issuer keys refuse the request.
- An OAuth principal names no agent and no user, and is never an
  administrator.
- A token claim never grants a namespace, a role or a tenant.
- OAuth mode serves one MCP endpoint path.
- `bearer` and `signed-agent` behave as before this record.
- The live PKCE receipt is still owed. This record is not that receipt.
- The hosted carrier is not pinned by this change.

## Consequences

Issue #108 start condition 1 can be met by merging this change. Start
condition 2 needs an operator to run the receipt tool against the real
tenant.

The deployment in front of the server must route
`/.well-known/oauth-protected-resource/mcp` to Memory as well as `/mcp`.
That route belongs to the carrier and to l9-deploy, not to this change.

The hosted image grows by `PyJWT` and `cryptography` once it is rebuilt.

Memory availability in OAuth mode depends on the issuer's key set at least
once every 10 minutes. A key the issuer withdraws stops verifying within
that time.

The principal's `principal_id` is the token subject. `MCPToolApplication`
passes `principal_id` to `oauth_actor_ref` as the client id. With `agent_id`
unset that comparison is never reached, so the refusal holds; section 3 of
issue #108 must carry the client id explicitly when it binds an actor.

## Security Impact

The trust boundary of OAuth mode is the issuer's signing keys, read over TLS
from a location the issuer's own metadata names. Algorithm confusion,
unsigned tokens, token-supplied keys, a wrong issuer, a wrong audience and an
expired token are each refused and covered by tests.

A `401` is returned when issuer keys are unavailable, so a client may start a
new authorization during an issuer outage. That is preferred to serving a
request that could not be validated.

Any subject the issuer authenticates for the Memory audience can call
`initialize`, `tools/list`, `memory.health` and `memory.capabilities`. It can
read nothing without a grant. Restricting who may obtain a token for the
audience is an authorization-server setting.

The server does not limit token lifetime, does not check revocation and does
not read scopes. Refusals never repeat the token. Subjects appear in errors
and logs as a fingerprint.

Authorization-server behaviour the receipt tool relies on. Each is an
assumption about the tenant until the receipt exists:

- The `resource` parameter selects the API audience. Auth0 documents this for
  a tenant whose resource parameter profile is `compatibility`; with the
  `audience` profile the parameter is not used for that purpose.
- An API is registered with the identifier
  `https://memory.quantumaipartners.com/mcp` and signs with an allow-listed
  asymmetric algorithm.
- The public client has no secret, allows the authorization-code grant, and
  lists the tool's loopback redirect URI exactly.
- A request for an unregistered resource is answered with an error on the
  redirect. If the server shows an error page instead, the mismatch check is
  recorded as not evaluated and the receipt fails.
- No default audience is set to the Memory API. If one is, the mismatch check
  fails, correctly.

## Migration Impact

No runtime, schema or client migration is executed. No existing deployment
changes behaviour: the mode is opt-in and the carrier does not select it.

Contract impact: one additive `http_auth_mode` value, two server-side
variables, one unauthenticated metadata route in OAuth mode, and `/mcp/`
refused in OAuth mode. Wiring path: `config/models.py`, `config/loader.py`,
`authz/oauth.py`, `server.create_http_app`, `contracts/identity.py`,
`mcp_tools.py`, `pyproject.toml`, `uv.lock`.

## Validation Requirements

- `tests/unit/test_oauth_resource_server.py`: token, key-set, issuer, grant
  and metadata rules.
- `tests/integration/test_remote_mcp_oauth.py`: the same refusals as `401`
  over a real socket, no fallback, one endpoint, startup refusals, and the
  unchanged modes.
- `tests/regression/test_oauth_pkce_receipt.py`: the receipt tool against an
  issuer in the test process, including the cases that must fail the receipt.
- `python tools/assurance/validate_adrs.py` reports a contiguous ledger
  through ADR-102.

None of these is evidence about the live tenant.

## Rollback Conditions

Setting `L9_MEMORY_HTTP_AUTH_MODE` to another value disables the mode.
Reverting this change removes it; no stored data depends on it. A defect in
validation that admits a token it should refuse is a reason to revert before
any carrier pins the mode.

## Supersedes / Superseded By

Supersedes none. Implements the *Credentials* and *Identity* provisions of
ADR-100 for the package's HTTP transport. Replaces the statement in
`docs/REMOTE_MCP_CONTRACT.md` section 5 that RFC 9728 discovery is not
covered. Superseded by none.
