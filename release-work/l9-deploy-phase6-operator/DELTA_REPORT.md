<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/l9-deploy-phase6-operator/DELTA_REPORT.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Phase 6H.2 Delta Report

| Before second hardening | After Phase 6H.2 |
|---|---|
| Evidence could be edited after import | Every record and artifact digest is reconciled against a signed ledger event |
| Ledger could be rewritten and rehashed | Every ledger event requires the separate operator Ed25519 signature |
| Record provenance was self-declared | Independent evidence-attestor signature, named producer digest, source restriction, and locator contract are required |
| One authority could control proof and event history | Evidence and ledger keys must be distinct and independently delivered |
| Cross-run record replay was possible in principle | Every record binds run ID, config digest, both key fingerprints, and control-plane digest |
| `immediate_no_go` existed only in YAML | All terminal rules execute before scenario aggregation |
| Collector proof could stand in for raw evidence | Policy requires raw Git/API/JWKS/receipt/audit/health artifacts by role and cardinality |
| OIDC authenticity could be a boolean assertion | JWT signature, issuer, audience, time, subject, run, workflow, JWKS, and exchange receipt are verified |
| Workflow receipts admitted weak structure | Exact envelope, class schema, check-specific fields, and run/artifact equality are enforced |
| Infisical audit could be empty or leak values | Non-empty staging events, redaction checks, and secret-shape rejection are enforced |
| Final health was minimally typed | Exact repository, commit, run, artifact, endpoint, image, config, HTTP, and time bindings are required |
| Documented `unittest` invocation found zero tests | Standard discovery finds and executes 19 tests; zero tests is a hard failure |
