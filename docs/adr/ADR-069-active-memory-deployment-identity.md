# ADR-069: Active-Memory Deployment Identity

- Status: Accepted
- Date: 2026-07-28
- Supersedes: None
- Related: ADR-006 (namespace authorization), ADR-025 (storage partitioning)

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
  (ADR-072).
