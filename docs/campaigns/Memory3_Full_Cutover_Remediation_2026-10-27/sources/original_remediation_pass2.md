# Correctness Remediation Contract — l9-graphiti-memory @ eb0bcbed1e16
status: PROPOSED (not approved, not executed). Mutation/publication authority UNKNOWN. Every item requires owner decision, `bash scripts/validate_release.sh`, ADR update where a decision changes, and a rollback condition.

## RC-1 Provider error envelope (F-001 HIGH, F-017, F-019, U-002)
Objective: a provider failure can never settle DELIVERED or install a link; attested digests match delivered bytes.
Files: transport.py (call_tool, _rpc), adapters/graphiti_projection.py (_settle_write), zep_transport.py (write)
Acceptance: isError => ProjectionError; body > provider limit => ProjectionError (or truncated=True + delivered digest); -32602 does not count toward the breaker; add_memory argument contract verified against the pinned server.
Regression: fake Graphiti isError fixture => RETRY, no projection_links row; >10k Zep body test; breaker count test.

## RC-2 Breaker contract (F-002)
Files: circuit_breaker.py, transport.py. Acceptance: HALF_OPEN re-arms after recovery_timeout; _ensure_session failures record_failure.

## RC-3 Dispatch error typing (F-003)
Files: server.py, mcp_tools.py. Acceptance: missing argument => -32602; remote_client classifies INVALID_REQUEST.

## RC-4 Async edge (F-004)
Files: server.py, runtime.py. Acceptance: /healthz < 500 ms during a 2 s tools/call. Bounded: offload at the edge only.

## RC-5 SQLite hygiene (F-005, F-007)
Files: adapters/sqlite_store.py. Acceptance: BEGIN failure surfaces real error; close() releases all threads' connections.

## RC-6 Door parity & policy (F-006, U-005, U-010)
Files: authz/signed_assertion.py, server.py, group_resolver.py; ADR-098/ADR-006 decisions. Acceptance: shared TTL ceiling; documented decision on local_is_admin over HTTP and env-namespace override.

## RC-7 Outbox/deletion atomicity & authority (F-008, F-009, U-001, U-004, U-013)
Files: ports/record_store.py, services/outbox_worker.py, services/memory_service.py, all store adapters.
Acceptance: complete_deletion requires the capability (or invariant 6 amended); retirement link+receipt in one transaction; complete_deletion idempotency test on all three adapters; decision+test on deferred supersession at quarantine release; lease-expiry two-worker test.

## RC-8 Admission data integrity (F-010, F-012, U-012)
Files: admission/normalization.py, mcp_tools.py. Acceptance: epoch/9-digit ids not redacted; sensitive-class explicit-evidence rule enforceable over MCP; consent timing decision documented.

## RC-9 Readiness truthfulness (F-014, F-015)
Files: zep_transport.py, services/generated_data.py. Acceptance: fresh Zep transport probes; capability report derives from health.

## RC-10 Retention & migration scope (F-018, F-016)
Files: curation/retention.py, maintenance/*, migration/legacy_write_queue.py. Acceptance: incoming references counted via store query; REJECTED drain items retained.

## RC-11 Misc (F-011, F-013, F-020)
Files: memory_guard.py, adapters/in_memory_store.py, runtime.py.

## Priority order
RC-1 → RC-7 → RC-2 → RC-3 → RC-8 → RC-4 → RC-9 → RC-10 → RC-6 → RC-5 → RC-11

## Preconditions for any remediation claim
Full test-suite execution on the corrected revision (pin currently 1955); completion of the audit over the blocked files listed in source_coverage.yaml.
