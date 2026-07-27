<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/l9-deploy-phase6-operator/references/CURRENT_STATE_AND_UNKNOWNS.md
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
role: state_boundary
tags: [state, unknowns, phase5, provenance]
owner: igor_beylin
status: active
version: 3.1.0
updated: 2026-07-26
-->
# Current State and Unknowns

## Established by this pack

- P6-01 is a protected staging lifecycle with zero target-repository source changes.
- The control plane contains executable policy checks, strict evidence schemas, two-key authority separation, run binding, signed ledger events, proof-artifact reconciliation, raw source-artifact role enforcement, terminal NO-GO enforcement, official-JWKS OIDC verification, strict final-health binding, redacted Infisical audit validation, and adversarial tests.
- Phase 1 through Phase 4 source evidence is retained as provenance.
- Canonical identity is `Quantum-L9/l9-deploy`.

## Not established by this pack

- The exact live remote revision or whether all earlier phases are merged.
- Whether Phase 5 release artifacts and `uv.lock` are current and valid.
- Current protected-environment rules, runner state, OIDC policy, Infisical policy, GHCR permissions, SSH access, Docker state, staging health, or rollback readiness.
- Whether the receiving organization has implemented truly independent evidence-key custody and independently sourced the collector inputs.
- Whether live staging scenarios pass.

## Mandatory interpretation

Offline PASS proves only that the control plane rejects the modeled bypasses. It does not prove staging readiness. A prior conversational statement, locally authored JSON, synthetic evidence, or a manually written GO report has no authority. Live GO exists only after independent validation of a complete live-mode bundle.
