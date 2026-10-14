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

That surface, on current `main` (package version 2.6.0), authenticates with a static bearer token-to-principal map and is not qualified for remote agents: it has no Streamable HTTP conformance, protocol negotiation or `Origin` validation, and its bearer principal is not equivalent to the signed per-agent identity of the stdio agent door. The centrally hosted HTTPS target (ADR-038 and ADR-083 amendments, 2026-10-13) is not implemented, and this client is not bound to it.

It does not create a second memory authority. It calls the canonical tools already owned by `MemoryService`:

- `memory.hydrate`
- `memory.ingest`
- `memory.promote`
- `memory.health`

<<<<<<< HEAD
Client isolation uses the canonical namespace `client:<clientId>`, and the principal stays server-derived from the configured bearer token; nothing the client sends widens it.
=======
Client isolation uses the canonical namespace `client:<clientId>` and server-derived bearer-token principals remain authoritative.

**3.0.0 (breaking).** The client speaks Streamable HTTP `2025-11-25` (or
`2025-06-18`): it refuses a server that negotiates any other revision and sends
the negotiated `MCP-Protocol-Version` on every request after `initialize`, as
`l9-graphite-memory` 2.7.0 requires (ADR-098). Consequences:

- it requires `l9-graphite-memory` **2.7.0 or later**; earlier servers answer
  `2024-11-05` and are refused;
- `protocolVersion` accepts only `'2025-11-25'` or `'2025-06-18'` (the old
  `'2025-03-26'` default is rejected at construction).

It authenticates as a bearer service principal; it does not carry a signed
agent identity.
>>>>>>> origin/claude/http-mcp-identity-repair-2sx6oy
