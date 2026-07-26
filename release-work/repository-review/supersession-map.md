<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/repository-review/supersession-map.md
layer: repository_review
owner: memory-control-plane
status: active
version: 2.2.0
pinned_sha: 16d5305c0124d85bf06b719c5bac4c516bfe9085
generated: 2026-07-26
generated_by: Manus AI repository review
/L9_META -->

# Supersession Map

This map records the five binding supersession decisions (REV-001 through REV-005) that govern how release 2.2.0 replaces prior behavior, plus the general supersession law they instantiate. Each decision is grounded in `docs/COMPATIBILITY_MATRIX.md`, `MIGRATION.md`, `docs/HARVEST_MAP.md`, and the ADR ledger at pinned SHA `16d5305c0124d85bf06b719c5bac4c516bfe9085`. All five decisions are also persisted in machine-readable form in `reconciliation-ledger.json` in this directory.

## A. General supersession law

Record-level supersession is non-destructive by construction: corrections create new records plus supersession status events, prior truth is never overwritten, and superseded records retain their lineage (ADR-008). Decision-level supersession follows the same discipline: a superseding choice creates a new ADR rather than rewriting an accepted one (`docs/adr/README.md`), and legacy surfaces are retired through documented aliases and migrations rather than silent removal (ADR-023, ADR-058).

## B. Decision register

### REV-001 — Provider role reclassification: canonical-like transport → rebuildable projection

The v0.2 lineage treated the graph provider as a de facto system of record. Release 2.2.0 supersedes that role: the `RecordStore` is the sole canonical owner of memory state, and Graphiti/Zep become deletable, rebuildable projections behind a durable outbox. `docs/COMPATIBILITY_MATRIX.md` classifies this as an intentional architecture change, and ADR-025 fixes it as law. Consequence: no provider outage can lose canonical data, and projections can be rebuilt wholesale. Status: **superseding behavior implemented and tested locally**; live provider lifecycle proof remains external (RP-004, RP-005).

### REV-002 — Graphiti tool dialect supersession: legacy `add_episode`/`search_facts` → preferred `add_memory`/`search_memory_facts`

The transport (`src/l9_graphite_memory/transport.py`) negotiates dialects per server: it prefers the current Graphiti MCP tool names `add_memory` and `search_memory_facts` while retaining support for the legacy `add_episode` and `search_facts` names. The legacy dialect is superseded but not removed, preserving compatibility with older Graphiti servers as documented in `docs/COMPATIBILITY_MATRIX.md`. Status: **implemented**, exercised by transport unit tests.

### REV-003 — Search failure semantics: empty-result masking → typed per-strategy receipts

Prior behavior could represent a failed backend search as zero results. Release 2.2.0 supersedes this with typed complete/partial/failed retrieval receipts that record every attempted, succeeded, and failed strategy (ADR-015, ADR-039, ADR-054). `docs/COMPATIBILITY_MATRIX.md` marks this as an intentional correctness break: callers that previously conflated emptiness with failure must now inspect the receipt. Status: **implemented**, enforced by retrieval planner tests.

### REV-004 — Namespace authority supersession: caller-asserted namespaces → server-derived claim intersection

The v0.2 surface accepted arbitrary remote namespaces from callers. Release 2.2.0 supersedes this with server-derived `MemoryPrincipal` claims: requested namespaces are intersected with principal authority before any read or write (ADR-006, ADR-030). `docs/COMPATIBILITY_MATRIX.md` classifies this as a security break by design; remote callers lose implicit reach and must hold explicit claims. Status: **implemented**, enforced by `tests/unit/test_authz.py` and server principal tests.

### REV-005 — Deletion semantics supersession: undefined/destructive deletion → redacted tombstone with verified projection erasure

Deletion previously lacked a verified contract. Release 2.2.0 supersedes it: canonical content is redacted immediately into a tombstone that preserves referential integrity, and the deletion receipt completes only after locator-verified erasure in every required projection — Graphiti `delete_episode`, Zep `graph.episode.delete`, keyed by the persisted `ProjectionLink` (ADR-024, ADR-057). In the same compatibility pass, guard state moved from the legacy `~/.cursor/graphiti-state` path to the new state directory with legacy read compatibility. Status: **implemented**, exercised by `tests/integration/test_privacy_deletion.py`.

## C. Superseded-surface disposition table

| Superseded surface | Replacement | Disposition | Decision |
|---|---|---|---|
| Provider as system of record | RecordStore canonical + projections | Retired; providers demoted | REV-001 |
| `add_episode`, `search_facts` dialect | `add_memory`, `search_memory_facts` | Retained as negotiated legacy dialect | REV-002 |
| Empty results on backend failure | Typed per-strategy receipts | Retired; correctness break documented | REV-003 |
| Arbitrary remote namespace acceptance | Server-derived claim intersection | Retired; security break by design | REV-004 |
| Undefined destructive deletion | Redacted tombstone + verified erasure | Retired; erasure verified by locator | REV-005 |
| Legacy MCP tool names (`write`, `search`, `health`, `bootstrap`, `phase_lock`, `conflicts`) | Canonical `memory.*` tools | Retained as thin aliases (ADR-014) | supporting REV-002 |
| Legacy guard state path | New state directory | Legacy read preserved | supporting REV-005 |
| Legacy v0.2 record schema | Versioned schema with upcasters | Upcast on read (ADR-035, ADR-047) | supporting REV-001 |

## D. Closure

Every legacy concept from the eight harvest source packs is dispositioned as `implemented`, `rejected_boundary`, or `blocked_external` in `docs/harvest_coverage.yaml` (44 decisions, validated by `tools/assurance/validate_harvest_coverage.py` under ADR-056), so no superseded behavior remains undocumented. The five REV decisions above are the review-level consolidation of that ledger and are mirrored entry-for-entry in `reconciliation-ledger.json`.
