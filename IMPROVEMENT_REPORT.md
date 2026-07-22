<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: IMPROVEMENT_REPORT.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Improvement Report

## Objective

Recursively compare the v2 rewrite with all prior pack audits, implement every missed in-scope concept, preserve valid compatibility, and produce evidence-backed release artifacts.

## Baseline

The v2.0 pack had a working canonical memory service, bi-temporal store, authorization, admission, retrieval, outbox, CLI/MCP adapters, and ADR ledger. Its own documents still marked several promised harvests as partial or deferred, and provider erasure lacked a stable locator path.

## Recursive passes

| Pass | Main finding | Accepted improvement | Validation state |
|---|---|---|---|
| 1 | Pack promises and implementation inventory diverged | built extraction, profiles, consent, lineage, recovery, procedural, and phase-lock closure | tests advanced through 78 and 82 passing checkpoints |
| 2 | Hybrid strategy labels exceeded actual execution | made graph and semantic strategies execute independently with per-strategy receipts | expanded suite passed |
| 3 | Privacy deletion could not prove provider erasure | added `ProjectionLink`, SQLite schema v4, locator-aware outbox, Graphiti and Zep erasure | 93 tests passed |
| 4 | Graphiti provider dialect had evolved | added live inventory negotiation for current and legacy tool names | 103 tests passed |
| 5 | Completion was not machine-proven | added 44-decision harvest ledger, validator, secret scan, SLO benchmark, and regenerated docs | full release validation passed |

## Accepted improvements

- 16 new or materially expanded production modules
- provider locator persistence and erasure
- current Graphiti MCP tool compatibility
- consent-governed profiles and deletion
- evidence-bound extraction and distillation
- lineage, procedural, recovery, and phase-lock verification
- harvest coverage assurance
- release evidence and operator docs

## Rejected improvements

The following were rejected because they would recreate monolith coupling or duplicate authority:

- mandatory multi-database and LLM infrastructure
- agent checkpoint ownership
- world-model and reasoning nodes in the write transaction
- direct provider or SQL recovery writes
- duplicate memory service in L9-Ops-MCP
- raw private source data in fixtures

## Regression checks

- Distribution and import names remain compatible.
- CLI and MCP entrypoints remain intact.
- Legacy MCP aliases remain present.
- Canonical write bypass and silent provider fallback remain prohibited.
- Existing hook output contracts remain unchanged.
- SQLite migration is additive and retains canonical records.

## Remaining gaps

Only external proof remains:

- live Graphiti and Zep operations
- production-like migration and rollback
- credential loading and rotation
- hosted Ruff, strict mypy, CodeQL, branch protection, and release environment

## Decision

The artifact is approved as a complete recursive closure pack for review and external validation. Production release remains blocked on the named external gates.
