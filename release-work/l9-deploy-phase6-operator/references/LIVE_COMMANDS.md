<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/l9-deploy-phase6-operator/references/LIVE_COMMANDS.md
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
role: live_command_sequence
tags: [commands, phase6, keys, evidence, validation]
owner: igor_beylin
status: active
version: 3.1.0
updated: 2026-07-26
-->
# Phase 6H.2 Live Commands

The paths below are examples. Keep all private keys and run data outside the handoff pack.

## 1. Create separate authorities

Operator context:

```bash
python3 scripts/generate_signing_key.py \
  --purpose ledger \
  --private-key /secure/operator/ledger-private.pem \
  --public-key /secure/operator/ledger-public.pem
```

Independent evidence-authority context:

```bash
python3 scripts/generate_signing_key.py \
  --purpose evidence-attestor \
  --private-key /secure/attestor/evidence-private.pem \
  --public-key /secure/attestor/evidence-public.pem
```

Exchange only public keys. The two private keys must never share custody.

## 2. Initialize

```bash
RUN_DIR=$(python3 scripts/phase6ctl.py init \
  --config /secure/run/phase6-inputs.json \
  --run-root /secure/run/evidence \
  --ledger-signing-key /secure/operator/ledger-private.pem \
  --trusted-evidence-public-key /secure/attestor/evidence-public.pem)
```

## 3. Collect, attest, and import each check

Collector context:

```bash
python3 scripts/collect_repository_evidence.py \
  --config /secure/run/phase6-inputs.json \
  --check-id phase5_validation_passed \
  --output-root /secure/run/stage
```

Independent attestor context:

```bash
python3 scripts/build_evidence_record.py \
  --run-dir "$RUN_DIR" \
  --check-id phase5_validation_passed \
  --proof-file /secure/run/stage/evidence/artifacts/phase5_validation_passed/repository-proof.json \
  --artifact-root /secure/run/stage \
  --evidence-signing-key /secure/attestor/evidence-private.pem \
  --output /secure/run/records/phase5_validation_passed.json
```

Operator context:

```bash
python3 scripts/phase6ctl.py add-evidence \
  --run-dir "$RUN_DIR" \
  --file /secure/run/records/phase5_validation_passed.json \
  --artifact-root /secure/run/stage \
  --ledger-signing-key /secure/operator/ledger-private.pem
```

Repeat only with the collector and check mapping in `GO_NO_GO_POLICY.yaml`.

## Required raw proof roles

A collector proof is not sufficient by itself. The policy requires the corresponding raw source roles, including Git outputs, GitHub API exports, OIDC JWKS and exchange receipts, the redacted Infisical audit export, workflow receipts plus GitHub run metadata, canary findings, the receipt manifest, and the strict host-health snapshot. `build_evidence_record.py` rejects a proof directory missing any policy-owned role.

For final convergence, prepare a `l9.deploy.phase6-host-health/v1` snapshot that validates against `schemas/host-health.schema.json`, then run:

```bash
python3 scripts/collect_final_convergence.py \
  --config /secure/run/phase6-inputs.json \
  --health-snapshot /secure/run/authoritative-host-health.json \
  --convergence-id "$RUN_ID" \
  --output-root /secure/run/stage
```

The independent attestor must verify how the snapshot was obtained before signing it.

## 4. Canary scan

```bash
PHASE6_CANARY_VALUE="$CANARY" python3 scripts/phase6ctl.py scan-canary \
  --root /secure/run/material-to-scan \
  --output-root /secure/run/stage \
  --scan-id "$RUN_ID"
```

Attest and import `canary_scan_zero_matches` through the same evidence-authority flow.

## 5. Generate and independently validate

```bash
python3 scripts/phase6ctl.py generate-report \
  --run-dir "$RUN_DIR" \
  --ledger-signing-key /secure/operator/ledger-private.pem

python3 scripts/phase6ctl.py validate-evidence \
  --run-dir "$RUN_DIR" \
  --trusted-ledger-public-key /secure/verifier/ledger-public.pem \
  --trusted-evidence-public-key /secure/verifier/evidence-public.pem
```

## 6. Package

```bash
bash scripts/package_evidence.sh \
  "$RUN_DIR" \
  /secure/verifier/ledger-public.pem \
  /secure/verifier/evidence-public.pem \
  /secure/output/l9-deploy-phase6-evidence.zip
```

There is no operator-supplied PASS command. Synthetic mode and `--allow-synthetic` are test-only and forbidden in live execution.
