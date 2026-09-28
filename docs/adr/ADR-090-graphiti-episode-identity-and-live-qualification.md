# ADR-090: Graphiti Episode Identity and Live Qualification

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-090-graphiti-episode-identity-and-live-qualification.md
layer: adr
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-09-26
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.5+ (campaign `l9-memory-graph-intelligence-v1`, slice PR-G)

## Status

Accepted

## Context

Live qualification against real `graphiti-core` 0.30.2 (GI-080) showed that
the projection's episode identity assumption was wrong:

1. `GraphitiProjection.project` passed `uuid = record_id` so the episode uuid
   would equal the canonical record id. In Graphiti a caller-supplied `uuid`
   means "update the existing episode": `add_episode` calls
   `EpisodicNode.get_by_uuid`, which raises `NodeNotFoundError` for a new id.
2. The official MCP server's `add_memory` queues that call and replies
   "queued" before it runs; the queue worker logs and drops the failure. The
   caller sees success and the episode never exists.
3. With no provider locator in the reply, the projection link fell back to the
   record id, so retirement and verified erasure called `delete_episode` with
   an id Graphiti never issued.
4. Graphiti facts cite provider episode uuids, not record ids, and entity
   nodes carry no episode reference, so projection search could not map real
   Graphiti results back to canonical records.

The in-repo fake of the official server stored whatever uuid it was given,
which hid all four. GI-026 (evidence binds to canonical records) still holds
if the mapping is carried by something Graphiti preserves: the episode name
`memory:<record_id>`, which the projection already set.

## Decision

1. **Create without identity.** `project` never sends `uuid`. Graphiti issues
   the episode uuid; the canonical name `memory:<record_id>` carries the
   mapping.
2. **Locator.** A provider-issued episode id in the write reply is the locator
   (Zep and any provider that returns one). Otherwise the locator is
   `graphiti-episode-name:<group_id>:memory:<record_id>`. The group id is the
   ADR-084 digest, so no raw tenant id enters the locator.
3. **Resolve at removal.** Retirement and erasure with a name locator call
   `get_episodes(group_ids=[group_id], max_episodes=episode_lookup_limit)`,
   keep exact-name matches in that group, and `delete_episode` each. No match
   fails closed with `ProjectionError`, because Graphiti ingests
   asynchronously and "not yet ingested", "never ingested" and "outside the
   window" cannot be told apart; the outbox retries. Legacy uuid locators still
   delete directly.
4. **Evidence mapping in the graph adapter.** Supporting-episode templates
   return `CASE WHEN ep.name STARTS WITH 'memory:' THEN substring(ep.name, 7)
   ELSE ep.uuid END`. Record anchors match `ep.name = 'memory:<id>'` or the
   legacy `ep.uuid`. Edge episode uuids map through the new registered
   `episode_support_ids_v1` template, restricted to authorized groups. The
   canonical linker still admits only ids that rehydrate in scope.
5. **Fact search mapping.** When a fact carries no record id, the projection
   maps its `episodes` through one bounded `get_episodes` listing per group.
   Entity-node search has no provenance to map and returns no canonical hits
   (a disclosed limitation, not a guess).
6. **Qualification harness.** `tests/qualification` runs the production
   projection, outbox, graph adapter and service against real `graphiti_core`
   0.30.2 on Neo4j 5.26 + GDS 2.13. The LLM, embedder and reranker are
   deterministic stand-ins; the test transport reproduces the official MCP
   reply and swallowed-failure semantics.

## Alternatives Considered

- Keep `uuid = record_id` and first create the episode through another path.
- Store the provider uuid by reading it back after ingestion.
- Carry the record id in the episode's `source_description`.
- Change `search_nodes` handling to guess a record from entity summaries.

## Rejected Alternatives

- No official MCP tool creates an episode with a chosen uuid; any other path
  bypasses the transport contract.
- A read-back after an asynchronous queue races ingestion and needs a second
  write to the projection link after delivery.
- `source_description` is free text other writers set; the name is the field
  the projection already owns and `get_episodes` returns.
- Guessing support from text violates GI-026.

## Invariants

GI-005, GI-007, GI-010, GI-026, GI-029, GI-080.

## Consequences

- Projection writes to real Graphiti persist and can be withdrawn and erased.
- Name resolution costs one bounded listing per removal, and per group for
  fact search.
- A group holding more than `episode_lookup_limit` episodes (default 1000) can
  fail removal closed until the limit is raised. Upstream orders the listing
  by uuid and exposes no cursor through MCP.

## Security Impact

Resolution is confined to the locator's own group, and the adapter template to
the authorized groups. An episode named `memory:<id>` by another writer in the
same group can only point at a record the canonical linker then rehydrates
under the caller's tenant and namespace.

## Migration Impact

Links written before this decision against the official MCP server point at
episodes that never existed. `rebuild-projection` re-queues links from before
ADR-084 (no `scope_scheme`) and re-projects them under name locators. Links
that have `scope_scheme` but carry a record-id locator need a re-projection
(delete the link and run rebuild). Zep locators are unaffected.

## Validation Requirements

- `tests/unit/test_graphiti_projection_episode_identity.py`: no uuid sent;
  name and provider locators; in-group resolution deletes every match;
  unresolved names fail closed; missing `get_episodes` fails closed; legacy
  locators; malformed locators; fact-episode mapping confined to the group.
- `tests/unit/test_neo4j_structural_operations.py`: edge episodes map through
  `episode_support_ids_v1` with bound groups.
- `tests/integration/test_graphiti_http_projection_loop.py`: the official
  dialect fake now drops caller-supplied uuids as upstream does.
- `tests/qualification/test_graphiti_live_qualification.py` (13 tests, live).

## Rollback Conditions

Revert the slice. Records projected under name locators then need a rebuild,
because a legacy-style locator cannot address them.

## Supersedes / Superseded By

Amends ADR-076 (projection retirement) and ADR-086/ADR-087 (support mapping).
Superseded by none.
