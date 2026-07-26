<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/repository-review/INDEX.md
layer: repository_review
owner: memory-control-plane
status: active
version: 2.2.0
pinned_sha: 16d5305c0124d85bf06b719c5bac4c516bfe9085
generated: 2026-07-26
generated_by: Manus AI repository review
/L9_META -->

# Repository-Review Artifact Index

Repository: `Quantum-L9/l9-graphiti-memory` at pinned SHA `16d5305c0124d85bf06b719c5bac4c516bfe9085` (release 2.2.0). All eleven gate-required artifacts are grounded exclusively in tracked repository contents; provenance for every claim is recorded in `source-citations.json`.

| File | Description |
|---|---|
| `document-index.json` | Machine-readable index of all 295 tracked files by document class: governance docs, 62 ADRs, production source, tests, assurance tools, validation evidence, operations |
| `architecture-summary.md` | Binding architecture narrative: classification, layered structure, canonical write transaction, read/hydration path, erasure, failure posture, extension model, validation state |
| `authority-map.md` | Which artifact governs each concern (ADR ledger as contract law), enforcement mechanism per concern, and explicitly external or subordinated authorities |
| `runtime-dependency-map.md` | Package dependencies, entry points, internal import flow, optional external services, filesystem state, and dependency invariants |
| `persistence-map.md` | Every class of durable state: canonical RecordStore entities, atomicity and bi-temporal guarantees, projections, recovery queue, schema evolution, verified erasure |
| `provider-capability-matrix.md` | Capability table for `none`/`http` (Graphiti)/`zep` backends, the ProjectionAdapter contract, degradation ladder, and explicit non-capabilities |
| `validation-map.md` | All 20 executed local checks with evidence paths (103 tests, 62 ADRs, 44 harvest decisions, 25 preflight gates) and the five external blocker classes |
| `supersession-map.md` | The five binding supersession decisions REV-001 through REV-005 with superseded-surface disposition table and closure statement |
| `reconciliation-ledger.json` | Machine-readable mirror of REV-001 through REV-005 with authority, evidence, classification, status, and residual risk per decision |
| `open-questions.md` | Ten open questions (OQ-1 to OQ-10) mapped to trackers RP-001 through RP-009 plus review observations, with disposition summary |
| `source-citations.json` | Fifty citations (S-01 to S-50) tracing every factual claim to a tracked repository file |
