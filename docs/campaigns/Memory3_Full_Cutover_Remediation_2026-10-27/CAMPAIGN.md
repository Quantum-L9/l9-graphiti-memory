# C1 Shared Memory Campaign: Full Cutover Successor v2.0

**Date:** 2026-10-27 | **Status:** Working, non-admitted; repository and runtime unchanged.

The earlier v1.2 campaign already identified C1, the protected neighboring services, an operator-reported verified legacy SQLite backup and a narrow permission to remove that one legacy service/store **after** a working replacement. Those historical observations and decisions remain in the unchanged source files and original predecessor ZIP. This successor does **not** reopen historical backup work.

## New locked target

Memory 3.0 is one **Auth0 OAuth protected, native MCP Streamable HTTP** service at `memory.quantumaipartners.com`, with one new PostgreSQL 16 canonical store. Historical transport compatibility is explicitly **not** required. Remove stdio, signed-agent headers/HMAC, static bearer service auth, SQLite server fallback and migration queue. Client-specific OAuth lives in Claude and Cursor host-managed connection flows. Infisical is reserved for server secrets, not pasted client bearers.

Identity resolution covers product, release, runtime, actor, surface and constellation applicability with distinct governing sources. User OAuth tokens do not prove program identity; neither a shared account connector nor a local environment variable proves a per-request mobile surface. Material unknown actor attribution fails closed, while unproved surface stays Unknown.

## Source and PR posture

- Memory main `eb0bcbed1e1652529675af52584185d2f09dd737` remains audited baseline.
- [Memory PR #101](https://github.com/Quantum-L9/l9-graphiti-memory/pull/101) at `52d1e4bba2ab8f56f1e73bb5254b79d8e3a818f2` is only an unmerged C1 carrier candidate and still pins signed-agent mode; do not merge it until OAuth-only retargeting.
- [Cursor PR #784](https://github.com/Quantum-L9/Cursor-Governance/pull/784) at `e9c42599c83ceefccd33576fd6ea9d085e5c3cc8` is a consumer PR, not the server authority; it needs verified native OAuth and full actor/surface binding.
- The original correctness audit's 20 confirmed findings and nine unresolved concerns have workstream nodes and tests in `remediation_graph.json`. No correction was implemented or tested in this planning task.

## Milestone routing

`GOV-03` successor ADR -> `DATA-06` canonical sensitive truth + `AUTH-13` complete identity + `MCP-08/MCP-12` native protocol -> `AUTH-15/MCP-03/STOR-03` old paths removed -> `QA-03/QA-04/QA-09` release gates -> `OPS-01` PR101 retarget -> `CONS-01..09` PR784 and real connectors -> `CUT-01..13` C1 service proof.

Parallel correctness lane: `PROJ-02/04/06/07` provider success and breaker -> `LIFE-03/05/07/10` atomic service-owned lifecycle -> `RET-02/03` incoming refs -> `QA-05/06/07` integrated proof -> `CUT-14` full correctness. Operator and independent acceptance converge at `CUT-15`.

**The key distinction:** `CUT-13` proves working core shared memory. `CUT-14` proves the entire audited product remediation. Neither can self-authorize `CUT-15`.

See `README.md`, `graphs/`, `ledgers/`, `contracts/PR_SEQUENCE.md` and `runbooks/CUTOVER_RUNBOOK.md` for the executable plan.
