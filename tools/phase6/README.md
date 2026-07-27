<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: tools/phase6/README.md
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
role: package_readme
tags: [handoff, phase6, operator, evidence-authority]
owner: igor_beylin
status: active
version: 3.2.0
updated: 2026-07-26
-->
# L9 Deploy Phase 6 Operator Handoff

This portable pack gives an infrastructure-capable operator and an independent evidence authority the control plane needed to execute and validate the protected staging lifecycle for `Quantum-L9/l9-deploy`.

The pack does **not** contain credentials, private keys, secret values, production access, or proof that the live repository has passed Phase 5. Those are external authorities and must be established during preflight.

## Decision boundary

| State | Meaning |
|---|---|
| Offline self-test PASS | The packaged control plane rejects the modeled forgery and integrity bypasses. |
| BLOCKED | A required live authority, recovery path, input, or proof remains Unknown. |
| NO-GO | A terminal safety or integrity condition occurred. |
| GO | A complete live-mode evidence bundle passed independent validation. |

Offline PASS is never a staging GO.

## Start here

1. Verify the archive checksum through an independent channel.
2. Extract into a new, non-repository directory.
3. Verify `MANIFEST.sha256` by running `python3 scripts/validate_pack.py .`.
4. Create an isolated Python 3.11+ environment and install `requirements.txt`.
5. Run `bash scripts/self_test.sh`. Require all discovered tests and the pack validator to pass.
6. Read `RUNBOOK.md`, `references/TRUST_MODEL.md`, and `references/CURRENT_STATE_AND_UNKNOWNS.md`.
7. Copy `config/phase6-inputs.example.json` outside the pack and resolve every `null` without adding secrets to the file.
8. Establish distinct ledger-operator and evidence-attestor key custody.
9. Execute S00-S07 using `references/LIVE_COMMANDS.md` and `references/SCENARIO_MATRIX.md`.

## Roles

| Role | Owns | Must not own |
|---|---|---|
| Staging operator | Run initialization, ledger key, scenario execution, evidence import | Evidence-attestor private key or self-approval |
| Independent attestor | Collector-output inspection, evidence record derivation and signing | Ledger private key or scenario mutation |
| Final verifier | Both independently delivered public keys and final validation | Either private key |

The two private keys must never share an execution context.

## Core execution path

```text
collector output + raw proof artifacts
        ↓ independent inspection
signed, run-bound evidence record
        ↓ one-time operator import
signed append-only ledger
        ↓ policy derivation
machine-generated GO / NO-GO report
        ↓ independent public-key validation
evidence archive
```

There is no operator-supplied PASS command.

## Package navigation

- `RUNBOOK.md`: end-to-end operator procedure and recovery path.
- `AGENT_EXECUTION_PROMPT.md`: compact receiving-agent contract.
- `references/GO_NO_GO_POLICY.yaml`: executable checks and terminal law.
- `references/LIVE_COMMANDS.md`: exact command patterns.
- `references/SCENARIO_MATRIX.md`: ordered S00-S07 lifecycle.
- `references/TRUST_MODEL.md`: key custody, signatures, replay binding, and proof authority.
- `schemas/`: strict input, proof, host-health, and evidence schemas.
- `scripts/phase6ctl.py`: initialization, import, derivation, report, and validation CLI.
- `scripts/run_adversarial_tests.py`: isolated bounded regression runner.
- `tests/test_hardening.py`: authority and anti-forgery suite.

## Safety boundaries

- Production is forbidden.
- Target-repository source changes are forbidden.
- Raw OIDC tokens must be destroyed after verification.
- Private keys and secret values must remain outside this pack and outside evidence archives.
- Any production contact, source mutation, unauthorized OIDC success, secret leakage, invalid-secret state mutation, or rollback non-convergence is terminal NO-GO.

Do not copy the external negative-OIDC probe workflow into `l9-deploy`; keep it in an independently controlled repository or workflow surface.
