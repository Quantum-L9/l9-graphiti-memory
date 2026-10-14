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

This README describes client package **3.0.0** (an npm package version; it is not Memory 3.0.0). The client speaks the `memory-remote-mcp/v1` HTTP contract introduced by the ADR-098 candidate (PR #94, server source version 2.7.0, unmerged at 2026-10-14). It works only against a server that implements that contract in **bearer** mode, and it is not bound to, or evidence of, any deployment, including the Memory 3.0.0 C1 target. Released servers (2.5.0, 2.6.0) answer `2024-11-05` and are refused.

It does not create a second memory authority. It calls the canonical tools already owned by `MemoryService`:

- `memory.hydrate`
- `memory.ingest`
- `memory.promote`
- `memory.health`

Client isolation uses the canonical namespace `client:<clientId>`, and the principal stays server-derived from the configured bearer token; nothing the client sends widens it.

**3.0.0 (breaking).** The client speaks Streamable HTTP `2025-11-25` (or
`2025-06-18`): it refuses a server that negotiates any other revision and sends
the negotiated `MCP-Protocol-Version` on every request after `initialize`, as
the ADR-098 server requires. Consequences:

- it requires a server implementing `memory-remote-mcp/v1` (the ADR-098
  candidate, source version 2.7.0, or a later release that carries it);
  earlier servers answer `2024-11-05` and are refused;
- `protocolVersion` accepts only `'2025-11-25'` or `'2025-06-18'` (the old
  `'2025-03-26'` default is rejected at construction).

It authenticates as a bearer service principal; it does not carry a signed
agent identity. A server runs one HTTP authentication mode, so this client
cannot use a server in `signed-agent` mode, which is the mode the 3.0.0 agent
deployment requires.
