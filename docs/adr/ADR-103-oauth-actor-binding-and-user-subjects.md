# ADR-103: OAuth Actor Binding, Server-Verified Consent, and User-Only Subjects

**Date:** 2026-11-13
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** the OAuth door (`http_auth_mode=oauth`) of `l9-memory-server` in `Quantum-L9/l9-graphiti-memory`

This record implements issue #108 section 3 on top of ADR-102. It does not
change ADR-100 or ADR-102, and identity meanings stay in `Quantum-L9/.github`.

## Status

Proposed

The author of this change does not accept its own decision record. Merging
this record on the default branch by the decision owner accepts it; the index
status changes in that same merge.

## Context

ADR-102 gave the HTTP transport an OAuth resource-server mode. A validated
access token yields a principal whose `principal_id` is the token subject and
whose namespaces come from `L9_MEMORY_OAUTH_GRANTS_JSON`. ADR-100 *Identity*
binds that an OAuth subject or public client id proves neither actor nor
surface, and that a client id is never an actor.

So every consequential tool was refused over OAuth: `MCPToolApplication.call`
passed `evidence_refs=()` to `oauth_actor_ref`, and since commit `87d8460`
that gate covers every handler not on the read-only allowlist. The hosted
store is meant to be shared and written by several agents (Claude Code,
Cursor and others), each under its own identity, which it could not be.

Four further gaps were recorded in issue #108 section 3 and in this campaign:

1. `MCPToolApplication.call` passed `principal_id` (now the subject) as the
   client id, so the client id the token actually names was nowhere.
2. `HostedIdentityCoordinates` and `hosted_coordinates_from_oauth` had no
   caller in `src/`.
3. Over MCP the server decides explicit evidence, never the caller (operator
   decision 2026-11-02, issue #104). Writes that need explicit evidence
   (identity, preference) therefore always quarantined or were rejected over
   OAuth.
4. A token obtained with the client-credentials grant has no end user, yet
   with a valid issuer, audience and signature it was admitted as a principal
   (operator-approved requirement 2026-11-13: such tokens must be refused).

Auth0 documents (access-token profiles; client-credentials and agent-as-
principal pages) that a client-credentials token carries `gty:
"client-credentials"` in the Auth0 profile, a subject of `<client id>@clients`
by default, the plain client id or an agent id (with `sub_profile:
"ai_agent"`) when agent subject claims are enabled, and the client id in
`azp` (Auth0 profile) or `client_id` (RFC 9068 profile). RFC 9068 section 2.2
makes the client the subject when no resource owner is involved.

## Decision

### Actor evidence is an operator binding for a verified (subject, client) pair

A new optional server-side variable, `L9_MEMORY_OAUTH_ACTORS_JSON`, maps a
verified token subject and a verified client id to one actor and, optionally,
one surface:

```json
{
  "<sub>": {
    "<azp or client_id>": {
      "actor_ref": "l9.actor-registry/global@1#<actor-id>",
      "surface_ref": "l9.surface-registry/global@1#<surface-id>"
    }
  }
}
```

- The token proves the subject and the client. The operator, in server-side
  configuration, states which actor that person runs through that client.
  The client id selects among one subject's bindings and resolves nothing on
  its own; the same client under another subject, or the same subject under
  another client, has no actor.
- Coordinates use the organization's canonical prefixes. An `actor_ref`
  whose fragment equals the client id or the subject, a subject ending in
  `@clients`, an unknown field, or a malformed coordinate stops the server at
  startup, naming the subject and client only by fingerprint.
- When a binding matches, the resource server sets `agent_id` to the actor
  fragment (the spelling the signed-agent door already uses), `surface_ref`,
  and one server-built `actor_evidence_refs` entry naming the variable and a
  digest of the binding and the pair it was declared for. Nothing in a
  request can set these: the existing refusal of `actor`, `actor_identity`,
  `surface`, `surface_identity` and `client_id` tool arguments stays, and
  token claims such as `agent_id` or `act` are ignored.
- Absent or `{}`, no pair has an actor: reads work and every consequential
  tool is refused with `AuthorizationError` (`-32010`), exactly as before.
- The variable is orthogonal to `L9_MEMORY_OAUTH_GRANTS_JSON`: grants decide
  namespaces, bindings decide attribution. A binding gives no namespace and a
  grant gives no actor.

### The client id is carried explicitly

`MemoryPrincipal` gains three optional fields, set only by the OAuth door:
`oauth_client_id` (from `azp`, else `client_id`), `actor_evidence_refs` and
`surface_ref`. Their defaults (`None`, `()`, `None`) leave every bearer,
signed-agent, stdio and local principal unchanged.

### Hosted coordinates are the gate's source

`MCPToolApplication.call` builds the principal's hosted coordinates with
`hosted_coordinates_from_oauth` (through `oauth_hosted_coordinates`) and
refuses a consequential tool when their `actor_ref` is null. That function
already refused an actor equal to, or evidenced only by, the client id;
`oauth_actor_ref` now also refuses an actor whose fragment equals the client
id.

### Consent from the verified subject is server-verified explicit evidence

On the OAuth door, when a write carries purpose-bound consent whose
`subject_id` equals the token's verified subject and the principal has a
bound actor, the server appends one `EvidenceRef(kind=explicit)` whose
`source_id` is the principal's audit subject. Admission is unchanged: it
still requires the consent to permit the namespace, class, assertion subject,
purpose and validity time. Consent naming anyone else adds nothing, so a
caller's own `kind=explicit` claim stays a claim and quarantines; other doors
add nothing.

### Tokens without an end user are refused

After signature and claim validation, a token is refused with `401` when any
of: a `gty` or `grant_type` claim names client credentials; the subject ends
in `@clients`; the subject equals the `azp` or `client_id` the token names; a
`sub_profile` claim is present and is not `user`. The check reads claim
semantics Auth0 and RFC 9068 define, not any tenant's names.

The remote MCP contract version (`memory-remote-mcp/v1`) and the admission
contract are unchanged.

## Alternatives Considered

- **Actor fields inside each `L9_MEMORY_OAUTH_GRANTS_JSON` entry.** One file,
  but a grant is documented as naming no principal and no agent, and keying
  by subject alone would let one actor be claimed through any client.
- **Client id to actor mapping.** Rejected by ADR-100: a client id is never
  an actor, and a public client id is known to every caller.
- **Auth0 `act` claim or a custom claim as the actor.** The token is issued
  to whatever the person authorized; a claim the client can influence is not
  operator evidence, and the live tenant does not emit `act` for this flow.
- **Refuse only `gty`.** The RFC 9068 profile omits `gty`; the subject checks
  catch those tokens too.

## Rejected Alternatives

- Treating the client id as the surface. A surface still needs its own
  evidence; unbound it stays null.
- Accepting caller-supplied `kind=explicit` once an actor is proven. The
  operator decision of 2026-11-02 stands: the server decides.

## Invariants

1. An OAuth principal has an actor only from an operator binding for its
   exact verified (subject, client id) pair.
2. A client id never resolves as an actor or a surface.
3. No request argument or token claim sets `agent_id`, `oauth_client_id`,
   `actor_evidence_refs` or `surface_ref`.
4. Without an actor, every consequential tool is refused over OAuth.
5. Server-verified explicit evidence on the OAuth door comes only from
   consent whose subject is the verified token subject.
6. A token without an end user is never a hosted Memory principal.
7. Non-OAuth doors behave as before.

## Consequences

- An operator can let several agents share the hosted store, each attributed
  to its own canonical actor, by listing each person's (subject, client id)
  pairs.
- A person using a new client must be bound before that client can write.
- Identity and preference writes about the authenticated person themself can
  admit over OAuth with their consent; writes about anyone else cannot.
- Machine-to-machine access to the hosted store is closed.

## Security Impact

- The attribution source is server configuration plus a validated token; the
  caller cannot widen it (L9-AUTH-001).
- A leaked public client id gives nothing: it is one half of a key whose
  other half is a signed subject.
- Misconfiguration fails closed at startup; an unmatched pair fails closed at
  the write.
- Logs and errors name subjects and clients by fingerprint only.

## Migration Impact

- New optional variable `L9_MEMORY_OAUTH_ACTORS_JSON`. Without it the server
  behaves as ADR-102 left it.
- `MemoryPrincipal` gains three optional fields with neutral defaults; no
  stored record or receipt changes shape.
- Pinning OAuth in the hosted carrier (issue #108 section 2) is a later lane.

## Validation Requirements

- `tests/unit/test_oauth_actor_path.py`: bound pair admitted and attributed;
  unbound subject, other client and other subject refused; token actor claims
  and caller actor arguments ignored; malformed bindings refused at startup;
  every user-less token shape refused; consent from the verified subject
  admits a preference with server explicit evidence, foreign-subject consent
  with a caller claim quarantines, and a non-OAuth door adds nothing.
- `tests/integration/test_remote_mcp_oauth.py`: the same over a socket,
  including `401` with the Bearer challenge for client-credentials tokens.
- No test exercises the live tenant; the live PKCE receipt is still owed.

## Rollback Conditions

Revert this record and its code if an operator binding is shown to admit an
actor for a pair it was not declared for, if any request input is shown to
set an actor, or if a user token from the live tenant is refused as
user-less. Removing `L9_MEMORY_OAUTH_ACTORS_JSON` returns every OAuth write to
refused without a code change.

## Supersedes / Superseded By

Supersedes: nothing. Superseded by: nothing.
