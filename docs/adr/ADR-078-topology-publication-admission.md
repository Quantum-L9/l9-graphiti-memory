# ADR-078: Topology Publication Admission and Structured Source Locators

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-078-topology-publication-admission.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-08-23
/L9_META -->


**Date:** 2026-08-23
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.2+

## Status

Accepted

## Context

`l9-constellation-topology` now emits a versioned publication plan
(`l9.topology-publication-plan` 1.0.0): topology facts lowered into
destination-neutral `memory.ingest` intents, each carrying an explicit
idempotency key and a fail-closed eligibility decision. The constellation
needs a governed L3 → L4 boundary where those plans become canonical memory —
without Topology acquiring write authority over Memory, without a second
control plane beside `MemoryService`, and without a network hop that belongs
to Gate.

Separately, Topology and Meta preserve truthful format-specific source
coordinates (PDF pages, DOCX blocks, PPTX shapes, spreadsheet cells, notebook
cells, CSV rows, HTML nodes), while Memory's evidence contract could only
carry line/offset ranges — inviting fabricated line numbers for binary
sources.

## Decision

Topology publication eligibility is a request to Memory admission, not a
replacement for Memory admission.

1. A local, in-process adapter
   (`l9_graphite_memory/ingestion/topology_publication.py`) ingests
   integrity-bound plan and topology packet bundles, validates the exact
   1.0.0 contract, and binds every candidate's citations to the supplied
   topology packet. Local plan ingestion is not cross-node routing;
   production cross-node transport still requires Gate, and every eligible
   intent must pass `GateMemoryBridge.validate_intent` with zero dispatches.
2. Only candidates Topology marked `eligible` may reach `MemoryService.write`.
   Held, rejected, and skipped candidates produce zero write calls.
   MemoryService remains the final write authority: an eligible intent may
   still be admitted, quarantined, rejected, or identified as a duplicate,
   and the principal is server/operator derived — never taken from the plan.
3. Topology's explicit idempotency key is preserved exactly as the retry
   identity. The batch is per-operation atomic, never plan-atomic; replay of
   the same plan after interruption relies on those keys turning committed
   operations into duplicate receipts. No adapter-side write-ahead log exists.
4. Graphiti and Zep remain rebuildable projections. Qualification runs against
   temporary stores with a null projection and zero external calls.
5. The evidence contract gains a discriminated `SourceLocator` union
   (line/pdf/docx/pptx/spreadsheet/notebook/csv/html) on `Provenance` and
   `EvidenceRef`, extending `SourceRange` without breaking it. A binary
   locator may never be doubled with a line range, and a line locator beside
   a range must repeat it exactly. `MEMORY_SCHEMA_VERSION` moves to 2.2.0
   with a restamp upcaster from 2.1.0.

## Alternatives Considered

Revalidating plans against the producer's JSON Schema at runtime — rejected
because it adds a `jsonschema` runtime dependency for a check the narrow
typed adapter model plus canonical intent validation already makes stricter.

Recomputing the producer's semantic hash to authenticate plans — rejected;
a second implementation claiming equivalence is exactly how hash contracts
drift. Integrity binding is done through bundle manifests whose per-file
sha256 hashes this repository can recompute, and semantic-hash recomputation
stays producer-owned.

## Rejected Alternatives

Letting the adapter write through `RecordStore` for batch speed; minting
adapter-side idempotency keys; treating a publication plan as one atomic
transaction; promoting Topology candidate-domain records into writes; adding
peer URLs or destination selection to the adapter.

## Invariants

`MemoryService` is the only canonical write path; `RecordStore` is canonical
state; `NamespacePolicy` and `AdmissionEngine` cannot be bypassed; the
principal never comes from the plan payload; held/rejected/skipped candidates
never reach `MemoryService`; Topology idempotency keys are never re-minted;
structured binary locators never become fabricated line ranges; projections
stay rebuildable and optional.

## Consequences

Interrupted publications are recovered by rerunning the same plan. Batch
receipts expose per-candidate outcomes (including Memory refusals) without
carrying memory content. The evidence contract can hold truthful binary
coordinates the day the producer lowers them — the bound producer revision
does not emit `source_locator` yet, and Memory does not invent one.

## Security Impact

Plans are treated as untrusted input: strict schemas (`extra="forbid"`),
bundle path traversal and symlink escapes rejected, per-file hash and size
verification, and forged packet references failing closed before any write.
Authorization stays entirely inside MemoryService; an unauthorized namespace
in a plan is recorded as Memory's refusal, never overridden.

## Migration Impact

Persisted records upcast from 2.1.0 via a pure version restamp; the new
`source_locator` field is optional and absent on historical records. No
backfill, no store migration, no projection change.

## Validation Requirements

`tests/unit/topology_publication/` (parser, integrity, containment,
idempotency binding, execution modes, crash replay, Gate conformance,
architecture boundary), `tests/unit/test_source_locator_contract.py`,
`tests/conformance/test_source_locator_roundtrip.py`, and
`tests/integration/test_topology_publication_e2e.py` against the exact bound
producer plan fixture (`tests/fixtures/topology_publication/PROVENANCE.md`).
All run inside `scripts/validate_release.sh`.

## Rollback Conditions

Remove the adapter module, CLI subcommand, and suites; the locator contract
and 2.2.0 schema version stay (records may already carry them). If 2.2.0
must be abandoned before any locator-bearing record exists, revert the
version bump and the restamp upcaster together.

## Supersedes / Superseded By

Supersedes: none. Superseded by: none. Builds on ADR-071 (explicit operation
identity), ADR-072 (shared canonical backend), and the Gate-only constellation
boundary in `integrations/constellation.py`.
