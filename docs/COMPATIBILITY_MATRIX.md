<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/COMPATIBILITY_MATRIX.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-10-14
/L9_META -->

# Compatibility Matrix

| Surface | v0.2 behavior | v2.2 / v2.3 behavior | Status |
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
| consumer control plane (2.3) | none; consumers spoke the provider dialect | `l9-memory close` / `capabilities`, `memory.close` idempotency, `HealthReport.contract_version = memory-control-plane/v1`, governed `session_continuation` candidates with lossless `structured_payload` (ADR-082) | additive |
| tag selector (2.3) | none | `tags` on search and hydrate requests (`--tag`, MCP `tags`): a selector, every tag required, admits regardless of query relevance | additive |
| `client cursor verify` (2.3) | probed the generated entry only | with `--path` (or an existing default config) probes the entry as written on disk; receipt carries `argv_source` and `config_path` | corrected |
| HTTP MCP transport (ADR-098 candidate, PR #94, source 2.7.0; unmerged, not a release) | at 2.6.0: `initialize` answered `2024-11-05`; notifications got `200 {"status":"ok"}`; no Origin, Accept, or version-header checks; static bearer only | in the candidate: stateless Streamable HTTP `2025-11-25`/`2025-06-18`: `202` for notifications, `405` for GET/DELETE, `403` bad Origin, `400` absent/unsupported `MCP-Protocol-Version` or batch; `signed-agent` mode verifies the stdio agent evidence per request (ADR-098, `docs/REMOTE_MCP_CONTRACT.md`) | intentional correctness break for HTTP callers; stdio unchanged |
| agent MCP transport | local stdio entry (`client cursor install`) | stdio unchanged in every version; remote HTTPS to one hosted `MemoryService` is the Memory 3.0.0 target, not deployed (ADR-038, ADR-064, ADR-082, ADR-083, ADR-094) | stdio preserved; remote target pending |
| TransportPacket | injected protocol only; shared package unknown | `constellation-node-sdk` from `Quantum-L9/Gate_SDK` `v1.0.1` (`>=1.0.1,<1.1.0`, Python `>=3.12` extra); upgrade by bumping the git tag and supported range together | RP-001 bound |
| Gate client | injected protocol only; package unknown | same pin; `CanonicalGateClient` wraps `GateClient.send_to_gate` / `/v1/health`. Auth and node identity come from `GATE_URL` / `L9_NODE_NAME` / signing env. No peer URL, destination argument, retry, or circuit-breaker | RP-002 bound |

## Release and transport states

Facts as of 2026-10-14. A Git tag, a published artifact, a deployment and
operator release acceptance are separate facts.

| | 2.5.0 (operational) | 2.6.0 / `main@441b741` | ADR-098 candidate (PR #94) | Memory 3.0.0 (target) |
|---|---|---|---|---|
| Status | operator-designated current release | `v2.6.0` tag and published artifact exist; not the operational release | unmerged; source version 2.7.0; not a release | first live release of the remote architecture; not built or deployed |
| stdio MCP | `2024-11-05` | `2024-11-05` | `2024-11-05`, unchanged | supported for local use |
| HTTP MCP | not conforming Streamable HTTP | not conforming Streamable HTTP; static bearer | Streamable HTTP `2025-11-25`, `2025-06-18`; `bearer` or `signed-agent` | signed-agent HTTPS behind TLS on C1 |
| Remote agent identity | none | none (bearer is not an agent identity) | per-request signed agent; credential reusable until expiry; admin grant not refused | same; admin grant refused or excluded by policy (ADR-083) |
| Control-plane contract | per release | `memory-control-plane/v1` | `memory-control-plane/v1` plus `memory-remote-mcp/v1` | same, re-proven on 3.0.0 bytes |
| TypeScript client | client 2.x | client 2.x | client 3.0.0 (bearer only; refuses `2024-11-05`) | client 3.0.0 cannot use a signed-agent server |
| Canonical store for shared use | — | — | HTTP proven on in-memory (suite) and SQLite (wheel proof) stores only | new, empty PostgreSQL; nothing imported |
| Consumer binding | consumer-owned | Cursor-Governance seals agent HTTP | unchanged | each consumer's own campaign |
