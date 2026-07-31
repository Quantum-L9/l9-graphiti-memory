<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/WIP/l9-bot-memory-integration-pr-pack/RECURSIVE_AUDIT_REPORT.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Recursive Audit Report

## Decision

The prior Graphiti-canonical pack was **not safe to apply unchanged**. It contained one critical live-compatibility defect, two high correctness defects, and several validation/packaging defects. All confirmed pack-local findings below were repaired.

## Adapter routing

- Universal evidence core
- Repository and architecture review
- Artifact-quality and validation review
- Recursive improvement
- L9 platform adapter because the artifact is an L9 multi-repository integration pack

## Confirmed findings and repairs

### F-001: Client rejected the pinned canonical server

- Severity: critical
- Evidence: the client required `Mcp-Session-Id`; the pinned `server.py` returns no session header and treats initialized notifications statelessly.
- Impact: every real consumer initialization failed despite mock tests passing.
- Repair: made session support optional, added an explicit initialized state, retained optional propagation for newer servers, and added a pinned-stateless-server contract test.

### F-002: Package versions were mutually unsatisfiable

- Severity: high
- Evidence: the client package declared `1.0.0`, LLM-Router required `^2.0.0`, and Website/SEO required `^1.0.0`.
- Impact: the four PRs could not converge on one published artifact.
- Repair: standardized the client and all consumers on `2.0.0` / `^2.0.0`; added a machine validation gate.

### F-003: SEO fabricated corroboration

- Severity: high
- Evidence: each individual outcome was promoted with `testSuccessCount: 2` despite only one measured row being evaluated.
- Impact: uncorroborated observations could be mislabeled as validated learnings.
- Repair: record single outcomes as observations, group matching measured outcomes, require at least two records, supply actual supporting record IDs, and use the real support count.

### F-004: Promotion failures were stranded

- Severity: high
- Evidence: once `memoryRecordId` was persisted, the old query excluded the row even when promotion failed.
- Impact: transient failures became permanent silent non-promotion.
- Repair: select all successful measured but unpromoted rows; reuse existing receipt pointers and retry promotion idempotently.

### F-005: TypeScript validation ignored compiler errors

- Severity: high
- Evidence: `tsc ... || true` and forced emit allowed tests to run against code with type errors.
- Impact: pass claims did not prove compilability.
- Repair: compiler diagnostics are now fatal; a narrow local Node ambient shim replaces unavailable registry typings without suppressing project errors.

### F-006: Endpoint normalization could create `/mcp/mcp`

- Severity: medium
- Evidence: the client unconditionally appended `/mcp`.
- Impact: operators supplying the documented endpoint rather than host root received 404s.
- Repair: normalize either host roots or existing `/mcp` URLs to exactly one endpoint.

### F-007: Stateless clients reinitialized before every call

- Severity: medium
- Evidence: initialized state was inferred only from presence of a session ID.
- Impact: the canonical stateless server incurred repeated initialize/notification traffic.
- Repair: track protocol initialization independently from optional sessions and test multiple calls.

### F-008: Notification handling assumed a JSON-RPC response

- Severity: medium
- Evidence: initialized notifications used the ordinary response parser.
- Impact: legal empty 202/204 notification responses failed.
- Repair: added a notification-specific HTTP path accepting empty successful responses.

### F-009: Hydration inputs were not bounded client-side

- Severity: medium
- Evidence: invalid budgets, record limits, and empty tasks crossed the network.
- Impact: malformed environment values produced avoidable runtime errors.
- Repair: enforce the canonical MCP bounds before transport.

### F-010: Failed hydration could still enter prompts

- Severity: medium
- Evidence: rendering checked only whether sections existed.
- Impact: malformed or stale failed results could be injected into model context.
- Repair: failed hydration now renders as an empty string.

### F-011: Multiline SSE events were parsed incorrectly

- Severity: medium
- Evidence: every `data:` line was treated as a separate payload.
- Impact: valid multiline SSE JSON could not be decoded.
- Repair: join data lines within each SSE event and parse the final event payload.

### F-012: Release artifact contained Python caches

- Severity: low
- Evidence: `__pycache__/*.pyc` files were shipped and validation regenerated them.
- Impact: non-source noise, nondeterministic artifact churn, and misleading manifest scope.
- Repair: removed caches, replaced compileall with AST parsing, and added a hard hygiene gate.

### F-013: Memory PR base pin contradicted the stated grounded SHA

- Severity: high
- Evidence: docs declared `f5b802...`; `apply.sh` required `4aa86f...`.
- Impact: the canonical overlay refused the repository state it claimed to target.
- Repair: aligned the apply pin to `f5b802a8aafcba1590a5a90966b9efbc411d2c0c`.

## Validation

- Strict TypeScript compilation of isolated packages
- Node contract tests
- Canonical stateless MCP dialect test
- Optional session dialect test
- Endpoint normalization test
- Multiline SSE test
- Apply-script rollback and wrong-origin tests
- Version-convergence gate
- Corroboration-policy static gates
- Python AST and JSON parsing
- Cache, CRLF, secret, placeholder, PostgreSQL-shadow, and pgvector-shadow scans
- Manifest verification and clean-extraction rerun

## Residual external gates

- Native CI in all four repositories
- Publishing `@quantum-l9/graphiti-memory-client@2.0.0`
- Live bearer-token authorization and namespace tests
- Real legacy PostgreSQL/pgvector export and receipt reconciliation
- Production concurrency and outage testing

## Convergence

Three adversarial passes were completed. No confirmed pack-local release blocker remains. Further proof requires the four actual repositories or live infrastructure and is therefore retained as an external gate rather than simulated.
