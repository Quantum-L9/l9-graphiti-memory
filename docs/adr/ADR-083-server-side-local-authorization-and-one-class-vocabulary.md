# ADR-083: Server-Side Local Authorization and One Class Vocabulary

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-083-server-side-local-authorization-and-one-class-vocabulary.md
layer: adr
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-09-24
/L9_META -->


**Date:** 2026-09-19 (authorization decision revised 2026-09-24)
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.5+ and its consumer `Quantum-L9/Cursor-Governance`

## Status

Accepted

## Context

ADR-0031 made `memory.write_agent` the model's ordinary durable write: no
phase-lock, no session receipt, visible to the next `hydrate`. The tool takes a
`namespace` argument, which implies the caller may address any repository it is
granted.

It could not. Two defects, found together in a multi-root Claude Code session,
meant the governed agent lane was both less capable and less truthful than the
operator CLI it was meant to supersede.

**The principal was resolved once, from the process's working directory.**
`run_stdio` called `_stdio_principal` before entering its stdin loop, and the
Tier 3 fallback called `resolve_local_context(settings)` with no `cwd`. Grants
therefore came from wherever the host launched the server, and every later
`namespace` argument was validated against that frozen set. A session with a
primary workspace and the governance SSOT mounted as a second root could write
to exactly one of them for the life of the process, and no correct tool usage
from inside the session could change it. Verified rather than inferred:

```
$ readlink -f /proc/$(pgrep -f l9_graphite_memory.server)/cwd
/home/user/Constellation.Gate
memory.write_agent {"namespace": "cursor-governance", "dry_run": true}
  -> authorization.allowed = false
  -> reasons = ["namespace did not match any write grant"]
```

The same fact written through `l9-memory write --workspace /root/.cursor-governance`
was admitted, because the CLI resolves authorization per invocation. The
fallback was the flexible lane and the governed lane was the constrained one.
That inversion is the defect.

The rejection also read like a malformed argument. It named neither the grant
set nor the door the principal came through, so a scope limit was
indistinguishable from a typo — which is what made the diagnosis expensive.

**The two lanes disagreed about what a class name means.** `cli.py` mapped
`lesson` to `procedural`; `mcp_tools.py` mapped it to `insight`. `memory.search`
filters on `memory_classes`, so a caller filtering `["insight"]` silently
missed every lesson the other lane had written. Nothing errored. Worse,
`procedural` was absent from the agent lane's allowlist entirely, so the lane
could not emit the class the operator lane routed every lesson into: the two
could not produce a comparable corpus even in principle. A third hand-kept copy
of the vocabulary sat in the tool description an agent reads before calling,
and `pickup` was valid on one lane while the other only knew `pickup_context`.

**Revision (2026-09-24).** The first version of this ADR fixed the frozen
principal by reading the `namespace` a `tools/call` names and, when it was a
registered repository slug and no local ACL was configured, granting that
namespace read, write, promote and maintain. That let an unauthenticated Tier 3
caller manufacture the very claim its request was then checked against,
including over auth-disabled HTTP. It contradicts ADR-006 (claims are
established server-side; a requested namespace is intersected with them) and
the consumer registry's own contract (`namespace_request_hints`, grants
nothing). The open-PR audit of 2026-09-24 recorded it as F-64-AUTHZ-001. The
authorization decision below replaces it; the vocabulary decision is kept.

## Decision

The agent lane and the operator lane are two adapters over one
`MemoryService`. They must be equally capable and must mean the same thing.

1. **Authorization on a local transport is established server-side, before
   any request is read.** Tier 1 (human door) and Tier 2 (signed agent door)
   read their claims from the environment and are verified once at startup.
   Tier 3 (unauthenticated local-operator fallback) takes its claims from the
   repository the process runs in, or from the operator-configured
   `local_*_namespaces` when present. `StdioPrincipalResolver.for_request`
   ignores the request: a requested namespace is an address that
   `MemoryService` checks against those claims, never a source of them.
   Auth-disabled HTTP serves exactly the stdio principal and is never wider.

2. **Registry membership grants nothing.** The registry resolves repository
   identity from a working directory. A registered slug named in a request
   body is a hint and does not widen any grant. Multi-root access is expressed
   by a trusted server-side claim instead: the signed Tier 2 grant map
   (`L9_MEMORY_AGENT_GRANTS_JSON`, the canonical agent path) or, for a local
   operator, an explicit `L9_MEMORY_LOCAL_*_NAMESPACES` ACL, which remains a
   hard ceiling (ADR-006).

3. **One vocabulary table.** `contracts.class_vocabulary` owns the alias map
   and the agent-lane allowlist. The CLI's `--kind`, every MCP write tool's
   `memory_class`, the `--kind` help text, and the `memory.write_agent`
   description are all derived from it. `lesson` resolves to `procedural`
   everywhere: that is the established meaning, carried by the CLI since the
   legacy kind map was introduced and by the corpus already written through it.

4. **The allowlist is closed under the alias table.** Every class an alias
   resolves to is writable on the agent lane. `identity` is the one class the
   lane refuses, and it is refused as an authority decision — an identity
   record asserts who a subject *is*, which is not a claim an agent may make
   for itself on a lane that takes no lock and no review.

5. **A denial names the grant set and the door.** The authorization receipt's
   reason carries `auth_method` and the granted patterns, so a scope limit is
   legible as one.

6. **The capability receipt reports what the transport exposes.**
   `write_agent` and `write_governed` are named in `MCP_OPERATION_TOOLS`. They
   stay out of `LIFECYCLE_OPERATIONS` because they are MCP-only and the CLI's
   `write` is the operator form of `ingest`, not a twin of either.

## Alternatives Considered

**Resolve Tier 3 per request from the namespace the request names.** This was
the first version of this ADR. Rejected: the request supplies the grant it is
checked against, so any registered repository becomes writable, promotable and
maintainable by an unauthenticated caller. Requiring registry membership does
not help, because the registry is a hints list that grants nothing.

**Union every known root's grants at spawn.** Rejected: it still infers
authority from the registry rather than from a trusted claim, and it grants
more than any single request needs.

**Require Tier 2 for multi-root agent sessions.** Adopted. The signed agent
door carries an explicit grant map and is what the consumer's canonical
launcher already requires; anonymous local fallback there needs an explicit
operator override. A local operator who needs several roots lists them in
`L9_MEMORY_LOCAL_*_NAMESPACES`.

**Let the consumer patch the installed package.** Cursor-Governance consumes a
pinned vendored wheel, so a `site-packages` edit is discarded by the next
`uv sync`, and re-implementing the vocabulary in the consumer would fork a
contract it does not own.

**Change `lesson` to `insight` on both lanes instead.** Rejected: the CLI
mapping is the older of the two and the corpus already written through it
carries `procedural`. Existing code is the source of truth; the newer table
adapts to it.

## Rejected Alternatives

- Deriving any grant from request data, on any transport.
- Treating registry membership as authority.
- Keeping two alias tables and documenting the divergence instead of removing
  it. A documented silent-retrieval-miss is still a silent retrieval miss.
- Allowing `identity` on the agent lane to make the allowlist trivially closed.
- Unifying the receipt envelope across `write`, `search`, and `hydrate` in this
  change. The shapes are load-bearing for the current consumer; they are
  documented below instead and any change to them is a contract bump.

## Invariants

- `INV-AUTHZ-01` A local principal's claims are fixed before any request is
  read; no request field can add a read, write, promote or maintain grant.
- `INV-AUTHZ-02` Configured `local_*_namespaces` are a ceiling and are never
  widened by a request.
- `INV-AUTHZ-03` A forbidden or unregistered namespace is never granted.
- `INV-AUTHZ-04` Auth-disabled HTTP is never wider than stdio.
- `INV-AUTHZ-05` A signed Tier 2 principal can write every namespace in its
  signed grant map and nothing else.
- `INV-VOCAB-01` Exactly one alias table exists; the CLI and every MCP write
  tool resolve a spelling identically.
- `INV-VOCAB-02` No alias points at another alias, and no alias shadows a
  canonical class value.
- `INV-VOCAB-03` Every alias target is writable on the agent lane.
- `INV-VOCAB-04` Descriptions and help text naming classes are generated from
  the table.

## Consequences

An agent writes to every repository its signed Tier 2 grant names, in one
session, on the lane doctrine tells it to use. An unconfigured Tier 3 process
stays scoped to the repository it runs in; a write to another root is refused
with a reason naming the door and the granted patterns, and the remedy is a
trusted claim (a signed grant or an explicit local ACL), never a request
argument.

`lesson` written through `memory.write_agent` now lands in `procedural` rather
than `insight`. Records written through that lane before v2.5 carry `insight`
and are not migrated: they remain retrievable by content and by a class filter
naming `insight`. The lane is unreleased (2.4.0 was never tagged or published),
so the exposure is limited to sessions that used the vendored candidate wheel.
A consumer filtering strictly by class across the v2.4/v2.5 boundary should
include both until it is satisfied no such records remain.

The receipt shape still differs per operation, and this is now written down
rather than discovered:

| Operation | Payload location |
|---|---|
| `write`, `write_agent`, `write_governed` | `receipt.record_id`, with `receipt.status` and `receipt.admission` |
| `get` | `{"found": bool, "record": {...} \| null}` |
| `search` | `receipt.hits[].record`, each hit carrying `factors`, `matched_by`, `record`, `score` |
| `hydrate` | top-level `record_count` and `record_ids`; no `hydrate_stats` |

## Security Impact

Closes F-64-AUTHZ-001. Tier 3 is the unauthenticated local-operator fallback,
so the first version of this ADR widened unauthenticated authority to every
registered repository, over stdio and auth-disabled HTTP. That path is removed:
Tier 3 authority is again repository-scoped or explicitly operator-configured,
exactly as ADR-006 requires. `is_admin` is not set by any request, tenant
isolation is untouched, and the memory phase-lock continues to govern
memory-write consistency only — it is never repository-write authority.

Naming the granted patterns in a denial reason discloses the principal's own
grant set to the principal itself. That is information the caller already holds
by construction and is what makes the limit diagnosable.

## Migration Impact

No record migration. No schema change: `MEMORY_SCHEMA_VERSION` stays `2.2.0`.
`CONTROL_PLANE_CONTRACT_VERSION` stays `memory-control-plane/v1` — the
lifecycle operation set and every receipt shape are unchanged, and the
capability additions are additive, so a consumer's binding proof still holds.

`_LEGACY_KIND_MAP` remains exported from `cli.py` and is now the shared table.

Downstream, `Quantum-L9/Cursor-Governance` pins this package as a vendored
wheel, so adopting v2.5.0 there requires a wheel rebuild, a re-vendor into
`ops/vendor/wheels/`, and a `pyproject.toml` plus `uv.lock` bump.

## Validation Requirements

- `tests/unit/test_stdio_namespace_resolution.py` — a registered namespace in
  a request widens no read/write/promote/maintain grant on stdio or
  auth-disabled HTTP; explicit local ACL allows only its configured
  namespaces; forbidden and unregistered namespaces are refused; the signed
  Tier 2 grant map works across several roots end to end.
- `tests/unit/test_class_vocabulary.py` — single-source table, no chaining, no
  shadowing, allowlist closure, cross-lane agreement, generated descriptions.
- `tests/unit/test_write_agent_mcp.py` — `lesson` is stored as `procedural`;
  `identity` is refused.
- `python tools/assurance/validate_adrs.py`
- `python -m pytest tests/`

## Rollback Conditions

Roll back the vocabulary half if a consumer depends on `memory.write_agent`
resolving `lesson` to `insight`. The authorization half is not rolled back to
request-derived grants under any condition; a consumer that needs multi-root
Tier 3 configures `L9_MEMORY_LOCAL_*_NAMESPACES`. The vocabulary
half can be reverted independently of the authorization half; they share no
module.

## Supersedes / Superseded By

Amends ADR-0031 (signed agent MCP write classes) on the agent-lane class
vocabulary. Its Tier 3 statement is that of ADR-006: repository-scoped or
explicitly operator-configured. Extends ADR-082 (consumer
control-plane transport parity) with the two write tools the receipt omitted.
Does not supersede ADR-006 (local ACL claims), which it explicitly preserves.
Superseded by: none.
