<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: CHANGE_SUMMARY.md
layer: repository
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-09-06
/L9_META -->

# Change Summary

## Release

`3.0.0` is the release candidate on `main`: untagged, with no admission receipt under `docs/receipts/` (ADR-094), and not deployed. The last admitted release is `2.6.0`. Entries below run oldest first; the 3.0.0 entry is at the end.

`2.3.0` consumer control-plane conformance release (campaign stages M1 and M2 of the Cursor-Governance memory realignment, ADR-082). `2.2.0` was the recursive convergence and harvest-closure release.

## Added

- Evidence-bound atomic extraction and offline distillation
- Identity, preference, behavior, session, and domain profile contracts
- Purpose-bound consent and verified deletion
- Persistent projection links with stable provider locators
- Graphiti `delete_episode` and Zep `graph.episode.delete` erasure paths
- Current Graphiti MCP dialect negotiation for `add_memory` and `search_memory_facts`
- Lineage replay, cycle detection, and orphan reporting
- Procedural synthesis candidates with approval boundary
- Checkpoint integrity utility without checkpoint ownership
- Canonical ingress recovery queue
- Strategy-specific hybrid retrieval receipts
- Secret scanning and local SLO benchmark
- Machine-readable 44-decision harvest coverage ledger
- Recursive improvement, delta, and convergence evidence

## Corrected

- Closed every prior `partial` or `deferred` in-scope harvest item
- Removed false provider-erasure completion claims
- Reconciled provider tool naming with current and legacy Graphiti MCP surfaces
- Updated docs and roadmap to match executable behavior
- Extended SQLite schema to persist projection links

## Preserved

- Distribution name `l9-graphite-memory`
- Import package `l9_graphite_memory`
- CLI and MCP entrypoints
- Legacy MCP aliases
- Hook output shape
- Explicit projection choice and no silent fallback

## External blockers

Live provider, hosted CI, production migration, rollback, and credential-rotation proof remain external gates and are not represented as local passes.

## 2.2.0 recursive alignment

- Added injected TransportPacket and Gate boundary protocols.
- Added immutable Gate-only root and follow-up dispatch.
- Reclassified the local hook component as a receipt guard.
- Added L9_META coverage, manifest v2, layer checks, and recursive alignment enforcement.
- Removed deprecated transport references, camel-case hook aliases, print calls, and generated caches.

## 2.3.0 — consumer control-plane conformance (ADR-082, campaign M1 + M2)

### M1 — transport parity

- Added `l9-memory close` with exit-code verdicts (`0` committed, `3` dry run, `2` failed)
- Added `CloseRequest.idempotency_key` and `CloseReceipt.replayed`: a replayed close yields one logical close
- Added `l9-memory capabilities`, `memory.capabilities`, and `HealthReport.contract_version` (`memory-control-plane/v1`)
- Added `MemorySDK.write_governed`, `ingest_governed_candidate`, `conflicts`, `verify_phase_lock`, `close`, `health`
- Extended the governed-candidate contract: `session_continuation` class, `namespace_local` visibility, lossless `structured_payload`

### M2 — consumer conformance hardening

- Added a tag selector to `MemorySearchRequest` and `HydrationRequest` (`--tag` on `l9-memory search` / `hydrate`, `tags` on `memory.search` / `memory.hydrate`): every requested tag must be present, and a tag match admits a record regardless of query-text relevance. A consumer selects its typed `session_continuation` records with it instead of guessing at content
- `l9-memory client cursor verify --path` now launches the managed entry as written in that file (`ProbeReceipt.argv_source = "installed"`, `config_path`); the default path is probed the same way when it already carries the entry, and only a machine with no config falls back to the generated entry. An entry existing on disk was never proof; now the receipt says what was proven
- Added `probe_installed_entry` to `client_config`
- Added the installed-wheel lifecycle test (`tests/integration/test_installed_wheel_lifecycle.py`): capabilities, health, continuation admission and replay, tag-selected hydrate and search, dry-run and idempotent close, and `client cursor install` + `verify --path`, all from a wheel installed into an empty target with nothing else importable
- Added consumer conformance coverage (`tests/unit/test_consumer_conformance.py`): candidate rejection and quarantine as visible verdicts, authorized and refused read fan-in, canonical operations with `projection=none` and with a failing projection, stale / wrong-task / wrong-namespace phase locks, and the same lifecycle over MCP
- Added the cross-surface fixture `tests/fixtures/control_plane/continuation_candidate.json`, consumed verbatim by Cursor-Governance's cross-repo lifecycle test
- Added `tests/regression/test_release_version_consistency.py`: `pyproject.toml`, `version.py`, the assurance stampers, and the evidence pins must name one release
- Release `2.3.0` is `MEMORY_TARGET_VERSION` for the Cursor-Governance binding (`ops/config/memory-binding.json` there pins it); tag `v2.3.0` on the merge commit

## 2.3.1 — PyPI metadata (no direct URL extra)

`v2.3.0` built and validated but PyPI rejected the upload: the `constellation` extra declared `constellation-node-sdk` as a git URL, which becomes `Requires-Dist` and is a 400 (`Can't have direct dependency`). The extra is removed from published metadata. CI/dev still install Gate_SDK via a uv `dependency-groups.constellation` entry and `[tool.uv.sources]`. Tag `v2.3.0` stays immutable; this patch is the first uploadable release.

## 2.4.0 — never released

`2.4.0` was a source identifier only. `e3a7962` aligned `version.py` with the `2.4.0` already declared in `pyproject.toml`, but no `v2.4.0` tag exists and no 2.4.0 wheel was published (`20ce2df`; ADR-083 says the same). Its changes ship in 2.5.0 under a new wheel filename, so a consumer that vendors by filename sees the change explicitly. There is no 2.4.0 admission receipt and none is owed.

## 2.5.0 — signed-agent door and one class vocabulary

Tag `v2.5.0` (merge commit `78b304a`). No admission receipt for 2.5.0 is in `docs/receipts/`; the exact-release admission gate (ADR-094, publish gate from #98) did not exist yet.

- Signed-agent door, `memory.write_agent`, and one memory-class vocabulary (#63, ADR-083)
- Search receipts bind every result-affecting selector (#58, MEM-P2-01)
- MCP tool-handler parity enforced by test (#61)
- Reproducible publish digest; CI-based SonarQube Cloud analysis gated on the project's analysis method (#57)
- Committed validation evidence regenerated and bound to 2.5.0 (`98510a6`): `validation/validation_report.yaml` still reports release `2.5.0`

## 2.6.0 — projection runtime, product topology, canonical actor assertion

Tag `v2.6.0` (peeled commit `846f283`, #86). Admission receipt: `docs/receipts/l9-memory-release-2.6.0.md` (wheel sha256 `d4935732…`, sdist sha256 `537ff040…`, local validation `1595 passed`).

- Manifest projection runtime with target-aware lifecycle (#76, ADR-084)
- Graph intelligence campaign landed over ADR-084 (#84)
- Authoritative ProductTopology and derived release binding (#80, ADR-094)
- Selector-matched invalidation archives records through `MemoryService` (#81)
- Graphiti `initialize` `clientInfo.version` derived from `PACKAGE_VERSION` (#79)
- Canonical actor assertion verified at the signed-agent door (#85)
- Admitted core profile consumed; release identified as 2.6.0 (#86)
- Release validation made observational and artifact-exact (#77, #78)
- Stale root alignment artifacts removed (#75)

Known defect in the published artifact: the sdist on PyPI for 2.6.0 (`7507070e…`) is not the sdist the receipt admitted (`537ff040…`). Found and closed for later releases by the admission-receipt publish gate in 3.0.0 (#98).

## 3.0.0 — hosted Memory candidate (unreleased)

Covers `v2.6.0..main@cc10253` (97 commits; #87, #88, #91, #92, #96 integrating #93/#94/#95, #97–#106, #109, then #112–#117 and #120 integrating #118/#119/#121/#122, and #123). Status: version carriers say `3.0.0` (`52cf4ec`); no `v3.0.0` tag, no admission receipt, no deployment. The 2.7.0 identifier that appears in ADR-098 and older commits was #94's source version; it was never tagged or published and is integrated here.

### Breaking changes and migration

Read `MIGRATION.md` "Upgrading from 2.6.0 to 3.0.0". In summary:

- HTTP MCP is stateless Streamable HTTP `2025-11-25` / `2025-06-18`; an absent or unsupported `MCP-Protocol-Version` is a `400`. 2.6.0 HTTP clients cannot talk to a 3.0.0 server, and the reverse (ADR-098, `docs/REMOTE_MCP_CONTRACT.md`). This is the reason for the major version.
- stdio MCP and the canonical store schema (9) are unchanged; persisted record models are unchanged since 2.6.0.
- The root inventory `MANIFEST.md` / `manifest.json` and the `L9_META` tools (`apply_l9_meta`, `check_l9_meta`, `generate_manifest`, `validate_manifest`, `l9_meta`) are removed; a tracked root `MANIFEST.md` or `manifest.json` is now forbidden (ADR-099 supersedes ADR-062, #99).
- The TypeScript client is npm `3.0.0` (was `2.0.0`), requires a 2.7.0+ server, and no longer defaults to `2025-03-26` (`d673ada`). Its version number is not the Memory version.
- `validate_product_topology.py --release-version` rejects a release below the `3.0.0` floor for the hosted-Memory kind exception (#97).
- `MIGRATION.md`'s 2.6.0 → 3.0.0 table predates ADR-100 and still lists `signed-agent` as an opt-in HTTP mode. For the hosted service ADR-100 governs (next section).

### Hosted door (ADR-098, ADR-100)

- ADR-098 (#94 via #96): MCP Streamable HTTP is the remote transport. It also added a signed-agent HMAC HTTP identity; a signed-agent grant carrying `is_admin` stops the server at startup (`3530d0f`).
- ADR-100 (#102): the hosted Memory service is OAuth-only native MCP Streamable HTTP. Memory stdio, signed-agent HMAC and static bearer are not hosted doors and not fallbacks. ADR-098's signed-agent identity and bearer mode are superseded for the hosted service; that code stays in the tree as legacy until a later change removes it.
- The Auth0 resource identifier is published in ADR-100 (#106); the carrier pins the issuer (`.l9/deployment.yaml`, #121).
- OAuth resource-server mode `http_auth_mode=oauth` (ADR-102, #113): issuer-key signature, exact issuer, Memory audience, one `/mcp` endpoint, RFC 9728 metadata, subject-keyed grants, and the operator tool `tools/assurance/oauth_pkce_receipt.py`. The live PKCE receipt passed six of six checks against the live Auth0 tenant and a local server (issue #108 comment 6862806068, 2026-11-13T19:25:56Z, receipt sha256 `8e0eeb4ed9cb8853b71e448cc38b0ea0fd801372eddc04b2d3f39e6f671b02ad`); no deployed service was exercised.
- OAuth actor path (ADR-103, #119): an actor only from an operator binding (`L9_MEMORY_OAUTH_ACTORS_JSON`) for the verified (subject, client id) pair; consent from the verified subject is server explicit evidence; client-credentials (user-less) tokens are refused.
- An OAuth client id does not resolve an actor, a surface or an operator grant; every state-changing MCP tool is refused without OAuth actor evidence (allowlist of read-only handlers) (#103).
- `RemoteMemoryClient`: `l9-memory` lifecycle commands run against a hosted `MemoryService` with `--remote-url` / `L9_MEMORY_REMOTE_URL`, same argv, receipts and exit codes; no local store is opened (#100). It carries the signed-agent door's identity, which ADR-100 supersedes for the hosted service.

### HTTP and store hardening

- Hostile credentials and bodies are 4xx, never 500; bodies over 4 MiB refused; one 401 for unknown agent and bad signature (`4d2aa95`)
- NaN / Infinity request bodies refused (`efa9006`)
- Query strings kept out of the uvicorn access log (`c31f0fd`)
- First-time PostgreSQL schema initialization serialized by an advisory lock (`8eb6e6f`)
- Missing tool arguments are invalid params; `isError` tool results are not success; tool work on a bounded pool; health probes on their own pool (#103)
- Cross-process shared memory on PostgreSQL proven over loopback TCP, from source and from the installed wheel (`757cd1e`, #97). Not proven: TLS, a non-loopback path, any deployed host.

### OCI carrier and deployment profile (#101)

- `Dockerfile` builds `l9-memory-server` (`server` + `postgres` extras, linux/amd64, uid 10001, port 8200); dependencies install from wheels only; base images pinned by digest
- The entrypoint guard requires the PostgreSQL store and pins graph, active memory and projection off. Since #121 it admits only `L9_MEMORY_HTTP_AUTH_MODE=oauth` and refuses signed-agent, bearer and any other mode (ADR-100, ADR-102)
- `.l9/deployment.yaml`: v2 deployment profile targeting C1 with external ingress and a required external PostgreSQL; the hosted carrier is pinned to the OAuth door (#121)
- `.github/workflows/release-container.yml` reuses `l9-ci-core` `container-release@89c9bc4` behind the ADR-094 exact-release admission; carrier test failures fail the job
- C1 data plane: PostgreSQL 16 as an operator-provisioned external store on the `l9-runtime` network, a backup path that dumps from a pinned image on that network, and the cutover runbook to match (#117)
- Release workflows runnable for 3.0.0: the annotated-tag admission check, the admission interpreter, the nightly setup-uv gate, and third-party actions in `publish.yml` pinned to full SHAs (#115); `release-dispatch.yml` dispatches the container release as the repository bot so the requester and the production approver differ (#118)

### Admission and projection fixes

- Bare epochs and nine-digit identifiers are no longer stored as phone or SSN placeholders; ambiguous numerics are held redacted and escalate to a person; explicit evidence is server-decided, so caller-asserted `explicit` evidence quarantines instead of admitting (#104)
- Graphiti `isError` results are refused instead of unwrapped as a write; only the official queued-success shape is accepted; socket faults count on the circuit breaker and a stuck half-open breaker re-arms (#105)
- ADR-097 active-memory composition and five-family full-capability readiness, with positive probe evidence required (#91)
- 28 RECON-0 repositories registered as exact-remote namespaces; an exact remote match outranks enclosing path hints (#92)
- Phone and SSN redactors match only at alphanumeric token boundaries, so a digit run inside a hex identifier is no longer stored as a phone number (#123)

### Assurance

- ADR-099: inventory and `L9_META` enforcement retired; `candidate_integrity` is the tracked-byte digest compared after validation, `UNVERIFIED` when git cannot enumerate (#99)
- ADR-101: V-001 is derived from the run (no failures or errors, every collected node accounted for, skips on a committed allow-list, no node lost since the merge-base) instead of an exact pass count; missing input is `UNKNOWN`, never `PASS`. Release validation checks out full history (#109)
- Publication gated on the exact-release admission receipt read from the protected default branch (ADR-022 amendment, #98)
- ProductTopology rebound to `.github` Semantic Foundation v3.21.0, claiming the hosted-Memory product-kind exception (ADR-094 amendment, #97)
- A failing validation step prints its log (`cdf7fa5`); the alignment walk no longer races `git gc` (`4f1284a`)
- Admitted-tag release publication procedure documented (#88); 2.6.0 admission recorded (#87)
- ADR-104: Core repository execution V2 (`.l9/repo-workflow.json`, Core's `make-v1` facade as the root `Makefile`, recipes in `Repo.mk`); the alignment scan judges only this repository's files (#120)
- Six code-scanning findings on `main` cleared (#116)
- Release and hosted-door statements in the tracked documents made true for 3.0.0 (#112)

### Dependencies

- `pyjwt` 2.13.0 → 2.15.0 (#93); `src/l9_graphite_memory/authz/oauth.py` imports it for OAuth token validation (#113)
- `[project]` dependencies unchanged since `v2.6.0`; the `server` extra gains `cryptography>=50.0,<51` and `PyJWT>=2.13,<3` (#113, #122), and the `dev` extra moves to `pytest-asyncio>=1.3,<2` (#122)
- New: container base images (digest-pinned) and `l9-ci-core` `container-release@89c9bc4` (#101)
- Known vulnerabilities cleared in `uv.lock`: cryptography 46.0.7 → 50.0.2 (constraint `>=50.0,<51`), certifi → 2026.10.23, pytest 8.4.2 → 9.0.3 with pytest-asyncio 1.3.0 (#122)

## Pending before the 3.0.0 tag

- The 3.0.0 admission receipt `docs/receipts/l9-memory-release-3.0.0.md` (ADR-094; checked by `tools/assurance/verify_release_admission.py`). It is the operator's decision and can only be written after the tag's commit exists.

