<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/COMPATIBILITY_MATRIX.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Compatibility Matrix

| Surface | v0.2 behavior | v2.2 behavior | Status |
|---|---|---|---|
| repository name | `l9-graphiti-memory` | unchanged | preserved |
| distribution/import | `l9-graphite-memory` / `l9_graphite_memory` | unchanged during compatibility window | preserved |
| CLI entrypoint | `l9-memory` | unchanged and expanded | preserved |
| server entrypoint | `l9-memory-server` | unchanged | preserved |
| worker entrypoint | limited or absent | `l9-memory-worker` with locator-aware outbox | additive |
| direct source script | sometimes documented | unsupported; use entrypoint or `python -m` | corrected |
| MCP legacy tools | write/search/health/bootstrap/phase_lock/conflicts | aliases to canonical `memory.*` tools | preserved |
| Graphiti write tool | older `add_episode` assumption | current `add_memory` preferred, `add_episode` supported | repaired |
| Graphiti fact search | older `search_facts` assumption | current `search_memory_facts` preferred, old name supported | repaired |
| Graphiti deletion | not safely wired | `delete_episode` with persisted locator | implemented |
| Zep deletion | not safely wired | `graph.episode.delete` with persisted locator | implemented |
| group registry | external path mismatch | packaged default plus explicit override | repaired |
| Cursor hook JSON | allow/deny permission object | unchanged shape | preserved |
| gate state | `~/.cursor/graphiti-state` | new path with legacy read compatibility | migrated |
| provider role | canonical-like transport | optional rebuildable projection | intentional architecture change |
| episode JSON | direct episode contract | schema-upcast and import compatibility | preserved through adapter |
| failure on search | empty results possible | typed complete, partial, or failed receipt | intentional correctness break |
| arbitrary remote namespace | accepted | intersected with server-derived claims | security break by design |
| sensitive profile memory | generic fact | purpose-bound consent contract | intentional privacy hardening |
| deletion | undefined or destructive | redacted tombstone plus verified projection erasure | intentional privacy hardening |
| package wheel | registry could be missing | installed-wheel resource and entrypoint smoke | repaired |
| TransportPacket | injected protocol only; shared package unknown | `constellation-node-sdk` from `Quantum-L9/Gate_SDK` `v1.0.1` (`>=1.0.1,<1.1.0`, Python `>=3.12` extra); upgrade by bumping the git tag and supported range together | RP-001 bound |
