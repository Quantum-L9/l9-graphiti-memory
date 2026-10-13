<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: clients/typescript/README.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# @quantum-l9/graphiti-memory-client

Typed Node.js client for the existing authenticated HTTP MCP surface exposed by `l9-graphiti-memory`.

It does not create a second memory authority. It calls the canonical tools already owned by `MemoryService`:

- `memory.hydrate`
- `memory.ingest`
- `memory.promote`
- `memory.health`

Client isolation uses the canonical namespace `client:<clientId>` and server-derived bearer-token principals remain authoritative.

Since 2.1.0 the client speaks Streamable HTTP `2025-11-25` (or `2025-06-18`):
it refuses a server that negotiates any other revision and sends the negotiated
`MCP-Protocol-Version` on every request after `initialize`, as
`l9-graphite-memory` 2.7.0 requires (ADR-098). It authenticates as a bearer
service principal; it does not carry a signed agent identity.
