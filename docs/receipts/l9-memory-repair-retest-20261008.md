<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/receipts/l9-memory-repair-retest-20261008.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.6.0
updated: 2026-07-22
/L9_META -->

# L9 memory repair retest receipt

Campaign `L9-MEMORY-REPAIR-RETEST-002`. Recorded 2026-10-08. This receipt lists the runs and their statuses. It does not authorize a production cutover, a rebind of `l9-graphite-memory` 2.5.0, or a push.

Source evidence is under `/Users/ib-mac/tmp/l9-memory-repair-retest-20261008/`. The narrative report is `L9_MEMORY_REPAIR_RETEST_REPORT.md` in that directory.

## Staged fixes

| Repo | Base | Fix |
|---|---|---|
| `l9-graphiti-memory` | `407041f6c533ff3f647fadc889fe2b424d20b963` | Six files staged on `fix/memory-repair-retest-002`. Search abandonment stays `runtime_budget_exhausted`. Release paths no longer call GNU `realpath -m`. An absolute `L9_MEMORY_MCP_COMMAND` becomes the managed Cursor command. |
| `Cursor-Governance` | `bd6b403e4c6fdcee0589cf19a1aecf8af64bc4db` | Four files staged on `main`. Install and verify set `L9_MEMORY_MCP_COMMAND` to `ops/memory/run_memory_mcp.sh`. |

`.github` was not modified. Live `~/.cursor/mcp.json` was not rewritten. The 434-record SQLite ledger was not switched to Postgres.

## Runs

| Run | Status | Result |
|---|---|---|
| Memory suite, URI-shaped test DSN (`logs/mem-pytest-repair.txt`) | discarded | Harness failure. `options=-csearch_path` was parsed as part of the database name. 21 failed, 1452 passed, 60 skipped, 106 errors. Not a product result. |
| Memory suite, keyword DSN, Redis unset (`logs/mem-pytest-repair-2.txt`) | superseded | 1579 passed, 60 skipped, exit 0. Extra skips were the unset Redis URL. |
| Memory suite, keyword DSN, disposable Postgres 16 and Redis 7 (`logs/mem-pytest-repair-3.txt`) | **PASS** | Collected 1639. **1599 passed, 0 failed, 40 skipped, 0 errors.** 45.30s. Exit 0. This is the authoritative memory run. |
| Stalled-search test, 20 consecutive repeats | **PASS** | Same token each time: `runtime_budget_exhausted` at stage `provider`. |
| Darwin release-shell and cursor-config modules | **PASS** | Inside the authoritative suite, including symlink and spaced-path guards. |
| Linux `python:3.12` guard replay | **PASS** | Unsafe paths were rejected with the original guard messages, including a symlink that resolved to `docs/adr`. |
| Cursor-Governance launcher tests on the repair branch | **PASS** | 22 passed, 2 skipped. Skips are the real-configurator proofs because `L9_MEMORY_DEV_CHECKOUT` was unset. The new launcher env assertions passed. |
| Subject A lifecycle, pinned wheel (`logs/subject-a-rerun.json`) | **PASS** | 5 passed, 0 skipped, 14.86s. Binding `compatible`. Source `78b304a3948214fa4b17bf97ed0529c5b0c22673`. Wheel `794ad0e6e0b9c278623ff79314ae70ee539ce0cd7bea772ce8556400887cab3a`. |
| Product topology at `07b0df96` (`logs/topology-07b0df96.txt`) | **PASS** | `validate_product_topology.py` exit 0. Pin left unchanged. |
| Product topology at `9b27869` (`logs/topology-9b27869.txt`) | **FAIL** | Provenance does not pin that HEAD, and `semantics/contracts.yaml` is not pinned at `4b4ca1b7abf456ba28df2f2a8071412a2bd1ff84`. Expected for this classification. Pin not updated. |
| `.github` semantic validator | not rerun | Acceptance run at `9b27869` was 41 PASS, 0 FAIL, RC-023-NEG 57. Head was unchanged, so it was not repeated. |
| Live signed-agent launcher spawn | **FAIL** | Process exited 1. `AgentDoorGrant` rejected `tenant_id`, `organization_id`, `workspace_id`, and `agent_id`. Live ledger unchanged. |
| Hosted Claude Code Mobile session | not run | No hosted session. No remote marker was set. |

Subject A tests, all passed:

- `test_lifecycle_against_the_real_memory_runtime`
- `test_hook_distill_record_bound_holds_against_the_exact_bound_cli`
- `test_recency_search_holds_against_the_exact_bound_cli`
- `test_task_isolation_and_refinement_supersession_against_the_real_runtime`
- `test_canonical_actor_identity_handoff`

## Authoritative memory skips

Pytest reported 40 skipped. The log printed 37 `SKIPPED` lines. None of them are the budget or release-shell repairs.

| Reason | Printed lines |
|---|---|
| `L9_MEMORY_TEST_NEO4J_URI` is not set | 24 |
| `constellation_node_sdk` is not installed | 10 |
| qualification needs `graphiti-core==0.30.2` | 1 |
| identity is not writable on the agent lane | 1 |
| `CURSOR_GOVERNANCE_ROOT` is not configured | 1 |

## Finding status

| ID | Status |
|---|---|
| F-MEM-001 budget token | FIXED |
| F-MEM-002 Darwin realpath | FIXED |
| F-MEM-003 topology pin | ALREADY_SATISFIED |
| F-MEM-004 exact artifact guard | ALREADY_SATISFIED |
| F-MEM-004 production rebind | BLOCKED |
| F-RT-001 shared store | BLOCKED |
| F-RT-002 live signed-agent process | BLOCKED |
| F-EXT-001 Claude Code Mobile | BLOCKED |
