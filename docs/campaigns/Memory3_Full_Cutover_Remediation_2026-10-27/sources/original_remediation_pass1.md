# Correctness Remediation Contract — l9-graphiti-memory @ eb0bcbed1e16

status: PROPOSED (not approved, not executed)
authorization: Mutation and publication authority UNKNOWN. Every item below requires an owner decision
and the repository's own gate (`bash scripts/validate_release.sh`, ADR update, rollback condition) before merge.

## Root-cause group RC-1 — Provider error envelope not honored (F-001, U-002, U-006)
Objective: a Graphiti tools/call failure must never settle an outbox event as DELIVERED or create a projection link.
Files: src/l9_graphite_memory/transport.py (call_tool, _rpc), adapters/graphiti_projection.py (_settle_write)
Acceptance:
- call_tool raises ProjectionError when result.isError is truthy (text or JSON content).
- Decide and document whether tool-level JSON-RPC errors count toward the circuit (U-006).
- Verify add_memory argument contract against the pinned Graphiti server; drop or map `metadata` (U-002).
Regression evidence: fake Graphiti fixture returning isError on add_memory -> event RETRY, no projection_links row;
retire/erase of a never-accepted record does not dead-letter.
Cross-component validation: outbox worker + GraphitiProjection + transport integration loop.

## Root-cause group RC-2 — Circuit breaker half-open contract (F-002)
Objective: an OPEN circuit always re-admits a probe after recovery_timeout, regardless of how the previous probe failed.
Files: circuit_breaker.py (can_execute HALF_OPEN branch), transport.py (_rpc/_rpc_once around _ensure_session)
Acceptance: unit test OPEN->HALF_OPEN->unreported probe->timeout->can_execute()==True; _ensure_session failures call record_failure.
Regression evidence: new unit tests; existing transport tests unchanged.

## Root-cause group RC-3 — Error-type overloading in MCP dispatch (F-003)
Objective: -32601 only for unknown tools; missing/invalid arguments -> -32602.
Files: server.py (MCPServer.handle), mcp_tools.py (MCPToolApplication.call/_write_request/_consent_from_payload)
Acceptance: tools/call memory.ingest without namespace -> -32602 naming the field; remote_client classifies it INVALID_REQUEST.
Cross-component validation: tests/unit/test_remote_client.py classification table; tests/integration/test_remote_mcp_http.py.

## Root-cause group RC-4 — Sync stack behind async HTTP handlers (F-004)
Objective: no synchronous store/provider call executes on the event loop.
Files: server.py (mcp_endpoint, healthz, readyz), runtime.py (readiness)
Acceptance: with a 2 s-sleeping projection transport, /healthz responds <500 ms during an in-flight tools/call.
Bounded: do not convert the service stack to async; offload at the transport edge only.

## Root-cause group RC-5 — SQLite adapter hygiene (F-005, F-007)
Objective: faithful error surfacing and complete resource release.
Files: adapters/sqlite_store.py (_transaction, close)
Acceptance: BEGIN failure surfaces 'database is locked'; close() closes connections from all threads.

## Root-cause group RC-6 — Trust-model parity across doors (F-006, U-005)
Objective: identical assertion lifetime ceiling on stdio and HTTP; explicit policy for local_is_admin over auth-disabled HTTP.
Files: authz/signed_assertion.py, server.py (_agent_door_principal, _http_local_principal), ADR-098 (update if policy changes)
Acceptance: stdio refuses exp beyond ceiling+skew; documented decision for U-005.

## Root-cause group RC-7 — Outbox atomicity of retirement evidence (F-008, U-001, U-004)
Objective: retirement receipt and link mutation commit together; complete_deletion idempotent under concurrent erase.
Files: services/outbox_worker.py, ports/record_store.py, both store adapters
Acceptance: fault injection between link drop and receipt still yields a receipt on retry; two-worker erase test completes deletion exactly once.

## Priority order
1. RC-1 (HIGH, data-integrity + deletion lifecycle)  2. RC-2  3. RC-3  4. RC-4  5. RC-7  6. RC-6  7. RC-5

## Required before any remediation claim
- Full test-suite execution on the corrected revision (count pin currently 1955 per commit 4f1284a).
- Re-audit of the truncated/unread surfaces listed in correctness_findings.yaml coverage.access_limits.
