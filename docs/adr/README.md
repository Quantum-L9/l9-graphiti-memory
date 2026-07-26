<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/README.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Architecture Decision Records

This directory is the binding decision ledger for the v2 memory replatform. The implementation, tests, CI, migration tools, and operator documentation must agree with accepted ADRs.

## Decision rules

1. Accepted ADRs are contract law for this repository.
2. A code change that crosses an ADR boundary must update the ADR, tests, migration notes, and validation evidence in the same pull request.
3. Superseding decisions create a new ADR. Existing ADRs are not silently rewritten into a different conclusion.
4. Every ADR includes rollback conditions and executable validation expectations.

## Inventory

| ID | Decision | Status |
|---|---|---|
| ADR-001 | [Repository Role and Boundaries](ADR-001-repository-role-and-boundaries.md) | Accepted |
| ADR-002 | [Canonical Memory Service](ADR-002-canonical-memory-service.md) | Accepted |
| ADR-003 | [Memory Contract and Taxonomy](ADR-003-memory-contract-and-taxonomy.md) | Accepted |
| ADR-004 | [Bi-Temporal Semantics](ADR-004-bi-temporal-semantics.md) | Accepted |
| ADR-005 | [Provenance and Evidence](ADR-005-provenance-and-evidence.md) | Accepted |
| ADR-006 | [Namespace Authorization](ADR-006-namespace-authorization.md) | Accepted |
| ADR-007 | [Admission and Quarantine](ADR-007-admission-and-quarantine.md) | Accepted |
| ADR-008 | [Idempotency, Deduplication, and Supersession](ADR-008-idempotency-deduplication-and-supersession.md) | Accepted |
| ADR-009 | [Memory Promotion and Curation](ADR-009-memory-promotion-and-curation.md) | Accepted |
| ADR-010 | [Retention, Decay, and Pruning](ADR-010-retention-decay-and-pruning.md) | Accepted |
| ADR-011 | [Hydration and Context Budgeting](ADR-011-hydration-and-context-budgeting.md) | Accepted |
| ADR-012 | [Hybrid Retrieval Strategy](ADR-012-hybrid-retrieval-strategy.md) | Accepted |
| ADR-013 | [Transport Abstraction and Vendor Neutrality](ADR-013-transport-abstraction-and-vendor-neutrality.md) | Accepted |
| ADR-014 | [MCP Tool Contracts](ADR-014-mcp-tool-contracts.md) | Accepted |
| ADR-015 | [Failure and Degradation Policy](ADR-015-failure-and-degradation-policy.md) | Accepted |
| ADR-016 | [Secret and Credential Boundaries](ADR-016-secret-and-credential-boundaries.md) | Accepted |
| ADR-017 | [Hook and Agent Integration](ADR-017-hook-and-agent-integration.md) | Accepted |
| ADR-018 | [Outbox and Write Recovery](ADR-018-outbox-and-write-recovery.md) | Accepted |
| ADR-019 | [Observability and Evidence Receipts](ADR-019-observability-and-evidence-receipts.md) | Accepted |
| ADR-020 | [Package and Configuration Layout](ADR-020-package-and-configuration-layout.md) | Accepted |
| ADR-021 | [Testing and Adapter Conformance](ADR-021-testing-and-adapter-conformance.md) | Accepted |
| ADR-022 | [Release, Publishing, and Rollback](ADR-022-release-publishing-and-rollback.md) | Accepted |
| ADR-023 | [Legacy Migration and Compatibility](ADR-023-legacy-migration-and-compatibility.md) | Accepted |
| ADR-024 | [Memory Privacy, Consent, and Deletion](ADR-024-memory-privacy-consent-and-deletion.md) | Accepted |
| ADR-025 | [Storage Source of Truth and Backend Partitioning](ADR-025-storage-source-of-truth-and-backend-partitioning.md) | Accepted |
| ADR-026 | [TransportPacket Constellation Boundary](ADR-026-transportpacket-constellation-boundary.md) | Accepted |
| ADR-027 | [Semantic, Episodic, and Meta-Memory Ownership](ADR-027-semantic-episodic-and-meta-memory-ownership.md) | Accepted |
| ADR-028 | [Agent Checkpointing Boundary](ADR-028-agent-checkpointing-boundary.md) | Accepted |
| ADR-029 | [Temporal Coordinate Model](ADR-029-temporal-coordinate-model.md) | Accepted |
| ADR-030 | [RLS and Transaction-Scoped Authorization](ADR-030-rls-and-transaction-scoped-authorization.md) | Accepted |
| ADR-031 | [Reasoning Lineage versus Private Reasoning](ADR-031-reasoning-lineage-versus-private-reasoning.md) | Accepted |
| ADR-032 | [Performance SLOs and Partial Result Policy](ADR-032-performance-slos-and-partial-result-policy.md) | Accepted |
| ADR-033 | [Legacy Monolith Harvest and Rejection Record](ADR-033-legacy-monolith-harvest-and-rejection-record.md) | Accepted |
| ADR-034 | [Private Data, Fixtures, and Repository Hygiene](ADR-034-private-data-fixtures-and-repository-hygiene.md) | Accepted |
| ADR-035 | [Schema Registry and Upcasting](ADR-035-schema-registry-and-upcasting.md) | Accepted |
| ADR-036 | [Canonical Write Bypass Enforcement](ADR-036-canonical-write-bypass-enforcement.md) | Accepted |
| ADR-037 | [Configuration Authority and Drift Prevention](ADR-037-configuration-authority-and-drift-prevention.md) | Accepted |
| ADR-038 | [SDK, MCP, CLI, and HTTP Surface](ADR-038-sdk-mcp-cli-and-http-surface.md) | Accepted |
| ADR-039 | [Retrieval Planning and Tier Fusion](ADR-039-retrieval-planning-and-tier-fusion.md) | Accepted |
| ADR-040 | [Importance, Ranking, and Decay Policy](ADR-040-importance-ranking-and-decay-policy.md) | Accepted |
| ADR-041 | [LLM Extraction and Typed Failure Semantics](ADR-041-llm-extraction-and-typed-failure-semantics.md) | Accepted |
| ADR-042 | [Offline Source Ingestion](ADR-042-offline-source-ingestion.md) | Accepted |
| ADR-043 | [Package Wiring and Public API Governance](ADR-043-package-wiring-and-public-api-governance.md) | Accepted |
| ADR-044 | [Authority, Trust, Confidence, and Relevance Separation](ADR-044-authority-trust-confidence-and-relevance-separation.md) | Accepted |
| ADR-045 | [Procedural Synthesis Approval Boundary](ADR-045-procedural-synthesis-approval-boundary.md) | Accepted |
| ADR-046 | [Core Commit versus Asynchronous Enrichment](ADR-046-core-commit-versus-asynchronous-enrichment.md) | Accepted |
| ADR-047 | [Schema Migration and Legacy Record Compatibility](ADR-047-schema-migration-and-legacy-record-compatibility.md) | Accepted |

| ADR-048 | [Atomic Extraction and Evidence Binding](ADR-048-atomic-extraction-and-evidence-binding.md) | Accepted |
| ADR-049 | [Sensitive Profiles and Purpose-Bound Consent](ADR-049-sensitive-profiles-and-purpose-bound-consent.md) | Accepted |
| ADR-050 | [Phase-Lock Snapshot Verification](ADR-050-phase-lock-snapshot-verification.md) | Accepted |
| ADR-051 | [Explicit References and Lineage Replay](ADR-051-explicit-references-and-lineage-replay.md) | Accepted |
| ADR-052 | [Procedural Synthesis Worker and Approval Boundary](ADR-052-procedural-synthesis-worker-and-approval-boundary.md) | Accepted |
| ADR-053 | [Checkpoint Integrity Utility Boundary](ADR-053-checkpoint-integrity-utility-boundary.md) | Accepted |
| ADR-054 | [Strategy-Specific Hybrid Retrieval Receipts](ADR-054-strategy-specific-hybrid-retrieval-receipts.md) | Accepted |
| ADR-055 | [Canonical Ingress Write Recovery Queue](ADR-055-canonical-ingress-write-recovery-queue.md) | Accepted |
| ADR-056 | [Recursive Harvest Convergence](ADR-056-recursive-harvest-convergence.md) | Accepted |
| ADR-057 | [Verified Deletion and Projection Erasure](ADR-057-verified-deletion-and-projection-erasure.md) | Accepted |
| ADR-058 | [Graphiti Repository Name and Graphite Package Compatibility](ADR-058-graphiti-repository-name-and-graphite-package-compatibility.md) | Accepted |
| ADR-059 | [Recursive Alignment Authority and Applicability](ADR-059-recursive-alignment-authority-and-applicability.md) | Accepted |
| ADR-060 | [Gate-Only Constellation Dispatch](ADR-060-gate-only-constellation-dispatch.md) | Accepted |
| ADR-061 | [Local Receipt Guard Boundary](ADR-061-local-receipt-guard-boundary.md) | Accepted |
| ADR-062 | [L9 Metadata and File Provenance](ADR-062-l9-meta-and-file-provenance.md) | Accepted |
| ADR-063 | [Projection Manifest, Compiler, and Control-Plane Boundaries](ADR-063-projection-manifest-compiler-and-control-plane-boundaries.md) | Accepted |

## Validation

Run:

```bash
python tools/assurance/validate_adrs.py
```

The validator requires a contiguous ADR-001 through ADR-063 ledger and all mandatory sections.
