<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/WIP/l9-bot-memory-integration-pr-pack/repos/SEO-Bot/pr-body.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

## Summary

Consumes the canonical Website-Bot handoff package, returns the exact acknowledgement contract, initializes all active Router clients, persists atomic budget reservations in operational database, hydrates Graphiti memory for SEO tasks, and promotes only measured successful outcomes into shared memory.

## Type of Change

- [x] Bug fix
- [x] Feature / enhancement
- [x] Refactor (no behavior change)
- [x] Documentation
- [ ] CI / governance change
- [x] Breaking change (see rollback plan below)

---

## Governance Checklist

- [ ] **Governance setup verified** — ran `setup_workspace_symlinks.sh`, symlinks resolve ([§2](https://github.com/Quantum-L9/Cursor-Governance/blob/main/CANONICAL_LAW.md#2-symlink-contract))
- [ ] **Symlinks validated** — `ls -la .cursor/rules .cursor/skills .cursor/commands` all resolve
- [ ] **All CI gates green** — no required checks failing or bypassed
- [x] **Anti-patterns checked** — financial state remains outside cognitive memory; unmeasured recommendations stay in operational database
- [ ] **CODEOWNERS notified** — blast-radius files trigger auto-request; confirmed reviewers assigned
- [x] **Workspace wiring intact** — operational database remains SEO operational authority; Graphiti stores only curated cross-agent knowledge
- [ ] **TRACEABILITY_MAP.yaml updated** — if this PR resolves an open unknown, mark as RESOLVED
- [x] **Kernel ref discipline** — released packages are version-pinned, not sourced from `main`

---

## Breaking Change

- [x] This is a breaking change

`POST /api/clients/register` now accepts the canonical v3 handoff and no longer accepts the legacy local v2 schema. Website-Bot is the migration path and already emits v3. Run the database migration before starting the updated service.

## Rollback Plan

1. Stop SEO-Bot workers and API.
2. Revert this commit.
3. Redeploy the previous application version.
4. The additive budget tables and outcome columns may remain; they are ignored by the prior version. Drop them only after confirming no rollback is needed.

---

## Stack Position

**Stack 4/4**. Depends on all preceding layers.

## Dependencies and Release Gate

Requires `@quantum-l9/graphiti-memory-client@2.0.0`, `@quantum-l9/llm-router@1.1.0`, and `@quantum-l9/bot-interop@1.0.0` published and installable.

## Validation

- `npm run migrate`
- `npm run typecheck && npm test && npm run verify:assurance`
- Start with two replicas and confirm concurrent reservations cannot exceed client/global ceilings.
- Confirm successful measured outcomes receive `memory_record_id` and `memory_promoted_at`; unsuccessful or unmeasured outcomes do not.


## Canonical-memory realignment

- Uses `Quantum-L9/l9-graphiti-memory` as the sole shared cognitive-memory authority.
- Introduces no PostgreSQL/pgvector memory store or dual-write path.
- All durable writes and promotion requests cross the authenticated canonical service boundary.
- Application-local databases remain operational state only.

## Push Contract

- Base branch: `main`
- Base SHA: `0a660de9ac042af3b315fdfeb94d4b8847f42a6e`
- Branch: `feat/persistent-budgets-and-governed-memory`
- Create as a **draft PR** until native CI and the stated release gate pass.
- Do not force-push or bypass required checks.
