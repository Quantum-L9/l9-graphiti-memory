<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/WIP/l9-bot-memory-integration-pr-pack/repos/LLM-Router/pr-body.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

## Summary

Adds an asynchronous `BudgetStore` port so Router budget reservations, reconciliation, resets, and reports can be backed by an external atomic ledger while preserving the current in-process `BudgetTracker` as the default adapter.

## Type of Change

- [ ] Bug fix
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
- [x] **Anti-patterns checked** — Router defines the persistence port but does not own PostgreSQL, Redis, memory, or consumer credentials
- [ ] **CODEOWNERS notified** — blast-radius files trigger auto-request; confirmed reviewers assigned
- [x] **Workspace wiring intact** — default single-process behavior remains available through `InMemoryBudgetStore`
- [ ] **TRACEABILITY_MAP.yaml updated** — if this PR resolves an open unknown, mark as RESOLVED
- [x] **Kernel ref discipline** — consumers pin the released package version

---

## Breaking Change

- [ ] This is a breaking change

Existing synchronous report methods remain valid for the default in-memory adapter. External stores use the new async report methods. `initClient` now returns a Promise; existing in-memory initialization still occurs synchronously before that Promise resolves.

## Rollback Plan

Revert this commit and republish the previous package version. Consumers can remove the injected `budgetStore` and return to process-local accounting.

---

## Stack Position

**Stack 2/4**. Depends on `memory-client`.

## Dependencies and Release Gate

Requires layer 1 merged and `@quantum-l9/graphiti-memory-client@2.0.0` published and installable.

## Validation

- `npm run verify:all`
- Confirm default in-memory reservation tests remain green.
- Confirm the external-store test observes `reserve -> provider dispatch -> reconcile` and releases on failure.

## Review note: full-file overlay, not a minimal hunk

`apply.sh` replaces `src/index.ts` and `src/budget/index.ts` wholesale (`cp -R files/. .`, no `transform.py`) rather than an anchored patch, because the real change is a structural refactor (sync `BudgetTracker` methods become an async `BudgetStore` port; `computeThrottleLevel`/`validateBudgetConfig` move to top-level exported functions; `initClient` becomes idempotent) that is safer to review as a whole file than to reconstruct from a chain of fragile string anchors. `REVIEW.diff` in this directory is the actual scoped unified diff against the pinned base SHA (`d83299bc6e81efae1eb6e6c3032cbb3e0cb77184`) — review that instead of diffing the full files by hand. It was generated directly from the live repository at the pinned SHA and is only valid against that exact base; regenerate it if the base is ever rebased. The apply-time backstop against clobbering local drift is unchanged: `apply.sh` still refuses unless `HEAD` matches the pinned SHA exactly and the working tree is clean.


## Canonical-memory realignment

- Uses `Quantum-L9/l9-graphiti-memory` as the sole shared cognitive-memory authority.
- Introduces no PostgreSQL/pgvector memory store or dual-write path.
- All durable writes and promotion requests cross the authenticated canonical service boundary.
- Application-local databases remain operational state only.

## Push Contract

- Base branch: `main`
- Base SHA: `d83299bc6e81efae1eb6e6c3032cbb3e0cb77184`
- Branch: `feat/persistent-budget-store-port`
- Create as a **draft PR** until native CI and the stated release gate pass.
- Do not force-push or bypass required checks.
