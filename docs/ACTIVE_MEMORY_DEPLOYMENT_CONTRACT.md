<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/ACTIVE_MEMORY_DEPLOYMENT_CONTRACT.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Active Memory Deployment Contract

This document defines what any consumer application must satisfy to
run a compliant active-memory deployment against this package. It is
deployment-neutral: it does not reference any specific consumer
application, hosting provider, or orchestration tool.

## Required deployment properties

A compliant deployment MUST:

1. Define a unique `deployment_id` and `trust_domain`
   (see ADR-065) that are not recognized placeholder values when
   `environment = production`.
2. Not expose the Redis backend on any publicly routable network
   interface. The backend should be reachable only from the processes
   that constitute this deployment.
3. Require authentication on the Redis backend (no `nopass`, no
   anonymous default-user access) in `staging` and `production`
   environments.
4. Supply Redis credentials via one of the supported credential
   sources in `RedisCredentialSettings` (see ADR-066), documented in
   the consumer's own deployment configuration.
5. Set a bounded `maxmemory` and an eviction policy appropriate for
   ephemeral, TTL-bearing keys (e.g. `volatile-lru` or
   `allkeys-lru`) on the Redis backend.
6. Run a startup capability probe (PING, authenticated scalar
   read/write, sorted-set read/write, publish) before declaring the
   deployment healthy.
7. Test backend-outage behavior at least once before declaring
   production readiness: stop the backend, confirm the consumer
   application degrades according to its configured `required` flag,
   and confirm canonical (non-active-memory) operations are
   unaffected.
8. Run the adapter-conformance smoke subset
   (`tests/conformance/active/`) against the deployed backend
   configuration as part of deployment validation.
9. Ensure diagnostic/log output from the deployment redacts credential
   material, consistent with `ResolvedRedisCredential.redacted_summary()`.

## Explicitly out of scope for this document

This contract does not specify:

- Which container runtime, orchestrator, or cloud provider to use.
- Specific firewall or network ACL tooling.
- Specific secret-management product integration.

Those choices belong entirely to the consumer application's own
deployment repository, per the ownership split established when this
plan was revised (core subsystem vs. consumer-owned deployment).

## Compliance checklist (consumer-side)

A consumer deployment runbook should be able to check every box below
without needing to read this package's source code:

- [ ] `deployment_id` and `trust_domain` chosen and validated.
- [ ] Redis backend not publicly reachable.
- [ ] Redis authentication enabled.
- [ ] Credential source chosen and secret material never committed.
- [ ] `maxmemory` and eviction policy configured.
- [ ] Startup capability probe passes.
- [ ] Backend-outage test performed at least once.
- [ ] Adapter-conformance smoke subset passes against the real backend.
- [ ] Diagnostic output reviewed for credential leakage.
