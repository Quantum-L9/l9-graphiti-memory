# C1 Memory legacy retirement operator decision

**Date:** 2026-10-26  |  **Campaign revision:** 1.2

## Accepted input

- The operator stated that the old C1 Memory store was backed up and independently **verified by them**.
- The operator authorized deletion and replacement with a new store.
- The operator accepted the 12-node graph; the topology and 13 edges are unchanged.

## Decision effect

- Legacy backup verification is **closed based on direct operator attestation**. No redundant old SQLite restore test.
- Scoped C1 Memory 2.2.0 retirement and corresponding SQLite deletion are **operator-approved** for the controlled replacement; actual execution remains conditional on new Memory 3.0 deployment readiness and established publication/deployment gates.
- No historical records need to be migrated; canonical replacement is a new empty PostgreSQL store.
- Reuse `memory.quantumaipartners.com` and existing Caddy upstream loopback `127.0.0.1:8200`, after confirming present routing and stopping the old listener.
- After new runtime passes `/readyz`, signed `/mcp`, and no-neighbor-regression checks, retire/delete obsolete local service/store files. Preserve the verified backup.
- The **new PostgreSQL database** has separate backup, isolated restore and rollback acceptance. This is not a re-test of the old backup.

## Explicit negative scope

No change to the Graphiti route `/graphiti/*` or its listener 8100, Neo4j volumes/episodes, other Hetzner servers, Cognitive Runtime/port 18080, arbitrary C1 workloads, L9 global semantics, or deployment-platform invariants. No actual deployment or deletion occurred while recording this decision.
