<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: tools/phase6/references/REPOSITORY_BASELINE.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

<!--
skill_schema: 1
parent: l9-deploy-phase6-operator
layer: reference
role: repository_contract_snapshot
tags: [baseline, workflow, cli, drift]
owner: igor_beylin
status: active
version: 1.0.0
updated: 2026-07-26
-->
# Repository Contract Snapshot

The supplied Phase 4 artifact establishes these operational interfaces:

- Dispatch event: `l9.release.requested.v1`.
- Deploy workflow: `.github/workflows/deploy-dispatch.yml`.
- Deploy job runner labels: `self-hosted`, `l9-deployment`, `hetzner-private`.
- Deploy job alone consumes Infisical OIDC in that workflow.
- Runtime secret materialization: `scripts/infisical-oidc-env.sh <environment> runtime.env`.
- Provenance verification: `scripts/verify-attestation.sh <image-ref> <source-repository>`.
- Deployment CLI requires plan, fleet, environment, expected plan digest, approval receipt/history/run ID, runtime env, base URL, request digest, receipt ledger, and output path.
- Rollback workflow: `.github/workflows/rollback.yml` with protected authorization and expected plan digest.

`references/repository-baseline-manifest.json` contains hashes of the relevant reconstructed Phase 4 files. The live executor must compare them. Any drift requires architectural review rather than blind execution.
