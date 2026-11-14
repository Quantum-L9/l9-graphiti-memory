<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: VALIDATION.md
layer: repository
owner: memory-control-plane
status: active
version: 3.0.0
updated: 2026-11-14
/L9_META -->

# Validation

> This page records the 2.2.0 validation run as produced. Since ADR-099
> (2026-10-15) the "L9 metadata coverage" and "release manifest integrity"
> checks below no longer exist; current release validation is
> `scripts/validate_release.sh` and its evidence under `build/release-validation`.

## 3.0.0 release run — owed

No 3.0.0 release validation run is recorded here. This page is written by
hand; no tool generates it. `publish.yml` uploads it unchanged beside the
generated evidence.

The 3.0.0 record is produced at release time, from the tagged source, by:

```bash
bash scripts/validate_release.sh
```

That script writes `build/release-validation/` (logs, `SHA256SUMS`, and the
report from `tools/assurance/generate_validation_evidence.py --evidence-dir`).
In `publish.yml` it runs with `L9_RELEASE_EVIDENCE_DIR=build/release-validation`
and `L9_RELEASE_ARTIFACT_DIR` set, so it validates the already-built wheel and
sdist instead of building them. V-001 (ADR-101) needs full git history and
`origin/main`; a shallow checkout makes it `UNKNOWN`.

The tracked `validation/validation_report.yaml` reports release `2.5.0`, not
3.0.0. The 2.2.0 record below is kept as produced.

## Outcome

### 3.0.0 release position

- Release outcome proposed for 3.0.0: **ADMISSIBLE_WITH_ACCEPTED_RESIDUAL_RISK**, the same string the release evidence generator writes (ADR-105). Under the per-item classification in `docs/REMAINING_PRODUCTION_PROOF.md` ("3.0.0 classification"), no remaining-proof item blocks admitting the release of the package `l9-graphite-memory` 3.0.0 and its hosted carrier as profiled in `.l9/deployment.yaml`.
- RP-001 is CLOSED for the package.
- RP-002 to RP-006 are NOT APPLICABLE TO THIS RELEASE for the hosted carrier, because it has no Gate egress, its projection, graph and active-memory backends are pinned off, and its store starts empty.
- For the package, RP-002 to RP-006 are OPEN — ACCEPTED RESIDUAL RISK. RP-007 and RP-008 are OPEN — ACCEPTED RESIDUAL RISK for this release.
- RP-009, the release decision, is discharged only by the decision owner merging the 3.0.0 admission receipt (`docs/receipts/l9-memory-release-3.0.0.md`, ADR-094).
- That classification is proposed for acceptance by the decision owner. Merging it on the default branch is that acceptance. Until then the 2.2.0 outcome below stands.
- No 3.0.0 deployment exists. Release admission, service admission and deployment are separate decisions.

The generated release evidence (`tools/assurance/generate_validation_evidence.py`, ADR-105) still records five external findings, B-001 to B-005, each stating what local evidence cannot prove. Whether each one blocks this release, and the report's `production_release_status`, are computed from `release-work/remaining-proof-classification.json`, the machine-readable form of the classification. Anything that file does not settle fails closed to `BLOCKED_ON_EXTERNAL_VALIDATION`. `ADMISSIBLE_WITH_ACCEPTED_RESIDUAL_RISK` does not claim that production validation happened.

### 2.2.0 outcome, as produced

- Local deterministic outcome: **PASS**
- Recursive L9 alignment outcome: **PASS**
- Review-package outcome: **APPROVED_WITH_EXTERNAL_BLOCKERS**
- Production release outcome: **BLOCKED_ON_EXTERNAL_VALIDATION** (2.2.0; for 3.0.0 see above)

The source tree, canonical stores, compatibility surfaces, constellation boundary, local receipt guard, CLI, MCP inventory, assurance gates, wheel, and isolated-wheel smoke pass. External provider, Gate, hosted repository, secret-rotation, and production-migration checks remain explicitly blocked rather than being represented as local passes.

## Executed checks

| Check | Result | Evidence |
|---|---:|---|
| pytest | PASS, 598 tests | `validation/logs/pytest.txt` |
| Python compilation | PASS | `validation/logs/compileall.txt` |
| ADR ledger | PASS, 78 ADRs | `validation/logs/adr_validation.txt` |
| harvest coverage | PASS, 44 decisions | `validation/logs/harvest_coverage.txt` |
| L9 metadata coverage | PASS | `validation/logs/l9_meta.txt` |
| layer-boundary alignment | PASS | `validation/logs/layer_boundaries.txt` |
| recursive ten-pass alignment | PASS | `validation/logs/recursive_alignment.txt` |
| write-bypass audit | PASS, zero findings | `validation/logs/bypass_check.txt` |
| configuration drift | PASS, zero findings | `validation/logs/config_drift.txt` |
| package wiring | PASS, 86 modules and zero unexplained orphans | `validation/logs/wiring_audit.txt` |
| deterministic source quality | PASS, 119 production files | `validation/logs/source_quality.txt` |
| committed-secret scan | PASS, zero high-confidence findings | `validation/logs/committed_secrets.txt` |
| local SLO benchmark | PASS | `validation/logs/local_benchmark.txt` |
| preflight | PASS, 25 gates | `validation/logs/preflight.txt` |
| shell syntax | PASS | `validation/logs/shell_syntax.txt` |
| wheel build | PASS | `validation/logs/wheel_build.txt` |
| isolated wheel install | PASS | `validation/logs/wheel_install.txt` |
| installed registry resolution | PASS | `validation/logs/installed_resolve.txt` |
| installed CLI health | PASS | `validation/logs/installed_health.txt` |
| installed MCP/resources/entrypoints/constellation bridge | PASS, 22 tools | `validation/logs/installed_mcp.txt` |
| structured validation evidence | PASS, 22 local checks and 5 external blockers | `validation/logs/validation_evidence.txt` |
| release manifest integrity | PASS | `validation/logs/manifest_validation.txt` and final validator execution |

## Recursive alignment evidence

The supplied ten-pass contract is enforced by executable checks, not documentation alone:

- canonical inter-node packet ownership is injected rather than duplicated;
- all root and follow-up dispatch uses the Gate client port;
- follow-up derivation preserves trace and grows lineage without mutating the parent;
- the local memory guard owns no routing or workflow state;
- L9 metadata covers every packaged file inline or through the cryptographic manifest;
- deprecated transport references, direct node routing, layer leakage, aliases, unsafe YAML, generated caches, and forbidden builtin calls fail validation.

Detailed findings and corrections are in `docs/RECURSIVE_ALIGNMENT_UPDATE.md` and `docs/alignment_report.yaml`.

## Local SLO scope

The benchmark exercises the in-memory canonical write, search, and hydration path only. It does not measure external Gate, Graphiti, Zep, network, LLM, or secret-manager latency. Exact metrics and thresholds are in `validation/logs/local_benchmark.txt`.

## Wheel

- Artifact: `validation/dist/l9_graphite_memory-2.2.0-py3-none-any.whl`
- SHA-256: `2f69b2a66b2d9eddaf71dc1bfa5af37463abb81ec915478df590f93bac4e5181`
- Installed smoke proves package resources, `l9-memory`, `l9-memory-server`, `l9-memory-worker`, the MCP inventory, and `GateMemoryBridge` load outside the source checkout.

## Remaining production proof

The canonical remaining-proof statement is maintained in `docs/REMAINING_PRODUCTION_PROOF.md`. Its "3.0.0 classification" section classifies each item below for the 3.0.0 release scope. The table and the paragraph after it are the 2.2.0 record, as produced.

The package is internally aligned and self-policing, but the injected Gate boundary is intentionally generic because the canonical Gate and TransportPacket APIs were not available inside the pack. Substituting guessed shared contracts would create a beautifully typed counterfeit. The next valid move is wiring those authoritative dependencies in staging and proving the complete packet lifecycle.

| Pack issue | Required proof |
|---|---|
| `RP-001` | authoritative TransportPacket package and derivation contract |
| `RP-002` | production Gate client and dispatch-receipt schema |
| `RP-003` | credentialed root and follow-up Gate staging lifecycle |
| `RP-004` | live Graphiti add, search, supersede, delete, and replay |
| `RP-005` | live Zep add, search, supersede, delete, and replay |
| `RP-006` | production-like migration, interruption, resume, and rollback |
| `RP-007` | hosted Ruff, strict mypy, CodeQL, branch, and release controls |
| `RP-008` | secret loading, rotation, revocation, and no-plaintext persistence |
| `RP-009` | consolidated evidence review and production release decision |

For 2.2.0: until these release-blocking issues close with the required evidence, production status remains `BLOCKED_ON_EXTERNAL_VALIDATION`. For 3.0.0 the per-item classification in `docs/REMAINING_PRODUCTION_PROOF.md` replaces this sentence once the decision owner merges it.

## Structured evidence

- `validation/validation_report.yaml`
- `validation/validation_checks.jsonl`
- `validation/validation_findings.jsonl`
- `validation/SHA256SUMS`
- `validation/logs/`

These files are generated from executed logs by `tools/assurance/generate_validation_evidence.py`. Missing or mismatched evidence causes that generator to exit nonzero.

## Reproduce

```bash
bash scripts/validate_release.sh
```

The command exits nonzero on a local hard-gate failure. External gates remain separately blocked until executed in their required environments.
