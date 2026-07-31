<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/WIP/l9-bot-memory-integration-pr-pack/RUNBOOK.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# PR Stack Runbook

`AUTHORITY.md` governs. `PR_STACK.yaml` is the executable stack index. Stop on drift instead of overriding a base check.

## 1. Workspace layout

Create one parent directory containing clean clones named exactly `l9-graphiti-memory`, `LLM-Router`, `Website-Bot`, and `SEO-Bot`. Each clone must be on `main` at the pinned SHA in `PR_STACK.yaml`.

## 2. Provision bot principals (required before any hydration or write will authenticate)

The pack ships zero secrets by design. Nothing will authenticate against the canonical memory server until an operator hand-registers a bearer-token principal for each consumer. Only Website-Bot and SEO-Bot need one: LLM-Router never builds its own `GraphitiMemoryClient`, it only receives one already-constructed from its caller (`repos/LLM-Router/files/src/memory.ts`).

```bash
./scripts/provision-bot-principals.sh /path/outside/any/repo/tokens.json
```

This writes a `L9_MEMORY_AUTH_TOKENS_FILE`-compatible JSON mapping (mode `600`) with two fresh random bearer tokens and refuses to write inside this repository. Then, on the machine running `l9-memory-server`:

```bash
export L9_MEMORY_AUTH_TOKENS_FILE=/path/outside/any/repo/tokens.json
export L9_MEMORY_HTTP_AUTH_REQUIRED=true   # default; keep it true
l9-memory-server --transport http --host <bind-address> --port 8200
```

Distribute the two generated token values to Website-Bot's and SEO-Bot's own secret stores (e.g. Infisical, matching this repo's existing convention for `GRAPHITI_MCP_TOKEN`/`ZEP_API_KEY` in the top-level `RUNBOOK.md`) as `L9_MEMORY_TOKEN`, and set each bot's `L9_MEMORY_URL` to the server's real reachable address. Never commit either value; the pack's `.env.example` overlay blocks intentionally ship `L9_MEMORY_TOKEN=` empty.

**Both principals share `tenant_id=l9-bot-trio` on purpose, not by oversight.** Authorization here has two independent layers: `NamespacePolicy` glob grants (`read_namespaces`/`write_namespaces`/`promote_namespaces`) and a hard `tenant_id` equality check enforced on every record read, get, lineage, and delete (`services/memory_service.py`; ADR-006: "no cross-tenant record is returned even if record ID is known"). Verified live against a real local server on 2026-07-30:

- Distinct `tenant_id` per bot → `memory.get` across bots fails closed with `record belongs to a different tenant`, even for an identical `client:<id>` namespace both bots are granted.
- Shared `tenant_id` → seo-bot could `memory.get`/hydrate a record website-bot wrote into `client:acme-corp`, matching `AUTHORITY.md`'s framing of `l9-graphiti-memory` as "the sole **shared** cognitive-memory authority for Website-Bot, SEO-Bot, and LLM-Router."
- website-bot's `promote_namespaces` is deliberately empty and was confirmed denied (`principal 'website-bot' is not authorized to promote`); seo-bot's promote call passed the namespace layer and was correctly denied one layer deeper, by the default-deny corroboration policy (`promotion denied: default deny: promotion evidence is insufficient`), not by authorization.
- An unrecognized bearer token was rejected with HTTP 401.

If per-bot isolation is actually wanted instead of shared cross-bot memory, give each bot a distinct `tenant_id` and accept that neither bot's writes will ever be visible to the other, in any namespace.

## 3. Validate and preflight

```bash
./scripts/validate-pack.sh
./scripts/preflight-stack.sh /path/to/workspace
```

The preflight rejects missing clones, wrong origins, dirty trees, and base drift. Rebase the pack deliberately when upstream moves; do not use bypass flags for publication.

## 4. Prepare local PR branches

```bash
./scripts/prepare-stack.sh /path/to/workspace
```

This creates each scoped branch, applies only that repository's overlay, generates lockfiles, stages the exact diff, and commits using the supplied message. It does not push.

## 5. Run native proof

Run each repository's complete formatter, lint, type-check, unit, integration, build, assurance, and CI-equivalent commands. Execute the live gates in `VALIDATION.md`. Capture lockfiles and package tarball digests.

## 6. Release gates between layers

1. Merge memory-client PR and publish `@quantum-l9/graphiti-memory-client@2.0.0`.
2. Prove registry installation, merge Router, and publish `@quantum-l9/llm-router@1.1.0`.
3. Prove both packages in Website-Bot, merge it, and publish `@quantum-l9/bot-interop@1.0.0`.
4. Prove all exact packages in SEO-Bot, then merge and deploy its migration.

A downstream draft PR may open earlier, but remains blocked until its release gate passes. Each repository's `dependency-resolvable` CI check (added alongside the memory-client dependency bump) enforces this mechanically: it fails closed until the exact pinned upstream package version resolves on the registry, so a downstream PR cannot go green before its gate is actually satisfied.

## 7. Push draft PRs

```bash
PUSH_STACK=1 ./scripts/push-stack.sh /path/to/workspace
```

The publisher requires GitHub CLI authentication, verifies branch, clean tree, and exact commit parent, pushes without force, and creates draft PRs from packaged titles and bodies. Existing PRs are not duplicated.

## 8. Rollback

Revert consumers in reverse order. Do not delete canonical memory as generic rollback. Use supersession, retention, or verified administrative deletion.
