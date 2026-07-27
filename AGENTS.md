<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: AGENTS.md
layer: repository
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-07-27
/L9_META -->

# AGENTS.md

## Repository law

Read `docs/adr/README.md` before changing contracts, authorization, storage, MCP tools, temporal semantics, or release workflows.

## Sacred behavior, not sacred files

No file is immune from correction. These invariants are protected:

1. MemoryService is the canonical control plane.
2. Caller identity is server-derived.
3. Canonical persistence is atomic and evidence-bearing.
4. Valid time and transaction time remain distinct.
5. Graph and semantic systems are projections.
6. No direct store/provider write bypass.
7. No secret persistence in generated config.
8. No release claim without executable validation.
9. Client instantiation flows through `client_config`; no ad hoc MCP config edits.
10. No instantiation claim without a passing `client cursor verify` probe receipt.

## Change requirements

Every material change includes:

- contract impact
- migration impact
- exact wiring path
- tests or validation
- ADR update when a decision changes
- rollback condition

Run `bash scripts/validate_release.sh` before proposing a merge.
