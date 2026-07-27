<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/l9-deploy-phase6-operator/references/TRUST_MODEL.md
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
role: evidence_authority_model
tags: [trust, ed25519, provenance, separation-of-duties, replay-protection]
owner: igor_beylin
status: active
version: 1.0.0
updated: 2026-07-26
-->
# Phase 6 Evidence Trust Model

## Two independent authorities

Phase 6H.2 uses two distinct Ed25519 keypairs:

1. **Run-ledger key**: held by the staging operator. It signs append-only run events and generated-report events.
2. **Evidence-attestor key**: held by an independent approver or protected evidence-authority job. It signs collector-derived evidence records.

The keys must differ. The operator may not possess the evidence-attestor private key. The evidence attestor does not need staging mutation access.

Only public keys enter the run directory. Private keys, JWTs, secret values, SSH keys, and runtime environment files are forbidden from evidence and packaged output.

## Authority flow

```text
live authority/API/workflow/host
  -> packaged collector
  -> proof envelope + raw redacted artifacts
  -> independent evidence attestor
  -> signed evidence record
  -> operator imports record once
  -> operator-signed hash-chain event
  -> independent validator recomputes policy and report
```

`build_evidence_record.py` is the evidence-attestor boundary. It checks collector identity, collector executable digest, policy-owned source kind, authoritative locator shape, required proof roles, artifact paths and digests, schema constraints, and the current run binding before signing.

## Run and replay binding

Every signed evidence record contains the exact `integrity/run-binding.json` object:

- run ID;
- configuration SHA-256;
- ledger public-key fingerprint;
- evidence-attestor public-key fingerprint;
- executable control-plane digest.

A valid record from another run is rejected even when the same evidence-attestor key is reused.

## Control-plane binding

The run binding hashes the executable policy, all evidence schemas, the integrity and decision engines, the evidence builder, and every live collector. Changing any bound control-plane file after initialization invalidates the run.

The final archive checksum remains the external package identity. The independent validator should execute from a clean extraction whose ZIP checksum matches the handoff checksum.

## Trust assumptions

Cryptography does not make a compromised authority honest. Final GO assumes:

- the ledger private key remains with the operator;
- the evidence private key remains with an independent attestor or protected signing job;
- both public keys are delivered to the final validator through an independent channel;
- live collectors access the named authoritative systems;
- the final validator uses the trusted, checksummed pack.

If key separation, external public-key delivery, or clean-pack identity cannot be established, the run is `BLOCKED`, never GO.

## Synthetic mode

`synthetic_test` exists only for offline regression tests. Synthetic records are rejected in live mode and cannot authorize a live GO. `--allow-synthetic` is limited to the test suite and never appears in the live command sequence.
