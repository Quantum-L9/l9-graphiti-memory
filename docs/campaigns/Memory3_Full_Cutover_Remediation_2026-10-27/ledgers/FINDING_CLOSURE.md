# Finding-by-Finding Closure Requirements

Evidence from attached audit pass 2. **All fixes and live tests NOT_RUN** on new source; mapping is a plan, not closure.

| ID | Severity | Audit finding | Nodes | PR slices | Test status |
|---|---|---|---|---|---|
| F-001 | HIGH | Graphiti tool failures flagged with MCP isError are recorded as successful projections with a durable link | MCP-05, PROJ-02, PROJ-06, PROJ-07, PROJ-08, PROJ-10 | P03, P05, P08 | NOT_RUN |
| F-002 | MEDIUM | Circuit breaker wedges permanently in HALF_OPEN when the probe's outcome is never reported | PROJ-04, PROJ-05 | P05 | NOT_RUN |
| F-003 | MEDIUM | Missing required tool arguments are reported as -32601 'method not found' and misclassified by remote_client as CONTRACT_MISMATCH | MCP-04, HYG-03 | P03, P08 | NOT_RUN |
| F-004 | MEDIUM | HTTP transport runs synchronous blocking I/O inside async handlers | MCP-06, MCP-07 | P03 | NOT_RUN |
| F-005 | LOW | SQLite _transaction masks the real failure when BEGIN IMMEDIATE itself fails | STOR-03, HYG-02 | P09 | NOT_RUN |
| F-006 | LOW | Stdio agent door omits the assertion-lifetime ceiling the HTTP door enforces | HYG-02 | P09 | NOT_RUN |
| F-007 | LOW | SQLiteRecordStore.close() closes only the calling thread's connection and flips the shared initialized flag | STOR-03, HYG-02 | P09 | NOT_RUN |
| F-008 | LOW | Retirement drops the live link and writes the ADR-076 receipt in two separate store operations | LIFE-05, LIFE-06, LIFE-12 | P06 | NOT_RUN |
| F-009 | MEDIUM | Canonical lifecycle mutation complete_deletion (and link/retirement writes) bypass the ServiceWriteCapability gate | LIFE-01, LIFE-02, LIFE-03, LIFE-05, LIFE-07, LIFE-12 | P06 | NOT_RUN |
| F-010 | MEDIUM | PII regexes irreversibly redact non-PII numerics (Unix epochs, 9-digit identifiers); only redacted content is persisted | DATA-01, DATA-03, DATA-06 | P01 | NOT_RUN |
| F-011 | LOW | memory_guard read-only shell classifier accepts mutating commands | DATA-08 | P08 | NOT_RUN |
| F-012 | LOW | MCP write path stamps EXPLICIT evidence on every write, making the identity/preference 'requires explicit evidence' rules vacuous | DATA-04, DATA-06 | P01 | NOT_RUN |
| F-013 | LOW | Store parity: in-memory candidate window is limit*10 while SQLite/Postgres use limit*20 | DATA-09, STOR-05 | P07 | NOT_RUN |
| F-014 | MEDIUM | Zep-backed active projection target reports unhealthy until the first successful call, so /readyz stays 503 until traffic arrives | PROJ-11, PROJ-13 | P08 | NOT_RUN |
| F-015 | LOW | generated_data_capabilities() hard-codes store_ready/ready=True without probing | MCP-07, DATA-10, RET-06 | P03, P07 | NOT_RUN |
| F-016 | LOW | Legacy write-queue drain treats a REJECTED receipt as delivered and removes the pending file; record+unlink is not atomic | STOR-04, HYG-02 | P09 | NOT_RUN |
| F-017 | MEDIUM | Zep write silently truncates the episode body to 10,000 chars while the projection link attests the full content digest | PROJ-11, PROJ-12 | P08 | NOT_RUN |
| F-018 | MEDIUM | Reference-aware retention only counts references inside the loaded record window, so referenced expired records can be archived | RET-01, RET-02, RET-03, RET-04, RET-05 | P07 | NOT_RUN |
| F-019 | LOW | Every JSON-RPC error from Graphiti counts as a circuit failure (promoted from U-006) | PROJ-03, PROJ-05, HYG-03 | P05, P08 | NOT_RUN |
| F-020 | LOW | _run_sync schedules teardown with create_task without retaining the task (promoted from U-007) | HYG-01 | P08 | NOT_RUN |
| U-001 | UNVERIFIED | Lease expiry mid-provider-call may orphan a provider episode when the surviving link locator is a provider uuid | PROJ-09, PROJ-10, LIFE-03, LIFE-04, LIFE-12 | P06, P08 | NOT_RUN |
| U-002 | UNVERIFIED | write() forwards 'metadata' to Graphiti add_memory, which the official tool may not declare | PROJ-01, PROJ-10 | P05, P08 | NOT_RUN |
| U-004 | UNVERIFIED | Concurrent erase events may double-call complete_deletion | LIFE-08, LIFE-09, LIFE-12 | P06 | NOT_RUN |
| U-005 | UNVERIFIED | local_is_admin honored on HTTP auth-disabled Tier-3 principal | DATA-07, STOR-08 | P02, P04 | NOT_RUN |
| U-008 | UNVERIFIED | Secret refresh (SIGHUP / interval) never reaches already-constructed authenticators or settings | STOR-07 | P02 | NOT_RUN |
| U-010 | UNVERIFIED | Tier-3 local principal namespace is settable from L9_MEMORY_NAMESPACE / GRAPHITI_GROUP_ID env with write authority | DATA-07, STOR-08 | P02, P04 | NOT_RUN |
| U-011 | UNVERIFIED | MemorySettings exposes graphiti_mcp_token, zep_api_key and postgres_dsn in repr/model_dump (only graph_neo4j_password has repr=False) | STOR-06 | P02 | NOT_RUN |
| U-012 | UNVERIFIED | MCP consent granted_at defaults to now, so identity/preference writes with a past valid_from are always REJECTED | DATA-05, DATA-06 | P01 | NOT_RUN |
| U-013 | UNVERIFIED | Deferred supersession of a quarantined record may never be applied on release | LIFE-10, LIFE-12 | P06 | NOT_RUN |

## Previously ruled out or promoted

- U-003: disproven (superseded_at not used in filtering, cosmetic stale field). Keep historical disposition.
- U-006: confirmed and promoted to F-019, no duplicate issue.
- U-007: confirmed and promoted to F-020, no duplicate issue.
- U-014: disproven (Pydantic rejects NaN/inf); no new patch required.

## Remediation method contract

A finding closes by an actual negative regression and exact-head test, or by independent source/entrypoint reachability proof that the faulty code was deliberately removed. Deletion lifecycle and provider-copy obligations additionally require live PostgreSQL and provider proof. No code execution or hosted acceptance occurred while authoring this pack.
