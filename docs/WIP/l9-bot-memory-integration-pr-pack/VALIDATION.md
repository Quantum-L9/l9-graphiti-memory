<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/WIP/l9-bot-memory-integration-pr-pack/VALIDATION.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Validation Record

## Pack-local gates

- Shell syntax for every apply, preflight, prepare, validate, and push script.
- JSON and strict JSON-compatible YAML parsing.
- Authority and PR-stack order agreement.
- Per-PR metadata agreement across `PR_STACK.yaml`, `PR_METADATA.json`, branch, base, title, apply script, and PR body.
- Push authorization defaults to denied; draft creation required; force-push absent.
- TypeScript syntax, isolated package contract tests, apply rollback, repository-identity rejection, manifest hashes, secret scan, placeholder scan, and shadow-memory scan.
- Package version convergence: memory client `2.0.0`, Router `1.1.0`, bot interop `1.0.0`.

## Grounded bases verified on July 31, 2026

`l9-graphiti-memory`'s `main` moved twice (two merged PRs, `#23` and `#24`) since the pack was first built against `f5b802a`. Neither commit touches `clients/typescript/` or `.github/workflows/typescript-client.yml`, the only paths this overlay writes, so the rebase carried no functional risk; it was still done as an explicit re-pin rather than `ALLOW_UNPINNED_BASE=1`, per `AUTHORITY.md`'s "stop on drift" rule. Live-checked against GitHub on July 31, 2026 (`gh api repos/<repo>/branches/main`):

- `l9-graphiti-memory`: `18d857688c43b0e3d4d7b2d1dc4ce0eea0d866c1` (rebased from `f5b802a8aafcba1590a5a90966b9efbc411d2c0c`)
- `LLM-Router`: `d83299bc6e81efae1eb6e6c3032cbb3e0cb77184` (unchanged, confirmed current)
- `Website-Bot`: `db5f485b1929f6d6635e7511493098ac229004b6` (unchanged, confirmed current)
- `SEO-Bot`: `0a660de9ac042af3b315fdfeb94d4b8847f42a6e` (unchanged, confirmed current)

## Live authorization proof (2026-07-31)

Ran a real local `l9-memory-server --transport http` instance against an isolated SQLite data dir with a generated `L9_MEMORY_AUTH_TOKENS_FILE` for `website-bot` and `seo-bot` (see `RUNBOOK.md` §2 and `scripts/provision-bot-principals.sh`). This is genuine executed proof, not a simulation:

- Bearer-authenticated `initialize` and `memory.health` succeeded for both principals; an unrecognized token was rejected with HTTP 401.
- `website-bot` wrote into `client:acme-corp`; with a shared `tenant_id`, `seo-bot` could `memory.get`/hydrate that same record. With distinct `tenant_id` values the identical call failed closed with `record belongs to a different tenant` — `NamespacePolicy` and the per-record `tenant_id` check are independent enforcement layers, and namespace grants alone do not imply cross-tenant visibility.
- `website-bot`'s empty `promote_namespaces` produced a hard authorization denial on `memory.promote`. `seo-bot`'s namespace grant let the call reach the deeper policy layer, which correctly denied it for insufficient corroboration evidence rather than for authorization — confirming the two-layer defense (namespace authz, then default-deny curation policy) both function as designed.

## External gates before marking ready to merge

1. Run each repository's native CI on its prepared branch.
2. Exercise authenticated and denied MCP namespaces against the deployed memory service. *(Partially closed: proven locally above; still needs the same proof against the actual production deployment and network path the bots will use.)*
3. Publish and reinstall each exact package version before unblocking the next layer.
4. Prove Router concurrent reservation and reconciliation failure behavior.
5. Prove Website-Bot end-to-end handoff digest and governed write.
6. Prove SEO-Bot migration, concurrent budget ceilings, sub-threshold promotion denial, and corroborated promotion success.

Pack status means **ready to push as draft PRs**, not pre-certified for merge.
