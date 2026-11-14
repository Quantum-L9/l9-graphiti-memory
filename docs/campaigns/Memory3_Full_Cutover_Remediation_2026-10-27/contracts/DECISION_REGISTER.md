# Decision Register: Resolved, Proposed and Still Blocked

## Operator-resolved constraints

**O-001 ACCEPTED 2026-10-27:** No historical compatibility, full cutover to one native OAuth Streamable HTTP MCP server, no Memory stdio, static bearer, signed-agent HMAC, legacy local SQLite or legacy queue fallback. Plan still must formally supersede historical ADRs; no repository edit automatically authorized.

**O-002 PREVIOUSLY REPORTED/SCOPED:** Old C1 Memory SQLite backup completed and verified by operator on 2026-10-26; narrow permission to delete old Memory service/store **after** replacement confirmed. No repeat old-backup test and no permission to touch Graphiti, Neo4j, Cog, other tenants.

**O-003 LOCKED TARGET:** Auth0 selected as issuer subject to real client/resource interoperability, `.github` as global identity authority, Memory as server and lifecycle owner, Cursor-Governance as native consumer, `l9-deploy` as deployment owner.

## Unresolved technical decisions with cheap distinguishing proofs

| ID | Decision needed | Preferred bounded interpretation | Cheapest disambiguating proof | Blocks |
|---|---|---|---|---|
| D-01 | Native Auth0 resource parameter, API audience, client metadata | Use Auth0 native Resource Parameter Compatibility Profile, approved client metadata and standard discovery, no OAuth proxy | AUTH-01 live PKCE + resource/JWKS receipt | AUTH-04 and C1 |
| D-02 | How to cryptographically bind authenticated OAuth user+client to an automated ActorIdentity | Use provider/trust-backed binding only when verifiable; otherwise Unknown and refuse consequential agent writes | AUTH-09 negative spoof, CONS-05 real provenance | Agent write acceptance |
| D-03 | Per-request mobile SurfaceIdentity assurance | Unknown absent trusted runtime evidence; do not infer from Claude account connector | CONS-04 actual Claude Code Mobile hosted session and available signed context | Mobile assurance claim |
| D-04 | Identity assertion wire/application contract after deleting HMAC door | Use server-consumed evidence-bound schema and provider-native claims, no client-supplied role/header authority | AUTH-13 receipt with forged/stale negative | Complete identity gate |
| D-05 | Consent timestamp semantics for historical valid_from | Require consent already effective at applicable event time or explicit documented retrospective authorization | DATA-05 + ADR-049 review and negative tests | Sensitive historical writes |
| D-06 | Zep retained or removed | Remove Zep if no admitted active consumer; if retained fix health/truncation before enabling | PROJ-11 consumption census; optional PROJ-12/13 live tests | Full remediation if retained |
| D-07 | Python/TypeScript remote clients still real consumers | Keep only used packages, migrate to OAuth, delete unused old auth clients | MCP-09/10 consumer inventory | Release artifact inventory |
| D-08 | Temporary staging OAuth hostname / route | Disposable restricted route, independent DB; never permanent duplicate service | OPS-10 real authenticated cloud reachability with operator approval | C1 switch |
| D-09 | Secure operator/admin path without legacy stdio human secret | Keep native local CLI as an authorized operator interface; separate file-local operations from agent MCP rights | AUTH-16 local admin negative suite | Privileged tooling |
| D-10 | Outbound Graphiti qualification timetable | Initial core PG service may launch with projections disabled; ALL provider findings still in full-remediation milestone and provider activation blocked until qualified | CUT-13 vs CUT-14 independent receipts | Projection activation/full closure |

An unresolved technical choice is an explicit blocking node, not an invitation to silently add architecture or test-only stub behavior.
