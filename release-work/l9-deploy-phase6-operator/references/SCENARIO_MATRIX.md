<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/l9-deploy-phase6-operator/references/SCENARIO_MATRIX.md
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
role: scenario_protocol
tags: [scenarios, deployment, rollback, fault-injection, evidence-authority]
owner: igor_beylin
status: active
version: 3.1.0
updated: 2026-07-26
-->
# Scenario Matrix

Execute S00 through S07 sequentially. Never parallelize fault injection. Every external check follows the same authority path:

```text
named live collector
  -> strict proof envelope + raw source artifacts
  -> independent evidence attestor
  -> Ed25519-signed, run-bound evidence record
  -> operator import into signed append-only ledger
  -> policy-derived scenario result
```

The operator cannot author PASS. The evidence attestor must not possess the ledger private key. The final validator receives both public keys independently.

## S00: Baseline and Phase 5 gate

Required checks:

- exact staging-only configuration;
- production forbidden;
- Phase 5 validation against the exact live commit;
- protected `staging` GitHub Environment with an approval;
- exact eligible runner labels.

Required raw proof includes Git commit output, Git status output, Phase 5 command output, GitHub environment API export, and GitHub runner API export. Any dirty target tree, revision mismatch, missing Phase 5 output, or unprotected environment blocks mutation.

## S01: OIDC and Infisical authority

1. The authorized `Quantum-L9/l9-deploy` staging job obtains a GitHub OIDC token.
2. `verify_oidc_claims.py` verifies RS256 signature, official issuer, audience, time bounds, key ID, repository, subject, environment, run ID, and workflow reference.
3. The authorized exchange is allowed.
4. An external unauthorized probe performs the same exchange and is denied.
5. A non-empty, staging-only Infisical audit slice is exported. Sensitive fields must be redacted and secret-shaped values are rejected.

Required artifacts include OIDC verification, the Infisical exchange receipt, the issuer JWKS used for verification, the Infisical audit proof, and the redacted raw audit export. Unauthorized exchange success is an immediate NO-GO.

## S02: Immutable healthy candidate

The GitHub workflow receipt must be bound to the canonical repository, exact commit, numeric run ID, and numeric artifact ID. Its detail object must validate against the deployment schema and the check-specific receipt contract.

Pass requires:

- digest-pinned image identity;
- attestation verification;
- release-owned configuration identity;
- green health;
- candidate promoted active.

The record must include the workflow proof, raw deployment receipt, and GitHub run metadata.

## S03: Invalid-secret pre-activation containment

Introduce only an approved reversible staging test secret. The governed candidate must fail before active-state promotion.

Pass requires:

- candidate rejected;
- active state explicitly unchanged;
- production contact false;
- workflow proof, raw containment receipt, and GitHub run metadata all present and content-bound.

`candidate_rejected` and `active_state_unchanged` are separate facts. They are not inferred from one overloaded promotion-state value.

## S04: Health-failure rollback convergence

Use the approved staging-only health-failure adapter. Pass requires equality of prior and restored image digests, equality of prior and restored configuration identities, restored state pointer, and green health.

A container restart without configuration and state restoration is not convergence. Any failed convergence is an immediate NO-GO.

## S05: Secret-only rotation

Rotate an approved reversible staging secret without changing the image.

Pass requires:

- previous and active image digests equal;
- previous and active configuration identities differ;
- final health green;
- production contact false;
- workflow proof, raw rotation receipt, and GitHub run metadata present.

## S06: Leakage and audit review

Scan all collected logs, receipts, state snapshots, API exports, and evidence artifacts for the in-memory canary and its encoded variants. The canary proof and raw findings report are both mandatory.

Pass requires zero matches and zero unauthorized access. Any match is an immediate NO-GO.

## S07: Final convergence and decision

Required checks:

- receipt manifest and every listed digest valid;
- target repository still at the authorized commit and clean;
- final host-health snapshot validates against `schemas/host-health.schema.json`;
- snapshot repository, commit, workflow run, artifact, HTTPS endpoint, image digest, configuration identity, and staging environment match the authorized run;
- final HTTP status is successful and health is green;
- all 18 checks and all eight scenarios derive PASS;
- no immediate NO-GO rule is triggered;
- evidence reconciliation reports no missing, altered, replayed, duplicated, or unledgered item.

The final report is generated from the recomputed decision. A manually edited report has no authority.
