<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: tools/phase6/CHANGE_REPORT.md
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
role: hardening_change_report
tags: [change, hardening, authority, traceability]
owner: igor_beylin
status: active
version: 1.0.0
updated: 2026-07-26
-->
# Phase 6H.2 Authority Hardening Change Report

## Objective

Close the second-audit false-GO paths by making evidence immutable after ingestion, executing terminal NO-GO law, separating evidence authority from ledger authority, requiring raw proof artifacts, binding evidence to one run and one control plane, and adding adversarial regression coverage.

## Finding resolution

| Finding | Root cause | Applied remediation | Closing evidence |
|---|---|---|---|
| Post-ingestion evidence mutation | Ledger digest was recorded but not reconciled against current files | Recompute record and artifact digests during every derivation and validation | Record-tampering and unledgered-file tests pass |
| Rehashed ledger forgery | Ledger had no external signature authority | Sign every event with an operator-held Ed25519 key and verify with independently supplied public key | Rehashed-ledger test is rejected |
| Self-attested provenance | Evidence shape and booleans were trusted without a separate authority | Separate evidence-attestor key, named producer digest, source and locator restrictions, strict record schema, and run binding | Wrong-key, fake-locator, live-synthetic, and cross-run replay tests pass |
| Decorative immediate NO-GO | Policy terminal rules were not evaluated | Execute all terminal rules before aggregation and force NO-GO | Unauthorized OIDC success test triggers terminal NO-GO |
| Optional or weak artifacts | Proof envelope alone could satisfy role requirements | Require raw Git, GitHub, OIDC, Infisical, workflow, leakage, receipt, and final-health artifacts by policy role | Policy and pack validators enforce role cardinality; synthetic role coverage passes |
| OIDC boolean claim | Signature authenticity was represented as a field | Verify RS256 against issuer JWKS, claims, timestamps, run/workflow identity, and exchange receipt; destroy raw token | Real-signature and corrupted-signature tests pass |
| Weak final health input | Health snapshot was minimally checked | Add strict host-health schema and exact commit, run, artifact, endpoint, image, configuration, and staging bindings | Bound-snapshot positive and wrong-commit negative tests pass |
| Weak receipt and audit inputs | Receipts accepted extra/unbound fields; audit export could contain secrets or no events | Strict receipt envelope, evidence-class details, run/artifact equality, non-empty staging audit, redaction and secret-shape rejection | Receipt and Infisical adversarial tests pass |
| Zero-test discovery and dirty validation order | Prior test layout was not discovered, and `py_compile` residue reached the pack validator | Standard `unittest.TestCase` suite, explicit nonzero discovery gate, and bytecode cleanup before exact-state validation | 19 tests discovered and passed; clean pack validator passes |

## Preserved contracts

- staging-only execution;
- zero target-repository source changes;
- no production access;
- digest-pinned image and release-owned configuration semantics;
- sequential S00-S07 lifecycle;
- reversible fault injection;
- live infrastructure and credentials remain external;
- no commit, push, merge, release, or deployment performed by this hardening pass.

## Contract changes

- evidence record schema advances to signed, run-bound v3 authority;
- GO authority now requires two distinct external public keys;
- collector proof must include policy-required raw artifact roles;
- final health input must satisfy `l9.deploy.phase6-host-health/v1`;
- workflow receipts are strict and bound to GitHub run and artifact IDs;
- synthetic evidence is test-only and cannot authorize live GO.
