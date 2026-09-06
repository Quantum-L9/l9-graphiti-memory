<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: tests/fixtures/control_plane/README.md
layer: test
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-09-06
/L9_META -->

# Control-plane cross-surface fixtures

Payloads that cross the memory boundary from a consumer, kept here so both
sides of the seam test the same bytes (ADR-082).

| File | Producer | Consumed by |
|---|---|---|
| `continuation_candidate.json` | Cursor-Governance `ContinuationCapsuleV2.to_governed_candidate()` | `tests/unit/test_consumer_conformance.py` here; `tests/ops/memory/test_cross_repo_lifecycle.py` in Cursor-Governance (via `L9_MEMORY_DEV_CHECKOUT`) |

A change to this file is a contract change: update the consumer's expectation
in the same campaign stage.
