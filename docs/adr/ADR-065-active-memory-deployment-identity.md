# ADR-065: Active-Memory Deployment Identity

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-065-active-memory-deployment-identity.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

## Status

Accepted (2026-07-28)

Related: ADR-006 (namespace authorization), ADR-025 (storage partitioning)

## Context

The active-memory subsystem (Redis-backed presence, leases, and short-
TTL context) was originally designed assuming a single implicit Redis
backend per process. External consumer applications (any application
embedding this package to coordinate multiple agent instances) require
running independent active-memory backends — each with its own Redis
instance, credentials, and network — without the core package
containing any consumer-specific configuration or identifiers.

Without an explicit deployment identity, two failure modes are
possible:

1. Key/channel collisions if two independent consumer deployments
   share network reachability to overlapping Redis namespaces.
2. Ambiguous provenance when active-memory records are promoted into
   canonical Graphiti memory, since a promoted record would not
   identify which runtime/backend it originated from.

## Decision

Introduce `ActiveDeployment` (`deployment_id`, `trust_domain`,
`environment`) as an immutable, server-injected identity bound to one
running active-memory runtime instance at startup.

Rules:

1. One runtime process selects exactly one backend and one
   `ActiveDeployment` at startup. There is no per-request backend
   selection or multi-tenant routing inside this package.
2. `deployment_id` and `trust_domain` are validated
   (1–128 chars, `[a-z0-9._:-]`) and must not contain Redis glob
   wildcards or path separators.
3. Production environments reject a fixed set of recognized
   placeholder values (`example`, `changeme`, `test`, `unset`,
   `unknown`, empty string) for either field.
4. All Redis keys and Pub/Sub channels embed a deterministic
   `deployment_hash` derived via SHA-256 over a versioned canonical
   string (`v1|{trust_domain}|{deployment_id}`), truncated to 16 hex
   characters.
5. Deployment identity is injected into `AgentPresence`, `ActiveContext`,
   `AgentEvent`, and Graphiti promotion provenance. Callers cannot
   override these fields via any public API.

## Consequences

- Positive: independent consumer deployments can safely share
  reachability to network infrastructure without record collision.
- Positive: promoted Graphiti records carry auditable
  deployment/trust-domain provenance.
- Negative: changing `deployment_id` or `trust_domain` for a running
  deployment is a breaking key-space migration (all existing active
  keys become unreachable under the new hash); this is documented in
  `docs/ACTIVE_MEMORY_DEPLOYMENT_CONTRACT.md`.
- Negative: this package still has no built-in support for a single
  process serving multiple deployments concurrently; a future ADR
  would be required to add that if a genuine multi-tenant hosting need
  arises.

## Alternatives Considered

- **Per-request backend registry.** Rejected: adds request-time trust
  surface and complexity disproportionate to the stated need (multiple
  independent single-tenant deployments, not one multi-tenant server).
- **Namespacing by raw `deployment_id` string in keys (no hash).**
  Rejected: raw identifiers could be crafted to contain Redis glob
  characters or excessively long values, complicating ACL pattern
  design; a fixed-length hash simplifies ACL key-pattern generation
  (ADR-068).

## Rejected Alternatives

A per-request backend registry was rejected because it would let a
single process silently multiplex multiple Redis backends behind one
API surface, expanding the request-time trust boundary and making
deployment isolation implicit rather than a startup-time contract.
Namespacing by the raw `deployment_id` string was rejected because
`deployment_id` accepts a broader character set than is safe to embed
directly in Redis key/channel glob patterns, and a fixed-length hash
keeps ACL pattern generation (ADR-068) independent of identifier length.

## Invariants

Exactly one `ActiveDeployment` is bound per running process; there is
no runtime API to rebind it. `deployment_id` and `trust_domain` are
validated on every construction (1-128 chars, `[a-z0-9._:-]`, no
whitespace, no Redis glob wildcards, no path separators). A production
environment rejects recognized placeholder values for either field.
`derive_deployment_hash()` is a pure, deterministic function of
`{trust_domain}|{deployment_id}` under algorithm version `v1`; the same
inputs always produce the same 16-hex-character hash within one
algorithm version. Callers can never supply `deployment_id` through a
public request payload; it is only ever injected server-side at
construction time.

## Security Impact

Deployment identity is the isolation boundary between independent
consumer applications sharing Redis network reachability; a validation
gap here (e.g. accepting glob wildcards) could let one deployment's
key pattern collide with or enumerate another's. Rejecting placeholder
`deployment_id`/`trust_domain` values in production prevents an
operator from accidentally shipping a development identity (and its
implied key namespace) into a shared production Redis instance.
`derive_deployment_hash()` never embeds raw secret material; it only
hashes the identifier strings themselves.

## Migration Impact

No stored data, schema, or wire contract changes; this ADR introduces
a new, previously nonexistent subsystem. Consumers adopting
active-memory for the first time must choose a `deployment_id` and
`trust_domain` before startup. Changing either value for an
already-running deployment is a breaking key-space migration (see
`docs/ACTIVE_MEMORY_DEPLOYMENT_CONTRACT.md`). The ADR ledger extends to
ADR-068 and the assurance validator's expected range advances
accordingly.

## Validation Requirements

Unit tests must cover identifier validation (length bounds, character
set, whitespace, glob wildcards, path separators), placeholder
rejection in the `production` environment only, and determinism/
stability of `derive_deployment_hash()` across repeated calls with the
same inputs and across algorithm-version boundaries. `scripts/
validate_release.sh` must exercise the `active` package's unit suite.

## Rollback Conditions

Revert to an implicit single-backend-per-process model (no
`ActiveDeployment`) only if deployment identity is shown to be
unnecessary overhead for every real consumer, or if the hash derivation
is found to produce collisions in practice. Rollback requires a
coordinated key-space migration for any consumer that has already
deployed under a `deployment_hash`-namespaced key layout.

## Supersedes / Superseded By

Supersedes no prior ADR (the active-memory subsystem is new). Not
superseded.
