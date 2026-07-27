<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/l9-deploy-phase6-operator/IMPROVEMENT_REPORT.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Phase 6H.2 Improvement Report

## Executive improvement decision

The two confirmed false-GO root causes from the second audit are remediated in the offline control plane. Evidence mutation, ledger rewriting, unsigned provenance, missing raw artifacts, terminal-rule bypass, forged OIDC claims, cross-run replay, manually authored GO reports, and weak final inputs are now deterministic rejection paths.

The pack is approved for transfer to an authorized live staging operator and independent evidence attestor. It does not prove that live Phase 6 passed.

## Baseline defects

- evidence content could change after ingestion without invalidating the run;
- a ledger could be rehashed without an external signature authority;
- evidence provenance was represented by caller-controlled fields;
- terminal `immediate_no_go` policy was not executable;
- raw proof artifacts were optional or could be substituted by the collector proof itself;
- the OIDC verifier boundary was not fully authoritative;
- the documented test command discovered zero tests.

## Accepted improvements

1. Distinct Ed25519 authorities for evidence records and ledger events.
2. External public-key verification and key-fingerprint run binding.
3. Signed hash-chained ledger with file-content reconciliation.
4. Signed evidence records bound to run ID, config digest, both authority keys, and control-plane digest.
5. Strict source kind, producer digest, source locator, scenario, class, and artifact-role enforcement.
6. Executable immediate NO-GO evaluation before normal aggregation.
7. Official-issuer OIDC signature and claim verification with token destruction.
8. Mandatory raw source artifacts for every external evidence family.
9. Strict workflow receipt envelope and check-specific detail requirements.
10. Strict non-empty, staging-only, redaction-verified Infisical audit input.
11. Strict final host-health schema and exact-run bindings.
12. Eighteen discovered adversarial tests plus exact-state package validation.

## Regression assessment

Existing staging boundaries, scenario ordering, rollback law, canary scanning, evidence packaging, prior-phase provenance, and zero-source-change constraints remain intact. No target repository was modified.

## Remaining gaps

Live GitHub, Infisical, GHCR, runner, SSH, Docker, and staging execution were not available and remain Unknown. Cryptographic integrity assumes honest, separate custody of the ledger and evidence private keys and independent delivery of both public keys.

## Updated validation status

`APPROVED_WITH_FINDINGS`: offline authority hardening passed; live Phase 6 execution remains required.
