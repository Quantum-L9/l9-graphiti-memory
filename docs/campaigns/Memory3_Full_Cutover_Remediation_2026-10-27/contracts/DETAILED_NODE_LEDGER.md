# File-level Remediation Node Ledger

**143 nodes, as-of 2026-10-27. All states are planning/evidence definitions, not completed execution.**

## P00. Architecture decision, source/authority inventory

### GOV-01  Revision-bound authority and source census
**Owner:** Quantum-L9/l9-graphiti-memory + Quantum-L9/.github  |  **Scope:** core  |  **Risk:** high  |  **Kind:** authority  |  **Status:** proposed

**Intent:** Resolve and pin exact main, PR101, PR784 and global identity/product-kind authority, with observed vs uninspected evidence.

**Acceptance:** (1) Revision manifest binds full SHAs (2) every consequential finding points to owner and source (3) missing sources remain UNKNOWN.

**Negative controls:** (1) Stale SHA must not qualify as current.

**Source paths:** AGENTS.md, docs/adr/README.md, product-topology.yaml, docs/REMEDIATION_AND_INTEGRATION_PLAN.md
**Proposed tests/proofs:** new:authority_snapshot_consistency, new:source_epoch_refusal
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** none

### GOV-02  Admit full-cutover decision to working plan
**Owner:** Quantum-L9/l9-graphiti-memory + Quantum-L9/.github  |  **Scope:** core  |  **Risk:** high  |  **Kind:** decision  |  **Status:** operator_decision_observed

**Intent:** Capture operator instruction: no historical transport, auth, data or migration compatibility; no second Memory authority.

**Acceptance:** (1) Current plan declares oauth native HTTP only and no stdio/signed-agent/static bearer fallback (2) prior campaign record retained immutable.

**Negative controls:** (1) Old stdio or signed-agent paths cannot be treated as required compatibility.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:forbidden_fallback_manifest
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-01

### GOV-03  Supersede conflicting legacy ADRs explicitly
**Owner:** Quantum-L9/l9-graphiti-memory + Quantum-L9/.github  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Record a new dated superseding ADR rather than rewriting historical ADR decisions into apparent original intent.

**Acceptance:** (1) New ADR explicitly supersedes transport/auth/client provisions of ADR-038, ADR-082, ADR-083, ADR-098, and ADR-064 where applicable (2) all ten AGENTS invariants preserved or amendment approved by owner.

**Negative controls:** (1) No accepted ADR may still require a live Memory stdio door.

**Source paths:** docs/adr/README.md, docs/adr/ADR-038-sdk-mcp-cli-and-http-surface.md, docs/adr/ADR-098-remote-mcp-transport-and-signed-agent-http-identity.md, docs/adr/ADR-082-consumer-control-plane-transport-parity.md, docs/adr/ADR-064-cursor-client-instantiation-and-proof-boundary.md
**Proposed tests/proofs:** new:adr_supersession_consistency, new:legacy_transport_negative
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-02

### GOV-04  Reconfirm Memory Dependency hosted-service exception
**Owner:** Quantum-L9/l9-graphiti-memory + Quantum-L9/.github  |  **Scope:** core  |  **Risk:** medium  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Use the already admitted product-kind exception instead of inventing a new node or Gate route.

**Acceptance:** (1) Topology explicitly binds l9.product-kind-exception/memory-hosted-service@1 and service runtime identity (2) no ConstellationIdentity asserted.

**Negative controls:** No additional negative specified

**Source paths:** product-topology.yaml, release-work/product-release-binding.yaml
**Proposed tests/proofs:** existing:validate_product_topology, new:hosted_exception_exact_subject
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-01

### GOV-05  Identity dimensions and provenances contract
**Owner:** Quantum-L9/l9-graphiti-memory + Quantum-L9/.github  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Distinguish product, release, runtime, actor, surface, constellation applicability, and nonidentity OAuth principal claims.

**Acceptance:** (1) Every field has a canonical owner, evidence input and unknown/invalid policy (2) auth never treated as authorship or surface attestation.

**Negative controls:** (1) An OAuth client_id alone cannot prove execution surface or agent authorship.

**Source paths:** src/l9_graphite_memory/contracts/identity.py, docs/adr/ADR-083-server-side-local-authorization-and-one-class-vocabulary.md
**Proposed tests/proofs:** new:identity_authority_matrix
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-04, GOV-02

### GOV-06  Threat model native OAuth agent/machine distinction
**Owner:** Quantum-L9/l9-graphiti-memory + Quantum-L9/.github  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Prove user/client authentication does not silently claim agent actor or mobile-specific surface; prohibit prompt-controlled identity.

**Acceptance:** (1) Threat model covers stolen token, client-ID spoofing, false surface, cross-tenant authorization, admin escalation, replay, token exchange and revocation.

**Negative controls:** (1) Unsigned headers and user input cannot promote unknown ActorIdentity to resolved.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:threat_model_abuse_case_register
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-05

### GOV-07  No-legacy-data cutover disposition
**Owner:** Quantum-L9/l9-graphiti-memory + Quantum-L9/.github  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Preserve operator-confirmed old SQLite backup and narrowly authorized legacy Memory retirement while requiring a fresh isolated PostgreSQL 16 database.

**Acceptance:** (1) No unapproved migration or import of old Memory/Neo4j (2) fresh database lifecycle and rollback policy distinguish pre-first-write from post-first-write.

**Negative controls:** (1) Backup attestation is not misrepresented as independently reverified (2) no Graphiti/Neo4j deletion.

**Source paths:** docs/adr/ADR-072-shared-canonical-store-backend.md, docs/adr/ADR-077-canonical-store-backend-transition-safety.md
**Proposed tests/proofs:** new:cutover_scope_negatives
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-02

### GOV-08  Cross-repository ownership / PR disposition
**Owner:** Quantum-L9/l9-graphiti-memory + Quantum-L9/.github  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Memory owns server, protocol, policy, package and carrier; Cursor-Governance consumes canonical identity projection and native client config; l9-deploy owns hosting and release.

**Acceptance:** (1) PR101 remains carrier candidate until OAuth retarget (2) PR784 remains consumer candidate until native endpoint and actor provenance proof (3) no new identity registry.

**Negative controls:** (1) No second MCP gateway or OAuth server inside Cursor-Governance.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:cross_repo_contract_refs
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-03, GOV-04

### GOV-09  Source coverage census and audit closure routing
**Owner:** Quantum-L9/l9-graphiti-memory + Quantum-L9/.github  |  **Scope:** full  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Recover original 144-module ledger, which was not attached, and rerun targeted missing large-file source census with line ranges.

**Acceptance:** (1) Every one of 20 confirmed and nine unresolved concerns classified (2) uninspected code remains explicitly NOT_REVIEWED (3) discoveries fed back as new nodes.

**Negative controls:** (1) Do not declare whole-codebase audit complete from 36 fully read files.

**Source paths:** src/l9_graphite_memory/services/memory_service.py, src/l9_graphite_memory/adapters/postgres_store.py, src/l9_graphite_memory/server.py
**Proposed tests/proofs:** new:source_coverage_ledger, new:nonzero_unreviewed_alarm
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-01

### QA-01  Map all audit findings to verified fix or proven removal
**Owner:** independent reviewer + repository CI  |  **Scope:** full  |  **Risk:** high  |  **Kind:** assurance  |  **Status:** proposed

**Intent:** Build one finding registry for F-001..F-020 and nine unresolved U issues, preserving promoted/disproven history.

**Acceptance:** (1) All findings have owner, node, test, status, scope and release gate (2) nothing omitted.

**Negative controls:** (1) No item closed if faulty code remains reachable.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:findings_coverage_linter
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-09

## P01. Canonical data integrity and sensitive admission

### DATA-01  Prevent ambiguous integer PII corruption
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Fix F-010 redaction of Unix epochs and numeric ticket identifiers without losing detection of true phone/SSN.

**Acceptance:** (1) Integer epochs and nine-digit IDs persist accurately or receive explicit ambiguity outcome (2) true formatted phone/SSN sanitized per policy.

**Negative controls:** (1) 1761573600 and 123456789 must not silently collapse to placeholders.

**Source paths:** src/l9_graphite_memory/admission/normalization.py, src/l9_graphite_memory/services/memory_service.py
**Proposed tests/proofs:** new:test_pii_numeric_negative_matrix, existing:test_normalization
**Findings:** F-010  |  **Prerequisites:** GOV-02

### DATA-02  Ambiguous PII policy explicit quarantine or evidence
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Handle indistinguishable unformatted phone/identifier through policy and meaningful warnings, not silent preservation or silent replacement.

**Acceptance:** (1) Ambiguous values are quarantined or require declarative context (2) redaction confidence recorded as evidence.

**Negative controls:** (1) Unformatted genuine phone cannot be unconditionally exempted.

**Source paths:** src/l9_graphite_memory/admission/normalization.py, src/l9_graphite_memory/admission/policy.py
**Proposed tests/proofs:** new:test_ambiguous_pii_quarantine
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** DATA-01

### DATA-03  Normalized content, digest and provenance integrity
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Bind redacted normalized text and source digest to provenance with clear lossless/changed status and collision prevention.

**Acceptance:** (1) Different operational epochs yield distinguishable canonical normalized content/digests (2) original digest before transformation preserved.

**Negative controls:** (1) Different source content with distinct accepted semantics cannot share redacted digest silently.

**Source paths:** src/l9_graphite_memory/admission/normalization.py, src/l9_graphite_memory/services/memory_service.py
**Proposed tests/proofs:** new:test_digest_collision_negative, new:test_admission_content_provenance
**Findings:** F-010  |  **Prerequisites:** DATA-01, DATA-02

### DATA-04  Explicit evidence cannot be fabricated by MCP
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Transport provenance is not EvidenceKind.EXPLICIT and does not prove human consent.

**Acceptance:** (1) Sensitive identity/preference request without independent explicit evidence is REJECTED regardless of authenticated connector.

**Negative controls:** (1) Authenticated write alone cannot mint explicit sensitive evidence.

**Source paths:** src/l9_graphite_memory/mcp_tools.py, src/l9_graphite_memory/services/generated_data.py, src/l9_graphite_memory/admission/engine.py
**Proposed tests/proofs:** new:test_mcp_sensitive_without_explicit, existing:test_write_agent_mcp
**Findings:** F-012  |  **Prerequisites:** GOV-05

### DATA-05  Purpose-bound consent semantics and timestamps
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** policy_decision  |  **Status:** proposed

**Intent:** Resolve U-012 policy on consent.granted_at vs valid_from, preserving time semantics and requiring actual subject authorization.

**Acceptance:** (1) Typed consent with subject/class/namespace/purpose/issued/expiry checked at documented event time (2) past valid_from treated deliberately, not now by accident.

**Negative controls:** (1) Wrong subject, class, purpose, namespace or time cannot be admitted.

**Source paths:** src/l9_graphite_memory/mcp_tools.py, src/l9_graphite_memory/contracts/privacy.py, src/l9_graphite_memory/admission/engine.py
**Proposed tests/proofs:** new:test_retrospective_valid_from_consent, new:test_consent_expiry_and_revoke
**Findings:** U-012  |  **Prerequisites:** DATA-04, GOV-03

### DATA-06  End-to-end sensitive admission negative matrix
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** integration_proof  |  **Status:** proposed

**Intent:** Integrate normalization, explicit evidence, consent and canonical store test through native MCP and direct SDK.

**Acceptance:** (1) A valid authorized sensitive request admits (2) invalid sensitive requests reject without persisted record (3) warnings/receipts consistent.

**Negative controls:** (1) No bypass through memory.write_agent, ingest, write_governed or generated-data.

**Source paths:** tests/integration/, tests/unit/test_normalization.py
**Proposed tests/proofs:** new:test_sensitive_admission_end_to_end
**Findings:** F-010, F-012, U-012  |  **Prerequisites:** DATA-03, DATA-05

## P02. Auth0 OAuth resource server and Postgres security

### AUTH-01  Auth0 tenant resource-parameter and client proof
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** external_proof  |  **Status:** proposed

**Intent:** Verify Auth0 Resource Parameter Compatibility Profile, API audience, RFC8707 resource, client registration and target Claude/Cursor behavior before coding an assumption.

**Acceptance:** (1) Real PKCE authorization produces aud-bound access token for Memory resource and expected scope (2) no userinfo-audience fallback.

**Negative controls:** (1) resource mismatch or third-party client denied aud must fail release.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:auth0_live_discovery_receipt, new:pkce_audience_probe
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-06, GOV-08

### AUTH-02  OAuth protected resource metadata (RFC9728)
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Advertise one resource and one authorized issuer from native Memory endpoint with correct WWW-Authenticate metadata pointer.

**Acceptance:** (1) /.well-known/oauth-protected-resource serves valid resource, authorization_servers, scopes (2) unauthenticated /mcp challenges with resource_metadata.

**Negative controls:** (1) Incorrect resource URI and unreachable AS metadata rejected.

**Source paths:** src/l9_graphite_memory/server.py, docs/REMOTE_MCP_CONTRACT.md
**Proposed tests/proofs:** new:test_oauth_prm_discovery
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-01, GOV-03

### AUTH-03  Authorization-server discovery and client metadata contract
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Consume Auth0 OIDC / RFC8414 discovery; do not synthesize a second issuer or brittle authorization endpoint rewriting.

**Acceptance:** (1) Issuer, authorization endpoint, JWKS, PKCE and client registration behavior validated against real tenant (2) CIMD supported or controlled static registration documented.

**Negative controls:** (1) Mismatched discovery issuer blocks server startup.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:test_oauth_discovery_metadata
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-01, AUTH-02

### AUTH-04  Native resource server middleware
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Install upstream OAuth-compatible MCP SDK security layer where adequate; server enforces auth before dispatch.

**Acceptance:** (1) Authenticated caller is verified per request by one middleware (2) no client-controlled claims or custom signed headers (3) SDK gap documented if library insufficient.

**Negative controls:** (1) Anonymous, invalid and wrong-resource requests refused.

**Source paths:** src/l9_graphite_memory/server.py, pyproject.toml
**Proposed tests/proofs:** new:test_native_mcp_oauth_authentication
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-02, AUTH-03

### AUTH-05  Cryptographic token verification JWKS/JWT
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Verify issuer, exact audience, signature/alg allowlist, kid, exp, nbf, freshness and key rotation from Auth0.

**Acceptance:** (1) Forged, expired, not-yet-valid, tampered, wrong issuer, wrong audience, unsupported alg tokens all rejected before reaching tools.

**Negative controls:** (1) alg none, kid confusion, wrong aud, invalid nbf, issuer alias all denied.

**Source paths:** src/l9_graphite_memory/authz/, src/l9_graphite_memory/config/models.py
**Proposed tests/proofs:** new:test_jwt_negative_matrix, new:test_jwks_rotation
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-04

### AUTH-06  OAuth scopes, tool risk and resource binding
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Enforce least-privilege scopes for read, write, maintain and administrator workflows above namespace policy.

**Acceptance:** (1) Scope refusal is distinct from missing namespace grant (2) admin/high-risk tools require independently authorized privileged channel.

**Negative controls:** (1) Read token cannot mutate, admin operation cannot be obtained with ordinary tool scope.

**Source paths:** src/l9_graphite_memory/mcp_tools.py, src/l9_graphite_memory/authz/, src/l9_graphite_memory/services/memory_service.py
**Proposed tests/proofs:** new:test_scope_tool_matrix, existing:namespace_authorization
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-05

### AUTH-07  Auth0 client registrations for Claude and Cursor
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** external_proof  |  **Status:** proposed

**Intent:** Register distinct, narrow client identities or CIMD with explicit Auth0 controls; refuse uncontrolled DCR.

**Acceptance:** (1) Claude and Cursor integrations authenticate through provider-managed OAuth with distinct verified authorization context (2) PKCE and redirect URIs grounded in actual clients.

**Negative controls:** (1) Unapproved DCR clients must not acquire Memory privileges.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:auth0_claude_login_probe, new:auth0_cursor_login_probe
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-01, AUTH-06

### AUTH-08  Server-derived principal and namespace grants
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Derive principal, tenant, organization, workspace, user and roles from verified issuer/subject and server policy, not request.

**Acceptance:** (1) All tool paths reuse one MemoryPrincipal (2) tenant and namespace maps on server (3) cross-tenant refusals verified.

**Negative controls:** (1) Payload-submitted user_id/tenant_id/scope does not override grants.

**Source paths:** src/l9_graphite_memory/contracts/identity.py, src/l9_graphite_memory/runtime.py, src/l9_graphite_memory/authz/, src/l9_graphite_memory/group_resolver.py
**Proposed tests/proofs:** new:test_oauth_principal_resolution, existing:tenant_isolation_suite
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-05, AUTH-06

### AUTH-14  Token, grant and JWKS revocation/rotation
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Define bounded JWKS cache, refresh and old-key refusal; do not treat Infisical reload as completed authenticator refresh.

**Acceptance:** (1) Key rotation, permission withdrawal and replay across resource audience have measured behavior (2) no stale grants after required bound.

**Negative controls:** (1) Removed grant cannot continue writing after refresh boundary.

**Source paths:** src/l9_graphite_memory/secrets.py, src/l9_graphite_memory/server.py
**Proposed tests/proofs:** new:test_key_refresh_and_revoke, new:test_secret_rotation_live
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-05, AUTH-08

### AUTH-17  No token exfiltration, logs or config persistence
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Prove authenticated headers and server credentials are never echoed, logged or stored in generated client config; keep Infisical server-side only.

**Acceptance:** (1) CI secret-scan and hosted logs show token redaction (2) no user pasted bearer/HMAC credentials in native client config.

**Negative controls:** (1) Invalid request cannot reflect Authorization header.

**Source paths:** src/l9_graphite_memory/observability.py, src/l9_graphite_memory/secrets.py, config/memory.yaml.example
**Proposed tests/proofs:** new:test_auth_log_redaction, new:client_config_secret_scan
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-04, AUTH-07

### STOR-01  PostgreSQL-only canonical server and RLS isolation
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Make PostgreSQL 16 the only supported hosted canonical backend; create isolated database/role and verify tenancy policy and transaction-scoped claims.

**Acceptance:** (1) Any missing DSN/unreachable DB is fatal (2) no SQLite, ephemeral file, Zep or Neo4j silently promoted to canonical authority.

**Negative controls:** (1) No fallback even when PG unavailable.

**Source paths:** src/l9_graphite_memory/adapters/factory.py, src/l9_graphite_memory/adapters/postgres_store.py, src/l9_graphite_memory/config/models.py, docs/adr/ADR-030-rls-and-transaction-scoped-authorization.md
**Proposed tests/proofs:** new:test_hosted_pg_only, new:test_rls_cross_tenant
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-07, GOV-04

### STOR-06  Secret model redaction and telemetry hygiene
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Avoid accidental credential leaks from MemorySettings repr/model_dump and CLI diagnostic errors; use proper secret-typed fields.

**Acceptance:** (1) DSN, graphiti token, zep key, Auth0 secrets never rendered in repr/log/response (2) test dangerous serialization.

**Negative controls:** (1) Config show and exception messages never print DSN password.

**Source paths:** src/l9_graphite_memory/config/models.py, src/l9_graphite_memory/cli.py, src/l9_graphite_memory/observability.py
**Proposed tests/proofs:** new:test_secret_repr_serialization
**Findings:** U-011  |  **Prerequisites:** AUTH-17

### STOR-07  Infisical rotation applied to active authenticators
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Either rebind authenticator/key+grant state atomically on refresh or require supervised restart with proof; environment reload alone is not proof.

**Acceptance:** (1) Rotated key and grants take effect within documented bound, with consistency and no auth bypass.

**Negative controls:** (1) Old authenticator cache cannot silently ignore rotated secret.

**Source paths:** src/l9_graphite_memory/secrets.py, src/l9_graphite_memory/server.py
**Proposed tests/proofs:** new:test_live_rotation_applies, new:test_failed_rotation_preserves_safe_state
**Findings:** U-008  |  **Prerequisites:** AUTH-14

### STOR-08  Operational principal/env override lockdown
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Ensure L9_MEMORY_NAMESPACE and GRAPHITI_GROUP_ID cannot become remote claim authorities; old local selectors cannot influence OAuth principal.

**Acceptance:** (1) Remote namespace based solely on signed token claims plus server-side grant mapping (2) explicit local CLI is isolated.

**Negative controls:** (1) No env namespace injection or auth-disabled admin drift.

**Source paths:** src/l9_graphite_memory/group_resolver.py, src/l9_graphite_memory/runtime.py
**Proposed tests/proofs:** new:test_env_cannot_escalate_remote
**Findings:** U-010, U-005  |  **Prerequisites:** AUTH-08, STOR-01

### STOR-09  Provider credentials and key lifecycle isolated by role
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Infisical project/machine identity can read only Memory service deployment secrets; OAuth is auth provider not secret store; Graphiti separate credentials.

**Acceptance:** (1) Secrets rendered to server env only with least privilege and rotation (2) no reuse of other C1 tenant secrets.

**Negative controls:** (1) Missing secret must fail closed without adopting environment from another service.

**Source paths:** src/l9_graphite_memory/secrets.py, config/memory.yaml.example
**Proposed tests/proofs:** new:test_infisical_role_isolation_receipt
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** STOR-01, STOR-06

## P03. Native MCP wire/runtime and client behavior

### MCP-01  Pin supported native MCP protocol revisions
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Probe installed Claude and Cursor clients against server protocols and pin only revisions they demonstrably negotiate.

**Acceptance:** (1) Negotiation and tool listing pass for each target (2) unsupported revision yields explicit refusal, no fake compatibility.

**Negative controls:** (1) No pretending to serve a revision whose required features are absent.

**Source paths:** src/l9_graphite_memory/version.py, src/l9_graphite_memory/server.py
**Proposed tests/proofs:** new:installed_client_protocol_matrix
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-01, GOV-03

### MCP-02  Native MCP SDK/transport selection
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Reuse a well-maintained Python MCP SDK for Streamable HTTP and its auth extensions, reducing handcrafted wire logic; identify gaps before selection.

**Acceptance:** (1) One transport implementation and one tool registry (2) no additional API sidecar (3) SDK version pinned and negative conformance run.

**Negative controls:** (1) No proxy or bespoke auth server compensating for an inadequate SDK silently.

**Source paths:** src/l9_graphite_memory/server.py, pyproject.toml, docs/REMOTE_MCP_CONTRACT.md
**Proposed tests/proofs:** new:test_official_mcp_sdk_interop
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** MCP-01, AUTH-04

### MCP-04  UnknownTool vs invalid-argument error dispatch
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Separate method/tool dispatch error from missing fields, so -32601 never swallows KeyError in handlers (F-003).

**Acceptance:** (1) Missing namespace/purpose -> -32602 Invalid params (2) unknown method/tool -> -32601 (3) remote clients classify correctly.

**Negative controls:** (1) Missing argument cannot trigger CONTRACT_MISMATCH.

**Source paths:** src/l9_graphite_memory/server.py, src/l9_graphite_memory/mcp_tools.py, src/l9_graphite_memory/remote_client.py
**Proposed tests/proofs:** new:test_missing_args_32602, existing:test_remote_client
**Findings:** F-003  |  **Prerequisites:** MCP-02

### MCP-05  MCP tool-result envelope and client exceptions
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** RemoteMemoryClient and any retained TypeScript client must surface tool isError and JSON-RPC errors as typed failures.

**Acceptance:** (1) Neither Python nor TS client treats isError:true as a successful write (2) no catch-all success JSON conversion.

**Negative controls:** (1) Tool text Error: cannot become successful output.

**Source paths:** src/l9_graphite_memory/remote_client.py, clients/typescript/src/index.ts
**Proposed tests/proofs:** new:test_remote_client_isError, new:ts_isError_negative
**Findings:** F-001  |  **Prerequisites:** MCP-02

### MCP-06  Bounded executor offload on HTTP handler edge
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Keep synchronous MemoryService; offload blocking store/provider/readiness to bounded worker pool, preserve contextvars and per-thread DB safety.

**Acceptance:** (1) Two-second slow tool does not block healthz (2) 99p responsiveness cap measured in finite test (3) backpressure limits finite and explicit.

**Negative controls:** (1) Unbounded threads or event loop blocking fail.

**Source paths:** src/l9_graphite_memory/server.py, src/l9_graphite_memory/runtime.py, src/l9_graphite_memory/adapters/postgres_store.py
**Proposed tests/proofs:** new:test_concurrent_health_liveness, new:test_worker_backpressure
**Findings:** F-004  |  **Prerequisites:** MCP-02

### MCP-07  Healthz/readiness reflect real selected capabilities
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Probe canonical Postgres and selected projection/graph services separately, never return static true readiness on failure.

**Acceptance:** (1) Healthz remains responsive (2) readyz 503 for required store unavailable (3) disabled optional family is not interpreted as healthy active.

**Negative controls:** (1) Unreachable canonical database must never report ready=true.

**Source paths:** src/l9_graphite_memory/runtime.py, src/l9_graphite_memory/server.py, src/l9_graphite_memory/services/generated_data.py
**Proposed tests/proofs:** new:test_postgres_readiness_fault, new:test_generated_capabilities_health
**Findings:** F-004, F-015  |  **Prerequisites:** MCP-06

### MCP-08  Streamable HTTP protocol and transport negative suite
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Validate origin, version, headers, size, JSON-RPC envelopes, notification semantics and 401 PRM challenge against current negotiated specs.

**Acceptance:** (1) One /mcp endpoint, protocol checks and auth before dispatch (2) no docs/openapi exposure without deliberate policy.

**Negative controls:** (1) Batch, missing content-type, malicious Origin, token URL, unauthenticated docs denied.

**Source paths:** src/l9_graphite_memory/server.py, docs/REMOTE_MCP_CONTRACT.md
**Proposed tests/proofs:** new:test_http_protocol_negative_matrix, existing:test_remote_mcp_http
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** MCP-02, AUTH-05

### MCP-09  Native Python client OAuth and result semantics
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** medium  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Retain Python remote client as OAuth resource consumer only if it has active use; remove custom per-agent signed header support.

**Acceptance:** (1) Client uses provider/native token grant and refresh (2) strict error classification (3) no HMAC or raw bearer setting committed.

**Negative controls:** (1) Expired token or 403 cannot downgrade to local stdio.

**Source paths:** src/l9_graphite_memory/remote_client.py, src/l9_graphite_memory/sdk.py
**Proposed tests/proofs:** new:test_oauth_python_client, new:test_refresh_and_isError
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** MCP-05, AUTH-07

### MCP-12  Installed-wheel and true TCP PostgreSQL contract
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Run actual installed wheel HTTP server with OAuth issuer test fixture and PostgreSQL 16, not only in-memory TestClient.

**Acceptance:** (1) Add/get/search/write/read/restart and auth negatives pass on exact wheel (2) STDIO mode cannot launch.

**Negative controls:** (1) SQLite fallback and unsigned tool writes refused.

**Source paths:** tests/integration/test_installed_wheel_lifecycle.py, tests/integration/test_remote_mcp_postgres_multiprocess.py
**Proposed tests/proofs:** new:test_installed_http_pg_oauth, new:test_mcp_removed_stdio
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** MCP-06, AUTH-08, MCP-08

## P04. Complete evidence-bound identity and operator authority

### AUTH-09  ActorIdentity source and assurance binding
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Apply global identity projection and verified credential-context mapping without assigning actor purely from public OAuth client_id.

**Acceptance:** (1) Consequential agent memory write has validated actor coordinate/evidence binding or fails closed (2) authenticated user and actor remain separate.

**Negative controls:** (1) Caller-supplied actor, JWT client_id alone, or projected profile cannot establish author.

**Source paths:** src/l9_graphite_memory/contracts/identity.py, src/l9_graphite_memory/authz/, product-topology.yaml
**Proposed tests/proofs:** new:test_actor_assertion_negative, new:test_actor_evidence_currentness
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-05, GOV-06, AUTH-08

### AUTH-10  SurfaceIdentity evidence and Unknown discipline
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Resolve Cursor/Claude surface only when trustworthy specific evidence is present, otherwise preserve unknown; no automatic Claude desktop/mobile relabel.

**Acceptance:** (1) One identity assertion records surface independently from actor (2) all receipts/tags reflect resolved or explicit Unknown consistently.

**Negative controls:** (1) Account-level Claude connector is not per-request proof of mobile origin.

**Source paths:** src/l9_graphite_memory/contracts/identity.py, src/l9_graphite_memory/mcp_tools.py
**Proposed tests/proofs:** new:test_surface_unknown_and_spoof, new:test_mobile_is_not_inferred
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-05, AUTH-09

### AUTH-11  Memory ProductIdentity, ReleaseIdentity, RuntimeIdentity proof
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Bind service product coordinate, exact admitted wheel/container release, and C1 deployment instance to records/operational receipts.

**Acceptance:** (1) Product stable, release digest-locked, runtime deployment-identified (2) one does not stand in for another (3) Unknown blocks consequential release provenance.

**Negative controls:** (1) Environment label, package version alone, or container name not sufficient release evidence.

**Source paths:** product-topology.yaml, release-work/product-release-binding.yaml, src/l9_graphite_memory/contracts/identity.py
**Proposed tests/proofs:** new:test_service_identity_provenance, new:test_unadmitted_release_rejection
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-04, GOV-05

### AUTH-12  Constellation identity explicit non-applicability
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** medium  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Memory is a hosted Dependency exception; no Constellation identity is invented or Gate routing required.

**Acceptance:** (1) Identity assertion marks constellation inapplicable separately from Unknown (2) tests enforce exact product-kind exception.

**Negative controls:** (1) No synthetic l9-constellation id or Gate grant.

**Source paths:** product-topology.yaml, src/l9_graphite_memory/contracts/identity.py
**Proposed tests/proofs:** new:test_constellation_nonapplicable
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-11

### AUTH-13  One complete evidence-bound identity assertion
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Unify caller Actor/Surface and service Product/Release/Runtime coordinates without conflating caller and service runtime.

**Acceptance:** (1) Typed receipt lists applicability, value/Unknown, authority, evidence refs, resolver and governing revision, consistent across MCP tools, hooks and logs.

**Negative controls:** (1) Missing, conflicting or stale assertion refuses consequential operations.

**Source paths:** src/l9_graphite_memory/contracts/identity.py, src/l9_graphite_memory/mcp_tools.py, src/l9_graphite_memory/services/memory_service.py
**Proposed tests/proofs:** new:test_complete_assertion_projection, new:test_identity_currentness_negative
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-09, AUTH-10, AUTH-11, AUTH-12

### AUTH-16  Operator/admin workflow separated from agent OAuth
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Keep privileged maintenance/deletion safe while eliminating stdio human secret doors; use separately authenticated and audited narrow operator authorization.

**Acceptance:** (1) Admin-only tools have explicit remote or administrative operator path, no default admin, and server side tenant boundaries (2) file-system tools require local secure operation.

**Negative controls:** (1) No ordinary Claude/Cursor OAuth grant can read arbitrary C1 filesystem or become admin.

**Source paths:** src/l9_graphite_memory/mcp_tools.py, src/l9_graphite_memory/cli.py, docs/adr/ADR-006-namespace-authorization.md
**Proposed tests/proofs:** new:test_operator_privilege_matrix, new:test_filesystem_tool_boundary
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-08, AUTH-13

### DATA-07  Namespace and local privilege threat closure
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Resolve U-005/U-010 in context of OAuth-only public HTTP: no Tier-3 fallback; server grants remain explicit.

**Acceptance:** (1) No request or env-only string widens namespace permissions in remote OAuth server (2) local CLI admin isolated to operator policy.

**Negative controls:** (1) Remote unauthenticated requests cannot claim arbitrary namespaces or admin.

**Source paths:** src/l9_graphite_memory/group_resolver.py, src/l9_graphite_memory/runtime.py, docs/adr/ADR-006-namespace-authorization.md
**Proposed tests/proofs:** new:test_env_namespace_override_not_http, new:test_local_admin_isolation
**Findings:** U-005, U-010  |  **Prerequisites:** AUTH-08, AUTH-16

## P05. Graphiti provider error transport

### PROJ-01  Pin Graphiti add_memory tool schema and metadata semantics
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** high  |  **Kind:** contract_probe  |  **Status:** proposed

**Intent:** Use the exact versioned Graphiti MCP server to verify add_memory/add_episode schema, result isError and accepted response shape.

**Acceptance:** (1) Schema contract test proves passed parameters are supported (2) unsupported metadata is translated or rejected explicitly.

**Negative controls:** (1) Provider rejects unknown metadata and no phantom success occurs.

**Source paths:** src/l9_graphite_memory/transport.py, src/l9_graphite_memory/adapters/graphiti_projection.py
**Proposed tests/proofs:** new:test_graphiti_add_memory_signature, existing:test_graphiti_http_projection_loop
**Findings:** U-002  |  **Prerequisites:** GOV-09

### PROJ-02  Honor MCP tool isError on all Graphiti responses
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Parse result envelope isError before content text/JSON unwrapping, preserving diagnostics and typed error kind.

**Acceptance:** (1) isError true always raises ProjectionError and returns no success envelope.

**Negative controls:** (1) MCP Error: text never accepted as success.

**Source paths:** src/l9_graphite_memory/transport.py
**Proposed tests/proofs:** new:test_graphiti_isError_text_and_json
**Findings:** F-001  |  **Prerequisites:** PROJ-01

### PROJ-03  Distinguish provider semantic and availability faults
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Classify JSON-RPC invalid params, unknown tools, provider application errors and transport faults correctly before updating breaker.

**Acceptance:** (1) -32602 does not increment circuit failure (2) network/availability failures do (3) policy for -32000 class documented.

**Negative controls:** (1) Five invalid-param calls must not open an otherwise healthy provider circuit.

**Source paths:** src/l9_graphite_memory/transport.py, src/l9_graphite_memory/circuit_breaker.py
**Proposed tests/proofs:** new:test_breaker_error_class_matrix
**Findings:** F-019  |  **Prerequisites:** PROJ-02

### PROJ-04  Half-open probe timeout recovery and single-probe rule
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Fix half-open state machine so an unreported probe expires and later recovery is permitted without unbounded probes.

**Acceptance:** (1) OPEN->HALF_OPEN->failed or stuck probe->OPEN->recover after timeout (2) at most one active probe until expiry.

**Negative controls:** (1) Breaker never remains HALF_OPEN forever after missing report.

**Source paths:** src/l9_graphite_memory/circuit_breaker.py
**Proposed tests/proofs:** new:test_breaker_half_open_rearm, new:test_concurrent_single_probe
**Findings:** F-002  |  **Prerequisites:** PROJ-03

### PROJ-05  Session handshake failures settle breaker state
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Ensure initialize/notifications/expired-session retry exceptions report breaker outcome exactly once.

**Acceptance:** (1) Failing _ensure_session records failure and resets session (2) recovered endpoint can reconnect without process restart.

**Negative controls:** (1) Failed handshake must not consume one permanent half-open permit.

**Source paths:** src/l9_graphite_memory/transport.py
**Proposed tests/proofs:** new:test_session_rehandshake_breaker_failure
**Findings:** F-002, F-019  |  **Prerequisites:** PROJ-04

### PROJ-06  Positive provider acceptance required for projection link
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Allow name-based locators only after verified successful write acceptance; preserve async-ingestion distinction and provider read-after-write verification.

**Acceptance:** (1) No provider failure can create ProjectionLink or DELIVERED (2) successful acceptance may create locator with explicit pending-ingest evidence.

**Negative controls:** (1) String Error result and ambiguous response cannot synthesize locator.

**Source paths:** src/l9_graphite_memory/adapters/graphiti_projection.py, src/l9_graphite_memory/services/outbox_worker.py
**Proposed tests/proofs:** new:test_no_phantom_projection_link
**Findings:** F-001  |  **Prerequisites:** PROJ-02, PROJ-03

### PROJ-07  Outbox integrated isError and erase proof
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** critical  |  **Kind:** integration_proof  |  **Status:** proposed

**Intent:** Run fake Graphiti MCP isError integration through transport->adapter->outbox->store.

**Acceptance:** (1) Failed project event retries/deadletters and no link (2) deletion of never-successfully-projected record does not require nonexistent provider copy.

**Negative controls:** (1) No DELIVERED or deletion DEAD from a fabricated locator.

**Source paths:** tests/integration/test_graphiti_http_projection_loop.py, src/l9_graphite_memory/services/outbox_worker.py
**Proposed tests/proofs:** new:test_graphiti_failed_add_no_delivered, new:test_no_link_deletion
**Findings:** F-001  |  **Prerequisites:** PROJ-06

### PROJ-08  Reconcile pre-existing phantom links safely
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** high  |  **Kind:** operator_remediation  |  **Status:** proposed

**Intent:** Detect candidate legacy phantom links from past faulty projection runs without declaring unverified provider absence as proved.

**Acceptance:** (1) Inventory with durable audit receipt (2) repair/queue re-projection only after provider confirmation and governed operator permission.

**Negative controls:** (1) No blind deletion, no false verified-erasure receipt.

**Source paths:** src/l9_graphite_memory/services/outbox_worker.py, src/l9_graphite_memory/adapters/graphiti_projection.py
**Proposed tests/proofs:** new:test_phantom_link_reconciliation_dry_run
**Findings:** F-001  |  **Prerequisites:** PROJ-07

## P06. Lifecycle capability, lease and deletion correctness

### PROJ-09  Graphiti provider call idempotency and duplicate episodes
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** critical  |  **Kind:** integration_proof  |  **Status:** proposed

**Intent:** Prove retries and lease expiry cannot leak duplicate provider copies; use stable scope-safe idempotency or exhaustive locator reconciliation.

**Acceptance:** (1) Two workers with expired lease converge to one logical obligation (2) orphan episodes counted and cleaned with proof.

**Negative controls:** (1) Provider UUID locator cannot strand a second duplicate episode.

**Source paths:** src/l9_graphite_memory/adapters/graphiti_projection.py, src/l9_graphite_memory/services/outbox_worker.py
**Proposed tests/proofs:** new:test_expired_lease_duplicate_episode_live
**Findings:** U-001  |  **Prerequisites:** PROJ-01, LIFE-03

### LIFE-01  Complete canonical mutation method and bypass census
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Inspect RecordStore mutations in Postgres, in-memory, outbox, maintenance; classify canonical vs worker operational metadata.

**Acceptance:** (1) Every consequential mutation has an explicit capability and service owner or a narrowly justified and admitted exception (2) scanner complete.

**Negative controls:** (1) Direct complete_deletion or link/receipt mutation cannot bypass service law.

**Source paths:** src/l9_graphite_memory/ports/record_store.py, tools/assurance/check_memory_write_bypass.py, src/l9_graphite_memory/ports/service_capability.py
**Proposed tests/proofs:** new:test_capability_method_census
**Findings:** F-009  |  **Prerequisites:** GOV-03, GOV-09

### LIFE-02  Service-owned outbox result application
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Outbox worker performs provider operations but submits evidence to narrow MemoryService methods for canonical link, lifecycle and receipt commits.

**Acceptance:** (1) No second control plane (2) worker cannot mint arbitrary capability (3) service issues and validates write scope.

**Negative controls:** (1) Bypass scanner disallows worker direct canonical status transitions.

**Source paths:** src/l9_graphite_memory/services/memory_service.py, src/l9_graphite_memory/services/outbox_worker.py, src/l9_graphite_memory/ports/record_store.py
**Proposed tests/proofs:** new:test_worker_cannot_directly_mutate_canonical
**Findings:** F-009  |  **Prerequisites:** LIFE-01

### LIFE-03  Lease-aware atomic projection link and delivery settle
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Bind active record check, current lease owner CAS, accepted provider evidence, link upsert and DELIVERED event in one Postgres transaction.

**Acceptance:** (1) Losing lease cannot install any durable link or DELIVERED status (2) link and outcome commit atomically after acceptance.

**Negative controls:** (1) Worker with expired lease cannot install link even if record ACTIVE.

**Source paths:** src/l9_graphite_memory/adapters/postgres_store.py, src/l9_graphite_memory/services/outbox_worker.py
**Proposed tests/proofs:** new:test_link_install_lease_expiry_two_workers, new:test_link_settle_transaction_fail
**Findings:** U-001, F-009  |  **Prerequisites:** LIFE-02, PROJ-06

### LIFE-04  Provider side effects compensable across lost leases
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** A failed atomic link/settle after a successful external provider write needs durable compensation or idempotency, never abandon an orphan.

**Acceptance:** (1) Compensation work is persisted/recoverable and eventually removes extra provider episode (2) closed if provider unavailable only as pending.

**Negative controls:** (1) Process kill after provider acceptance cannot cause silently forgotten episode.

**Source paths:** src/l9_graphite_memory/services/outbox_worker.py, src/l9_graphite_memory/adapters/graphiti_projection.py
**Proposed tests/proofs:** new:test_orphan_episode_compensation_recovery
**Findings:** U-001  |  **Prerequisites:** LIFE-03

### LIFE-05  Atomic retirement link/receipt/outbox settlement
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** After verified provider retirement, withdraw link and write ADR-076 receipt in same Postgres transaction with current lease.

**Acceptance:** (1) No possible transaction state with removed link and missing retirement receipt (2) event cannot be DELIVERED without receipt.

**Negative controls:** (1) Crash between link removal and receipt persists neither or both.

**Source paths:** src/l9_graphite_memory/adapters/postgres_store.py, src/l9_graphite_memory/ports/record_store.py, src/l9_graphite_memory/services/outbox_worker.py
**Proposed tests/proofs:** new:test_retirement_fault_injection, new:test_retirement_receipt_atomicity
**Findings:** F-008, F-009  |  **Prerequisites:** LIFE-02, LIFE-03

### LIFE-06  Retirement retries are idempotent and audit-preserving
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Ensure retries after accepted provider delete converge to same retirement receipt, avoiding a no-op when link withdrawn.

**Acceptance:** (1) Repeated event yields same proof and does not overwrite original retirement reason or stamp a false new event.

**Negative controls:** (1) No project_retire_noop can erase an owed receipt.

**Source paths:** src/l9_graphite_memory/services/outbox_worker.py, src/l9_graphite_memory/adapters/postgres_store.py
**Proposed tests/proofs:** new:test_retire_replay_after_crash
**Findings:** F-008  |  **Prerequisites:** LIFE-05

### LIFE-07  Verified deletion completion requires capability
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Route complete_deletion via MemoryService-issued service capability and require no remaining projections.

**Acceptance:** (1) Any direct adapter.complete_deletion without capability is refused by all supported stores (2) deletion completion writes once.

**Negative controls:** (1) No API can append DELETED status outside service authorization.

**Source paths:** src/l9_graphite_memory/ports/record_store.py, src/l9_graphite_memory/adapters/postgres_store.py, src/l9_graphite_memory/services/memory_service.py
**Proposed tests/proofs:** new:test_deletion_requires_service_capability
**Findings:** F-009  |  **Prerequisites:** LIFE-01, LIFE-02

### LIFE-08  Idempotent deletion receipt and status replay
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Guarantee complete_deletion of an already deleted record does not duplicate events or mutate original completed_at.

**Acceptance:** (1) Repeat on same receipt is byte-stable or documented idempotent (2) differing receipt cannot rewrite original authority.

**Negative controls:** (1) Two completed events or completion timestamp rewrite fails.

**Source paths:** src/l9_graphite_memory/adapters/postgres_store.py, src/l9_graphite_memory/adapters/in_memory_store.py
**Proposed tests/proofs:** new:test_complete_deletion_idempotence_all_supported_stores
**Findings:** U-004  |  **Prerequisites:** LIFE-07

### LIFE-09  Concurrent erase across targets and workers
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Synchronize final link check and deletion completion under Postgres locking and lease CAS.

**Acceptance:** (1) Two erase events for same deletion receipt converge to one completion, both provider copies removed, correct outbox statuses.

**Negative controls:** (1) No double completion and no premature DELETED while any copy remains.

**Source paths:** src/l9_graphite_memory/adapters/postgres_store.py, src/l9_graphite_memory/services/outbox_worker.py
**Proposed tests/proofs:** new:test_two_worker_same_record_erase
**Findings:** U-004  |  **Prerequisites:** LIFE-08, LIFE-03

### LIFE-10  Deferred quarantine supersession honored atomically
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** When QUARANTINED successor is released ACTIVE, validate its recorded supersedes list and commit predecessor SUPERSEDED status and retire intents in same lifecycle transaction.

**Acceptance:** (1) Released successor and predecessor updates cannot diverge (2) failure leaves quarantined or explicit conflict, not coexistence.

**Negative controls:** (1) Release cannot produce two active contradictory successor/predecessor records.

**Source paths:** src/l9_graphite_memory/services/memory_service.py, src/l9_graphite_memory/adapters/postgres_store.py
**Proposed tests/proofs:** new:test_quarantine_release_supersession, new:test_conflicting_predecessor_reject
**Findings:** U-013  |  **Prerequisites:** LIFE-02, DATA-05

### LIFE-11  Historical state, restore and reproject contract
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Preserve bi-temporal history and reactivation receipts when lifecycle operations are repaired, without reintroducing v2 migration.

**Acceptance:** (1) Restore/retire/reproject work only from current canonical state with correct events and no duplicate provider facts.

**Negative controls:** (1) Reactivation cannot resurrect deleted data or bypass consent.

**Source paths:** src/l9_graphite_memory/services/memory_service.py, src/l9_graphite_memory/services/outbox_worker.py
**Proposed tests/proofs:** new:test_reactivate_after_retirement, existing:test_projection_retirement_recovery
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** LIFE-10, LIFE-05

### LIFE-12  PostgreSQL 16 transaction and race integration suite
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** critical  |  **Kind:** integration_proof  |  **Status:** proposed

**Intent:** Run real Postgres two-worker leases, crash injection, rollback and synchronous health under intended server runtime.

**Acceptance:** (1) Atomicity, isolation, idempotency and one truthful outbox settle proved on exact source head.

**Negative controls:** (1) No SQLite-only or in-memory-only green accepted for C1.

**Source paths:** tests/integration/test_outbox_leases.py, tests/integration/test_projection_targets.py, tests/security/test_legacy_projection_erasure.py
**Proposed tests/proofs:** new:test_pg_lifecycle_atomic_fault_matrix
**Findings:** F-008, F-009, U-001, U-004, U-013  |  **Prerequisites:** LIFE-04, LIFE-06, LIFE-09, LIFE-10

### STOR-02  Postgres lifecycle adapter atomic persistence tests
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Make transaction-backed write, delete, link, receipt and lease operations conform to one service capability and lease invariant.

**Acceptance:** (1) Race and forced rollback produce no partial canonical state, including target-specific links.

**Negative controls:** (1) Commit failure cannot leave link without receipt.

**Source paths:** src/l9_graphite_memory/adapters/postgres_store.py, src/l9_graphite_memory/ports/record_store.py
**Proposed tests/proofs:** new:test_pg_atomic_lifecycle_contract
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** STOR-01, LIFE-07

## P07. Reference-safe retention and adapter parity

### DATA-09  Adapter candidate-window and retrieval parity
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** medium  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Unify candidate-window multiplier across test in-memory adapter and PostgreSQL production; no Sqlite production parity obligation.

**Acceptance:** (1) Planner and adapters share named constant (2) same fixture yields same candidate set after normalization.

**Negative controls:** (1) Limit*10 vs limit*20 divergence detected.

**Source paths:** src/l9_graphite_memory/adapters/in_memory_store.py, src/l9_graphite_memory/adapters/postgres_store.py, src/l9_graphite_memory/retrieval/planner.py
**Proposed tests/proofs:** new:test_candidate_window_cross_adapter
**Findings:** F-013  |  **Prerequisites:** STOR-01

### DATA-10  Generated-data capabilities are evidence-derived
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** medium  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Remove hard-coded store_ready/ready=True and use actual health/readiness.

**Acceptance:** (1) Unhealthy required canonical store yields false readiness and failed capability proof.

**Negative controls:** (1) Static true returns forbidden.

**Source paths:** src/l9_graphite_memory/services/generated_data.py
**Proposed tests/proofs:** new:test_generated_capabilities_store_down
**Findings:** F-015  |  **Prerequisites:** MCP-07

### RET-01  Full incoming-reference semantics
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** high  |  **Kind:** policy_decision  |  **Status:** proposed

**Intent:** Formalize whether protected links include references, supersedes, conflicts_with across tenant/namespace/state/time, without granting cross-tenant read.

**Acceptance:** (1) Policies specify exact source sets and target eligibility (2) no out-of-window reference is silently ignored.

**Negative controls:** No additional negative specified

**Source paths:** src/l9_graphite_memory/curation/retention.py, docs/adr/ADR-010-retention-decay-and-pruning.md
**Proposed tests/proofs:** new:test_reference_policy_decision
**Findings:** F-018  |  **Prerequisites:** GOV-03

### RET-02  Persisted incoming-reference count query
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Move reference enumeration from loaded in-memory slice into index-backed authorized store query for complete target set.

**Acceptance:** (1) Postgres counts every relevant incoming reference independent of watermark/limit/state and tenant-safe rules.

**Negative controls:** (1) Beyond max_records and newer than watermark still counted.

**Source paths:** src/l9_graphite_memory/ports/record_store.py, src/l9_graphite_memory/adapters/postgres_store.py, src/l9_graphite_memory/maintenance/service.py
**Proposed tests/proofs:** new:test_pg_incoming_reference_query
**Findings:** F-018  |  **Prerequisites:** RET-01, STOR-01

### RET-03  Retention planner uses global reference evidence
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Pass authoritative counts to pure RetentionEngine, preserve pure planner and dry-run semantics.

**Acceptance:** (1) Referenced expired record soft-expires, unreferenced archives, both with inspectable decision receipts.

**Negative controls:** (1) No archive of referenced record omitted from candidate slice.

**Source paths:** src/l9_graphite_memory/curation/retention.py, src/l9_graphite_memory/maintenance/planner.py, src/l9_graphite_memory/services/memory_service.py
**Proposed tests/proofs:** new:test_retention_out_of_window_soft_expire
**Findings:** F-018  |  **Prerequisites:** RET-02

### RET-04  Retention apply race/authorization proof
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Check reference snapshot or in-transaction guard against concurrent new reference while applying archive.

**Acceptance:** (1) Concurrent new incoming reference cannot be ignored by apply after dry-run decision (2) rejection/retry preserves state.

**Negative controls:** (1) Late reference cannot be silently lost on archive.

**Source paths:** src/l9_graphite_memory/adapters/postgres_store.py, src/l9_graphite_memory/services/memory_service.py
**Proposed tests/proofs:** new:test_retention_reference_toctou
**Findings:** F-018  |  **Prerequisites:** RET-03, LIFE-02

### RET-05  Retention and maintenance full Postgres proof
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** high  |  **Kind:** integration_proof  |  **Status:** proposed

**Intent:** Use real Postgres with multiple namespaces and out-of-window references, prove replay and reports, no cross-tenant leakage.

**Acceptance:** (1) Source count, action, receipt and eventual projection retirement agree.

**Negative controls:** (1) In-memory small-window tests alone cannot qualify retention.

**Source paths:** tests/integration/, src/l9_graphite_memory/maintenance/service.py
**Proposed tests/proofs:** new:test_retention_large_window_postgres
**Findings:** F-018  |  **Prerequisites:** RET-04

### RET-06  Maintenance readout reflects required capability state
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** medium  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Tie generated-data and scheduled maintenance readiness to actual selected backend health and source coherence.

**Acceptance:** (1) Unhealthy Postgres or active selected projection refuses false ready and emits degraded reason.

**Negative controls:** (1) No static ready=true.

**Source paths:** src/l9_graphite_memory/services/generated_data.py, src/l9_graphite_memory/runtime.py
**Proposed tests/proofs:** new:test_maintenance_readiness_truth
**Findings:** F-015  |  **Prerequisites:** MCP-07, RET-05

### STOR-05  In-memory test adapter remains nonproduction only
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** medium  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Keep deterministic disposable store for tests if needed, with shared retrieval and capability semantics; forbid hosting fallback.

**Acceptance:** (1) Conformance fixture cannot become production backend, source parity fixed with Postgres.

**Negative controls:** (1) Test adapter not activated by bad DSN.

**Source paths:** src/l9_graphite_memory/adapters/in_memory_store.py, src/l9_graphite_memory/adapters/factory.py
**Proposed tests/proofs:** new:test_inmemory_only_fixture_selection
**Findings:** F-013  |  **Prerequisites:** STOR-01, DATA-09

## P08. Provider qualification and remaining safety defects

### DATA-08  Memory guard hostile shell default-deny
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** medium  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Eliminate permissive regex bypass by default-denying shell without evidence or using a parser that rejects substitutions/newlines/write flags.

**Acceptance:** (1) ls $(...), multiline rm, git log --output and find -fprint all denied (2) read-only commands accepted only under strict contract.

**Negative controls:** (1) No shell substitution or output-write flags escape gate.

**Source paths:** src/l9_graphite_memory/memory_guard.py
**Proposed tests/proofs:** new:test_guard_adversarial_shell
**Findings:** F-011  |  **Prerequisites:** GOV-02

### PROJ-10  Graphiti real provider qualification in isolated scope
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** high  |  **Kind:** integration_proof  |  **Status:** proposed

**Intent:** Use disposable provider graph/namespace, not protected C1 Graphiti/Neo4j episodes, for true add-search-delete/retry proof.

**Acceptance:** (1) Exact pinned Graphiti version, tool schema, episode listing, deletion and async-ingest convergence recorded (2) no protected tenant mutations.

**Negative controls:** (1) Tool-returned accepted without eventual episode confirmation cannot be called integrated projection success.

**Source paths:** tests/qualification/test_graphiti_live_qualification.py, docs/graph-intelligence/CUTOVER_RUNBOOK.md
**Proposed tests/proofs:** existing:test_graphiti_live_qualification, new:test_provider_recovery_faults
**Findings:** F-001, U-002, U-001  |  **Prerequisites:** PROJ-07, PROJ-09

### PROJ-11  Explicit Zep disposition: retire or qualify, no automatic fallback
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** medium  |  **Kind:** decision  |  **Status:** proposed

**Intent:** Decide whether Zep has an admitted current consumer; default retire if none, otherwise qualify F-014/F-017 under separate provider contract.

**Acceptance:** (1) Decision receipt selects one path, package and tests agree (2) inactive optional Zep cannot claim ready.

**Negative controls:** (1) No hidden automatic provider fallback.

**Source paths:** src/l9_graphite_memory/zep_transport.py, src/l9_graphite_memory/adapters/factory.py
**Proposed tests/proofs:** new:test_zep_disposition_consistency
**Findings:** F-014, F-017  |  **Prerequisites:** GOV-09

### PROJ-12  If retained, Zep delivered bytes equal digested bytes
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** conditional  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Eliminate body[:10000] silent truncation; reject oversized writes or implement explicitly versioned faithful chunk projection.

**Acceptance:** (1) Digest attests exactly delivered bytes and legacy JSON never gets malformed by truncation.

**Negative controls:** (1) No silent truncation of >10000 characters.

**Source paths:** src/l9_graphite_memory/zep_transport.py, src/l9_graphite_memory/adapters/graphiti_projection.py
**Proposed tests/proofs:** new:test_zep_overlimit_rejected_or_chunked
**Findings:** F-017  |  **Prerequisites:** PROJ-11

### PROJ-13  If retained, Zep readiness probes real reachability
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** conditional  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** A fresh Zep transport health() must probe connectivity, not rely on last traffic result.

**Acceptance:** (1) Ready is truthful on a newly started ACTIVE target and false on outage.

**Negative controls:** (1) No ACTIVE provider deadlock before first traffic.

**Source paths:** src/l9_graphite_memory/zep_transport.py, src/l9_graphite_memory/projections/runtime.py
**Proposed tests/proofs:** new:test_zep_initial_readiness_probe
**Findings:** F-014  |  **Prerequisites:** PROJ-11

### HYG-01  Async close cannot fire and forget teardown
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** medium  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Remove unreferenced create_task in _run_sync; make async lifecycle await aclose or retain and join tasks deterministically.

**Acceptance:** (1) On cancellation/shutdown adapter close completes with testable receipt and no weak-referenced task loss.

**Negative controls:** (1) No lost Redis teardown task.

**Source paths:** src/l9_graphite_memory/runtime.py
**Proposed tests/proofs:** new:test_aclose_while_event_loop_running
**Findings:** F-020  |  **Prerequisites:** MCP-06

### HYG-03  Client and transport failure taxonomy consistency
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** medium  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Ensure remote_client, Graphiti provider, Zep provider and server distinguish tool rejection, upstream downtime and auth failure.

**Acceptance:** (1) All permanent vs retryable error outcomes documented, consistent, and receive regression coverage.

**Negative controls:** (1) Invalid argument must not become breaker outage or contract mismatch.

**Source paths:** src/l9_graphite_memory/errors.py, src/l9_graphite_memory/remote_client.py
**Proposed tests/proofs:** new:test_error_taxonomy_cross_clients
**Findings:** F-003, F-019  |  **Prerequisites:** PROJ-03, MCP-04, MCP-05

### QA-07  Provider and maintenance qualification, conditional truth
**Owner:** independent reviewer + repository CI  |  **Scope:** full  |  **Risk:** high  |  **Kind:** assurance  |  **Status:** proposed

**Intent:** Only advertise selected Graphiti/Zep/retention when qualified; removed optional providers are explicit.

**Acceptance:** (1) Active provider manifests pass exact tests, absent providers produce unavailable not healthy.

**Negative controls:** (1) Unqualified provider not reported ready.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:test_active_provider_manifest_proof
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** PROJ-10, RET-05, PROJ-11

## P09. Remove obsolete compatibility routes and docs

### GOV-10  Obsolete documentation, examples, configuration inventory
**Owner:** Quantum-L9/l9-graphiti-memory + Quantum-L9/.github  |  **Scope:** core  |  **Risk:** medium  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Remove or rewrite active documentation that instructs users to launch Memory stdio, use signed agent keys or migrate legacy SQLite, without erasing archived ADR history.

**Acceptance:** (1) All actively advertised setup paths show native OAuth HTTP only (2) historical source docs archived and marked superseded (3) docs/CLI examples tested.

**Negative controls:** (1) No README or quickstart yields stdio or static bearer config.

**Source paths:** README.md, QUICKSTART.md, ARCHITECTURE.md, SECURITY.md, MIGRATION.md, docs/CURSOR_INSTANTIATION.md, config/memory.yaml.example
**Proposed tests/proofs:** new:docs_forbidden_transport_scan
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-03, MCP-08, AUTH-15

### GOV-11  Material compatibility break and fresh release semantic identity
**Owner:** Quantum-L9/l9-graphiti-memory + Quantum-L9/.github  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Use exact source and artifact digests; version remains only a candidate until admitted. No implicit 2.x upgrade/migration or same package meaning.

**Acceptance:** (1) Version, manifest, upgrade refusal and changelog agree on no legacy reader/importer promise (2) no unearned product-release claim.

**Negative controls:** No additional negative specified

**Source paths:** src/l9_graphite_memory/version.py, pyproject.toml, release-work/product-release-binding.yaml
**Proposed tests/proofs:** new:release_exact_digest, new:old_artifact_negative
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-03, MCP-08, STOR-03

### AUTH-15  Remove signed-agent, static bearer, human stdio HTTP doors
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** retirement  |  **Status:** proposed

**Intent:** Delete legacy authentication and its environmental proof path from shipped server and client implementations.

**Acceptance:** (1) No live server auth mode other than OAuth resource server (2) no HMAC agent headers, static Bearer principal map, or local auth-disabled HTTP bypass on externally exposed service.

**Negative controls:** (1) Old signed-agent request and long-lived static bearer fail closed.

**Source paths:** src/l9_graphite_memory/server.py, src/l9_graphite_memory/authz/remote_agent.py, src/l9_graphite_memory/authz/signed_assertion.py, src/l9_graphite_memory/config/models.py
**Proposed tests/proofs:** new:test_legacy_auth_rejected, new:forbidden_auth_symbols_in_runtime
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-04, AUTH-08, AUTH-13

### MCP-03  Eliminate stdio MCP endpoint, launcher and advertised installers
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** retirement  |  **Status:** proposed

**Intent:** Remove Memory stdio process entry, stdio MCP server mode, SSE compatibility alias and stdio client installer/verify paths.

**Acceptance:** (1) Fresh install exposes only OAuth HTTP MCP remote surface (2) no .mcp.json command/args entry (3) removed stdio test fixtures replaced by negative legacy-path tests.

**Negative controls:** (1) Memory stdio cannot be selected with old flags or setup wrappers.

**Source paths:** src/l9_graphite_memory/server.py, src/l9_graphite_memory/client_config/cursor.py, src/l9_graphite_memory/client_config/mcp_probe.py, scripts/write_cursor_config.py, scripts/write_claude_config.py
**Proposed tests/proofs:** new:test_no_stdio_entrypoints, new:test_no_stdio_generated_config
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** MCP-02, AUTH-15

### MCP-10  Retain/retire TypeScript SDK with explicit scope
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** medium  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Prove actual consumer for TypeScript remote client; if retained, OAuth only; otherwise remove from release without compatibility shim.

**Acceptance:** (1) Exactly one supported TypeScript path or explicit retired package with no false support claim.

**Negative controls:** (1) No static token fallback marketed as agent authentication.

**Source paths:** clients/typescript/, docs/COMPATIBILITY_MATRIX.md
**Proposed tests/proofs:** new:typescript_package_scope_receipt
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** MCP-05, GOV-08

### MCP-11  MCP tool inventory and legacy alias trim
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** medium  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Keep canonical current tool names, remove deprecated aliases/old transport-coupled tools without keeping parser shims.

**Acceptance:** (1) Tool listing matches one approved contract and strict JSON-schema field semantics (2) removed names explicitly unavailable.

**Negative controls:** (1) Old aliases not silently routed to new writes.

**Source paths:** src/l9_graphite_memory/mcp_tools.py, src/l9_graphite_memory/version.py
**Proposed tests/proofs:** new:test_tool_inventory_exact, new:test_removed_aliases_negative
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** MCP-04, MCP-08

### STOR-03  Remove production SQLite storage and old transaction path
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** retirement  |  **Status:** proposed

**Intent:** Full cutover removes SQLite serving and old local-memory instantiation; any sqlite tests retained only as archived source if useful.

**Acceptance:** (1) No production code can select SQLite canonical store (2) F-005/F-007 retired by reachability removal and negative tests.

**Negative controls:** (1) SQLite connection logic not shipped in active server path.

**Source paths:** src/l9_graphite_memory/adapters/sqlite_store.py, src/l9_graphite_memory/adapters/factory.py, src/l9_graphite_memory/config/models.py
**Proposed tests/proofs:** new:test_sqlite_backend_unselectable, new:test_no_sqlite_fallback
**Findings:** F-005, F-007  |  **Prerequisites:** STOR-01, GOV-07

### STOR-04  Remove legacy deferred write queue and migration CLI
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** medium  |  **Kind:** retirement  |  **Status:** proposed

**Intent:** No historical queue drain or migration promise; disable/delete old queue path instead of repairing REJECTED receipt drop.

**Acceptance:** (1) F-016 closed by removal, no pending-file loss in any live path, docs identify intentional non-migration.

**Negative controls:** (1) No drain operation can delete a rejected record.

**Source paths:** src/l9_graphite_memory/migration/legacy_write_queue.py, src/l9_graphite_memory/cli.py, MIGRATION.md
**Proposed tests/proofs:** new:test_legacy_queue_command_absent, new:test_no_legacy_queue_references
**Findings:** F-016  |  **Prerequisites:** GOV-07, STOR-01

### HYG-02  Remove dead auth/stdio/SQLite docs and test golden files
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** medium  |  **Kind:** retirement  |  **Status:** proposed

**Intent:** Delete obsolete parser aliases and installation artifacts with explicit test replacing their active expectations.

**Acceptance:** (1) Static scanner finds no runnable legacy Memory stdio/signed-agent/SQLite serving contract.

**Negative controls:** (1) Legacy 2.x tests must not be retained to force fallback.

**Source paths:** docs/COMPATIBILITY_MATRIX.md, QUICKSTART.md, MIGRATION.md, tests/unit/test_stdio_namespace_resolution.py, src/l9_graphite_memory/client_config/
**Proposed tests/proofs:** new:test_no_legacy_surface_in_release
**Findings:** F-006, F-005, F-007, F-016  |  **Prerequisites:** MCP-03, AUTH-15, STOR-03, STOR-04, GOV-10

### QA-03  Forbidden compatibility reachability scanner
**Owner:** independent reviewer + repository CI  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** assurance  |  **Status:** proposed

**Intent:** Inspect runtime entrypoints/config/tests for stdio, static bearer, signed-agent, SQLite serving and legacy queue.

**Acceptance:** (1) No active path reachable (2) exception only provider-outbound transport and isolated test fixtures.

**Negative controls:** (1) Dormant env selector that reopens old auth or SQLite fails.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:test_forbidden_compatibility_reachability
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-15, MCP-03, STOR-03, STOR-04, HYG-02

### QA-04  Integrated critical negative controls
**Owner:** independent reviewer + repository CI  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** assurance  |  **Status:** proposed

**Intent:** Combine OAuth, identity, PII, sensitive consent, tenant and no-fallback negatives through actual MCP.

**Acceptance:** (1) All negative calls correctly refuse without durable write or leaked token.

**Negative controls:** (1) Unauthenticated write, wrong aud, sensitive auto-consent all refused.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:test_critical_negative_contracts
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-13, DATA-06, DATA-07, MCP-08

## P10. Retarget PR #101 and prove source-owned OCI carrier

### OPS-01  Retarget open PR #101 deployment profile to OAuth-only
**Owner:** Quantum-L9/l9-deploy + Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Rework PR101 C1 profile, Dockerfile guard and carrier tests from signed-agent to OAuth resource-server mode.

**Acceptance:** (1) No signed-agent-only guard remains (2) Postgres mandatory (3) tests verify real OAuth MCP and C1 profile.

**Negative controls:** (1) Image refuses signed-agent, bearer, stdio or SQLite.

**Source paths:** .l9/deployment.yaml, Dockerfile, tests/deployment/carrier/test_container_carrier.py, tests/deployment/carrier/test_deployment_profile.py
**Proposed tests/proofs:** new:test_oauth_carrier_profile, existing:test_deployment_profile
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-15, MCP-03, STOR-01, MCP-12

### OPS-02  Pinned image and reproducible installed artifact
**Owner:** Quantum-L9/l9-deploy + Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Use one source-owned OCI carrier with locked dependencies and exact source/wheel digests.

**Acceptance:** (1) Container starts as nonroot on expected port (2) expected wheel matches release binding.

**Negative controls:** (1) No floating image dependency or unsigned artifact substitution.

**Source paths:** Dockerfile, .dockerignore, .github/workflows/release-container.yml, release-work/product-release-binding.yaml
**Proposed tests/proofs:** existing:test_container_carrier, new:test_image_release_binding
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** OPS-01, GOV-11

### OPS-03  C1 host/port/Caddy ownership freshness check
**Owner:** Quantum-L9/l9-deploy  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** operator_preflight  |  **Status:** proposed

**Intent:** Verify current C1 identity, Memory HTTPS route, port 8200, Graphiti 8100 and reserved Cog 18080 without modifying neighbors.

**Acceptance:** (1) Signed inventory of host, route, TLS, processes, Caddy config, services and firewall (2) old observations not treated current.

**Negative controls:** (1) Do not target separate L9-Memory VM or overwrite Graphiti/Neo4j.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:c1_targeted_recon_receipt
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-07

### OPS-04  Fresh isolated PostgreSQL 16 database and role
**Owner:** Quantum-L9/l9-deploy  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** operator_preflight  |  **Status:** proposed

**Intent:** Provision empty Memory DB, RLS/role privilege constraints, isolated from existing C1 tenants.

**Acceptance:** (1) Zero imported Memory/Graphiti data (2) unique role/DSN, migrations apply to new DB only.

**Negative controls:** (1) No reuse of SQLite, Graphiti, Cognitive or other tenant DB.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:test_pg_new_empty_isolated, new:test_db_role_least_priv
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** OPS-03, STOR-01

### OPS-05  Memory-specific Infisical secrets and OAuth configuration
**Owner:** Quantum-L9/l9-deploy  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Create scoped service secret enrollment, separate Cognition and Graphiti identities.

**Acceptance:** (1) Issuer/resource/JWKS/client registry and PG DSN render (2) no secrets committed.

**Negative controls:** (1) No other tenant key or client-side bearer injection.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:test_secret_render_and_revocation
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** OPS-03, AUTH-07, STOR-09

### OPS-06  TLS proxy and public OAuth metadata routes
**Owner:** Quantum-L9/l9-deploy  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Use existing memory.quantumaipartners.com with TLS, /mcp and protected-resource discovery reachable externally.

**Acceptance:** (1) TLS, forwarded headers, Origin allowlist, challenge and metadata work from Claude cloud.

**Negative controls:** (1) No redirect to old bridge or private unreachable endpoint.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:hosted_prm_tls_probe, new:origin_caddy_negative
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** OPS-03, AUTH-02, OPS-01

### OPS-07  Real PostgreSQL health with injected carrier faults
**Owner:** Quantum-L9/l9-deploy + Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Exercise intended container startup/readiness with broken DB and concurrent work without touching other services.

**Acceptance:** (1) readyz true only on canonical PG (2) DB outage 503 (3) healthz responsive.

**Negative controls:** (1) No green from memory-only fixtures or static flags.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** existing:test_container_carrier, new:test_carrier_oauth_pg_fault
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** OPS-02, OPS-04, MCP-07

### OPS-08  New PostgreSQL backup and isolated restore rehearsal
**Owner:** Quantum-L9/l9-deploy  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Prove new canonical DB backup and isolated restore, distinct from old backup already operator verified.

**Acceptance:** (1) Restore exact record/digest/tenant and no copy duplication (2) measured RPO/RTO.

**Negative controls:** (1) No old SQLite import or VM snapshot-only claim.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:test_pg_backup_restore_no_data_loss
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** OPS-04, STOR-02

### OPS-09  Release runner and publisher readiness
**Owner:** Quantum-L9/l9-deploy + Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Validate C1 runner, CI Core caller, release environment and l9-deploy profile v2 on exact revised PR101.

**Acceptance:** (1) Source-owned release caller uses governed Core and l9-deploy (2) no raw push/direct deploy.

**Negative controls:** (1) Unbound hand-built image cannot be released.

**Source paths:** .github/workflows/release-container.yml, .l9/deployment.yaml
**Proposed tests/proofs:** existing:test_release_workflow, new:test_publisher_canonical
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** OPS-07, QA-09

### OPS-10  Disposable externally reachable staging proof
**Owner:** Quantum-L9/l9-deploy  |  **Scope:** core  |  **Risk:** high  |  **Kind:** operator_preflight  |  **Status:** proposed

**Intent:** Exercise native OAuth MCP against disposable PG and temporary TLS route where necessary; no permanent second Memory.

**Acceptance:** (1) Staging route temporary, owned and removed (2) protected production state separate.

**Negative controls:** (1) No permanent second service or unauthorized Caddy takeover.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:test_staging_disposable_remote_mcp
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** OPS-07, OPS-06, AUTH-07

### OPS-11  Runtime config drift and managed restart
**Owner:** Quantum-L9/l9-deploy + Quantum-L9/l9-graphiti-memory  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Check exact image digest, identity revision, TLS and OAuth provider at startup and after refresh.

**Acceptance:** (1) Drift fail-closed and visible (2) restart retains PG, never old credentials.

**Negative controls:** (1) Unknown issuer or DB cannot fallback.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:test_config_drift_reject, new:test_rotation_restart
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** OPS-02, OPS-05, STOR-07

### QA-09  Canonical release validation exact-head receipt
**Owner:** independent reviewer + repository CI  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** assurance  |  **Status:** proposed

**Intent:** Run validate_release.sh, complete pytest, Ruff, mypy, source scanners, wheel and integration on exact amended PR.

**Acceptance:** (1) All mandatory gates PASS with head SHA, skips disclosed (2) removed tests replaced by relevant negatives.

**Negative controls:** (1) No CI green claimed from sandbox reproductions or lint only.

**Source paths:** scripts/validate_release.sh, tools/assurance/check_memory_write_bypass.py, .github/workflows/ci.yml
**Proposed tests/proofs:** existing:validate_release.sh, existing:pytest -q, existing:ruff, existing:mypy
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** QA-03, QA-04, OPS-02, MCP-12, DATA-06

### QA-12  Exact source/OCI/runtime identity provenance receipts
**Owner:** independent reviewer + repository CI  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** assurance  |  **Status:** proposed

**Intent:** Bind source SHA, installed wheel+sdist, image digest, identity projection, C1 deployment and output capabilities.

**Acceptance:** (1) Every identity independent and coherent (2) signatures and admission status verified.

**Negative controls:** (1) Package 3.0.0 string alone is not release proof.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:test_artifact_digest_chain
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** QA-09, AUTH-11, OPS-02

### CUT-01  Authorize isolated staging exposure only after core gates
**Owner:** operator + l9-deploy  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** readiness_gate  |  **Status:** proposed

**Intent:** Require OAuth, sensitive data, Postgres and compatibility scanner before any staging write.

**Acceptance:** (1) QA-03/04 and carrier checks pass, scoped temporary endpoint approved.

**Negative controls:** (1) No unqualified client writes.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:staging_entry_gate_receipt
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** OPS-07, QA-04, QA-03, OPS-05

## C784. Consumer PR #784 native OAuth/identity handoff

### CONS-01  Cursor-Governance PR #784 refresh to settled server contract
**Owner:** Quantum-L9/Cursor-Governance  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Align open PR784 consumer with OAuth-only Memory contract and complete identity; no duplicate installer.

**Acceptance:** (1) PR784 rebased against exact Memory SHA and native HTTP/config identity projected upstream.

**Negative controls:** (1) No stale stdio or token env override.

**Source paths:** ops/memory/mcp_instantiation.py, ops/memory/agent_identity.py, generated/governance/canonical_identity.yaml
**Proposed tests/proofs:** new:cursor_http_config_with_oauth, new:identity_projection_verification
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** MCP-08, AUTH-13, GOV-08

### CONS-02  Cursor native remote MCP OAuth login
**Owner:** Quantum-L9/Cursor-Governance + operator  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Use Cursor native URL+OAuth rather than custom headersHelper, static bearer or subprocess.

**Acceptance:** (1) Real Cursor authenticates, tools list/read/write work, and connection survives restart.

**Negative controls:** (1) No plaintext bearer in mcp.json and no Memory command/args.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:real_cursor_oauth_tool_receipt
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CONS-01, AUTH-07

### CONS-03  Claude account-managed connector registration
**Owner:** Claude account operator  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** operator_proof  |  **Status:** proposed

**Intent:** Configure one remote connector for the Claude account via Auth0 native OAuth.

**Acceptance:** (1) Account connection provides authenticated Memory tools in supported surfaces without mobile env token.

**Negative controls:** (1) No duplicate per-device connection replacing managed OAuth.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:claude_account_connector_receipt
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-07, OPS-10

### CONS-04  Real Claude Code Mobile session acceptance
**Owner:** Claude account operator  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** operator_proof  |  **Status:** proposed

**Intent:** Verify mobile-launched hosted Claude Code session actually exposes the account connector; distinguish general Claude app mobile.

**Acceptance:** (1) Fresh mobile cloud Code session invokes read/write, or status BLOCKED if platform does not provide it.

**Negative controls:** (1) No relabeling a Claude web or app session as Code Mobile (2) unknown surface stays unknown.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:claude_mobile_fresh_session_e2e, new:claude_code_mobile_connector_availability
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CONS-03, AUTH-10

### CONS-05  Cursor/Claude complete identity assertion provenance
**Owner:** Quantum-L9/Cursor-Governance  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Consume actor and surface projection once with trusted runtime evidence, not client-controlled API headers.

**Acceptance:** (1) Different actors remain distinct (2) surface resolved or Unknown (3) Memory receipts agree.

**Negative controls:** (1) No untrusted marker used as remote authorship.

**Source paths:** ops/memory/agent_identity.py, ops/memory/print_agent_assertion_env.py, generated/governance/canonical_identity.yaml
**Proposed tests/proofs:** new:test_cursor_claude_complete_identity, new:test_unknown_surface_consistent
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** AUTH-13, CONS-02, CONS-04

### CONS-06  One governance bootstrap and thin native adapters
**Owner:** Quantum-L9/Cursor-Governance  |  **Scope:** core  |  **Risk:** high  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Retain shared bootstrap, projected authority, native platform OAuth connection and drift checks.

**Acceptance:** (1) Network allowlist and SessionStart verifier know Memory/Auth0 without implementing OAuth twice.

**Negative controls:** (1) No user-pasted long-lived secret or local MCP process.

**Source paths:** ops/scripts/bootstrap_agent_environment.sh, environment/agents/adapters/claude-code/web/network-policy.md, environment/agents/adapters/claude-code/verify_account_env.py
**Proposed tests/proofs:** new:test_shared_bootstrap_native_mcp, new:test_account_env_drift
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CONS-01, CONS-05

### CONS-07  Remove CG Memory stdio, signed-key bootstrap and bridge
**Owner:** Quantum-L9/Cursor-Governance  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** implementation  |  **Status:** proposed

**Intent:** Eliminate old Cursor-Governance rules and setup fragments, including closed PR783 bridge behavior.

**Acceptance:** (1) Generated config never launches local Memory or signs agent headers.

**Negative controls:** (1) No remote stdio bridge or key provisioning.

**Source paths:** ops/memory/mcp_instantiation.py, environment/agents/adapters/claude-code/web/setup.sh, environment/agents/adapters/claude-code/hooks/session_start_claude_governance.sh
**Proposed tests/proofs:** new:test_no_cg_stdio_remote_bridge, new:test_no_signed_agent_env
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CONS-06, MCP-03

### CONS-08  Shared memory cross-client write and denial proof
**Owner:** Quantum-L9/Cursor-Governance + operator  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** integration_proof  |  **Status:** proposed

**Intent:** Cursor write Claude read, reciprocal write, idempotency and persistence in authorized namespace.

**Acceptance:** (1) Two clients read same Postgres records, correct actor attribution, unauthorized scopes refused.

**Negative controls:** (1) Wrong tenant read/write and replay denied.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:real_two_client_shared_pg_roundtrip
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CONS-02, CONS-04, CONS-05, OPS-10

### CONS-09  Client disconnect revocation and reconnect
**Owner:** Quantum-L9/Cursor-Governance + operator  |  **Scope:** core  |  **Risk:** high  |  **Kind:** integration_proof  |  **Status:** proposed

**Intent:** Prove OAuth revoke/expiry and fresh session reauthorization without secrets injection.

**Acceptance:** (1) Revoked clients refused in bound, reconnect authorized data persists with same PG IDs.

**Negative controls:** (1) Revoked token cannot keep writing.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:real_claude_cursor_disconnect_revoke
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CONS-08, AUTH-14

### CONS-10  Non-core consumer claims remain individually qualified
**Owner:** Quantum-L9/Cursor-Governance + operator  |  **Scope:** full  |  **Risk:** medium  |  **Kind:** readiness_gate  |  **Status:** proposed

**Intent:** Prove each optional client surface independently or mark unsupported/retired.

**Acceptance:** (1) No blanket ready claim from two-client proof (2) exact surfaces recorded.

**Negative controls:** (1) Claude app mobile is not Claude Code Mobile proof.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:consumer_matrix_exact_surfaces
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CONS-08, MCP-10

### QA-08  Actual Claude/Cursor OAuth and surface evidence matrix
**Owner:** independent reviewer + repository CI  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** assurance  |  **Status:** proposed

**Intent:** Record real client, account connector, mobile Code, token lifecycle and exact actor/surface outcomes.

**Acceptance:** (1) Real hosted evidence distinguished from mocked SDK or generic Claude app mobile.

**Negative controls:** (1) No simulated client or guessed surface marked PASS.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:real_platform_connector_receipts
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CONS-09, AUTH-13

## P12. Independent assurance, authorized release and C1 cutover

### GOV-12  Independent plan admission and source closure
**Owner:** Quantum-L9/l9-graphiti-memory + Quantum-L9/.github  |  **Scope:** full  |  **Risk:** high  |  **Kind:** authority_gate  |  **Status:** proposed

**Intent:** Submit this working graph with executed receipts to owner; graph cannot self-admit or authorize code/publication.

**Acceptance:** (1) Strategy owner and independent assurance accept exact graph revision separately from the product release.

**Negative controls:** No additional negative specified

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:independent_acceptance_receipt
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** QA-11, CUT-15

### PROJ-14  Projection provider target manifest and activation gate
**Owner:** Quantum-L9/l9-graphiti-memory  |  **Scope:** full  |  **Risk:** high  |  **Kind:** readiness_gate  |  **Status:** proposed

**Intent:** Enforce explicit selected target manifests, scope and transport readiness; graph/vector optionality never weakens canonical readiness.

**Acceptance:** (1) Graphiti capability activated only after real provider suite (2) no optional provider family is inferred healthy or mandatory for base store.

**Negative controls:** (1) No Graphiti activation on fake tests or unresolved locator race.

**Source paths:** src/l9_graphite_memory/projections/runtime.py, src/l9_graphite_memory/adapters/factory.py
**Proposed tests/proofs:** new:test_projection_activation_gate
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** PROJ-10, RET-05, QA-07

### QA-02  Finish 144-module source audit with range reads
**Owner:** independent reviewer + repository CI  |  **Scope:** full  |  **Risk:** high  |  **Kind:** independent_audit  |  **Status:** proposed

**Intent:** Complete source census, particularly big stores, retrieval, privacy, graph, auth, and packaged clients.

**Acceptance:** (1) Per-file fully/partially/not-read ledger with new findings inserted (2) separate audit completeness from PR proof.

**Negative controls:** (1) 36/144 does not count as complete source review.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:complete_source_census_receipt
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** GOV-09

### QA-05  Provider/outbox fault-injected integration
**Owner:** independent reviewer + repository CI  |  **Scope:** full  |  **Risk:** critical  |  **Kind:** assurance  |  **Status:** proposed

**Intent:** Run Graphiti isError, breaker, expiry, retry, phantom reconciliation and live tool shape tests.

**Acceptance:** (1) No false projection evidence, permanent half-open wedge or silent dead-letter deletion.

**Negative controls:** (1) No phantom link allowed to certify deletion.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:test_provider_fault_injection_receipts
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** PROJ-10, LIFE-12

### QA-06  PostgreSQL 16 multi-process concurrency stress
**Owner:** independent reviewer + repository CI  |  **Scope:** full  |  **Risk:** critical  |  **Kind:** assurance  |  **Status:** proposed

**Intent:** Run real source/image PG concurrent writers, leases, restart and isolation with injected failures.

**Acceptance:** (1) No partial canonical state, no cross-tenant leakage, visible retry backlog.

**Negative controls:** (1) Worker crash cannot strand event without eventual recovery.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:test_pg_concurrency_soak, existing:test_remote_mcp_postgres_multiprocess
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** LIFE-12, MCP-12, STOR-02

### QA-10  Independent per-PR code audit, CI and review closure
**Owner:** independent reviewer + repository CI  |  **Scope:** full  |  **Risk:** high  |  **Kind:** independent_audit  |  **Status:** proposed

**Intent:** Audit every PR exact diff, cross-PR contract interactions and reviewer threads, not CI alone.

**Acceptance:** (1) Each new or amended PR audited at its exact tested head and defects remediated before merge.

**Negative controls:** (1) Green workflow is not equivalent to verified correctness.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:independent_pr_audit_receipts
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** QA-09, QA-02

### QA-11  Independent full-graph acceptance and unknown disposition
**Owner:** independent reviewer + repository CI  |  **Scope:** full  |  **Risk:** critical  |  **Kind:** independent_audit  |  **Status:** proposed

**Intent:** Audit all plan gates and findings against original intent, current sources, runtime and client evidence.

**Acceptance:** (1) Full report identifies remaining unknown/blockers (2) all closed findings have proof or removal.

**Negative controls:** (1) Unexecuted hosted/client proof remains NOT_RUN.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:independent_evidence_assessment
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** QA-10, QA-06, QA-08, CUT-14

### CUT-02  Real Auth0 -> Memory -> PostgreSQL staging proof
**Owner:** operator + l9-deploy  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** hosted_proof  |  **Status:** proposed

**Intent:** Authorize native OAuth client, list tools, write/read PG and restart service.

**Acceptance:** (1) Auth0 JWT aud/issuer/scope verified, exact record persists, no SQLite.

**Negative controls:** (1) No mocked issuer or local fallback counts.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:hosted_auth0_pg_smoke
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CUT-01, OPS-10, CONS-02

### CUT-03  Cross-client and Claude Code Mobile staging proof
**Owner:** operator + Cursor-Governance  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** hosted_proof  |  **Status:** proposed

**Intent:** Use actual Cursor and account-managed Claude connector with fresh mobile Code session and proven actor/surface behavior.

**Acceptance:** (1) Two-client shared data and negatives pass, mobile specifically PASS or BLOCKED.

**Negative controls:** (1) No web/app mobile passed off as Claude Code Mobile.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:hosted_multisurface_proof
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CUT-02, CONS-08, QA-08

### CUT-04  New PG restore and rollback rehearsal
**Owner:** operator + l9-deploy  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** hosted_proof  |  **Status:** proposed

**Intent:** Prove isolated backup/restore of new PG, application rollback that retains new data and no stdio revival.

**Acceptance:** (1) Exact record IDs/digests restored, safe rolling-forward image response documented.

**Negative controls:** (1) Never roll back to old 2.2 SQLite for new PG data.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:hosted_restore_and_rollback_rehearsal
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CUT-02, OPS-08

### CUT-05  Operator go/no-go for exact C1 handover
**Owner:** operator  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** operator_gate  |  **Status:** proposed

**Intent:** Decide handover only after staging, client, backup and protected-neighbor tests.

**Acceptance:** (1) Time-bound operator approval records old listener, new digest, rollback and ingress owner.

**Negative controls:** (1) Plan file never self-authorizes deployment.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:cutover_go_no_go_receipt
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CUT-03, CUT-04, OPS-03, OPS-09

### CUT-06  Stop only old Memory 2.2 listener
**Owner:** l9-deploy  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** deployment_execution  |  **Status:** proposed

**Intent:** Stop old Memory process at C1 loopback 8200, preserving backup and other services.

**Acceptance:** (1) Old pid/socket gone, Graphiti/Neo4j and Cog unaffected.

**Negative controls:** (1) No removal of protected neighboring data.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:cutover_listener_ownership
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CUT-05

### CUT-07  Activate one OAuth Memory service on same C1 route
**Owner:** l9-deploy  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** deployment_execution  |  **Status:** proposed

**Intent:** Serve admitted OCI Memory on memory.quantumaipartners.com with one canonical PG.

**Acceptance:** (1) TLS, OAuth metadata, exact release/runtime receipt, readyz pass externally.

**Negative controls:** (1) No signed-agent or SQLite mode.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:post_switch_hosted_http_pg_receipt
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CUT-06, QA-12

### CUT-08  Post-switch Cursor/Claude, grants and restart
**Owner:** operator + l9-deploy  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** hosted_proof  |  **Status:** proposed

**Intent:** Reauthenticate native clients on permanent route and prove shared data, idempotency and refusal.

**Acceptance:** (1) New route reproduces staging proof, no stale cache, restart preserves PG.

**Negative controls:** (1) No staging URL accidentally qualifies.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:production_two_client_acceptance
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CUT-07, CONS-09

### CUT-09  Production token/revocation/outage rehearsal
**Owner:** operator + l9-deploy  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** hosted_proof  |  **Status:** proposed

**Intent:** Test expired/revoked client, PG failure, Auth0 key rotation and Unknown surface with truthful readiness.

**Acceptance:** (1) Denied operations have no writes, service recovers, audit evidence consistent.

**Negative controls:** (1) No fallback or tenant elevation.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:production_auth_fault_rehearsal
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CUT-08, OPS-11

### CUT-10  Remove old SQLite files only after proven cutover
**Owner:** operator + l9-deploy  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** controlled_retirement  |  **Status:** proposed

**Intent:** Carry out narrow already-authorized legacy Memory storage deletion after new PG and route proven; retain verified backup.

**Acceptance:** (1) Only old Memory data removed, backup intact, neighbors unaffected.

**Negative controls:** (1) No repeat backup verification required and no Graphiti deletion.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:legacy_removal_scope_receipt
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CUT-08, CUT-09, GOV-07

### CUT-11  Decommission old client transport paths
**Owner:** Quantum-L9/Cursor-Governance + operator  |  **Scope:** core  |  **Risk:** high  |  **Kind:** controlled_retirement  |  **Status:** proposed

**Intent:** Remove remaining old stdio/HMAC from active Cursor and Claude setups.

**Acceptance:** (1) Clients use only OAuth HTTP after cutover and old credentials revoked.

**Negative controls:** (1) No accepted old connection in operating path.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:live_client_legacy_config_absent
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CONS-07, CUT-08

### CUT-12  Observe postcutover operations and PG recovery
**Owner:** l9-deploy  |  **Scope:** core  |  **Risk:** high  |  **Kind:** operational_proof  |  **Status:** proposed

**Intent:** Watch finite live run with read/write/restart/backup metrics and outbox handling.

**Acceptance:** (1) No silent failed writes or false ready (2) logs and alert receipts retained.

**Negative controls:** (1) No silent dead letter or deletion obligation.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:postcutover_operating_observation
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CUT-08, CUT-10

### CUT-13  Core hosted shared Memory outcome
**Owner:** operator  |  **Scope:** core  |  **Risk:** critical  |  **Kind:** milestone  |  **Status:** proposed

**Intent:** Accept core C1 OAuth-only PG service only after hosted+security proofs; distinct from full source audit.

**Acceptance:** (1) Two native clients, stable canonical PG, identity/namespace receipts and no history fallback verified.

**Negative controls:** (1) No partial connector proof as complete.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:core_memory_operating_receipt
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CUT-11, CUT-12, CUT-09

### CUT-14  Full correctness and provider/maintenance remediation outcome
**Owner:** independent reviewer + operator  |  **Scope:** full  |  **Risk:** critical  |  **Kind:** milestone  |  **Status:** proposed

**Intent:** All findings F-001..F-020 closed by tests/removal; U issues resolved, full source audit and optional provider qualification.

**Acceptance:** (1) Graphiti ready only if live tests, Zep explicitly qualified or removed, retention correct, no open HIGH/MEDIUM.

**Negative controls:** (1) No claimed full closure on 36/144 audit or a simulated provider.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:complete_remediation_coverage_acceptance
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** QA-07, QA-06, QA-02, HYG-03, DATA-08, RET-06, PROJ-14

### CUT-15  Final semantic and operational admission by owners
**Owner:** operator + authorized strategy/release owners  |  **Scope:** full  |  **Risk:** critical  |  **Kind:** admission_gate  |  **Status:** proposed

**Intent:** Compare intended architecture, exact source, hosted behavior and independent audit receipts.

**Acceptance:** (1) Owners independently accept core plus full remediation, preserving Unknown where still blocked.

**Negative controls:** (1) Self-authored graph and CI are not release permission.

**Source paths:** External proof or semantic owner; see source register.
**Proposed tests/proofs:** new:final_operator_admission_receipt
**Findings:** Upstream/cross-cutting  |  **Prerequisites:** CUT-13, CUT-14, QA-11
