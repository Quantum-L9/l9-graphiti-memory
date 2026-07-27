<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/l9-deploy-phase6-operator/references/ACCESS_MATRIX.md
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
role: access_matrix
tags: [access, least-privilege, github, infisical, ghcr, ssh]
owner: igor_beylin
status: active
version: 1.0.0
updated: 2026-07-26
-->
# Access Matrix

| System | Required capability | Minimum use | Forbidden use | Evidence |
|---|---|---|---|---|
| GitHub repository | read source, runs, artifacts; dispatch approved workflows | verify revision, dispatch staging, download evidence | rewrite history, bypass branch protection | API snapshots and run IDs |
| GitHub Environment | inspect protection and approve when independently authorized | enforce `staging` reviewer gate | self-approval or disabling protection | redacted environment export |
| GitHub Actions runner | execute jobs with labels `self-hosted`, `l9-deployment`, `hetzner-private` | deploy and rollback only | interactive unlogged production work | runner metadata and job logs |
| GitHub OIDC | `id-token: write` only on approved secret-consuming job | exchange for staging Infisical identity | workflow-level OIDC or broad subject policy | positive/negative results and policy export |
| Infisical | read staging project/path and read audit logs | materialize reversible staging secrets | production path, customer secrets, broad write | access-log export and policy summary |
| GHCR | pull immutable digest and read provenance | staging image pull and attestation verification | mutable-tag promotion | manifest digest and attestation result |
| Hetzner/VPS | SSH to declared staging host | readiness, state capture, health, recovery | production host or unrelated hosts | host fingerprint and command transcript |
| Docker engine | inspect, pull, compose, health, logs on staging | lifecycle proof | pruning unrelated images/volumes | container and image snapshots |
| Live staging service | health and controlled fault adapters | prove convergence | customer traffic or irreversible data mutation | health captures and scenario records |
| External OIDC probe repo | run negative exchange workflow | prove non-target repo is denied | adding probe workflow to `l9-deploy` | denied run ID and Infisical audit event |

Credentials remain outside this pack. Record names, scopes, IDs, and redacted policy only.

## Phase 6H.2 authority separation

The staging operator requires the run-ledger private key but must not receive the evidence-attestor private key. The independent attestor requires proof-artifact read access and the evidence private key but no staging mutation capability. The final verifier requires both public keys through an independent channel and a clean checksummed copy of this pack.
