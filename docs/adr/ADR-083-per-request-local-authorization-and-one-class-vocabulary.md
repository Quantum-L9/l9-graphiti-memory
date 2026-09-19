# ADR-083: Per-Request Local Authorization and One Class Vocabulary

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-083-per-request-local-authorization-and-one-class-vocabulary.md
layer: adr
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-09-19
/L9_META -->


**Date:** 2026-09-19
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

## Decision

The agent lane and the operator lane are two adapters over one
`MemoryService`. They must be equally capable and must mean the same thing.

1. **Authorization on a local transport is resolved per request.** Tiers 1 and
   2 read their claims from the environment, are verified once at startup, and
   remain static. Tier 3 derives its claims from *repository identity*, which
   is a property of the namespace being addressed and not of the process's
   working directory, so it is resolved for each request.
   `StdioPrincipalResolver.for_request` reads the `namespace` a `tools/call`
   names and resolves against it; `resolve_namespace_request` maps a namespace
   to a repository by registry membership, the reverse of `resolve_group`.

2. **Widening is narrow and explicit.** Only a *registered repository slug*
   resolves. Configured `local_*_namespaces` remain the sole ACL source
   (ADR-006) and are never widened by a request. Empty, forbidden, and
   unregistered namespaces fall through to working-directory resolution, which
   preserves read access to the workspace namespace and every previously
   observable outcome.

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

**Union every known root's grants at spawn.** Rejected in the issue that
reported this and rejected here: it is strictly weaker. It still freezes a set
at startup, so a root discovered later in the session is unreachable, and it
grants more than any single request needs.

**Require Tier 2 for multi-root sessions.** The signed agent door takes
explicit grants and would sidestep the freeze, but `L9_MEMORY_AGENT_GRANTS_JSON`
must be in the environment *before* the host launches the server. A SessionStart
hook is a child of the host and cannot deliver environment to a sibling
process, and a hosted surface has no launching shell the operator controls.
Tier 3 is the only lane available there, so the fix has to work on Tier 3.

**Let the consumer patch the installed package.** Cursor-Governance consumes a
pinned vendored wheel, so a `site-packages` edit is discarded by the next
`uv sync`, and re-implementing the vocabulary in the consumer would fork a
contract it does not own.

**Change `lesson` to `insight` on both lanes instead.** Rejected: the CLI
mapping is the older of the two and the corpus already written through it
carries `procedural`. Existing code is the source of truth; the newer table
adapts to it.

## Rejected Alternatives

- Resolving the principal from `cwd` at all on a transport that serves
  requests for more than one repository.
- Keeping two alias tables and documenting the divergence instead of removing
  it. A documented silent-retrieval-miss is still a silent retrieval miss.
- Allowing `identity` on the agent lane to make the allowlist trivially closed.
- Unifying the receipt envelope across `write`, `search`, and `hydrate` in this
  change. The shapes are load-bearing for the current consumer; they are
  documented below instead and any change to them is a contract bump.

## Invariants

- `INV-AUTHZ-01` A request naming a registered repository resolves to that
  repository's grants regardless of the process working directory.
- `INV-AUTHZ-02` Configured `local_*_namespaces` are never widened by a
  request.
- `INV-AUTHZ-03` A forbidden or unregistered namespace is never granted by
  namespace request.
- `INV-VOCAB-01` Exactly one alias table exists; the CLI and every MCP write
  tool resolve a spelling identically.
- `INV-VOCAB-02` No alias points at another alias, and no alias shadows a
  canonical class value.
- `INV-VOCAB-03` Every alias target is writable on the agent lane.
- `INV-VOCAB-04` Descriptions and help text naming classes are generated from
  the table.

## Consequences

An agent can durably record a fact about any registered repository in its own
session, on the lane doctrine tells it to use, without an operator fallback and
without a disclosed gap.

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

Tier 3 is the unauthenticated local-operator fallback. Its authority is
unchanged in kind: it was already able to address any repository, either by
being launched there or through `L9_MEMORY_NAMESPACE`, which `resolve_group`
honours for *any* non-forbidden value without consulting the registry.
Requiring registry membership makes the new path strictly stricter than that
existing one.

No new authority is created. `is_admin` is not set by this path, tenant
isolation is untouched, configured operator ACLs remain a ceiling, and the
memory phase-lock continues to govern memory-write consistency only — it is
never repository-write authority.

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

- `tests/unit/test_stdio_namespace_resolution.py` — per-request resolution,
  including a live contrast against the unchanged spawn-time path, the
  no-widening cases, and forbidden-namespace refusal.
- `tests/unit/test_class_vocabulary.py` — single-source table, no chaining, no
  shadowing, allowlist closure, cross-lane agreement, generated descriptions.
- `tests/unit/test_write_agent_mcp.py` — `lesson` is stored as `procedural`;
  `identity` is refused.
- `python tools/assurance/validate_adrs.py`
- `python -m pytest tests/`

## Rollback Conditions

Roll back if per-request resolution measurably degrades stdio throughput
(registry loading is per request and is the only added cost), or if a consumer
depends on `memory.write_agent` resolving `lesson` to `insight`. The vocabulary
half can be reverted independently of the authorization half; they share no
module.

## Supersedes / Superseded By

Amends ADR-0031 (signed agent MCP write classes) on the Tier 3 resolution
model and the agent-lane class vocabulary. Extends ADR-082 (consumer
control-plane transport parity) with the two write tools the receipt omitted.
Does not supersede ADR-006 (local ACL claims), which it explicitly preserves.
Superseded by: none.
