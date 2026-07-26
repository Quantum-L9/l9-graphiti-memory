<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/repository-review/authority-map.md
layer: repository_review
owner: memory-control-plane
status: active
version: 2.2.0
pinned_sha: 16d5305c0124d85bf06b719c5bac4c516bfe9085
generated: 2026-07-26
generated_by: Manus AI repository review
/L9_META -->

# Authority Map

This map records which artifact governs each concern at pinned SHA `16d5305c0124d85bf06b719c5bac4c516bfe9085`, and the enforcement mechanism that makes the authority executable rather than aspirational.

## A. Authority hierarchy

1. **Accepted ADRs are contract law.** `docs/adr/README.md` states: "Accepted ADRs are contract law for this repository. A code change that crosses an ADR boundary must update the ADR, tests, migration notes, and validation evidence in the same pull request." All 62 ADRs are status Accepted; superseding decisions create a new ADR rather than rewriting an existing one.
2. **Executable contracts and the harvest coverage ledger rank with ADRs.** `skill/SKILL.md` directs agents to "treat accepted ADRs, `docs/harvest_coverage.yaml`, and executable contracts as authority."
3. **The cryptographic manifest binds the inventory.** `manifest.json` hashes 286 inventory files; `MANIFEST.md` carries per-file SHA-256 digests; `tools/assurance/validate_manifest.py` fails on mismatch. Every packaged file carries `L9_META` inline or through the manifest (ADR-062).
4. **Documentation narratives (README, ARCHITECTURE, RUNBOOK) are derivative** and must agree with the ADR ledger; `tools/assurance/check_recursive_alignment.py` and the regression suite enforce agreement.

## B. Concern-to-authority table

| Concern | Authoritative artifact | Enforcement |
|---|---|---|
| Repository role and scope boundary | ADR-001; `ALIGNMENT.md` | `check_layer_boundaries.py`; `tests/regression/test_recursive_alignment.py` |
| Canonical write path | ADR-002, ADR-036; `services/memory_service.py` | `check_memory_write_bypass.py` (zero findings, `validation/logs/bypass_check.txt`) |
| Memory taxonomy and record schema | ADR-003, ADR-035; `contracts/`, `schema/registry.py`, `resources/memory_contract.yaml` | `tests/unit/test_contracts.py`, `test_schema_registry.py` |
| Temporal semantics | ADR-004, ADR-029; `contracts/temporal.py` | integration tests on bi-temporal queries |
| Principal identity and namespace authority | ADR-006, ADR-030; `authz/` | `tests/unit/test_authz.py`, `test_server_principal.py`; remote namespaces intersected with server-derived claims |
| Admission, quarantine, idempotency, supersession | ADR-007, ADR-008; `admission/` | unique-index and replay tests; supersession history tests |
| Canonical state ownership | ADR-025; `ports/record_store.py` | `tests/conformance/test_store_contract.py` |
| Constellation packet boundary | ADR-026, ADR-060; `integrations/constellation.py` (`GateMemoryBridge`) | `tests/unit/test_constellation_bridge.py`; bridge holds no destination/peer/registry data; Gate alone resolves destination |
| Local receipt guard boundary | ADR-061; `memory_guard.py`, `hooks/` | `tests/unit/test_gate.py`; guard performs no network I/O, routing, admission, or orchestration |
| Secrets and credentials | ADR-016; `secrets.py`, `SECURITY.md` | `check_secrets.py` and `check_config_drift.py`; generated MCP configs persist no tokens |
| Privacy, consent, verified deletion | ADR-024, ADR-049, ADR-057 | `tests/integration/test_privacy_deletion.py`; locator-verified projection erasure |
| Retrieval planning and ranking | ADR-039, ADR-040, ADR-044, ADR-054; `retrieval/` | `tests/unit/test_projection_strategies.py`, `test_query_classifier.py` |
| Promotion and procedural synthesis | ADR-009, ADR-045, ADR-052; `curation/` | `tests/integration/test_procedural_synthesis.py`; candidates are never auto-applied |
| Outbox and write recovery | ADR-018, ADR-055; `services/outbox_worker.py`, `recovery/write_queue.py` | `tests/integration/test_outbox.py`, `test_write_recovery.py` |
| Configuration authority and drift | ADR-037; `config/memory.yaml.example`, `resources/defaults.yaml` | `check_config_drift.py` (zero findings, `validation/logs/config_drift.txt`) |
| Package wiring and public API | ADR-043; `pyproject.toml` entry points | `audit_package_wiring.py` (86 modules, zero unexplained orphans) |
| Compatibility surface | ADR-023, ADR-058; `docs/COMPATIBILITY_MATRIX.md`, `MIGRATION.md` | regression tests; legacy MCP aliases remain thin adapters |
| Harvest closure | ADR-033, ADR-056; `docs/harvest_coverage.yaml`, `docs/HARVEST_MAP.md` | `validate_harvest_coverage.py` (PASS, 44 decisions) |
| File provenance | ADR-062; `manifest.json`, L9_META headers | `check_l9_meta.py`, `apply_l9_meta.py` |
| Release evidence | `VALIDATION.md`, `validation/validation_report.yaml` | `generate_validation_evidence.py` exits nonzero on missing or mismatched evidence |

## C. Authority that is intentionally external

1. The canonical **TransportPacket model and Gate client are owned outside this repository** and injected at integration time. The package never defines the shared packet model or resolves destinations (`ALIGNMENT.md` binding boundaries 2–4; ADR-026).
2. **Production release authority** is withheld: `MANIFEST.md` records local outcome `PASS` and production outcome `BLOCKED_ON_EXTERNAL_VALIDATION`; the final release decision belongs to the RP-009 evidence review (`docs/ISSUE_INDEX.md`).
3. Live provider credentials (Graphiti, Zep), hosted CI controls, and secret-rotation proof reside in external environments (RP-004, RP-005, RP-007, RP-008).

## D. Non-authorities (explicitly subordinated)

1. Graph and semantic providers cannot create canonical records, grant authority, or define lifecycle state — they are rebuildable projections (ADR-025).
2. Historical gate-named hook files are compatibility wrappers only; the local guard is not constellation Gate (ADR-061).
3. Legacy source packs listed in `docs/HARVEST_MAP.md` "contribute concepts and failure knowledge, not authority over the final dependency graph."
