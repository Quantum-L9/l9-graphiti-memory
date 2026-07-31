<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/WIP/l9-bot-memory-integration-pr-pack/repos/l9-graphiti-memory/pr-body.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

## Summary

Adds the reusable `@quantum-l9/graphiti-memory-client` TypeScript package over the existing authenticated HTTP MCP surface, enabling Node consumers to hydrate governed context, write decisions/outcomes, and promote evidence-backed learnings without creating a second memory authority.

## Type of Change

- [ ] Bug fix
- [x] Feature / enhancement
- [ ] Refactor (no behavior change)
- [x] Documentation
- [x] CI / governance change
- [ ] Breaking change (see rollback plan below)

---

## Governance Checklist

- [ ] **Governance setup verified** — ran `setup_workspace_symlinks.sh`, symlinks resolve ([§2](https://github.com/Quantum-L9/Cursor-Governance/blob/main/CANONICAL_LAW.md#2-symlink-contract))
- [ ] **Symlinks validated** — `ls -la .cursor/rules .cursor/skills .cursor/commands` all resolve
- [ ] **All CI gates green** — no required checks failing or bypassed
- [x] **Anti-patterns checked** — client calls canonical `MemoryService` tools; no duplicate store, authority engine, or projection owner
- [ ] **CODEOWNERS notified** — blast-radius files trigger auto-request; confirmed reviewers assigned
- [x] **Workspace wiring intact** — Python package/runtime remains authoritative; TypeScript is a thin adapter
- [ ] **TRACEABILITY_MAP.yaml updated** — if this PR resolves an open unknown, mark as RESOLVED
- [x] **Kernel ref discipline** — no `@main` dependency introduced

---

## Breaking Change

- [ ] This is a breaking change

No existing Python, CLI, MCP, hook, or projection surface changes.

## Rollback Plan

Revert this commit. The change is additive under `clients/typescript/` plus one path-scoped workflow; the canonical Python memory runtime is untouched.

---

## Stack Position

**Stack 1/4**. No preceding PR.

## Dependencies and Release Gate

None. This layer publishes `@quantum-l9/graphiti-memory-client@2.0.0`.

## Validation

- `cd clients/typescript && npm install && npm run verify:all`
- Confirm `memory.health`, `memory.hydrate`, `memory.ingest`, and `memory.promote` requests hit the existing `/mcp` endpoint with bearer auth.


## Canonical-memory realignment

- Uses `Quantum-L9/l9-graphiti-memory` as the sole shared cognitive-memory authority.
- Introduces no PostgreSQL/pgvector memory store or dual-write path.
- All durable writes and promotion requests cross the authenticated canonical service boundary.
- Application-local databases remain operational state only.

## Push Contract

- Base branch: `main`
- Base SHA: `18d857688c43b0e3d4d7b2d1dc4ce0eea0d866c1`
- Branch: `feat/typescript-memory-client`
- Create as a **draft PR** until native CI and the stated release gate pass.
- Do not force-push or bypass required checks.
