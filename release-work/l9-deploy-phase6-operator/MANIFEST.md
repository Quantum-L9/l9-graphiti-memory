<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/l9-deploy-phase6-operator/MANIFEST.md
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
role: package_manifest
tags: [manifest, inventory, execution-map, validation-map]
owner: igor_beylin
status: active
version: 3.1.0
updated: 2026-07-26
-->
# Package Manifest

## Control plane

- `SKILL.md`, `README.md`, `AGENT_EXECUTION_PROMPT.md`: receiving-agent authority and boundaries.
- `references/GO_NO_GO_POLICY.yaml`: 18 executable checks and terminal NO-GO law.
- `scripts/phase6ctl.py`: run initialization, signed ledger, evidence reconciliation, decision, report, and final validation.
- `scripts/phase6_integrity.py`: canonical hashing, Ed25519 signatures, and path containment.
- `scripts/build_evidence_record.py`: independent attestor boundary.

## Live evidence adapters

- repository, GitHub, OIDC, Infisical, workflow receipt, receipt-manifest, and final-convergence collectors under `scripts/`;
- `schemas/proof-envelope.schema.json`, `schemas/host-health.schema.json`, and nine strict evidence-class schemas;
- policy-owned source locators, producer digests, artifact roles, and check assertions.

## Operator material

- `RUNBOOK.md` and `references/LIVE_COMMANDS.md` for execution;
- `references/SCENARIO_MATRIX.md` for S00-S07;
- `references/TRUST_MODEL.md` for two-key custody and replay protection;
- `references/ROLLBACK_RECOVERY.md` and `assets/INCIDENT_RECORD.template.md` for failure handling;
- `assets/oidc-negative-probe.yml` for the external unauthorized probe.

## Validation and provenance

- `tests/test_hardening.py`: adversarial authority regression suite;
- `scripts/self_test.sh` and `scripts/validate_pack.py`: deterministic offline gates;
- `VALIDATION.md`, `validation_report.yaml`, and `CONVERGENCE_REPORT.yaml`: observed local results and remaining Unknowns;
- `MANIFEST.sha256`: exact file-level package integrity;
- `source-evidence/`: locked plan and Phase 1-4 provenance.

No credentials, private keys, live tokens, runtime environment files, or target-repository mutations are included.
