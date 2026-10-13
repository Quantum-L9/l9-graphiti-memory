<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: SECURITY.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-10-13
/L9_META -->

# Security

## Threat model

The system defends against:

- caller identity spoofing
- cross-tenant and cross-namespace access
- replay and duplicate writes
- credential persistence or logging
- prompt-injection-like content entering active retrieval without review
- PII leakage
- direct-store or provider write bypasses
- silent backend failure
- stale or malicious schema versions

## Controls

- server-side MemoryPrincipal
- separate read, write, promote, archive, and admin claims
- tenant predicates in every store operation
- explicit authentication for HTTP; unauthenticated HTTP refused on a non-loopback bind
- repository-scoped local/stdio claims with administrator authority disabled by default
- deterministic normalization and digests
- admission quarantine
- PII redaction with original source digest retention
- schema upcasting and validation
- atomic receipts and outbox
- CI bypass, config-drift, ADR, and wiring checks

## Remote HTTP: target boundary and current gaps

The target agent transport is a centrally hosted HTTPS MCP service (ADR-038
amendment, 2026-10-13). It is not implemented. The proposed boundary
(ADR-083 amendment, 2026-10-13) requires of any implementation:

- a per-request principal established server-side from an authenticated,
  per-agent credential with the same canonical identity proof the stdio agent
  door requires;
- no anonymous or local-operator fallback, and no role, tenant, grant or
  administrator escalation from any request field;
- human-door and administrator authority unreachable through the agent
  endpoint;
- ADR-006 tenant and namespace isolation, unchanged;
- `Origin` validation and protocol-version handling as the pinned MCP revision
  requires;
- TLS terminated at a trusted reverse proxy, with the service itself bound
  where only that proxy can reach it;
- credentials, signing keys and the PostgreSQL DSN held in the runtime secret
  path, never in tracked files, generated client configuration or logs.

Known gaps in the HTTP server on current `main` (package version 2.6.0), none of which this documentation
changes:

- static bearer token-to-principal authentication, not equivalent to the
  signed agent door; a token's principal may carry `is_admin` or
  `is_global_admin`, so administrator authority is reachable over HTTP if the
  token map grants it;
- `/healthz`, `/readyz` and FastAPI's default `/docs`, `/redoc` and
  `/openapi.json` are served without authentication;
- no `Origin` validation, protocol negotiation or `WWW-Authenticate`
  challenge;
- HMAC agent assertions are not nonce-tracked, so one is replayable until it
  expires; keep assertion lifetimes short and use them only as the stdio
  process credential they were designed as;
- auth-disabled loopback HTTP serves the stdio principal, which is the
  administrator when `L9_MEMORY_HUMAN_DOOR_SECRET` is set.

Do not expose the current HTTP server to remote agents.

## Secret handling

Generated MCP config files contain only executable and argument data. Tokens, Zep keys, Graphiti credentials, and Infisical machine identity values remain in the runtime environment or external secret manager.

## Reporting

Report vulnerabilities privately to the repository owner. Do not open a public issue containing credentials, personal memory data, tenant identifiers, or exploit details.

## Security non-goals

The default SQLite adapter does not provide database-at-rest encryption. Operators needing encrypted storage must use encrypted volumes or implement a conforming encrypted RecordStore adapter.
