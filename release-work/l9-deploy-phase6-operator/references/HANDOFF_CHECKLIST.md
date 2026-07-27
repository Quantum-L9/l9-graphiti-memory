<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/l9-deploy-phase6-operator/references/HANDOFF_CHECKLIST.md
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
role: handoff_checklist
tags: [handoff, operator, attestor, verifier]
owner: igor_beylin
status: active
version: 3.1.0
updated: 2026-07-26
-->
# Agent Handoff Checklist

The receiving operator and independent evidence attestor acknowledge all of the following before live mutation:

- the ZIP checksum and manifest were verified from a clean extraction;
- Phase 5 is independently proven against the exact live revision;
- target source remains clean and production is forbidden;
- protected-environment approvals and exact runner labels are live;
- Infisical policy and audit are inspectable;
- the external negative-OIDC probe exists outside `l9-deploy`;
- the GHCR image is digest-pinned and attested;
- SSH host identity is pinned and the prior release is recoverable;
- fault adapters are reversible, test-only, and staging-only;
- ledger and evidence private keys have separate custody;
- both public keys reach the final validator independently;
- only collector-derived, proof-bearing, raw-source-backed, run-bound records will be signed;
- the final host-health snapshot matches the strict schema and exact authorized run, commit, artifact, endpoint, image, and configuration identity;
- missing authority, evidence, or recovery capability yields BLOCKED before mutation.
