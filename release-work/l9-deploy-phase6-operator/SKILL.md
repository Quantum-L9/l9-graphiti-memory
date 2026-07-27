---
name: l9-deploy-phase6-operator
description: execute and independently validate the l9-deploy protected staging lifecycle when live github actions, oidc, infisical, ghcr, ssh, docker, and staging access are available
skill_schema: 1
layer: control_plane
role: skill_entrypoint
tags: [l9-deploy, phase6, staging, oidc, rollback, evidence-authority]
owner: igor_beylin
status: active
version: 3.1.0
updated: 2026-07-26
sources:
  - source-evidence/PLAN_LOCKED.md
  - references/repository-baseline-manifest.json
---

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/l9-deploy-phase6-operator/SKILL.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# L9 Deploy Phase 6 Operator

## Purpose

Prove the complete protected staging lifecycle for `Quantum-L9/l9-deploy` while changing zero target-repository source files and never contacting production.

## Trigger and rejection

Use only when the executor has authorized staging access to GitHub Actions, the protected environment, OIDC, Infisical, GHCR, SSH, Docker, and live staging services, and an independent evidence attestor is available.

Reject production targets, missing Phase 5 proof, shared ledger/evidence keys, untrusted pack identity, unavailable rollback state, non-reversible fault injection, or unavailable independent public-key verification.

## Authority order

1. Latest explicit staging execution authorization.
2. Protected GitHub Environment and external security policies.
3. Locked plan P6-01 and unresolved U-04/U-05 requirements.
4. Live repository at the exact verified revision.
5. Independent evidence-attestor public key and run-ledger public key.
6. This checksummed pack and its executable policy.
7. Unknowns, which fail closed.

## Compact workflow

1. Verify the pack checksum and run `bash scripts/self_test.sh`.
2. Resolve the run configuration outside the pack and prove Phase 5 from the live checkout.
3. Establish separate ledger and evidence-attestor keypairs according to `references/TRUST_MODEL.md`.
4. Initialize the run with the ledger private key and evidence-attestor public key.
5. Execute the collectors named by `references/GO_NO_GO_POLICY.yaml`.
6. Have the independent evidence authority convert each proof envelope into a signed evidence record using `build_evidence_record.py`.
7. Import each signed record once with `phase6ctl.py add-evidence`; never author scenario status.
8. Execute S00-S07 sequentially. Never parallelize failure injection.
9. Generate the report from recomputed policy state.
10. Validate using both independently delivered public keys.
11. Package only after live-mode validation returns PASS.

## Non-negotiable rules

- Environment is exactly `staging`; production is forbidden.
- Target source remains clean from baseline through final convergence.
- Evidence and ledger keys are distinct and held by separate authorities.
- Raw OIDC tokens are destroyed; secret values never enter evidence.
- Images are digest-pinned and attested.
- Invalid-secret failure leaves active state unchanged.
- Rollback restores image, configuration identity, state pointer, and health.
- Secret-only rotation preserves the image digest.
- Missing, altered, replayed, unledgered, wrong-key, or wrong-source evidence yields NO-GO.
- A generated report has no authority unless `validate-evidence` recomputes the same decision.

## Resource map

- `RUNBOOK.md`: end-to-end operator execution, validation, and recovery.
- `MANIFEST.md`: package role, execution, and validation map.
- `references/TRUST_MODEL.md`: key custody, provenance, run binding, replay protection, and trust assumptions.
- `references/EXECUTION_CONTRACT.yaml`: mission, entry gates, invariants, and stop conditions.
- `references/ACCESS_MATRIX.md`: least-privilege external capability matrix.
- `references/PREFLIGHT.md`: entry-gate procedure.
- `references/SCENARIO_MATRIX.md`: ordered live scenarios.
- `references/OIDC_PROOF.md`: cryptographic positive/negative OIDC proof.
- `references/SECRET_SAFETY.md`: canary and leakage controls.
- `references/ROLLBACK_RECOVERY.md`: rollback convergence and emergency recovery.
- `references/EVIDENCE_CONTRACT.yaml`: evidence authority and bundle contract.
- `references/GO_NO_GO_POLICY.yaml`: executable decision law.
- `references/CURRENT_STATE_AND_UNKNOWNS.md`: established facts and live Unknowns.
- `references/HANDOFF_CHECKLIST.md`: receiving-agent and independent-attestor acknowledgment.
- `references/LIVE_COMMANDS.md`: exact command sequence.
- `references/REPOSITORY_BASELINE.md`: repository interface snapshot.
- `references/repository-baseline-manifest.json`: Phase 4 interface hashes.
- `references/REPO_WIRING_DECISION.md`: why this portable pack is not installed into the target repository.
- `scripts/generate_signing_key.py`: external Ed25519 key generation.
- `scripts/phase6_integrity.py`: canonical hashing, signatures, and path safety.
- `scripts/build_evidence_record.py`: independent evidence-attestor boundary.
- `scripts/phase6ctl.py`: run initialization, signed ledger, evidence reconciliation, decision, report, and validation.
- `scripts/collect_repository_evidence.py`: repository and Phase 5 proof.
- `scripts/collect_github_evidence.py`: protected-environment and runner proof.
- `scripts/verify_oidc_claims.py`: issuer-JWKS OIDC verification and token destruction.
- `scripts/collect_infisical_audit.py`: redacted Infisical audit proof.
- `scripts/collect_workflow_evidence.py`: workflow run and artifact-bound receipts.
- `scripts/collect_host_evidence.py`: pinned-host readiness capture.
- `scripts/validate_receipts.py`: receipt-manifest verification.
- `scripts/collect_final_convergence.py`: final staging health proof.
- `scripts/package_evidence.sh`: independently validated evidence archive builder.
- `scripts/self_test.sh`: exact offline and adversarial validation.
- `schemas/`: strict input, proof, host-health, and evidence-class contracts.
- `assets/`: incident, staging inventory, and external negative-probe materials.
- `source-evidence/README.md`: governing plan and prior-phase provenance.

## Validation

```bash
bash scripts/self_test.sh
python3 scripts/validate_pack.py .
```

Live GO additionally requires every policy check and scenario to pass with `validation_mode: live`, no terminal NO-GO trigger, and both external trust anchors.

## Failure handling

Stop on production targeting, dirty source, missing Phase 5 proof, key-role collapse, control-plane drift, unauthorized OIDC success, canary leakage, active-state mutation, rollback non-convergence, evidence loss, signature failure, replay detection, or an unavailable independent validator. Preserve redacted evidence, restore the prior healthy staging state, and issue NO-GO.
