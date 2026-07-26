<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/repository-review/open-questions.md
layer: repository_review
owner: memory-control-plane
status: active
version: 2.2.0
pinned_sha: 16d5305c0124d85bf06b719c5bac4c516bfe9085
generated: 2026-07-26
generated_by: Manus AI repository review
/L9_META -->

# Open Questions

This register records the questions that remain genuinely open at pinned SHA `16d5305c0124d85bf06b719c5bac4c516bfe9085` after full repository review. Each question is anchored to the repository's own issue pack (`docs/ISSUE_INDEX.md`, epic RP-EPIC-001) or to a review observation, with owner, blocking status, and resolution path. Nothing here contradicts the local PASS outcome; these are the external-proof and integration questions the repository itself declares unresolvable from inside the pack.

## A. Constellation integration (highest structural risk)

**OQ-1. What is the canonical TransportPacket schema, and does `GateMemoryBridge` bind to it without adaptation?** The bridge accepts an injected packet factory precisely because the canonical model was unavailable during development; the repository states the injected Gate boundary is "intentionally generic." Resolution requires integrating the real packet package and running the bridge unit contract against it. Tracked as **RP-001**; blocks RP-003 and RP-009. Owner: constellation platform team.

**OQ-2. What is the real Gate client interface and dispatch receipt schema?** `derive_or_with_hop` follow-up derivation and dispatch receipt handling are modeled on the documented Gate contract, but no live Gate client exists in-tree (ADR-060 confines the package to Gate-only dispatch). Resolution: bind to the production Gate client and validate receipt round-trips in staging. Tracked as **RP-002**, then rehearsed end-to-end under **RP-003**.

## B. Live provider proof

**OQ-3. Does the Graphiti projection lifecycle (write → locator → search → verified erasure via `delete_episode`) hold against a live Graphiti MCP server, including dialect negotiation across server versions?** Local tests cover both dialects with simulated servers. Tracked as **RP-004**.

**OQ-4. Does the Zep lifecycle, including `graph.episode.delete` erasure confirmation, hold against live Zep Cloud within the `zep-cloud>=3,<4` constraint?** Tracked as **RP-005**.

## C. Operational rehearsal

**OQ-5. Does the v0.2 → v2.2 migration, including schema upcasting and guard-state path migration, survive contact with real legacy data volumes, and does rollback restore a consistent prior state?** `MIGRATION.md` defines the procedure and upcasters are unit-tested, but no rehearsal on production-shaped data exists. Tracked as **RP-006**.

**OQ-6. Are hosted CI, CodeQL, and branch-protection rules actually enforcing on the GitHub repository?** Workflow definitions exist in-tree (`.github/workflows/`), but hosted enforcement cannot be proven from a source checkout. Tracked as **RP-007**, priority P1 — this is the cheapest blocker to retire and gates trust in every subsequent green run.

**OQ-7. Has secret rotation been exercised end-to-end (environment and Infisical paths), proving no stale credential survives rotation?** `secrets.py` and ADR-016 define the boundary; rotation proof is operational. Tracked as **RP-008**.

## D. Review-level observations (not release-blocking)

**OQ-8. Naming drift risk.** The repository is `l9-graphiti-memory` while the package remains `l9-graphite-memory` (ADR-058). The decision is deliberate and documented, but future contributors may introduce inconsistent references; the source-quality gate does not currently lint prose spellings. Suggested disposition: add a lexical check to the assurance suite.

**OQ-9. SQLite at-rest encryption is a declared non-goal** (`SECURITY.md`). This is acceptable for single-operator deployments but should be revisited if the canonical store ever holds multi-tenant production data outside a controlled filesystem. Suggested disposition: record a threshold condition in a future ADR rather than leaving the non-goal unconditional.

**OQ-10. Benchmark scope.** ADR-032 SLOs are proven only on the in-memory store, excluding Gate, provider, network, LLM, and secret-manager latency. Once RP-004/RP-005 environments exist, extend the benchmark to the SQLite adapter and at least one live projection to establish an end-to-end latency budget.

## E. Disposition summary

| Question | Tracker | Blocks release | Resolution venue |
|---|---|---|---|
| OQ-1 TransportPacket binding | RP-001 | Yes | Constellation integration |
| OQ-2 Gate client and receipts | RP-002, RP-003 | Yes | Gate staging |
| OQ-3 Live Graphiti lifecycle | RP-004 | Yes | Provider staging |
| OQ-4 Live Zep lifecycle | RP-005 | Yes | Provider staging |
| OQ-5 Migration and rollback rehearsal | RP-006 | Yes | Ops rehearsal |
| OQ-6 Hosted CI enforcement | RP-007 (P1) | Yes | GitHub settings + first hosted run |
| OQ-7 Secret rotation proof | RP-008 | Yes | Ops rehearsal |
| OQ-8 Naming drift lint | review observation | No | Assurance suite addition |
| OQ-9 At-rest encryption threshold | review observation | No | Future ADR |
| OQ-10 End-to-end benchmark | review observation | No | Post-RP-004/005 |

The final release decision (**RP-009**) consumes the evidence from every blocking row above; until then the repository's own posture — local PASS, production claim withheld — is the correct one.
