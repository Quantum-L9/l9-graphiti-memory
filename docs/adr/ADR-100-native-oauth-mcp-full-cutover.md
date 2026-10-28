# ADR-100: Native OAuth MCP Full Cutover

**Date:** 2026-10-27
**Decision owner:** Quantum-L9 memory architecture, from the operator decision of 2026-10-27
**Applies to:** the hosted Memory service in `Quantum-L9/l9-graphiti-memory`

Identity meanings stay in `Quantum-L9/.github`. This record does not edit that
repository, Cursor-Governance, or `l9-deploy`.

## Status

Accepted

## Context

The hosted Memory contract still admits a Memory stdio MCP door, a
signed-agent HMAC HTTP door, and a static bearer service credential.

- ADR-038 keeps stdio MCP as a supported surface and rolls HTTP back by
  retaining stdio. Its later amendments name Streamable HTTP as a target and
  leave stdio supported.
- ADR-064 binds Cursor instantiation to a local stdio `mcp.json` entry and a
  probe of that argv. A passing probe is not proof of a remote client.
- ADR-082 requires lifecycle parity onto `MemoryService`. Its 2026-10-16
  amendment carries the remote consumer as the signed agent, with the HMAC
  assertion and no local fallback.
- ADR-083 makes the signed Tier-2 HMAC door and the auth-disabled stdio
  principal the agent trust boundary. A later amendment selects that same HMAC
  door for HTTP and says no OAuth profile is adopted.
- ADR-098 is the signed-agent HTTP identity. Static bearer remains a mode.
  stdio is unchanged. OAuth 2.1 protected-resource metadata is a rejected
  alternative in that record.

The operator decision of 2026-10-27 is a full cutover with no historical
transport compatibility. The hosted service is one native MCP Streamable HTTP
endpoint protected by Auth0, with one new PostgreSQL 16 canonical store. A
hidden stdio, HMAC, or bearer fallback is not a compatibility mode. Global
identity authority stays in `Quantum-L9/.github`. The ten invariants in
`AGENTS.md` stay in force. This change records that decision. It does not
delete the old doors, retarget PR #101, admit a release, or prove the Auth0
tenant.

## Decision

The hosted Memory service is one OAuth-protected native MCP Streamable HTTP
service. Memory stdio, signed-agent HMAC, and static bearer are not hosted
doors and are not fallbacks.

**Transport.** Remote agents reach `MemoryService` only through native MCP
Streamable HTTP. The package does not keep a Memory stdio door as a production
path or as a rollback of the hosted service. The operator CLI remains an
operator interface. It is not the agent MCP door. Outbound Graphiti HTTP is a
projection client. It is not an inbound Memory stdio compatibility route, and
this record neither enables nor retires it.

**Credentials.** The hosted credential is an Auth0 access token for one Memory
resource (RFC 8707 `resource`, Auth0 audience). The resource identifier is
`https://memory.quantumaipartners.com/mcp`. The host is the existing Memory
route. The path is the native MCP endpoint. The Graphiti route on that host
is not this identifier. The Auth0 issuer domain and the public client ids are
not named here. The issuer is Auth0. This repository does not stand up a second
authorization server or an OAuth proxy.
Signed-agent HMAC headers, `L9-Identity-Assertion` HMAC, and a static bearer
mapped to a configured principal are not hosted credentials. Resource-server
code is not treated as proven until a live PKCE authorization for that
resource returns an audience-bound token and a mismatched resource is refused.
This record does not contain that receipt.

**Identity.** A verified OAuth principal is not an actor and not a surface.
Product, release, runtime, actor, surface, and constellation applicability
stay distinct. Their meanings stay in `Quantum-L9/.github`. Unknown stays
Unknown. Consequential actor attribution fails closed when the actor is
unproved. Constellation identity is not applicable to this hosted Dependency.
This record does not define the assertion wire format and does not amend the
global registries.

**Local instantiation.** `AGENTS.md` invariants 1 through 10 are unchanged.
Invariants 9 and 10 still govern any local client entry this repository
writes through `client_config`. They do not make a stdio probe proof of the
hosted client. This record makes no hosted instantiation claim. Hosted
Cursor and Claude connections are host-managed OAuth, owned by those clients,
and are outside this pull request.

**Store.** The hosted canonical store is one new, empty PostgreSQL 16
database. SQLite is not a hosted fallback. Historical Memory rows are not
imported. Retirement of the old C1 SQLite store stays the narrow 2026-10-26
authorization and is not performed here. Graphiti, Neo4j, and Cognitive
Runtime are outside this decision.

**What this record does not do.** Paths that still implement the superseded
doors stay in the tree until a later change removes them. Until that change
they are legacy code, not the hosted contract. PR #101 still pins signed-agent
mode and is not retargeted here.

## Alternatives Considered

### Option A: Keep stdio, HMAC, and bearer as hidden fallbacks

- Pros: existing clients keep working during the cutover
- Cons: the operator forbade historical compatibility and a second door that
  can reopen the retired trust boundary

### Option B: Run a second authorization server in this repository or in Cursor-Governance

- Pros: the resource parameter could be rewritten before it reaches Auth0
- Cons: a second issuer splits audience, revocation, and client registration,
  and Cursor-Governance is a consumer, not an authorization server

### Option C: OAuth-only native Streamable HTTP, recorded now and removed in a later change

- Pros: the accepted contract stops requiring the old doors before code
  deletion, and the Auth0 proof stays an explicit gate
- Cons: the tree still contains the old doors until the removal change, so
  readers must use this record rather than the presence of code

## Rejected Alternatives

Option A is rejected. A compatibility flag that can serve stdio, HMAC, or
static bearer is a second hosted door. Option B is rejected. Auth0 is the
selected issuer, and this repository does not implement another one.

## Invariants

- No accepted hosted contract requires a live Memory stdio door.
- No accepted hosted contract requires signed-agent HMAC or a static bearer.
- The hosted issuer is Auth0. There is no second authorization server.
- A live PKCE audience receipt is still required before the resource server
  is treated as proven. This ADR is not that receipt.
- `AGENTS.md` invariants 1 through 10 are unchanged.
- This file does not amend `Quantum-L9/.github` identity meanings.
- OAuth subject and client identity do not prove actor or surface.
- SQLite is not a hosted canonical store and is not a rollback of PostgreSQL.

## Consequences

The five predecessor ADRs remain the historical record of the decisions they
made. Their stdio, signed-agent, and static-bearer provisions no longer bind
the hosted service. Streamable HTTP, chosen in ADR-098, remains the remote
MCP transport and loses the signed-agent identity that ADR-098 attached to it.

`MemoryService` stays the only canonical control plane. Caller identity stays
server-derived. Release admission, C1 cutover, client cutover, and deletion of
the old doors are separate changes. PR #101 cannot be deployed as the hosted
service until its signed-agent profile is replaced.

## Security Impact

The hosted trust boundary moves from a reusable HMAC assertion and a static
bearer to an audience-bound Auth0 access token. Until the live PKCE receipt
exists, no deployment may treat a local JWT test fixture as that proof. A
token with the wrong resource, issuer, or audience is a failed authentication.
An OAuth user or public client id is not an authorization to write as an
agent actor.

Removing the HMAC door from the contract before deleting the code does not
by itself close the old listener. The old listener stays a deployment
concern for the later cutover, not a permission granted by this ADR.

## Migration Impact

No runtime, schema, or client migration is executed in this change. Later
work removes the Memory stdio server, the signed-agent HTTP door, the static
bearer mode, the SQLite hosted fallback, and the legacy write queue, and
retargets the open carrier. Consumers move to host-native OAuth. No historical
canonical rows are migrated. Generated client config still must not persist
secrets.

Contract impact: hosted transport and HTTP identity only. Wiring path: this
ADR, the index, and the supersession pointers in ADR-038, ADR-064, ADR-082,
ADR-083, and ADR-098. Global identity wiring stays in `.github`.

## Validation Requirements

- `python tools/assurance/validate_adrs.py` reports a contiguous ledger
  through ADR-100.
- `tests/regression/test_adr_100_oauth_cutover.py` checks that this ADR names
  the five predecessors and that each predecessor points back here.
- The test does not claim the old doors are unreachable. That proof belongs
  to the removal change.

## Rollback Conditions

Restoring Memory stdio, signed-agent HMAC, or static bearer as a hosted door
requires a new ADR that supersedes this one. Reverting this text is the
rollback of the decision record. A future PostgreSQL deployment does not roll
back to SQLite or to the old MCP door.

## Supersedes / Superseded By

Supersedes, for the hosted Memory service, the stdio and signed-agent
provisions of:

- ADR-038, the requirement to retain a Memory stdio door and the rollback
  that disables HTTP while keeping stdio
- ADR-064, the requirement that the hosted Cursor client be a local stdio
  `mcp.json` entry proved by `client cursor verify`
- ADR-082, the 2026-10-16 remote-consumer identity that carries signed-agent
  HMAC
- ADR-083, the signed-agent HMAC door, static bearer, and auth-disabled HTTP
  principal as the hosted agent credential
- ADR-098, signed-agent HTTP identity, static bearer mode, and the obligation
  to leave stdio unchanged

ADR-098's choice of MCP Streamable HTTP as the remote transport is retained.
Server-derived authorization, lifecycle parity onto `MemoryService`, and the
atomic local `client_config` rules are retained. Superseded by none.
