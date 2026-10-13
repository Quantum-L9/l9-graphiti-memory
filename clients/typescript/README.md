<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: clients/typescript/README.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-10-13
/L9_META -->

# @quantum-l9/graphiti-memory-client

Typed Node.js client for the existing authenticated HTTP MCP surface exposed by `l9-graphiti-memory`.

That surface, in the 2.6.0 release, authenticates with a static bearer token-to-principal map and is not qualified for remote agents: it has no Streamable HTTP conformance, protocol negotiation or `Origin` validation, and its bearer principal is not equivalent to the signed per-agent identity of the stdio agent door. The centrally hosted HTTPS target (ADR-038 and ADR-083 amendments, 2026-10-13) is not implemented, and this client is not bound to it.

It does not create a second memory authority. It calls the canonical tools already owned by `MemoryService`:

- `memory.hydrate`
- `memory.ingest`
- `memory.promote`
- `memory.health`

Client isolation uses the canonical namespace `client:<clientId>`, and the principal stays server-derived from the configured bearer token; nothing the client sends widens it.
