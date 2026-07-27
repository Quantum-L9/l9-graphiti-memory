<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: tools/phase6/RUNBOOK.md
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
role: operator_runbook
tags: [runbook, staging, evidence, recovery]
owner: igor_beylin
status: active
version: 3.2.0
updated: 2026-07-26
-->
# Phase 6 Operator Runbook

## 1. Verify the delivered pack

From a clean extraction:

```bash
python3 scripts/validate_pack.py .
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --requirement requirements.txt
bash scripts/self_test.sh
```

Expected terminal results:

- adversarial test report: `PASS` with a nonzero discovered count;
- Python and Bash validation: success;
- pack validator: `{"status": "PASS", ...}`.

Stop if any result is Failed, Unknown, timed out, or applies to a different extraction.

## 2. Resolve the entry gate

Create the live configuration outside the pack:

```bash
cp config/phase6-inputs.example.json /secure/run/phase6-inputs.json
chmod 600 /secure/run/phase6-inputs.json
```

Resolve every `null` and independently establish:

- execution authorization and change ticket;
- exact repository checkout, ref, and commit;
- Phase 5 validation against that exact commit;
- protected `staging` environment and reviewer enforcement;
- required runner labels and runner eligibility;
- immutable GHCR image identity and attestation;
- pinned SSH host identity;
- healthy prior release and tested recovery path;
- reversible staging-only fault adapters;
- external unauthorized-OIDC probe;
- independent key custody.

Stop before mutation when any entry condition is Unknown.

## 3. Establish separate authorities

Follow `references/LIVE_COMMANDS.md` to generate:

- operator-held ledger keypair;
- independently held evidence-attestor keypair.

Exchange only public keys. Deliver public keys to the final verifier over independently controlled channels. Never place private keys in the run directory, target repository, logs, artifacts, or final evidence ZIP.

## 4. Initialize the run

Initialize once with the exact live configuration. Preserve the returned `RUN_DIR`; do not edit its input snapshot, run binding, trust anchors, or ledger.

Before S00, confirm the initialized control-plane digest matches the clean extracted pack.

## 5. Execute S00-S07 sequentially

Use `references/SCENARIO_MATRIX.md` as the ordering authority and `references/GO_NO_GO_POLICY.yaml` as the evidence authority.

For each external check:

1. Run only the policy-named collector.
2. Preserve the collector proof envelope and all required raw artifacts.
3. Inspect outputs for secrets before transfer.
4. Transfer the proof directory to the independent attestor.
5. Have the attestor derive and sign the evidence record using `build_evidence_record.py`.
6. Return the signed record and unchanged proof artifacts to the operator.
7. Import exactly once using `phase6ctl.py add-evidence`.
8. Recompute the decision before continuing.

The operator may not author PASS, edit signed records, replace imported artifacts, or combine the two private-key roles.

## 6. Observe terminal conditions

Stop immediately on:

- production contact;
- target source mutation;
- control-plane or run-binding drift;
- shared or mismatched authority keys;
- unauthorized OIDC exchange success;
- invalid-secret active-state mutation;
- rollback non-convergence;
- image change during secret-only rotation;
- canary or secret leakage;
- missing, altered, replayed, unledgered, or path-escaping proof;
- invalid signature or wrong-key evidence.

Do not continue merely to collect more failures.

## 7. Generate and independently validate the decision

Only the CLI may generate the report:

```bash
python3 scripts/phase6ctl.py generate-report \
  --run-dir "$RUN_DIR" \
  --ledger-signing-key /secure/operator/ledger-private.pem

python3 scripts/phase6ctl.py validate-evidence \
  --run-dir "$RUN_DIR" \
  --trusted-ledger-public-key /secure/verifier/ledger-public.pem \
  --trusted-evidence-public-key /secure/verifier/evidence-public.pem
```

Validation must recompute the control-plane digest, run binding, ledger chain and signatures, evidence signatures, record and artifact digests, source restrictions, policy checks, terminal NO-GO rules, scenario outcomes, and generated report.

A manually authored or edited report has no authority.

## 8. Package evidence

Package only after live-mode validation returns PASS:

```bash
bash scripts/package_evidence.sh \
  "$RUN_DIR" \
  /secure/verifier/ledger-public.pem \
  /secure/verifier/evidence-public.pem \
  /secure/output/l9-deploy-phase6-evidence.zip
```

Verify the evidence ZIP in a fresh extraction before handoff.

## 9. Failure and recovery

On any terminal trigger or integrity error:

1. stop further mutation;
2. restore the prior healthy staging release through the governed rollback path;
3. verify image digest, configuration identity, state pointer, and health;
4. preserve redacted evidence and incident metadata;
5. issue NO-GO or BLOCKED;
6. do not alter the target repository to repair the handoff run;
7. start a new run after remediation rather than rewriting the failed ledger.

Use `assets/INCIDENT_RECORD.template.md` and `references/ROLLBACK_RECOVERY.md`.
