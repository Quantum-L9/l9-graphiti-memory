# Source, Reality and Placement Ledger

This is a source-grounded successor to the existing C1 Memory campaign. The original audit materials are included verbatim in `sources/`. `C1_RECON_EVIDENCE.md` and `OPERATOR_DECISION_2026-10-26.md` are byte-preserved from the predecessor.

## Observed exact epoch

- Memory main `eb0bcbed1e1652529675af52584185d2f09dd737` at this planning run: same revision as both user-supplied audits.
- `.github` main `3dcdeaae355b6de08562993f705084d7a3714bfd`: canonical identity_model, actor_registry, surface_registry and admitted hosted Memory exception.
- Cursor-Governance main `e31ea23149ae2669bcaca82da65252e56cf2ace5`; open #784 head `e9c42599c83ceefccd33576fd6ea9d085e5c3cc8`.
- Memory open #101 head `52d1e4bba2ab8f56f1e73bb5254b79d8e3a818f2`: source-owned OCI carrier explicitly pins signed-agent auth; it cannot be deployed as the no-compatibility OAuth target unchanged.
- Memory `AGENTS.md` v2.3.0 retains MemoryService, server-derived identity, atomic persistence, temporal separation, projections, write capability, secret/validation/client-instantiation constraints.
- Graphiti `HttpMcpTransport.call_tool` ignores `isError`; its breaker can remain HALF_OPEN on failed session initiation. PostgreSQL and SQLite claim/update/link/deletion were examined through connector line ranges, removing the original read-size obstacle.
- `MemoryService._admit` defers supersession for QUARANTINED records, while ordinary release transitions only activate/reproject without applying the pending predecessor supersession. This is a source-level missing seam, not executed reproduction.
- `AdmissionEngine` enforces explicit evidence and consent but MCP write path inserts EvidenceKind.EXPLICIT itself; the privacy concern is genuine across source paths.

## Where code and global semantics live

`.github` has authority over the six identity *meanings*, actor and surface registries and product-kind exception. Memory product owns its own topology, identity consumer, canonical service, Postgres, MCP tool contracts, privacy, projections and release artifact. Cursor-Governance may project actor/surface meaning and detect its runtime context but cannot issue authorization grants or invent global identity. Auth0 authenticates users/clients as delegated OAuth issuer, not an actor-registry replacement. l9-deploy owns C1 execution and operational admission. No Gate routing is necessary for ordinary actor-to-Memory MCP consumption.

## Original audit limitations remain explicit

Pass 2 claims 144 first-party modules, of which 36 fully, eight partially and 100 not read. The per-module `source_coverage.yaml` is missing from attachments; therefore a truly complete code audit cannot be certified. The new targeted line-range reads confirm several seams without claiming the missing 100 have been reviewed. All repo and hosted tests for proposed remediations are NOT_RUN.

## Public reference checks

- MCP and RFC 9728 protected resource metadata require native discovery of OAuth issuer/resource.
- Auth0 notes RFC 8707 `resource=` can fail without its Resource Parameter Compatibility Profile; GA Auth for MCP supports it when tenant configured. This is not proof about this tenant's actual settings.
- Claude account connectors exist and can be used on general Claude mobile surfaces, but a real Claude Code Mobile hosted session still needs explicit acceptance proof. Cursor documentation names native Streamable HTTP OAuth support.

See `ledgers/source_register.csv` for exact hyperlinks and evidence grades.
