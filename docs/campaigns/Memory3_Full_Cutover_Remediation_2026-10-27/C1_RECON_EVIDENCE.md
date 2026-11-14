# C1 Reconnaissance Evidence, normalized

**Campaign:** c1-shared-memory-2026-10-26  
**Annex revision:** 1.2 (2026-10-26; subsequent operator authorization incorporated)  
**Evidence class:** historical observed configuration + current source/CI checks + **direct operator attestation** for completed/verified legacy backup and scoped service/store replacement authorization. **No live C1 access or mutations occurred during this update.**

## Primary sources and relative precedence

1. [October 13 Hetzner and memory reconnaissance archive](https://www.dropbox.com/scl/fi/051ob10wo07xb8pl5qyz9). Extracted sections: `C1_AND_DECISIONS.md`, `evidence/hetzner-api/servers.json`, `networks.json`, `firewalls.json`, `c1-snapshot/c1_snapshot_result.json`, `RUNTIME_CENSUS.json`, `HOST_CENSUS.json`, `VERDICT.md`. The C1 containment and C1 snapshot were separately authorized, completed on 2026-10-13. The earlier `VERDICT.md` in the same archive represents an initial blocked survey and is **superseded for C1 facts** by the later `C1_AND_DECISIONS.md` and real Hetzner API JSON. It remains relevant for October 13 Cursor-local runtime diagnostics.
2. [October 23 Memory C1 execution-pack README](https://www.dropbox.com/scl/fi/2l3qe69gyjob1eyf4qr4r). **Planning instructions, not C1 evidence**; its `SOURCE_BINDINGS.md` was authored without the recovered October 13 host survey, so its generic host Unknowns are narrowed below.
3. [October 23 Cognitive Runtime deployment contract](https://github.com/Quantum-L9/l9-cognitive-runtime/blob/94348537bb775d7fa1eb06f950d04dbde2442875/.l9/deployment.yaml). Pins C1 host `46.62.243.82`, C1 SSH host **public** key, `mcp-staging.quantumaipartners.com`, and host port `18080`. Source binding is not a current live host-key recheck. Treat Cognitive Runtime as read-only.
4. [October 24 Cognitive Runtime checkpoint](https://www.dropbox.com/scl/fi/ljitcgii8p641soe074xe). Confirms release/dispatch history and that no fresh C1 host probe was performed there; its recent operational claims are historical where so marked.
5. October 26 GitHub run evidence: [l9-deploy runner conformance](https://github.com/Quantum-L9/l9-deploy/actions/runs/40315689453) and [Infisical-backed infrastructure drift](https://github.com/Quantum-L9/l9-deploy/actions/runs/40304987574).

## Host and tenant facts resolved by recon

| Subject | Last observed fact | Evidence/class |
|---|---|---|
| C1 identity | Hetzner server ID **114194366**, name C1, public IPv4 **46.62.243.82**, x86-64 CPX32, status `running` at October 13 collection | Hetzner `servers.json`, **observed October 13** |
| Separate L9-Memory VM | Hetzner ID **119722208**, **89.167.34.78**, Arm CAX41, private **10.2.0.2** on network ID **11898082** | `servers.json`, **observed October 13**. This is NOT C1 |
| C1 private network | `private_net: []` on C1 (L9-Memory VM is attached to a private network; C1 is not) | Hetzner `servers.json` and `networks.json`, **observed October 13** |
| C1 cloud firewall | `c1-k8s-firewall` ID **10430780** attached to C1. Permits public 22, 80, 443 and also 6443 and several 30xxx TCP ports; actual listeners are distinct from firewall allowance | `firewalls.json`, **observed October 13** |
| C1 reverse proxy | Existing Caddy listens on 80/443. `memory.quantumaipartners.com` mapped `/graphiti/*` to loopback 8100 and default route to loopback 8200. Existing paths/ownership must be preserved | `C1_AND_DECISIONS.md`, **observed October 13** |
| Legacy Memory | `l9-memory-server` systemd service, package **2.2.0**, local SQLite ledger, bound **127.0.0.1:8200**; public `/mcp` returned 401 without bearer | `C1_AND_DECISIONS.md`, **observed October 13** |
| Legacy Graphiti | `graphiti-mcp-cursor` container bound **127.0.0.1:8100**. Prior anonymous `tools/list` returned tool inventory through public `/graphiti/mcp` (see risk below) | `C1_AND_DECISIONS.md`, **observed October 13** |
| Graph store | Neo4j 5.26 on loopback 7474/7687, source data under `/opt/graphiti-cursor/neo4j-data` (~1.4 GB); Graphiti recorded **6,441 episodes** across approximately 25 groups | `C1_AND_DECISIONS.md`, **observed October 13** |
| Cloud backups | C1 backups enabled with `backup_window: 22-02`. VM snapshot ID **443133337**, name `C1-pre-memory-rebuild-20261013`, completed/available October 13. **Crash-consistent image, not PostgreSQL restore proof** | Hetzner `servers.json`, `c1-snapshot` and `C1_AND_DECISIONS.md` |
| Hetzner storage | No attached Hetzner volume on C1 (`volumes: []`); separate L9-Memory VM owns 10-GB volume 104559037 | `servers.json` / `volumes.json`, **observed October 13** |
| C1 cognitive-runtime reservation | Current source design reserves host **18080** and hostname `mcp-staging.quantumaipartners.com`; original deployment dispatch **validated**, authorization then **failed**, deployment **skipped** | [Cognitive profile](https://github.com/Quantum-L9/l9-cognitive-runtime/blob/94348537bb775d7fa1eb06f950d04dbde2442875/.l9/deployment.yaml), [Deploy run](https://github.com/Quantum-L9/l9-deploy/actions/runs/40019807900), October 24 checkpoint |
| Generic v2 release dispatch | Cognitive Runtime source demonstrated a real v2 request accepted by `l9-deploy` validation job, so a generic Core-v2 producer is no longer an unproven architectural invention. Reuse the existing producer; prove the Memory consumer wiring independently | [Cognitive runtime PR 65](https://github.com/Quantum-L9/l9-cognitive-runtime/pull/65), [Deploy run 40019807900](https://github.com/Quantum-L9/l9-deploy/actions/runs/40019807900) |

## What is known vs. what still needs revalidation

**Resolved identity/census (historically observed):** exact C1 server identity; correct separate L9-Memory server; C1 lack of private NIC at capture; firewall IDs and attachments; Caddy routing; occupied legacy ports; existing Memory/Graphiti/Neo4j workloads; snapshot and Hetzner backup policy; existing source reservations for Cognitive Runtime. Do not restart a generic discovery campaign for these facts.

**Still needs current read-only operational proof before replacement:** (1) current C1 host key against trusted provenance and successful authorized runner SSH; (2) actual Caddy Memory/Graphiti route ownership and planned loopback **8200 handover**; (3) new PostgreSQL version, isolation and backup owner; (4) current Memory-specific Infisical project, secret references, per-agent signing keys/grants and no key disclosure; (5) current C1 firewall/live listeners and deployment runner route; (6) a restore test on **new isolated PostgreSQL**, NOT the verified legacy SQLite backup. These are freshness or **new-deployment setup obligations**, not grounds to rediscover the server from scratch.

**Current failures outside C1 snapshot:** October 26 runner conformance asserts `l9_management_cidr in l9_nft_rules.stdout` and fails; infrastructure drift fails Infisical export validation with `Infisical secret key is not a valid environment name`. These are exact observed jobs and require owner-specific diagnosis. Do not infer the C1 firewall is the cause of a check run on the separate deployment runner.

## Architectural consequences / no drift

- Existing C1 memory server **does not** satisfy Memory 3.0 shared PostgreSQL. **Operator-approved replacement:** retire `l9-memory-server` 2.2.0/SQLite and remove its obsolete local data after the new service is ready and verified. Its backup is completed and verified by the user; a second old-backup restore test is not a gate. Preserve Graphiti/Neo4j and Cognitive Runtime completely.
- **Do not target L9-Memory at 89.167.34.78.** C1 target is ID 114194366 / 46.62.243.82. Do not assume any private-network SSH route to C1; no requirement to create a new one unless the actual accepted deployment contract proves necessary.
- Reuse existing **memory.quantumaipartners.com** and **127.0.0.1:8200** for the new Memory 3.0 service after **stopping the old Memory 2.2.0 process**. No concurrent listener or duplicate permanent service. **8100** remains Graphiti, and Cog's **18080** is reserved/read-only. Verify current ownership before handover.
- Prefer retaining the existing Caddy TLS Memory route with `ingress.mode=external` **only if** the verified current route already directs the correct paths to loopback 8200. Any necessary Caddy edit must remain narrowly scoped and independently justified. Do not modify `/graphiti/*` and do not invent a second Memory hostname.
- Existing legacy Neo4j/Graphiti data is operational state, not disposable test data. Do not overwrite, delete, migrate or reinterpret it as canonical PostgreSQL memory.
- **Security finding to recheck:** on October 13, the legacy `/graphiti/mcp` endpoint accepted unauthenticated initialization and `tools/list`, revealing mutation-capable tool names. This was historically observed; current exposure is unknown. Do not touch those Graphiti routes during Memory deployment. Route any security containment as a separately scoped, authorized change.
- **Backup boundary:** The user completed and verified the **legacy Memory SQLite backup** and authorized deleting its obsolete live store. This is an operator attestation; no further old-backup test is required. The daily Hetzner VM backup/snapshot is supplemental, not proof of the **new PostgreSQL** recovery plan. Test new PostgreSQL backup/isolated restore and application rollback separately.
- Global law, semantic compiler and read-only Cognitive Runtime stay unchanged unless exact new evidence establishes a material obligation. A real governed Claude Mobile/Cursor bridge cutover also has an owner outside the current four writable repos; stop before broad consumer activation without scoped authorization.

## Reconciliation disposition

- **A3 state:** historical C1 recon complete; operator-verified legacy backup and authorization recorded; current SSH/Caddy/PG/secrets freshness checks remain.
- **A4 state:** verified October 26 deployment-runner and Infisical/drift failures remain in the graph; the C1 archive cannot close them.
- **A2:** reuse existing Memory HTTP server/remote client and generic Core-v2 producer. Only image/profile/thin consumer release caller and narrow tests are proposed.
- **A5–A8:** scope to retire/replace legacy Memory is **operator-authorized**, but no new C1 Memory 3.0 deployment, cross-host proof, **new PostgreSQL** restore or service admission is proven.

**No source, cloud, database, host, production workflow, or Dropbox files were modified while creating this recon-normalized plan.**

## Operator verification and authorized replacement (2026-10-26)

**User-attested, not independently file-inspected:** The backup of the **old** C1 Memory store was completed and verified, and deletion/replacement of the old service/store is approved. This resolves the prior legacy-backup/retention unknown. Backup location, integrity receipt and timestamp were not provided and are not fabricated; the operator's explicit verification is accepted without repeated testing.

**Strict scope:** Replace only legacy `l9-memory-server` 2.2.0 and its corresponding SQLite canonical store on **C1 ID 114194366**, with a new isolated PostgreSQL-backed Memory 3.0 runtime on the same authorized Memory endpoint. Confirm the exact live service identity and its filesystem ownership before stop/removal. Keep the verified backup, existing Graphiti MCP (8100), Neo4j data, and all unrelated C1 tenants, including Cognitive Runtime, unchanged. Prepare and validate the replacement before controlled retirement. Only delete old service/store bytes after the new runtime is healthy; do not read this authorization as permission to tear down other services.
