<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: tools/phase6/VALIDATION.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Phase 6H.2 Final Validation

## Validated scope

The validation suite covers the offline control plane delivered in this archive: schemas, policy execution, source restrictions, artifact containment, evidence signatures, ledger signatures and chaining, replay binding, report authority, OIDC verification logic, and packaging integrity.

It does not claim that live GitHub, Infisical, GHCR, SSH, Docker, rollback, or staging operations have passed.

## Required command

```bash
bash scripts/self_test.sh
```

The self-test:

1. discovers the adversarial suite;
2. runs every test in an isolated Python process with a bounded timeout;
3. emits a machine-readable test report outside the pack;
4. compiles all Python files;
5. validates all Bash scripts;
6. runs the exact-state pack validator.

Set `PHASE6_TEST_REPORT` to choose the report path and `PHASE6_TEST_TIMEOUT_SECONDS` to change the per-test timeout.

## Closing checks

| Check | Required result |
|---|---:|
| Isolated adversarial discovery and execution | PASS, 19 tests |
| Python compilation | PASS |
| Bash syntax | PASS |
| JSON and YAML parsing | PASS |
| JSON Schema validity | PASS |
| Evidence mutation and ledger forgery rejection | PASS |
| Wrong-key, shared-key, and replay rejection | PASS |
| Artifact containment and digest reconciliation | PASS |
| Synthetic live evidence and fake locator rejection | PASS |
| Executable immediate NO-GO law | PASS |
| OIDC signature verification and token destruction | PASS |
| Manual GO report rejection | PASS |
| Workflow receipt and final-health binding | PASS |
| Infisical audit redaction and non-empty evidence | PASS |
| Manifest and package-tree integrity | PASS |

## Interpretation

A clean result means the delivered control plane is ready for authorized live evidence collection. It does not authorize production, prove Phase 5, or create a live Phase 6 GO.
