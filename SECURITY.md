<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: SECURITY.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
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
- explicit authentication for remote HTTP
- repository-scoped local/stdio claims with administrator authority disabled by default
- deterministic normalization and digests
- admission quarantine
- PII redaction with original source digest retention
- schema upcasting and validation
- atomic receipts and outbox
- CI bypass, config-drift, ADR, and wiring checks

## Secret handling

Generated MCP config files contain only executable and argument data. Tokens, Zep keys, Graphiti credentials, and Infisical machine identity values remain in the runtime environment or external secret manager.

## Reporting

Report vulnerabilities privately to the repository owner. Do not open a public issue containing credentials, personal memory data, tenant identifiers, or exploit details.

## Security non-goals

The default SQLite adapter does not provide database-at-rest encryption. Operators needing encrypted storage must use encrypted volumes or implement a conforming encrypted RecordStore adapter.
