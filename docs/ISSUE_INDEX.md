# Issue Index

The issue IDs below are stable pack identifiers. GitHub issue numbers are assigned only when the creation script is executed.

| ID | Priority | Title | Dependencies | Release role |
|---|---:|---|---|---|
| [RP-EPIC-001](issues/rp-epic-001-complete-external-production-proof-for-l9-graphiti-memory-v2-2.md) | P0 | Complete external production proof for l9-graphiti-memory v2.2 | None | Epic |
| [RP-001](issues/rp-001-integrate-the-authoritative-transportpacket-package.md) | P0 | Integrate the authoritative TransportPacket package | None | Child release blocker |
| [RP-002](issues/rp-002-integrate-the-production-gate-client-and-dispatch-receipt-schema.md) | P0 | Integrate the production Gate client and dispatch-receipt schema | None | Child release blocker |
| [RP-003](issues/rp-003-execute-a-credentialed-gate-staging-packet-lifecycle-rehearsal.md) | P0 | Execute a credentialed Gate staging packet-lifecycle rehearsal | RP-001, RP-002 | Child release blocker |
| [RP-004](issues/rp-004-prove-the-live-graphiti-lifecycle-and-outbox-replay-path.md) | P0 | Prove the live Graphiti lifecycle and outbox replay path | None | Child release blocker |
| [RP-005](issues/rp-005-prove-the-live-zep-lifecycle-and-outbox-replay-path.md) | P0 | Prove the live Zep lifecycle and outbox replay path | None | Child release blocker |
| [RP-006](issues/rp-006-rehearse-production-like-legacy-migration-and-rollback.md) | P0 | Rehearse production-like legacy migration and rollback | None | Child release blocker |
| [RP-007](issues/rp-007-prove-hosted-ci-security-scanning-branch-protection-and-release-controls.md) | P1 | Prove hosted CI, security scanning, branch protection, and release controls | None | Child release blocker |
| [RP-008](issues/rp-008-prove-external-secret-loading-rotation-revocation-and-no-plaintext-persistence.md) | P0 | Prove external secret loading, rotation, revocation, and no-plaintext persistence | None | Child release blocker |
| [RP-009](issues/rp-009-aggregate-external-evidence-and-authorize-the-v2-2-production-release.md) | P0 | Aggregate external evidence and authorize the v2.2 production release | RP-001, RP-002, RP-003, RP-004, RP-005, RP-006, RP-007, RP-008 | Final release decision |

## Dependency graph

```text
RP-001 TransportPacket ─┐
                        ├─> RP-003 Gate staging ─┐
RP-002 Gate client ─────┘                       │
RP-004 Graphiti lifecycle ─────────────────────┤
RP-005 Zep lifecycle ──────────────────────────┤
RP-006 Migration/rollback ─────────────────────┤─> RP-009 Release decision
RP-007 Hosted CI/governance ───────────────────┤
RP-008 Secret lifecycle ───────────────────────┘

RP-EPIC-001 tracks RP-001 through RP-009.
```
