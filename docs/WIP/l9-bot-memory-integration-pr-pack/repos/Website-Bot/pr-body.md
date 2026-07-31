<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/WIP/l9-bot-memory-integration-pr-pack/repos/Website-Bot/pr-body.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

## Summary

Removes the local LLM stub, activates the published Router, creates the canonical `@quantum-l9/bot-interop` handoff package, hydrates bounded Graphiti memory before LLM work, and writes verified website release/content facts after release evidence converges.

## Type of Change

- [x] Bug fix
- [x] Feature / enhancement
- [x] Refactor (no behavior change)
- [x] Documentation
- [ ] CI / governance change
- [ ] Breaking change (see rollback plan below)

---

## Governance Checklist

- [ ] **Governance setup verified** — ran `setup_workspace_symlinks.sh`, symlinks resolve ([§2](https://github.com/Quantum-L9/Cursor-Governance/blob/main/CANONICAL_LAW.md#2-symlink-contract))
- [ ] **Symlinks validated** — `ls -la .cursor/rules .cursor/skills .cursor/commands` all resolve
- [ ] **All CI gates green** — no required checks failing or bypassed
- [x] **Anti-patterns checked** — memory hydration is bounded; raw stage noise is not promoted; Router remains memory-agnostic
- [ ] **CODEOWNERS notified** — blast-radius files trigger auto-request; confirmed reviewers assigned
- [x] **Workspace wiring intact** — release evidence remains Website-Bot authority and Graphiti receives only converged release facts
- [ ] **TRACEABILITY_MAP.yaml updated** — if this PR resolves an open unknown, mark as RESOLVED
- [x] **Kernel ref discipline** — package consumers pin released semantic versions

---

## Breaking Change

- [ ] This is a breaking change

The external handoff remains protocol `l9.website-factory.handoff/3.0`; the change centralizes its implementation rather than changing its wire shape.

## Rollback Plan

Revert this commit, restore `src/services/llm-stub.ts`, and remove the three package dependencies. Existing filesystem evidence and SQLite build records are unaffected.

---

## Stack Position

**Stack 3/4**. Depends on `memory-client` and `router-budget-port`.

## Dependencies and Release Gate

Requires `@quantum-l9/graphiti-memory-client@2.0.0` and `@quantum-l9/llm-router@1.1.0` published and installable. After merge, publish `@quantum-l9/bot-interop@1.0.0`.

## Validation

- `npm --prefix packages/bot-interop run verify:all`
- `npm run verify:all`
- End-to-end mode produces handoff evidence, writes one idempotent release fact, and receives the exact digest-bound SEO acknowledgement.


## Canonical-memory realignment

- Uses `Quantum-L9/l9-graphiti-memory` as the sole shared cognitive-memory authority.
- Introduces no PostgreSQL/pgvector memory store or dual-write path.
- All durable writes and promotion requests cross the authenticated canonical service boundary.
- Application-local databases remain operational state only.

## Push Contract

- Base branch: `main`
- Base SHA: `db5f485b1929f6d6635e7511493098ac229004b6`
- Branch: `feat/graphiti-memory-and-canonical-handoff`
- Create as a **draft PR** until native CI and the stated release gate pass.
- Do not force-push or bypass required checks.
