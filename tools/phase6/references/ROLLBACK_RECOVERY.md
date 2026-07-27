<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: tools/phase6/references/ROLLBACK_RECOVERY.md
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
role: rollback_protocol
tags: [rollback, recovery, convergence, staging]
owner: igor_beylin
status: active
version: 1.0.0
updated: 2026-07-26
-->
# Rollback and Recovery

Before any candidate deployment, prove the previous release has:

- immutable image digest;
- release-owned runtime env identity and existing env file;
- valid state pointer;
- known healthy service state;
- retained Compose/release directory;
- separate database recovery plan when migrations are involved.

A successful rollback must restore all four governed dimensions:

1. image digest;
2. release-owned configuration identity;
3. active state pointer;
4. service health.

If rollback health fails, stop all further scenarios, preserve evidence, avoid repeated mutation, and escalate. Database restoration is never inferred from container rollback.

If OIDC trust behavior is incorrect, restore the prior staging release, disable or revoke the staging identity, and issue NO-GO.
