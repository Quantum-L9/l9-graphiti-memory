# Topology Publication Admission

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/TOPOLOGY_PUBLICATION_ADMISSION.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-08-23
/L9_META -->

Governed admission of `l9-constellation-topology` publication plans into
canonical memory. Decision record: ADR-078.

## The boundary in one sentence

Topology may decide that a fact is *eligible to request* memory admission;
Topology may not decide that Memory *must admit* it.

## Flow

```
Topology PublicationPlan (l9.topology-publication-plan 1.0.0)
      |  eligible candidates only — held/rejected/skipped never proceed
      v
TopologyPublicationAdapter        src/l9_graphite_memory/ingestion/topology_publication.py
      |  canonical IngestMemoryIntent / MemoryWriteRequest validation
      v
MemoryService.write               authorization -> admission -> temporal -> atomic commit
      v
RecordStore (canonical)  ->  durable outbox  ->  Graphiti / Zep projections (rebuildable)
```

## Vocabulary

| Term | Meaning |
|---|---|
| topology eligible | eligible to *attempt* memory admission |
| memory admitted | canonical MemoryService admission succeeded |
| memory quarantined | admitted as quarantined under memory policy |
| memory rejected | MemoryService refused the write |
| memory duplicate | the explicit operation identity was already committed |

Topology-eligible never equals memory-admitted.

## Inputs

Both inputs are integrity-bound bundles whose manifests carry per-file
`sha256:` content hashes and sizes, re-verified on load. Symlinks and paths
that escape a bundle root fail closed; inputs are never modified.

1. **Plan bundle** — `publication-plan.json` + `manifest.json` (plus the
   producer's `intents/memory-ingest.json`). The manifest's `packet_id` and
   `semantic_hash` must match the plan's own `plan_id` / `semantic_hash`;
   recomputing the producer's semantic-hash algorithm stays producer-owned.
2. **Topology packet bundle** — the exact packet the plan cites. The plan's
   `source_topology_packet.packet_id` and `source_topology_semantic_hash`
   must match the bundle manifest, and every candidate's entity, evidence,
   and repository-model-packet citations must resolve inside it.

## Execution modes

| Mode | Trigger | Behavior |
|---|---|---|
| preflight | default | full validation; eligible candidates run through MemoryService with `dry_run=True`; zero canonical mutations, zero projection effects; batch rows carry no record ids |
| apply | `--apply` | same validation first, then eligible candidates execute exactly as the producer emitted them |

Preflight is advisory qualification: a later apply still runs Memory's
complete authorization and admission pipeline again.

## Identity and replay

Topology's explicit idempotency key (`l9-topology-publication/v3:...`) is the
retry identity and is preserved exactly — candidate key and embedded request
key must be equal or the entire plan fails validation before any write. The
batch is per-operation atomic, never plan-atomic: a crash mid-batch leaves a
committed prefix, and recovery is rerunning the same plan — committed
operations return duplicate receipts with unchanged record ids while the
remainder proceeds. There is no adapter-side write-ahead log by design.

## CLI

```bash
l9-memory ingest-topology-plan \
  --plan /path/to/plan-bundle \
  --topology-bundle /path/to/topology-bundle \
  [--apply]
```

`--plan` accepts the plan bundle directory or the `publication-plan.json`
inside it. The principal is derived from this runtime's configured settings
(`local_*_namespaces` or group resolution) — never from the plan payload.
Namespace authorization is evaluated per intent by `NamespacePolicy` inside
MemoryService; a refusal appears in the batch receipt as `memory_rejected`.

Exit is nonzero for a malformed plan, failed topology binding, or structural
intent failure. Held/rejected candidates alone never fail the command; Memory
admission refusals are reported in the batch receipt. The receipt carries ids,
statuses, and counts only — no memory content.

## Gate

This adapter performs local, in-process ingestion. Cross-node transport still
requires Gate: every eligible intent must pass
`GateMemoryBridge.validate_intent` during validation, and the adapter
instantiates no Gate client and dispatches nothing.

## Structured source locators

`Provenance.source_locator` / `EvidenceRef.source_locator` accept a
discriminated union — `line`, `pdf` (page/block), `docx` (block/kind),
`pptx` (slide/shape), `spreadsheet` (sheet/cell-or-range), `notebook`
(cell index/type), `csv` (row), `html` (stable node index) — extending
`SourceRange` without breaking it. Both coordinates together are legal only
for the `line` kind with identical values; a binary locator beside a line
range is rejected, so binary sources never grow fabricated line numbers.

The bound producer revision does not emit `source_locator` yet
(`CURRENT_TOPOLOGY_LOCATOR_LOWERING_NOT_YET_PRESENT`); Memory does not invent
one, and forward conformance is pinned by
`tests/unit/topology_publication/test_locator_future_conformance.py`.

## Qualification fixture

`tests/fixtures/topology_publication/` holds plan and topology bundles
generated by the producer's own compiler at the bound
l9-constellation-topology revision — provenance, counts, and the
regeneration rule are in `PROVENANCE.md` there. The E2E suite
(`tests/integration/test_topology_publication_e2e.py`) runs validation,
preflight, SQLite apply, replay, and canonical readback against it with zero
Gate/Graphiti/Zep/LLM calls.
