<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/l9-deploy-phase6-operator/references/PREFLIGHT.md
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
role: preflight_runbook
tags: [preflight, phase5, staging, readiness, key-custody]
owner: igor_beylin
status: active
version: 3.1.0
updated: 2026-07-26
-->
# Preflight

## 1. Verify the control plane

- Confirm the downloaded ZIP checksum through an independent channel.
- Extract into a clean directory and run `bash scripts/self_test.sh`.
- Install only the pinned dependencies in `requirements.txt`.
- Reject any modified control-plane digest or missing manifest entry.

## 2. Freeze authority and inputs

- Record explicit authorization, change ticket, operator, independent approver, and intended terminal state.
- Confirm the target is exactly `staging` and production is forbidden.
- Complete a run-specific input file conforming to `schemas/phase6-input.schema.json` outside the pack.
- Store names, identifiers, paths, and digests only. Never store secret values.

## 3. Enforce key separation

- Generate a run-ledger key under operator custody.
- Generate an evidence-attestor key under independent custody.
- Exchange public keys independently.
- Prove the keys are distinct.
- Block execution if the operator can access the evidence private key or the attestor can mutate staging.

## 4. Bind the live repository

Capture `git remote get-url origin`, `git rev-parse HEAD`, `git symbolic-ref -q HEAD`, and `git status --porcelain=v1 --untracked-files=all`. Require canonical repository identity, the authorized SHA/ref, and a clean worktree.

Use `collect_repository_evidence.py` for `phase5_validation_passed`; it executes the configured Phase 5 validator and produces a proof envelope plus command output. A prior conversational statement is not evidence.

## 5. Verify external authorities

Collect redacted proof for protected GitHub Environment rules, required reviewers, exact online runner labels, OIDC policy, Infisical staging identity and audit access, immutable GHCR digest and attestation, pinned SSH host, Docker readiness, prior active and rollback release identities, health endpoint, and reversible test-only fault adapters.

## 6. Initialize and capture baseline

Initialize the run only after steps 1-5 pass. The initialization event binds the configuration, both public keys, and executable control plane. Capture active image digest, active configuration identity, state pointer, containers, health, and rollback recovery information without secret values.

No live mutation is permitted until the `phase5_validation_passed`, `protected_environment_enforced`, and `exact_runner_labels_verified` signed records are imported and derive PASS.
