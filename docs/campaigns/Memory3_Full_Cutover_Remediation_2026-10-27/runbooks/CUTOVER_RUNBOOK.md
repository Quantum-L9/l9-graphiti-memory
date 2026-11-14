# C1 Full Cutover Runbook (operator-gated, NOT executed)

**Intended permanent service:** memory.quantumaipartners.com -> Caddy TLS -> Memory 3.0 native `/mcp` on loopback 8200 -> fresh isolated PostgreSQL 16. No Memory stdio, signed-agent or SQLite fallback. The existing Graphiti/Neo4j tenant and Cognitive Runtime are out of the mutation scope. Use the exact fresh C1 recon; October 13 inventory is historical, not a live receipt.

## Gate 0. Source and authority lock

- Confirm Memory main pinned revision, PR101 current head, PR784 current head, .github identity projection and hosted Dependency exception. Re-resolve if anything changes.
- Obtain a successor ADR superseding only the outdated relevant transport and auth decisions without rewriting history; `AGENTS.md` invariants remain active unless formally amended.
- Keep original C1 preflight/backups and the operator's verified legacy-backup attestation unchanged. This already authorizes only the narrow old Memory service+SQLite retirement after new replacement proof, **not** other tenants or unrelated deploys.
- Record approved source/image and deployment owner separately; a successful test is not publication authority.

## Gate 1. Canonical ingress truth and native OAuth

- Run DATA-01..06 PII, explicit-evidence and consent negatives against actual MemoryService and MCP write paths. Sensitive class writes without actual evidence or purpose-bound consent must refuse.
- Prove Auth0 `resource` and API audience interoperability with intended native client. In tenant Advanced enable Resource Parameter Compatibility Profile only if current operator-approved configuration and real client requests require it. Record issuer, resource, AS metadata, client registration and redirect URIs.
- Validate tokens via a native OAuth resource-server implementation. Check issuer, audience, signature, expiry, scope and permissions per call. Prove wrong grants, revoked users, malicious headers, cross-tenant and unknown actor fail closed.
- Require complete identity assertion: stable product identity, exact release, actual service runtime, verified actor, independently verified or Unknown surface, nonapplicable Constellation identity. No inference of mobile from account connector. Do not enable consequential agent writes where actor attribution is unresolved.
- Remove local signed-agent, static bearer, stdio MCP, SQLite server and legacy write queue runtime paths before exposing any public listener (QA-03).

## Gate 2. Carrier and database qualification

- Retarget existing Memory PR101 Dockerfile + `.l9/deployment.yaml` and negative tests from signed-agent to OAuth resource server. Postgres only, no compatibility choices. Run exact-head `bash scripts/validate_release.sh`, full pytest, lint, type checking, installed wheel protocol and security suite.
- C1 preflight current SSH host key, runner reachability, Caddy site import, DNS, current 8200 owner, Graphiti port 8100, Cog 18080, firewall and certificate status. Preserve separate service IDs; no speculative host mutation.
- Provision fresh, empty PostgreSQL 16 instance/database/schema role for Memory. Verify no imported SQLite or Neo4j data, unique DSN, least privilege/RLS, schema initialization, negative cross-tenant checks.
- Establish dedicated Infisical Memory secret rendering and Auth0 resource configuration. Prove secrets cannot be printed in client config, logs, CLI config dumps, model repr or error reports.
- Build signed/attested immutable image and test installed server under real PG. `/readyz` must be 503 on loss of required store, `/healthz` remains responsive during slow tools; no selected optional Graphiti/Zep state may make a false ready claim.

## Gate 3. Isolated real-hosted rehearsal before switching permanent listener

- Where external Claude cloud access requires it, use an explicitly approved **temporary, isolated** OAuth staging URL with disposable PG. Avoid a permanent duplicate canonical Memory authority and do not use protected neighbor data.
- Configure actual Cursor Streamable HTTP MCP with native OAuth. Configure actual Claude account remote MCP connector and sign in through Auth0. Verify the tool inventory and scopes.
- **Separately** test actual Claude Code mobile-launched hosted session. Anthropic documentation for generic Claude mobile app remote connectors is *not* a proof that a Claude Code Mobile cloud VM exposes them. Record exact session type and attachment. If unavailable, declare CUT-03 BLOCKED, do not relabel it.
- Perform Cursor write -> Claude read -> Claude write -> Cursor read in one authorized namespace; check exact record IDs, actor attribution, honest surface, idempotency and tenant/namespace refusal. Restart Memory and both clients and repeat.
- Exercise token revocation and refresh on both clients, issuer key rotation and stale cached grants. No fallback path allowed.
- Rehearse a **new PostgreSQL backup and isolated restore**. Validate exact record IDs and digests. This does not repeat the already operator-verified old SQLite backup.

## Gate 4. Release and controlled handover

- Independent PR review and release admission on the exact source/wheel/sdist/image digest. Product admission and hosted runtime admission remain separate. Use canonical `make pr` for code publication and l9-deploy's governed release interface for deploy. No raw push.
- Operator go/no-go CUT-05 identifies intended image SHA, exact C1 host, old Memory pid and 8200 listener, Caddy route, new PG DSN fingerprint, rollback steps, and protected neighbors.
- Stop only the old Memory 2.2.0 listener, retaining its verified external backup and *not deleting* Graphiti, Neo4j or Cognition state. Do not run both on the same permanent port.
- Start new Memory 3.0 OAuth service bound to the same hostname and loopback port 8200 and fresh PostgreSQL canonical DB. Confirm TLS, RFC9728 discovery, correct OAuth challenge, health/readiness, exact image/service identities and absence of old runtime modes.

## Gate 5. Permanent endpoint acceptance

- Repeat native Cursor+Claude connector shared-memory writes, reads, denial, idempotency, restart and revoked-token proofs on the **permanent** hostname; verify no old process/config/staging URL remains active.
- Confirm `/healthz` and `/readyz` under network/PG faults and issuer rotation; preserve observable persistent receipts and targeted alerts. Do not call a server operational because one synthetic HTTP test returned 200.
- After the replacement passes the operator-authorized condition, retire only legacy Memory SQLite storage files. Retain previously verified backup in an independent location. Record what was removed and what was preserved.
- Observe actual operation for a finite agreed acceptance window, with no silent unbounded outbox backlog or inaccurate capability claims.

## Gate 6. Full remediation acceptance (separate from base service)

- Fix/retire each F-001..F-020 defect and resolve nine unverified concerns with actual tests or unreachable-code proof; publish final coverage ledger. Full 144-module source audit must be independently assessed, not claimed from original 36/144 coverage.
- Prove outbound Graphiti MCP provider add/search/delete/async ingestion and real lease expiry in an isolated provider scope before enabling projection. Its outbound HTTP session lifecycle is **not** a forbidden inbound Memory stdio compatibility route.
- Choose Zep disposition: default remove if no live admitted consumer; if kept, F-014 health and F-017 silent truncation require real regression proof before activation.
- Prove reference-aware retention across out-of-window records, atomic deletion/retirement and eventual recovery on real PostgreSQL 16.
- Independent assurance and operator separately admit CUT-13 core operation, CUT-14 full correctness, and CUT-15 final architecture/release state.

## Stop conditions and rollback contract

**Stop immediately:** invalid token audience/issuer, Unknown consequential actor, false ready under PG failure, no clean new PG restore, unexpectedly touched protected C1 service, duplicated Memory listener, source/image mismatch, unexplained canonical data loss or an unbound release claim.

**Before first new PG write:** stop new image; rework the OAuth-only image/config. The prior legacy Memory backup exists, but old 2.x stdio/SQLite is not a permitted production compatibility rollback under this decision.

**After new PG writes:** never reverse to the old SQLite store or a legacy MCP door. Preserve PG and receipts, switch to a previously proven **OAuth-only PG-compatible** image or pause external writes until a fix is admitted. Backup restore is performed to an isolated PG destination and promoted only by authorized owner.

**Outbox/provider failure:** disable/hold projection worker, preserve canonical PG and pending obligations; do not fabricate delivery/deletion receipts. Full correctness lane can continue without enabling unqualified provider.
