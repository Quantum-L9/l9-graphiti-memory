# Sequential PR Contracts and Operation Handoffs

## Publication discipline

One bounded implementation PR at a time. Each code PR: freeze exact source, invoke canonical Coding Agent binding, run tests, publish through `make pr`, independently audit exact head, remediate same PR, then merge only with operator authority. `P12` is not a code PR. `C784` is the existing cross-repository consumer PR.

| Slice | Scope | Nodes | Prerequisites | Publication |
|---|---|---:|---|---|
| P00 | Architecture decision, source/authority inventory | 10 | none | Separate architecture PR |
| P01 | Canonical data integrity and sensitive admission | 6 | P00 | New bounded PR |
| P02 | Auth0 OAuth resource server and Postgres security | 15 | P00 | New bounded PR |
| P03 | Native MCP wire/runtime and client behavior | 9 | P00, P02 | New bounded PR |
| P04 | Complete evidence-bound identity and operator authority | 7 | P00, P02 | New bounded PR |
| P05 | Graphiti provider error transport | 8 | P00 | New bounded PR |
| P06 | Lifecycle capability, lease and deletion correctness | 14 | P00, P01, P02, P05 | New bounded PR |
| P07 | Reference-safe retention and adapter parity | 9 | P00, P02, P03, P06 | New bounded PR |
| P08 | Provider qualification and remaining safety defects | 8 | P00, P03, P05, P06, P07 | New bounded PR |
| P09 | Remove obsolete compatibility routes and docs | 11 | P00, P01, P02, P03, P04 | New bounded PR |
| P10 | Retarget PR #101 and prove source-owned OCI carrier | 14 | P00, P01, P02, P03, P04, P06, P09 | Amend existing open PR #101, not a parallel carrier PR |
| C784 | Consumer PR #784 native OAuth/identity handoff | 11 | P00, P02, P03, P04, P09, P10 | Amend existing open PR #784 in separate repo |
| P12 | Independent assurance, authorized release and C1 cutover | 21 | P00, P03, P06, P07, P08, P10, C784 | Operation/acceptance stage, NOT a coding PR |

**Upstream external proof:** Auth0 tenant `resource`->`audience`, PKCE client registration and real hosted connector behavior must be tested, not inferred from docs. The issuer is selected, not yet operationally accepted.

## P00. Architecture decision, source/authority inventory
**Owner:** Memory proposal; new ADR supersession  |  **Nature:** Separate architecture PR  |  **Status:** not_dispatched
**Prerequisite slices:** none

**Scope:** Record full no-compatibility decision, source epochs and release blockers
**Acceptance:** ADR/registry version and plan coverage, no arbitrary authority mutation
**Rollback/failure:** No operational rollback, architecture proposal stays versioned
**Nodes:** GOV-01, GOV-02, GOV-03, GOV-04, GOV-05, GOV-06, GOV-07, GOV-08, GOV-09, QA-01
**Finding coverage:** cross-cutting

**Implementation contract minimum:** Exact file/source slice, no extra architectural changes, tests for each node, validator evidence receipt, reviewer feedback revision loop, no merge/deploy implied.

## P01. Canonical data integrity and sensitive admission
**Owner:** Memory  |  **Nature:** New bounded PR  |  **Status:** not_dispatched
**Prerequisite slices:** P00

**Scope:** F-010/F-012/U-012, explicit evidence and privacy-safe normalization
**Acceptance:** Unit/integration privacy negative suite and no silent data loss
**Rollback/failure:** Disable sensitive writes until proven, preserve canonical data
**Nodes:** DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06
**Finding coverage:** F-010, F-012, U-012

**Implementation contract minimum:** Exact file/source slice, no extra architectural changes, tests for each node, validator evidence receipt, reviewer feedback revision loop, no merge/deploy implied.

## P02. Auth0 OAuth resource server and Postgres security
**Owner:** Memory  |  **Nature:** New bounded PR  |  **Status:** not_dispatched
**Prerequisite slices:** P00

**Scope:** RFC9728/Auth0 discovery, JWT, scopes, grants, rotation, PG backend
**Acceptance:** Auth0 audience + PKCE integration and Postgres tenant denials
**Rollback/failure:** Do not enable public service, refuse authentication if issuer fails
**Nodes:** AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06, AUTH-07, AUTH-08, AUTH-14, AUTH-17, STOR-01, STOR-06, STOR-07, STOR-08, STOR-09
**Finding coverage:** U-005, U-008, U-010, U-011

**Implementation contract minimum:** Exact file/source slice, no extra architectural changes, tests for each node, validator evidence receipt, reviewer feedback revision loop, no merge/deploy implied.

## P03. Native MCP wire/runtime and client behavior
**Owner:** Memory  |  **Nature:** New bounded PR  |  **Status:** not_dispatched
**Prerequisite slices:** P00, P02

**Scope:** MCP SDK or proven protocol, handler errors, offload, SDK clients
**Acceptance:** Real installed wheel OAuth/PG MCP protocol and readiness concurrency
**Rollback/failure:** Stay disabled for remote writes until protocol validation
**Nodes:** MCP-01, MCP-02, MCP-04, MCP-05, MCP-06, MCP-07, MCP-08, MCP-09, MCP-12
**Finding coverage:** F-001, F-003, F-004, F-015

**Implementation contract minimum:** Exact file/source slice, no extra architectural changes, tests for each node, validator evidence receipt, reviewer feedback revision loop, no merge/deploy implied.

## P04. Complete evidence-bound identity and operator authority
**Owner:** Memory  |  **Nature:** New bounded PR  |  **Status:** not_dispatched
**Prerequisite slices:** P00, P02

**Scope:** Product/Release/Runtime/Actor/Surface, non-applicable Constellation, admin boundary
**Acceptance:** Identity negative suite with Unknown and cryptographic provenance
**Rollback/failure:** Fail closed on author attribution, do not downgrade trust
**Nodes:** AUTH-09, AUTH-10, AUTH-11, AUTH-12, AUTH-13, AUTH-16, DATA-07
**Finding coverage:** U-005, U-010

**Implementation contract minimum:** Exact file/source slice, no extra architectural changes, tests for each node, validator evidence receipt, reviewer feedback revision loop, no merge/deploy implied.

## P05. Graphiti provider error transport
**Owner:** Memory  |  **Nature:** New bounded PR  |  **Status:** not_dispatched
**Prerequisite slices:** P00

**Scope:** F-001/F-002/F-019/U-002, strict tool error and breaker
**Acceptance:** Fake isError, breaker half-open, no phantom link tests
**Rollback/failure:** Disable Graphiti projection if uncertain
**Nodes:** PROJ-01, PROJ-02, PROJ-03, PROJ-04, PROJ-05, PROJ-06, PROJ-07, PROJ-08
**Finding coverage:** F-001, F-002, F-019, U-002

**Implementation contract minimum:** Exact file/source slice, no extra architectural changes, tests for each node, validator evidence receipt, reviewer feedback revision loop, no merge/deploy implied.

## P06. Lifecycle capability, lease and deletion correctness
**Owner:** Memory  |  **Nature:** New bounded PR  |  **Status:** not_dispatched
**Prerequisite slices:** P00, P01, P02, P05

**Scope:** F-008/F-009/U-001/U-004/U-013, atomic canonical commits
**Acceptance:** Postgres two-worker crash/lease/deletion/supersession suite
**Rollback/failure:** Pause projection worker and preserve pending obligations
**Nodes:** PROJ-09, LIFE-01, LIFE-02, LIFE-03, LIFE-04, LIFE-05, LIFE-06, LIFE-07, LIFE-08, LIFE-09, LIFE-10, LIFE-11, LIFE-12, STOR-02
**Finding coverage:** F-008, F-009, U-001, U-004, U-013

**Implementation contract minimum:** Exact file/source slice, no extra architectural changes, tests for each node, validator evidence receipt, reviewer feedback revision loop, no merge/deploy implied.

## P07. Reference-safe retention and adapter parity
**Owner:** Memory  |  **Nature:** New bounded PR  |  **Status:** not_dispatched
**Prerequisite slices:** P00, P02, P03, P06

**Scope:** F-013/F-015/F-018 and maintenance correctness
**Acceptance:** Postgres full incoming refs and planner regression
**Rollback/failure:** Disable apply-mode retention if unproven
**Nodes:** DATA-09, DATA-10, RET-01, RET-02, RET-03, RET-04, RET-05, RET-06, STOR-05
**Finding coverage:** F-013, F-015, F-018

**Implementation contract minimum:** Exact file/source slice, no extra architectural changes, tests for each node, validator evidence receipt, reviewer feedback revision loop, no merge/deploy implied.

## P08. Provider qualification and remaining safety defects
**Owner:** Memory  |  **Nature:** New bounded PR  |  **Status:** not_dispatched
**Prerequisite slices:** P00, P03, P05, P06, P07

**Scope:** Graphiti live qualification, Zep retire/qualify, F-011/F-020
**Acceptance:** Live disposable provider, Shell guard, teardown receipts
**Rollback/failure:** Do not activate unqualified provider or command guard bypass
**Nodes:** DATA-08, PROJ-10, PROJ-11, PROJ-12, PROJ-13, HYG-01, HYG-03, QA-07
**Finding coverage:** F-001, F-003, F-011, F-014, F-017, F-019, F-020, U-001, U-002

**Implementation contract minimum:** Exact file/source slice, no extra architectural changes, tests for each node, validator evidence receipt, reviewer feedback revision loop, no merge/deploy implied.

## P09. Remove obsolete compatibility routes and docs
**Owner:** Memory  |  **Nature:** New bounded PR  |  **Status:** not_dispatched
**Prerequisite slices:** P00, P01, P02, P03, P04

**Scope:** No Memory stdio, signed-agent, static bearer, SQLite-serving, old queue
**Acceptance:** AST reachability scanner and active docs/test contracts
**Rollback/failure:** Do not reopen old transport, rollback is new image with PG
**Nodes:** GOV-10, GOV-11, AUTH-15, MCP-03, MCP-10, MCP-11, STOR-03, STOR-04, HYG-02, QA-03, QA-04
**Finding coverage:** F-005, F-006, F-007, F-016

**Implementation contract minimum:** Exact file/source slice, no extra architectural changes, tests for each node, validator evidence receipt, reviewer feedback revision loop, no merge/deploy implied.

## P10. Retarget PR #101 and prove source-owned OCI carrier
**Owner:** Memory PR #101  |  **Nature:** Amend existing open PR #101, not a parallel carrier PR  |  **Status:** not_dispatched
**Prerequisite slices:** P00, P01, P02, P03, P04, P06, P09

**Scope:** OAuth-only C1 deployment profile, pinned OCI, PostgreSQL/Infisical/staging
**Acceptance:** Exact-head release gate, temporary staging, no C1 mutation yet
**Rollback/failure:** Do not merge/deploy if signed-only guard remains
**Nodes:** OPS-01, OPS-02, OPS-03, OPS-04, OPS-05, OPS-06, OPS-07, OPS-08, OPS-09, OPS-10, OPS-11, QA-09, QA-12, CUT-01
**Finding coverage:** cross-cutting

**Implementation contract minimum:** Exact file/source slice, no extra architectural changes, tests for each node, validator evidence receipt, reviewer feedback revision loop, no merge/deploy implied.

## C784. Consumer PR #784 native OAuth/identity handoff
**Owner:** Cursor-Governance PR #784  |  **Nature:** Amend existing open PR #784 in separate repo  |  **Status:** not_dispatched
**Prerequisite slices:** P00, P02, P03, P04, P09, P10

**Scope:** Claude/Cursor native OAuth, projection binding, no stdio bridge
**Acceptance:** Real clients and surface uncertainty evidence, strict drift checks
**Rollback/failure:** No client cutover before issuer and server proof
**Nodes:** CONS-01, CONS-02, CONS-03, CONS-04, CONS-05, CONS-06, CONS-07, CONS-08, CONS-09, CONS-10, QA-08
**Finding coverage:** cross-cutting

**Implementation contract minimum:** Exact file/source slice, no extra architectural changes, tests for each node, validator evidence receipt, reviewer feedback revision loop, no merge/deploy implied.

## P12. Independent assurance, authorized release and C1 cutover
**Owner:** l9-deploy + operator  |  **Nature:** Operation/acceptance stage, NOT a coding PR  |  **Status:** not_dispatched
**Prerequisite slices:** P00, P03, P06, P07, P08, P10, C784

**Scope:** Independent audit, exact release, staging, hosted two-client, rollback, old retirement
**Acceptance:** Full hosted and audit receipts for separate milestones
**Rollback/failure:** Stop/redeploy forward-compatible OAuth image; keep PG backup
**Nodes:** GOV-12, PROJ-14, QA-02, QA-05, QA-06, QA-10, QA-11, CUT-02, CUT-03, CUT-04, CUT-05, CUT-06, CUT-07, CUT-08, CUT-09, CUT-10, CUT-11, CUT-12, CUT-13, CUT-14, CUT-15
**Finding coverage:** cross-cutting

**Implementation contract minimum:** Exact file/source slice, no extra architectural changes, tests for each node, validator evidence receipt, reviewer feedback revision loop, no merge/deploy implied.

## Cross-PR collision and admission rules

Do not mutate PR #101 in parallel with unmerged root server contracts. Its signed-agent-only Dockerfile/profile is incompatible with OAuth full cutover and must be updated in the same PR after upstream semantics converge. Do not merge PR #784 as a completed consumer merely because local native HTTP config tests pass: real Auth0 and account-managed Claude Code Mobile tool availability are independent acceptance gates.

Only operator-designated release/deploy owner may cut over C1. Protected C1 neighbor services and old-backup attestation remain unchanged.
