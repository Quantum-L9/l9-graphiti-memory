<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: CONTRIBUTING.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Contributing

1. Create a focused branch.
2. Read the ADRs touching your change.
3. Keep adapters thin and route behavior through MemoryService.
4. Add deterministic tests before live-provider tests.
5. Run `bash scripts/validate_release.sh`.
6. Include migration and rollback notes in the pull request.

Direct canonical-store writes outside approved storage internals are rejected by CI. New public modules must have a consumer, entrypoint, or explicit design status.
