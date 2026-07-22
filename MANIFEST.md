<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: MANIFEST.md
layer: repository_root
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Manifest

## Identity

- Repository: `Quantum-L9/l9-graphiti-memory`
- Release: `2.2.0`
- Artifact class: dependency package with optional service and constellation adapters
- Local validation outcome: `PASS`
- Production release outcome: `BLOCKED_ON_EXTERNAL_VALIDATION`

## Responsibility map

| Plane | Owner paths |
|---|---|
| contracts and temporal law | `src/l9_graphite_memory/contracts/`, `schema/` |
| canonical memory control | `services/memory_service.py`, `admission/`, `authz/` |
| storage and projections | `ports/`, `adapters/`, `services/outbox_worker.py` |
| constellation boundary | `ports/constellation.py`, `integrations/constellation.py` |
| local receipt guard | `memory_guard.py`, compatibility hooks |
| assurance | `tools/assurance/`, `tests/`, `validation/` |

## Inventory summary

| Category | Files |
|---|---:|
| `architecture_decisions` | 63 |
| `assurance` | 15 |
| `ci` | 3 |
| `configuration` | 9 |
| `documentation` | 7 |
| `hooks` | 9 |
| `operations` | 7 |
| `production_source` | 89 |
| `repository_root` | 20 |
| `skill` | 2 |
| `tests` | 34 |
| `validation_evidence` | 28 |

- Hashed inventory files below: **286**
- `MANIFEST.md` is hashed by `manifest.json`.
- `manifest.json` excludes its own digest to avoid self-reference.
- Every manifest entry carries canonical `l9_meta`, including non-commentable files.

## File inventory

| Path | Category | Layer | Bytes | SHA-256 |
|---|---|---|---:|---|
| `.github/workflows/ci.yml` | `ci` | `ci` | 964 | `d366e14b0d6e605958cc0a2f5ae59eca47810dcbc168cc8a08777ab5b3c462b5` |
| `.github/workflows/codeql.yml` | `ci` | `ci` | 589 | `5366c6d30a7c4b66b898ae32737c99d7520351f1d9196079d1ab7ac13e5c33bf` |
| `.github/workflows/publish.yml` | `ci` | `ci` | 1131 | `fc0c1d03146e25d7ddf704c8d7b434a6ff1491d06ed7862c8ff591238f8638ff` |
| `.gitignore` | `repository_root` | `repository_root` | 859 | `5742eda9df58ea637c68e20e6fb7897c70c010795171f867acdcf01dcd80d670` |
| `AGENTS.md` | `repository_root` | `repository_root` | 1100 | `e5eddd9d67c1514b9794c64b14df4e9638ed379d0028d08f73d77f08fd7c465b` |
| `ALIGNMENT.md` | `repository_root` | `repository_root` | 1528 | `f8d7a877a2cb4cc6bfa9be1b1c335dd3da657a8dab96f9953146fc8c8e5092e2` |
| `ARCHITECTURE.md` | `repository_root` | `repository_root` | 7164 | `e50a1d7fe1081241b14fac9d2aa4e5e2ac80e6b080573a0807f4f9f4212a4238` |
| `CHANGE_SUMMARY.md` | `repository_root` | `repository_root` | 2213 | `cde3be8fe41714379bb3c92a683533a2bc874b8425a47143695315cf456b6de9` |
| `CONTRIBUTING.md` | `repository_root` | `repository_root` | 666 | `052f310924cad01f2f4735d476f54b1b75058b15249bc2ad0b4a42d467acaf67` |
| `CONVERGENCE_REPORT.yaml` | `repository_root` | `repository_root` | 2369 | `1b049f9264b7fa1ffbbf65ee663c10ccad1a3ed15b9bd1d457e1965baf66bc49` |
| `DELTA_REPORT.md` | `repository_root` | `repository_root` | 2642 | `6a387ff4ea95b5cc034deed28cc3cc8255c85595d07364842c19b347df579b22` |
| `IMPROVEMENT_REPORT.md` | `repository_root` | `repository_root` | 3181 | `351078f7327e2579509baec85a809b9a636f02636cc76612f0f598d33d4b9876` |
| `LICENSE` | `repository_root` | `repository_root` | 1067 | `01a08e5ca5f089101e81b14770940654805667c8ccbac9fa50429e20500af2a3` |
| `MANIFEST.in` | `repository_root` | `repository_root` | 624 | `0b09fe70fcf48900117c6dfd3a56a4037d93e3b1c50f2dad9cfa1e5286b54986` |
| `MIGRATION.md` | `repository_root` | `repository_root` | 3306 | `07f086cc8f907cc98ac550198bfd65f25038e566abc77f755b7d0ea36688fc49` |
| `QUICKSTART.md` | `repository_root` | `repository_root` | 1211 | `4e24f79cb5bf490fa7aec8e9a8cac13bb71811fc0d83d8d172ac953bad8dd4d6` |
| `README.md` | `repository_root` | `repository_root` | 5642 | `df770b5339da5d75f4bdc334e9de0aba0917186a7abf8d74ce503238964e3f09` |
| `ROADMAP.md` | `repository_root` | `repository_root` | 1792 | `ef2025bcb715218def4ae73c151fd7b6178480b1e4824016b280b443464860cd` |
| `RUNBOOK.md` | `repository_root` | `repository_root` | 6834 | `cad9ad8d19b1c4be2de687e85728c37a22a6eee7630a2845bb37772d7d6ee9a3` |
| `SECURITY.md` | `repository_root` | `repository_root` | 1718 | `8eb44c129daf83b389343dcf462662b6c6282a63cac6048cf084e10d2b964980` |
| `VALIDATION.md` | `repository_root` | `repository_root` | 5609 | `b0f456968bcfcc105e1c4386ec13c98254c7048ba9791a3f80c0772abcde327d` |
| `config/auth_tokens.json.example` | `configuration` | `configuration` | 405 | `7e2e9993115d39c1c1df3d45ce781fa157646a09c40de6cd737910bc5864d357` |
| `config/group_registry.yaml` | `configuration` | `configuration` | 1319 | `5ea0bc2e12ae50fe624d597f6ad808e09546f9b6cd6fc5c5cc9631b633662fec` |
| `config/mcp.json.example` | `configuration` | `configuration` | 162 | `3e755f7a79643d9900569b3cf82d8f58d264300540bceeb1426090a69e26915f` |
| `config/memory.yaml.example` | `configuration` | `configuration` | 1015 | `c4bbb5d9962c51dc1229cec65fe44ff54f07996540696ccc28d94c76fbe36303` |
| `docs/COMPATIBILITY_MATRIX.md` | `documentation` | `documentation` | 2490 | `8b9981ff9e7fab2d503365c7076701696b8187360145e3245712e482dabcc1ed` |
| `docs/HARVEST_MAP.md` | `documentation` | `documentation` | 2774 | `4904b15f0558b79cfd8f113a505d0d7a2f0ac50b9df46ea14859a2f9a525c205` |
| `docs/RECURSIVE_ALIGNMENT_UPDATE.md` | `documentation` | `documentation` | 10282 | `fe92a728d492b85be1349390137861c50a4c561d391d28bf0e3e78644ade9700` |
| `docs/RECURSIVE_HARVEST_AUDIT.md` | `documentation` | `documentation` | 4921 | `370cb913d5117345bd2355672c86115d1d4f6b875539e3cdd0e30aa55de1b393` |
| `docs/REMEDIATION_AND_INTEGRATION_PLAN.md` | `documentation` | `documentation` | 6077 | `b5f0314090e0c3f19d10e5c27690eb7f1bcd9bfb27407f3e32b65833c9bb66b3` |
| `docs/adr/ADR-001-repository-role-and-boundaries.md` | `architecture_decisions` | `architecture_decisions` | 2921 | `505219a9232c0d278f0f75af6cfa625c65443c0b3a75bae4e4191b0d3c58d33e` |
| `docs/adr/ADR-002-canonical-memory-service.md` | `architecture_decisions` | `architecture_decisions` | 2679 | `f11c9bf1748ebfa33be92f586daec4dc02dca1f219a594fe3cd61e69d8bf94b1` |
| `docs/adr/ADR-003-memory-contract-and-taxonomy.md` | `architecture_decisions` | `architecture_decisions` | 2609 | `8469a8f4d211052e7562ae857286e214033a0d9c9e1b5ad1e5ddb467053dabb5` |
| `docs/adr/ADR-004-bi-temporal-semantics.md` | `architecture_decisions` | `architecture_decisions` | 2594 | `6597814d5f6ec555f3ab412c3b4ba2b22a1c7567d7cf8f106b9429238909dabb` |
| `docs/adr/ADR-005-provenance-and-evidence.md` | `architecture_decisions` | `architecture_decisions` | 2552 | `7d82da860edc9617cf0b21d1d8f15f1766e7417193f3557b247c4b6d02ca28d9` |
| `docs/adr/ADR-006-namespace-authorization.md` | `architecture_decisions` | `architecture_decisions` | 2784 | `26877e8cfebffdcc1dd9462852c1d405c6458c6977d378713e20c77b6083d000` |
| `docs/adr/ADR-007-admission-and-quarantine.md` | `architecture_decisions` | `architecture_decisions` | 2611 | `fa177704c43e8b5d00e227cffb5922aa71c5bce937d9d6eada702b28b58b5dcc` |
| `docs/adr/ADR-008-idempotency-deduplication-and-supersession.md` | `architecture_decisions` | `architecture_decisions` | 2540 | `38d7d206946c228cf9e1d5064f9824c73e035677fe07304d57fffc73be3cbf45` |
| `docs/adr/ADR-009-memory-promotion-and-curation.md` | `architecture_decisions` | `architecture_decisions` | 2581 | `ff60c5235c8239ae0161fa9475a4f30a5259fce6f27b872fa3ebc8caf4acb462` |
| `docs/adr/ADR-010-retention-decay-and-pruning.md` | `architecture_decisions` | `architecture_decisions` | 2488 | `14e0f4e4a3e929aff48d50d1dde43c7dc2403096d62040105c81ad63d7dee5f4` |
| `docs/adr/ADR-011-hydration-and-context-budgeting.md` | `architecture_decisions` | `architecture_decisions` | 2581 | `c06fab2952b03ba3e1e1f3cdfefcaf68452911884fbba76ab7a756dd9439fa69` |
| `docs/adr/ADR-012-hybrid-retrieval-strategy.md` | `architecture_decisions` | `architecture_decisions` | 2536 | `d9e4fa6fe78a43ab35f778ea417bc6c3a458f2348798e0763340ad19d90cb9a3` |
| `docs/adr/ADR-013-transport-abstraction-and-vendor-neutrality.md` | `architecture_decisions` | `architecture_decisions` | 3087 | `01d3f3bdb18a0d2642e59efdd8e3b3cef809879bbddfe0405d19aae85839844a` |
| `docs/adr/ADR-014-mcp-tool-contracts.md` | `architecture_decisions` | `architecture_decisions` | 2697 | `bcb3313838433e3c04f67e078ad683632f95490bde25617c6810be579951a955` |
| `docs/adr/ADR-015-failure-and-degradation-policy.md` | `architecture_decisions` | `architecture_decisions` | 2600 | `b9e59641d47ba59aa8f6160f1c551d13f3f43c637de287d45f089acd81026ac6` |
| `docs/adr/ADR-016-secret-and-credential-boundaries.md` | `architecture_decisions` | `architecture_decisions` | 2574 | `bf0ec54cc55abd7616d0c998d99be6eeb439d6348e4843df9d42a00874ebc196` |
| `docs/adr/ADR-017-hook-and-agent-integration.md` | `architecture_decisions` | `architecture_decisions` | 2587 | `c39e99ce86fc8920938a5d9ba4759647e71f3234a1d80bb4cca9f1efe1a34c80` |
| `docs/adr/ADR-018-outbox-and-write-recovery.md` | `architecture_decisions` | `architecture_decisions` | 2442 | `e72ed0af2ff5873b410bd1c9b05bc30083d2629ee7c6f40da901abd1f547ad5b` |
| `docs/adr/ADR-019-observability-and-evidence-receipts.md` | `architecture_decisions` | `architecture_decisions` | 2492 | `7485d3f8a634c3ff131fc4784af0eb64cda067f7fd1eb97d5b06e5b2ec1897c3` |
| `docs/adr/ADR-020-package-and-configuration-layout.md` | `architecture_decisions` | `architecture_decisions` | 2528 | `8a821e0b4218496fbe674c628e0f58848c25fffbd890d6c0c9ec73204af46be0` |
| `docs/adr/ADR-021-testing-and-adapter-conformance.md` | `architecture_decisions` | `architecture_decisions` | 2536 | `6158264313f83fc1cc1c3fd11e738b3c11fd3f6fc3ea418839ddb3b7b77468f5` |
| `docs/adr/ADR-022-release-publishing-and-rollback.md` | `architecture_decisions` | `architecture_decisions` | 2514 | `b9ab332121590baebfc30c97ece6b57a9b797c3a524437efd01f9a27474c402e` |
| `docs/adr/ADR-023-legacy-migration-and-compatibility.md` | `architecture_decisions` | `architecture_decisions` | 2533 | `d5aa2d88dc1ca4f65acaaa6ae9186c1ee4731e5563fd6536d5644953cc63cfad` |
| `docs/adr/ADR-024-memory-privacy-consent-and-deletion.md` | `architecture_decisions` | `architecture_decisions` | 2582 | `dd31fb8a37a419235f9be2c6dbc54edefe336e4084c038ae3436da73a11987d4` |
| `docs/adr/ADR-025-storage-source-of-truth-and-backend-partitioning.md` | `architecture_decisions` | `architecture_decisions` | 2447 | `eaa46c6f11aa49164e8bd9e66db144865b05a8849cbf884137b2da69fa4ea637` |
| `docs/adr/ADR-026-transportpacket-constellation-boundary.md` | `architecture_decisions` | `architecture_decisions` | 2713 | `d941260435f5d466081f4dc994b9c6028a99f1718c59e2b950f1117428ddd8d6` |
| `docs/adr/ADR-027-semantic-episodic-and-meta-memory-ownership.md` | `architecture_decisions` | `architecture_decisions` | 2555 | `164ab339a4eff053ed11aec96b8bac586bd44c1bbbf1f2285875ec49146353d8` |
| `docs/adr/ADR-028-agent-checkpointing-boundary.md` | `architecture_decisions` | `architecture_decisions` | 2468 | `62775577955c8b56e145fd4a9d149b062078778f50014ac0267738d8bf179c5b` |
| `docs/adr/ADR-029-temporal-coordinate-model.md` | `architecture_decisions` | `architecture_decisions` | 2447 | `b65ca16a4cbb78ba7fb85a7ef2555fd7e181b28fa843f08c029f1a97fa4a90f5` |
| `docs/adr/ADR-030-rls-and-transaction-scoped-authorization.md` | `architecture_decisions` | `architecture_decisions` | 2634 | `4a87bd60746cba2c919a9149d9a9e9f640d448644f03eabbb391c0afe7889061` |
| `docs/adr/ADR-031-reasoning-lineage-versus-private-reasoning.md` | `architecture_decisions` | `architecture_decisions` | 2573 | `365800eac76ced98406d1f49646b2bbdbd6facba9a1c51fb6c6c0dd93608b730` |
| `docs/adr/ADR-032-performance-slos-and-partial-result-policy.md` | `architecture_decisions` | `architecture_decisions` | 2641 | `95635771a0262bf95d2f3443e41c40746a7d71be82c5e841c3fa2842744df517` |
| `docs/adr/ADR-033-legacy-monolith-harvest-and-rejection-record.md` | `architecture_decisions` | `architecture_decisions` | 2488 | `0bbb217342b523248cfa3aae4ac83d8f51da6e256e436e6c0bed69c51ffe426b` |
| `docs/adr/ADR-034-private-data-fixtures-and-repository-hygiene.md` | `architecture_decisions` | `architecture_decisions` | 2458 | `b788816ce4d30e21732d1336ce5a6a0d651aed66e28cfcade7c34b5df30ef605` |
| `docs/adr/ADR-035-schema-registry-and-upcasting.md` | `architecture_decisions` | `architecture_decisions` | 2465 | `8160ce21e2ce5625040f6c20bc7cbd8f6c10a266c1f0d7d1517994ef82e3c9d2` |
| `docs/adr/ADR-036-canonical-write-bypass-enforcement.md` | `architecture_decisions` | `architecture_decisions` | 2448 | `e122fbad59ce1b455501cbb9e4c5c94c0f84d74f0d9cb3fed2cf9952f08270a6` |
| `docs/adr/ADR-037-configuration-authority-and-drift-prevention.md` | `architecture_decisions` | `architecture_decisions` | 2450 | `5752b8e3ba24f7b72bd5f3061a24da2bdf2e44a18f014ddda155238082371131` |
| `docs/adr/ADR-038-sdk-mcp-cli-and-http-surface.md` | `architecture_decisions` | `architecture_decisions` | 2668 | `d84fc7da7d0bdca5ab8f0cdb872072fae7fdff0796a72ba9cc85d098b87c877f` |
| `docs/adr/ADR-039-retrieval-planning-and-tier-fusion.md` | `architecture_decisions` | `architecture_decisions` | 2662 | `62892754f8b4c437a83d71596afe36412f62a43adca70757fde5afb1e4ecc6a3` |
| `docs/adr/ADR-040-importance-ranking-and-decay-policy.md` | `architecture_decisions` | `architecture_decisions` | 2509 | `df6457b8fa6bb65f3a8239a998c79e8926c18ee10f5cf5de448a14e585d81405` |
| `docs/adr/ADR-041-llm-extraction-and-typed-failure-semantics.md` | `architecture_decisions` | `architecture_decisions` | 2653 | `97764420b9fdebb25864920fb392b4a137fa3132b6293dcda662c39f5b2fd694` |
| `docs/adr/ADR-042-offline-source-ingestion.md` | `architecture_decisions` | `architecture_decisions` | 2470 | `22275842816a0857b41a3dc263eb02e4d97b74c97a3d51dd02cdd48de33a3140` |
| `docs/adr/ADR-043-package-wiring-and-public-api-governance.md` | `architecture_decisions` | `architecture_decisions` | 2416 | `b58afe63ec3bad3cdd9394ad869276021ae469a3bbc841df8be3d3b5fafde8c1` |
| `docs/adr/ADR-044-authority-trust-confidence-and-relevance-separation.md` | `architecture_decisions` | `architecture_decisions` | 2505 | `77627076f1b61c79c85168e1d65d889a9c4cf1ea4a0913b20160ec97fcf0b453` |
| `docs/adr/ADR-045-procedural-synthesis-approval-boundary.md` | `architecture_decisions` | `architecture_decisions` | 2473 | `64b46843b047034df702a8914925f6be19384a63b9d2506db53546444fb3cf55` |
| `docs/adr/ADR-046-core-commit-versus-asynchronous-enrichment.md` | `architecture_decisions` | `architecture_decisions` | 2521 | `69c97e7a66ecdcc69f5fbb4dde56bd5781a8e2b951ce97e0014b1ea9ffb57a3c` |
| `docs/adr/ADR-047-schema-migration-and-legacy-record-compatibility.md` | `architecture_decisions` | `architecture_decisions` | 2556 | `921fb0f912cf4e056843090a3eeb501468920fce1ac31d2808013db97b060ba7` |
| `docs/adr/ADR-048-atomic-extraction-and-evidence-binding.md` | `architecture_decisions` | `architecture_decisions` | 2555 | `aec3c463c8ec19569d849a9c35567d5afeae4a1c56477cb99d9e95f3c96051e8` |
| `docs/adr/ADR-049-sensitive-profiles-and-purpose-bound-consent.md` | `architecture_decisions` | `architecture_decisions` | 2523 | `ae92389f1be1bb1337a496e2fafa3df6bb291b8dc39b4114b44ace08cbc8b251` |
| `docs/adr/ADR-050-phase-lock-snapshot-verification.md` | `architecture_decisions` | `architecture_decisions` | 2197 | `c47b32383693358228b01bf7970a966d5600090fbdd07719a89738e932d21409` |
| `docs/adr/ADR-051-explicit-references-and-lineage-replay.md` | `architecture_decisions` | `architecture_decisions` | 2276 | `5a53c832adcc7372c28188072e20b86a18a43568d19e1d02c39261862dd30299` |
| `docs/adr/ADR-052-procedural-synthesis-worker-and-approval-boundary.md` | `architecture_decisions` | `architecture_decisions` | 2314 | `957bcf626ecb3bc52b6d3edce8b50078c93f6488eaf2b42abdc8cb22a9ea5f6e` |
| `docs/adr/ADR-053-checkpoint-integrity-utility-boundary.md` | `architecture_decisions` | `architecture_decisions` | 2323 | `41488edcf641a07ad7ab070b29992aa6548b37f256a372db8a53c5743cf33b68` |
| `docs/adr/ADR-054-strategy-specific-hybrid-retrieval-receipts.md` | `architecture_decisions` | `architecture_decisions` | 2416 | `5e6813e92d91fe305758872b10e184f1ea0ed2a42fe2ebb7aaee82d552797d8d` |
| `docs/adr/ADR-055-canonical-ingress-write-recovery-queue.md` | `architecture_decisions` | `architecture_decisions` | 2232 | `aace73928ae3faa9720a80e350b753b8fbaa53e6d7793d868755df66c3ec8673` |
| `docs/adr/ADR-056-recursive-harvest-convergence.md` | `architecture_decisions` | `architecture_decisions` | 2327 | `b70d2fb0703de955ce6fb19686d99d539e789a54cb009fcf61dfe456b9361846` |
| `docs/adr/ADR-057-verified-deletion-and-projection-erasure.md` | `architecture_decisions` | `architecture_decisions` | 2829 | `d29908c1b2347c19a0569fc047b07571eeb1c98c64b72a0fe44367759a59f301` |
| `docs/adr/ADR-058-graphiti-repository-name-and-graphite-package-compatibility.md` | `architecture_decisions` | `architecture_decisions` | 2426 | `ccdd943109e2227f57ab419f54ff3d24a3ba0962d9d2100be0e16fc52612996b` |
| `docs/adr/ADR-059-recursive-alignment-authority-and-applicability.md` | `architecture_decisions` | `architecture_decisions` | 2801 | `ea13c320793122d1c4b4e242b6eb91a242c0cf15355e8bb325760036fae5292e` |
| `docs/adr/ADR-060-gate-only-constellation-dispatch.md` | `architecture_decisions` | `architecture_decisions` | 2294 | `221c3576df40f9694d579bd583e7ea102b5374ed53d21893b165eb29956a903d` |
| `docs/adr/ADR-061-local-receipt-guard-boundary.md` | `architecture_decisions` | `architecture_decisions` | 2306 | `96aac5780e63639a5d2999e1677443da8025d07ce1f36aaa6b3690418e098ab7` |
| `docs/adr/ADR-062-l9-meta-and-file-provenance.md` | `architecture_decisions` | `architecture_decisions` | 2076 | `fd4ec23e57b08a925736f5b60e77d9aff7ce296ace4e87e529750e45914c36fd` |
| `docs/adr/README.md` | `architecture_decisions` | `architecture_decisions` | 7915 | `a32f1655a3b75e1e1ec3eb02a738a39ea2a9c95e94bf59dda1dcfbc39409e39d` |
| `docs/alignment_report.yaml` | `documentation` | `documentation` | 3531 | `9479a76b0bf8e8757e2849ca089cba5f0c47d1fda61f2f75cde8b3ce28e6bd48` |
| `docs/harvest_coverage.yaml` | `documentation` | `documentation` | 20643 | `bb46aa4a43e3230c74e9ab7e282a6381d3fabdfc59bb3cb3fe7adeb4b1dc2060` |
| `hooks/graphiti-gate-edits.sh` | `hooks` | `hooks` | 358 | `29c1929141d3a27581a191b61021c197c5a2e30f6c47b3aa7574dccf388ac248` |
| `hooks/graphiti-gate-shell.sh` | `hooks` | `hooks` | 351 | `a0d160caeca8a0b2be539d9a012b31f2805954bb54741d41ae2f4927637e5385` |
| `hooks/graphiti-gate-subagent.sh` | `hooks` | `hooks` | 357 | `174d1642741954f70df6c8302aa21e8bd656fc22fd372ca9265feff6e7783ab2` |
| `hooks/graphiti-mark-ok.sh` | `hooks` | `hooks` | 2048 | `c30941535e114bf8cc8724f24aa8bfe65709df4e4dbd95151ce0846b556b9702` |
| `hooks/graphiti-prefetch.sh` | `hooks` | `hooks` | 760 | `23d24682ad3357c368f3b8e4cd528337c26cc7c8a55f4d1e1e5297987dc8a07e` |
| `hooks/graphiti-reset-generation.sh` | `hooks` | `hooks` | 453 | `022f034577ca3efa58852df51e8ef2a2f86a5e6e7ee729d5e41abe03b9634057` |
| `hooks/graphiti-session-end.sh` | `hooks` | `hooks` | 1591 | `78101e683885431565db87f8d81aef59cece7308f4d5045d86cef5fe9ff3d91a` |
| `hooks/graphiti_common.sh` | `hooks` | `hooks` | 1345 | `76ee5c40245b76f699fc5d6ec767a570da4b376ce9d61b59f5fa8e1ad7b3c71d` |
| `hooks/graphiti_gate_runner.sh` | `hooks` | `hooks` | 880 | `58203955f07dd049ed12c117f13405c7b651aa4f8d8df099a2e698d8a4e7174a` |
| `improvement_log.jsonl` | `repository_root` | `repository_root` | 2364 | `7a1b20557352284372622d9b11bc363a92b04286d61fecc2c4b2105f0280cab4` |
| `pyproject.toml` | `repository_root` | `repository_root` | 3128 | `cb8f29e90f3a208bc77b35b9c1a7a5d571234e2c4a575c1621e75ad6fd00c556` |
| `rules/03-graphiti-memory.mdc` | `configuration` | `configuration` | 603 | `20e03434589675053d739e5fa182eb650aaf821acf0cf757a913e60df7c879a6` |
| `rules/97-graph-engine-architecture.mdc` | `configuration` | `configuration` | 508 | `54defdb3c1813f10a6d102a94cf13b2979059db3ddfcc33d717bfc512ba72be8` |
| `rules/97-graph-layer-boundary.mdc` | `configuration` | `configuration` | 517 | `4ed80a718c926d7a87dad490e339c845a2efc2fa66af2ecdad7cf0c9dd5ffd24` |
| `rules/98-memory-receipt-guard.mdc` | `configuration` | `configuration` | 629 | `e9574ade26a2a38fdc2f1b6bf2613be00e6f906a0a9217c0e30531f413c09c09` |
| `rules/99-graphiti-temporal.mdc` | `configuration` | `configuration` | 436 | `349fb67ba2f191316fb1ebf7be7aeaecde3919a61af19bb507e8804f5688ef27` |
| `scripts/activate_gate.sh` | `operations` | `operations` | 461 | `3300ee59d612adaf379d07bc8b508bc2b8decb66bb680bc3ac5152e98a9d0340` |
| `scripts/activate_guard.sh` | `operations` | `operations` | 838 | `43c1cf62e97af8543a357547ac4bd87aacc6b62693d537596bad02b13a690491` |
| `scripts/install.sh` | `operations` | `operations` | 728 | `355df98cbde85f73aa78627afc3a4131cdf142271e1dbc410c929e41d0536d74` |
| `scripts/preflight.sh` | `operations` | `operations` | 3435 | `3c746e3cbd546e55d74f5b20f5912eeb083916df77c0cc5d92b599c8bf5eb18f` |
| `scripts/validate_release.sh` | `operations` | `operations` | 4848 | `27b16cfbd914b38664777412d828c9c29f7e789650e55273bb91e0ffb104b415` |
| `scripts/write_claude_config.py` | `operations` | `operations` | 2267 | `9d5a40dcf238e99aa5e72d0be72f8621aa687b908ef9185776f62ecd2f9fe5c6` |
| `scripts/write_cursor_config.py` | `operations` | `operations` | 1881 | `461c7c36c4002c42a1422a288ebb290bfda737923c88500f3ca18c4f5cee1f76` |
| `skill/SKILL.md` | `skill` | `skill` | 4860 | `9e9af67d407d1448176abf32b476f88d586f7b13d1618fd8f56ced15a2ee3d01` |
| `skill/agents/openai.yaml` | `skill` | `skill` | 344 | `24dde8236b9e5eb99ae579cce0b06185f11da542b5b151bbbbd8f1792a21cb59` |
| `src/l9_graphite_memory/__init__.py` | `production_source` | `production_source` | 1026 | `966af4c9e82b662a008ecd23bd8de67930212bf302b33d31e8b50624b7cc4bc8` |
| `src/l9_graphite_memory/__main__.py` | `production_source` | `production_source` | 340 | `3eedfcbce155174df8ff657ebd9bead64d6e063f25711bf682bbd00b55293c2f` |
| `src/l9_graphite_memory/adapters/__init__.py` | `production_source` | `adapter` | 680 | `5ff15b8007bc30de3ee38897910e660a2e7c774f3324bc07982bffcaf698a3ea` |
| `src/l9_graphite_memory/adapters/factory.py` | `production_source` | `adapter` | 1897 | `92db38e2ed5a1ac86e10293d9884ab8e2481e9b68eb8e6b37588441ed61d796c` |
| `src/l9_graphite_memory/adapters/graphiti_projection.py` | `production_source` | `adapter` | 8889 | `ffe51a428a94a2f29d4a280ce0a5b87ed718100aa27f7b48489bebd38ea4553e` |
| `src/l9_graphite_memory/adapters/in_memory_store.py` | `production_source` | `adapter` | 10900 | `5f816a6ba25336a5b0c2a92805b3bd51022799e5423b045d17ed2d3bb235dd66` |
| `src/l9_graphite_memory/adapters/null_projection.py` | `production_source` | `adapter` | 1572 | `b5d16bbc680eaf82ac2b4ccb8e55ebb277ba412fe20d6354148f335fb85c767d` |
| `src/l9_graphite_memory/adapters/sqlite_store.py` | `production_source` | `adapter` | 33815 | `67f6b48c881b1d9544eae0629c0d6f2497ccd4eb6e3d133e71a855fc6559d220` |
| `src/l9_graphite_memory/admission/__init__.py` | `production_source` | `production_source` | 540 | `a73bd08e4233213d1425707fbe5d1588f3488bcfd5a6b990ea7e059933d651d2` |
| `src/l9_graphite_memory/admission/engine.py` | `production_source` | `production_source` | 4974 | `558f2c95d36d5d8ae1f6f409f92344828ffa0d62bf1c4f0c3827d6dfb6b86176` |
| `src/l9_graphite_memory/admission/normalization.py` | `production_source` | `production_source` | 3432 | `3edfa01ed264e646d40c99570a93d7333e6d23f2d452a52dc9b3c8b2eae55a41` |
| `src/l9_graphite_memory/admission/policy.py` | `production_source` | `production_source` | 1062 | `e8113e40824d4cbd5b5e072c177e328dc1a8f1d85d92c8e944795537b1e05cae` |
| `src/l9_graphite_memory/authz/__init__.py` | `production_source` | `production_source` | 466 | `b079cd2be5c21827a96efb4615e4e21018d3461a6c05ef5747d4005155a2ef36` |
| `src/l9_graphite_memory/authz/authenticator.py` | `production_source` | `production_source` | 2988 | `40bd73cc395badcb5d45f9071182d67bc3df9014b90863ae51c0bde4197d600f` |
| `src/l9_graphite_memory/authz/policy.py` | `production_source` | `production_source` | 2722 | `8b77a142659ca5e3b991e71b1e31386e719054bcb1e8a0e8e5b0e02ee053bd58` |
| `src/l9_graphite_memory/circuit_breaker.py` | `production_source` | `production_source` | 2715 | `6f2a9323eb7e2917ce89c9396864001a606d5cf896807b35e27361519dc50751` |
| `src/l9_graphite_memory/cli.py` | `production_source` | `production_source` | 31149 | `c05c1ffe70a3bcc4627ac1783f019591cb4bceb560ce50ec8ecfa2be98e31f0c` |
| `src/l9_graphite_memory/config/__init__.py` | `production_source` | `production_source` | 448 | `ca7aaaa346d76faa176d150b1fe24a6c29318c3bece0bb48c7c419ef56fcae7f` |
| `src/l9_graphite_memory/config/loader.py` | `production_source` | `production_source` | 5905 | `0eab8f2d38e7d1517a5d288e264c437c14831fbf58cf38157c22d2e7cd970d43` |
| `src/l9_graphite_memory/config/models.py` | `production_source` | `production_source` | 3735 | `e1e218a31d12f38801fd9a545ecc769cc91e8b4be64ee64525419106b6c2d030` |
| `src/l9_graphite_memory/contracts/__init__.py` | `production_source` | `contract` | 2634 | `8d813e9eb82a4d8cee544fe107f0a20feca72e571e4ead1a093e4fbe1143d3c9` |
| `src/l9_graphite_memory/contracts/enums.py` | `production_source` | `contract` | 2303 | `1153fbc9db7437184a79b5b946af07c77a602ee34d73061c5e8d1b79e634a1d9` |
| `src/l9_graphite_memory/contracts/evidence.py` | `production_source` | `contract` | 2887 | `d28ad47ee2b3b83743de8cc57caef44e104335447399f962faadfc197753daf6` |
| `src/l9_graphite_memory/contracts/identity.py` | `production_source` | `contract` | 1348 | `f1f4a7467acd2f60bc40828eea561cbef83bf17dc4aa7b3d0ee844c38410ae98` |
| `src/l9_graphite_memory/contracts/memory.py` | `production_source` | `contract` | 3213 | `fffc735bc5592d03e81451909ed19520357224baa87ae59a35302549d62b71f3` |
| `src/l9_graphite_memory/contracts/privacy.py` | `production_source` | `contract` | 1769 | `68afd486e77b35b7a08bddc72cb1a367f4d98c909d648b0c8e47b2da9596059d` |
| `src/l9_graphite_memory/contracts/profiles.py` | `production_source` | `contract` | 3235 | `ba1550aa91af50829129325fa14af66711f84ee57fdb09085e3859e33de18a54` |
| `src/l9_graphite_memory/contracts/projection.py` | `production_source` | `contract` | 1275 | `1c86e80efef6e4a98e497cec7a421b1678aa6e69ef153521212d5e5d55d999dc` |
| `src/l9_graphite_memory/contracts/receipts.py` | `production_source` | `contract` | 8679 | `f81d04f838440ff3527e29322782fc873b45f8e60c9d004a959c9a873500d8e2` |
| `src/l9_graphite_memory/contracts/requests.py` | `production_source` | `contract` | 4140 | `a60f2137fd2430fc454f54ab4179959936687058b7de053b85d662e8a16b44ac` |
| `src/l9_graphite_memory/contracts/temporal.py` | `production_source` | `contract` | 1580 | `2d4be0c5a848489d880a7d688a3d6650540026dfcd79380c66d528f5b9b85dd0` |
| `src/l9_graphite_memory/curation/__init__.py` | `production_source` | `production_source` | 485 | `b575c39efbe3e37381594714c2057bedc927a42edb868e133506119634d421df` |
| `src/l9_graphite_memory/curation/procedural.py` | `production_source` | `production_source` | 6897 | `f3872cb0ed580ab61792945e873ead8dec51ccbeb8800e68cb15b6b4f9ca27aa` |
| `src/l9_graphite_memory/curation/promotion.py` | `production_source` | `production_source` | 2187 | `4455d5783647cfc8206f338fb061c5b0b9f3dbdded3292a1415153b8208d88d9` |
| `src/l9_graphite_memory/curation/retention.py` | `production_source` | `production_source` | 3895 | `2a11ef170dfe5c63c5779e1f35963206d6c3baa8057346613e5262eff6c3d96b` |
| `src/l9_graphite_memory/episode_contract.py` | `production_source` | `production_source` | 2209 | `c160b30614690bbd7b27b35bd30575e3740311dc1517f13efaa65eb22fd3a134` |
| `src/l9_graphite_memory/errors.py` | `production_source` | `production_source` | 1356 | `53fd533bae1f5597868bb3a2744f5026532564ae945697e181ae34eb7242a840` |
| `src/l9_graphite_memory/extraction/__init__.py` | `production_source` | `production_source` | 773 | `46a4c59ee8f9aa3efca42c7d301071508946e0053be01a59787bbee200a59ad1` |
| `src/l9_graphite_memory/extraction/atomic.py` | `production_source` | `production_source` | 8571 | `0a24130502494cd3a800a10e15ad01a83dcb36ef9b90dbbfced838ae2782b68d` |
| `src/l9_graphite_memory/extraction/distiller.py` | `production_source` | `production_source` | 4602 | `863de8913dfe0355beec35d641fd6f6177b7527cd4c9a5f23662caf0c642a230` |
| `src/l9_graphite_memory/graphiti_gate_lib.py` | `production_source` | `production_source` | 1409 | `f6e3a4d3b6992e6e3494524d08be1b8c788ecfef4694f0dbbf8350356dc2273b` |
| `src/l9_graphite_memory/graphiti_memory_client.py` | `production_source` | `production_source` | 441 | `1d52faf2979e368428395634d1828d55e35603c997cc06158b28f3162d0cdd52` |
| `src/l9_graphite_memory/group_resolver.py` | `production_source` | `production_source` | 4955 | `e86af36f848d1df020c6f3b991070fb7f540859c1021a2e0f34c4856a35f4be3` |
| `src/l9_graphite_memory/ingestion/__init__.py` | `production_source` | `production_source` | 506 | `b742787408499f8b1e2b4e1ec5e9ca5e7c1f0f9ed438c505028a48691fd8ebe3` |
| `src/l9_graphite_memory/ingestion/document.py` | `production_source` | `production_source` | 4715 | `47eb9cea4f4ab9646ffef6241feb5b5137de673bc63bc185b3c8b31dfe878246` |
| `src/l9_graphite_memory/ingestion/profiles.py` | `production_source` | `production_source` | 7545 | `c9be8cf43d5ba48ed70331f81651ad62217b4000a192dd98199fb94d421b2e85` |
| `src/l9_graphite_memory/ingestion/repository.py` | `production_source` | `production_source` | 2723 | `b664de965a16b438a0ac73a22876e21b5e3fdc6295856b37744630bacaab56cb` |
| `src/l9_graphite_memory/integrations/__init__.py` | `production_source` | `integration` | 837 | `af4b8ad2e3de1060882ad621befc78bc98cdc887c174c88d0cd4496a1c8938fb` |
| `src/l9_graphite_memory/integrations/constellation.py` | `production_source` | `integration` | 4544 | `78d98f1171355113825adeec3e06deb6ea03104d2401ae8c95b1acd8fbbf6268` |
| `src/l9_graphite_memory/integrations/session.py` | `production_source` | `integration` | 4929 | `11070bc71705ee93febb4c205114e71d4b7491f29024de79859cb5190d59dddd` |
| `src/l9_graphite_memory/integrity/__init__.py` | `production_source` | `production_source` | 414 | `a861f632d5719324d1a819ea8b93826d827f742fb6abaa797937a4ae5f821fdd` |
| `src/l9_graphite_memory/integrity/checkpoint.py` | `production_source` | `production_source` | 2952 | `1556b59757d094ced0be22a98391fef6374f3d6bf1645f30095767b1b97789c7` |
| `src/l9_graphite_memory/lineage/__init__.py` | `production_source` | `production_source` | 401 | `3fe9728159d495dc16e043b7200e5f8b1d58a78c80aa30fa17984cbcd86aa6d4` |
| `src/l9_graphite_memory/lineage/replay.py` | `production_source` | `production_source` | 3884 | `2e37f126fafde19cf2a5989135ff95325841ed4b9f0499663e7475f875a08293` |
| `src/l9_graphite_memory/mcp_tools.py` | `production_source` | `production_source` | 22632 | `94a559ddc2436dac131cc9b3020cf4910221623c0073c497fb0ff9b490a493f2` |
| `src/l9_graphite_memory/memory_guard.py` | `production_source` | `production_source` | 7800 | `1fd96a90d270e10331410f0988a3f84d0750a72d84cb2ce4ceeaa1a94ea2b332` |
| `src/l9_graphite_memory/observability/__init__.py` | `production_source` | `production_source` | 373 | `2584326a5b626b9415d794c630aa2df323129384bb6cfe822b9cc3536cd6c6ec` |
| `src/l9_graphite_memory/observability/logging.py` | `production_source` | `production_source` | 2172 | `3d3bf117dc14d63e62ed0e756d2299d441f1c8ac76dbd65c9670b66a6df0012b` |
| `src/l9_graphite_memory/ports/__init__.py` | `production_source` | `port` | 868 | `17d1cbeed7f01ac5cc21fb342126ff8b034b3da1555603051826d9e445ac0a0d` |
| `src/l9_graphite_memory/ports/clock.py` | `production_source` | `port` | 542 | `41677121a8599f45abe3b0ce0d02a3893833048e33eb25f6f1ee3be61a651b85` |
| `src/l9_graphite_memory/ports/constellation.py` | `production_source` | `port` | 1841 | `1fdff02c81a6f0d037a96c777f5e830fbeb51e7992caf74dc80711707afd5ba4` |
| `src/l9_graphite_memory/ports/projection.py` | `production_source` | `port` | 1407 | `b263357f8c75c8148f9f8589ddeaa1e67f6f50c4839f20d7780e6a022f472d43` |
| `src/l9_graphite_memory/ports/record_store.py` | `production_source` | `port` | 3286 | `965f546dd287c68ad999d493d3d3ba4e0e95c3c4666803d42cf12c6466dcaad9` |
| `src/l9_graphite_memory/ports/synthesis.py` | `production_source` | `port` | 917 | `237cc5ae1fc51cde5812dff077157b68dde1bd15eda961cb62fc4bbd8756994a` |
| `src/l9_graphite_memory/prune.py` | `production_source` | `production_source` | 1396 | `b25b36021e9b99cfd87c43bb89f09ec2f1fd2f71737c57b25aac71380eedba0f` |
| `src/l9_graphite_memory/rate_limiter.py` | `production_source` | `production_source` | 2338 | `bb48be949fd136c94cebbe2e30e77879923c4bb907507a577a4f54234a470dd6` |
| `src/l9_graphite_memory/recovery/__init__.py` | `production_source` | `production_source` | 520 | `1cf5cd83050380dc590eb81674e9e02d5c9092aca1661ed43050e2f78dd83433` |
| `src/l9_graphite_memory/recovery/write_queue.py` | `production_source` | `production_source` | 6143 | `750425ac05bf9f09855655c0514b0a613a453bd9107c879a53f372b3a126142b` |
| `src/l9_graphite_memory/resources/defaults.yaml` | `production_source` | `production_source` | 568 | `0d1e8d2d520504a197af9885d7d7d08797ef3f4bf1b11f24b1fee417c9bd3ff0` |
| `src/l9_graphite_memory/resources/group_registry.yaml` | `production_source` | `production_source` | 1339 | `104626fb987d50bf6ca63902ca4abb16b810db70fa272ab0cc8e0875fe51b825` |
| `src/l9_graphite_memory/resources/memory_contract.yaml` | `production_source` | `production_source` | 947 | `f01e8c8307cf923bbc16981cfda2862f93c5f0968a624ff460cd9f748f989030` |
| `src/l9_graphite_memory/retrieval/__init__.py` | `production_source` | `production_source` | 634 | `090e3caf5486287a3e9d187e3803c6388be3a4a30b90b7f97ca2b58e99bc5350` |
| `src/l9_graphite_memory/retrieval/budget.py` | `production_source` | `production_source` | 3281 | `dc106dc7b1cad907bb55d748fe77b2353970c7ef4b15d289ac290e328ace875a` |
| `src/l9_graphite_memory/retrieval/planner.py` | `production_source` | `production_source` | 7082 | `d6dfb5839dd465ce71c7f0b8eba8efd678382373dd14fdbf81c3401c2836f33d` |
| `src/l9_graphite_memory/retrieval/query_classifier.py` | `production_source` | `production_source` | 2856 | `373beeed5e4dff735873a9271c48f68c841048351d143e958b0634dc5f2bfea7` |
| `src/l9_graphite_memory/retrieval/ranking.py` | `production_source` | `production_source` | 5370 | `f460eb5a43e944dc76a0dc438e430050ac8062acc249385d4a079b320fcb8b4b` |
| `src/l9_graphite_memory/runtime.py` | `production_source` | `production_source` | 2660 | `95745c7cd2e91893c870d01b1f2319cd622093d4a52b9ab465f062492f49c1f8` |
| `src/l9_graphite_memory/schema/__init__.py` | `production_source` | `production_source` | 462 | `716b3d2a860487a61bfac424f8dff2ed19bd5f507bf70c1dcb551676adaae34d` |
| `src/l9_graphite_memory/schema/registry.py` | `production_source` | `production_source` | 3417 | `9e7977f27cb93e3ba6f5035fe3ad8811dede1a6f506cab49f9d2bc1bee2d3d89` |
| `src/l9_graphite_memory/schema/upcasters.py` | `production_source` | `production_source` | 6383 | `72fbcf9ba7275c46295a09b9ca2198f0d4fbc2a3881cc0cd38a2ad25f9d347a1` |
| `src/l9_graphite_memory/sdk.py` | `production_source` | `production_source` | 1742 | `2787d2190dbdff713e732402848458af8fbc4752926fde00edbb420570ad021f` |
| `src/l9_graphite_memory/secrets.py` | `production_source` | `production_source` | 6582 | `23f63bbe51e29ce1552fb38eee5cbfd34ad387ca0c619ca51dbda56ee1cd99e2` |
| `src/l9_graphite_memory/server.py` | `production_source` | `production_source` | 9769 | `a006ca3dc4ec4742e17fb708ad73f2d1fa2bb1a6e8ad1aa563b878f7fb37f644` |
| `src/l9_graphite_memory/services/__init__.py` | `production_source` | `service` | 401 | `a612ba4493e84650ac3df695bd3d459ae188b7d345a0ab743284c29475383fd4` |
| `src/l9_graphite_memory/services/memory_service.py` | `production_source` | `service` | 30171 | `8ff81b9d24197b45e05ae5f6d45d073cee50450f802856772d4074240dd46fbe` |
| `src/l9_graphite_memory/services/outbox_worker.py` | `production_source` | `service` | 6760 | `125b60e2304c2396ec9fd9fce4c074a89f5975fcaa57a1dcbcbc618d3da99d1b` |
| `src/l9_graphite_memory/transport.py` | `production_source` | `production_source` | 7824 | `c52d1e8fb6e99a4883475651370d2cc1d28bce98541a36da316cf15975c7849d` |
| `src/l9_graphite_memory/version.py` | `production_source` | `production_source` | 660 | `21b884e090a4bd09a8af9f46d6fbfd4cf4dbb68eec68f9b604e3c3351d522c9b` |
| `src/l9_graphite_memory/zep_transport.py` | `production_source` | `production_source` | 8167 | `759d78bca6cb04262ca19f846d77b8392c56b2cefbe861ff172706a3364c0fad` |
| `tests/conformance/test_store_contract.py` | `tests` | `tests` | 5688 | `02d423239316e166c7def6bb6b67505e885f95c72c9b61191d1edcfcf3051931` |
| `tests/conftest.py` | `tests` | `tests` | 1457 | `56b36cdc72ec287f257bf3a28ff53ba2c6856fb7a862109de1fe8b43ace4a219` |
| `tests/integration/test_distillation_profiles_sdk.py` | `tests` | `tests` | 2370 | `132d50b78e01a4b76ada3626ffe53c34a307281c6b6a9136acc8062451921887` |
| `tests/integration/test_mcp.py` | `tests` | `tests` | 979 | `336915dcb7d15ffe73e393b0a236549bdb02a14c2ae7ecb48fc04adde2b200de` |
| `tests/integration/test_mcp_harvest_tools.py` | `tests` | `tests` | 1468 | `a0a1e850025c40cec94d1cc955e2e7b60e3f4706ae500f72f7b6eca243b8085b` |
| `tests/integration/test_memory_service.py` | `tests` | `tests` | 8766 | `4c8cb2872eb15382416bb2b6b9891d0954bfffbdc0df77efd533d3b5af22b91a` |
| `tests/integration/test_outbox.py` | `tests` | `tests` | 2575 | `0e3f4eeebe737628aeb778d0940844484a8843ed43ff7c6c68ae1e20b110653d` |
| `tests/integration/test_privacy_deletion.py` | `tests` | `tests` | 5985 | `8be0c984555580e84917f7f92095147110fe7e7f84316f73990710c1f52a00ac` |
| `tests/integration/test_procedural_synthesis.py` | `tests` | `tests` | 1878 | `e806d3e67b181dc8f1e1ba538e28c7844466ebdfd9d229aed64670bebd27e458` |
| `tests/integration/test_retention_lineage_phase_lock.py` | `tests` | `tests` | 2798 | `21610020527e73b944baa67a1f16c988c2b31f0fa071e533156e0ce63d07feb3` |
| `tests/integration/test_write_recovery.py` | `tests` | `tests` | 1491 | `5cdc6ebbd63ccf915fafbeb8b52157f9e42603747b951b00b72a3dda20d29695` |
| `tests/regression/test_assurance_tools.py` | `tests` | `tests` | 1923 | `bce9a6ee21500a330ce0bd735d386d3409b6750006a47760385f0697a770f47e` |
| `tests/regression/test_recursive_alignment.py` | `tests` | `tests` | 1654 | `a4f070d17c9d88931b888ca6c2348505c51dd4231ffe53efaac808fe557dba29` |
| `tests/regression/test_release_shell.py` | `tests` | `tests` | 3274 | `ad6b14c1ae2a8dc7374d4e44175f45a9d8b243d153235026582d03dc10b00888` |
| `tests/regression/test_skill_pack.py` | `tests` | `tests` | 1017 | `858b8d5a88075a13703b0ae98ebf8cce02e59224e10b576d3c99f8fab2c5cd8d` |
| `tests/unit/test_atomic_extraction.py` | `tests` | `tests` | 1896 | `36fc3da3c860259f994fe130b15748712ac662983b335974117ca4e7cc0cf58a` |
| `tests/unit/test_authz.py` | `tests` | `tests` | 1520 | `9c74dc3cfbd6f4baf51249e4709f1431aa0387d3852f9e24da448828101ba6ae` |
| `tests/unit/test_checkpoint_integrity.py` | `tests` | `tests` | 921 | `29e809c79e8ac261ca0864bd7b9d06644656c86bc76ead0ac9a2039f254b505b` |
| `tests/unit/test_cli_parser.py` | `tests` | `tests` | 1087 | `8229b1875ca54da4864a7c8ce37ab07da51dde6eb3f1b7c8313c3f63999bf93e` |
| `tests/unit/test_cli_state.py` | `tests` | `tests` | 1723 | `0fb4557b0e68cdce0238424bedad894ae3dbd5feb28b3c3633aa7b0e0a6f078a` |
| `tests/unit/test_config.py` | `tests` | `tests` | 1056 | `a6a297235c00aa7ba3c755a825b66c33fa54a8bd011ad9aec34bc577229fef9e` |
| `tests/unit/test_constellation_bridge.py` | `tests` | `tests` | 3577 | `69ba1955f1dbca82316703fc86ebd4a22e6e4e2f0434c6c3935bc778d7b4fa6b` |
| `tests/unit/test_contracts.py` | `tests` | `tests` | 1666 | `f289defc84e7f048da6b83effab42e44b6d0b6b50e92c4118bf9ec3c0e773552` |
| `tests/unit/test_gate.py` | `tests` | `tests` | 3740 | `0c6851707e8fe50d1d5738e5e3b4c7202a6ec220c4459e61e44ca734086faa6b` |
| `tests/unit/test_group_resolver.py` | `tests` | `tests` | 1775 | `415aeeaff0582a2fa75dccde8319e7928394a6330821cf97baa897f20f5fe3b3` |
| `tests/unit/test_http_transport_dialect.py` | `tests` | `tests` | 1582 | `b903e799b4ac9b269e901f81857f89cd29f4fad72f968e47e951e842a5e0713f` |
| `tests/unit/test_ingestion.py` | `tests` | `tests` | 838 | `bf894f235cfa931af1a1d4de8a42ccca0fc29c27645b8c17ec27b0e2c1b3bc5d` |
| `tests/unit/test_normalization.py` | `tests` | `tests` | 1199 | `2cc925edccff70b0c7472e9167869bd6211d4ef4a8dbfbb9ea76227005145727` |
| `tests/unit/test_profiles.py` | `tests` | `tests` | 3445 | `08eaf508efac78a148cc69c19c43f19162fb19701ee5684b8c5459570fd1f7e0` |
| `tests/unit/test_projection_strategies.py` | `tests` | `tests` | 5103 | `8c38bce5eadc2aff0671e0a220f01670e8ab3c86df8032f39673a96c74dd3f20` |
| `tests/unit/test_query_classifier.py` | `tests` | `tests` | 1133 | `69a8f10343af4f7374db596db852b1b2f0782acbaa1b3eca6feb7249fa3b8cfe` |
| `tests/unit/test_schema_registry.py` | `tests` | `tests` | 964 | `008703c05aeabf16c0f6c03eb16d96cdeea72e7ed24958ffb51bd58a66e775ee` |
| `tests/unit/test_server_principal.py` | `tests` | `tests` | 870 | `ee90435a75d372007b48334e9cbe8b16e05af6a370e4c43af04d34cd9262c982` |
| `tests/unit/test_zep_transport.py` | `tests` | `tests` | 2614 | `4b08cdd26387ee78c67f27a398a71001cf1805284fd516f8d355af78350db65d` |
| `tools/assurance/apply_l9_meta.py` | `assurance` | `assurance` | 5317 | `7564ea7ffb267ea3af7d4f10fa8754aa54d8c3b962f4d93cf568b419ffefcf9e` |
| `tools/assurance/audit_package_wiring.py` | `assurance` | `assurance` | 3582 | `e8b02455559c3f99d1499615f84c2137de3677c4c549e52b8e572c0afc9229e5` |
| `tools/assurance/benchmark_local.py` | `assurance` | `assurance` | 4687 | `3a43cdd0dea142c3b2be45f84716178c55053848903cc79911d03a2b3037da53` |
| `tools/assurance/check_config_drift.py` | `assurance` | `assurance` | 1968 | `364327e746bfbcfe7f80e6ce12e0690746dd46c5368a92016bce5d26cf3323ee` |
| `tools/assurance/check_l9_meta.py` | `assurance` | `assurance` | 2881 | `835f1c411c2a927b4d25e4a6b175491e2dbae57926171c14cbcc65eaa281ac72` |
| `tools/assurance/check_layer_boundaries.py` | `assurance` | `assurance` | 3312 | `e163d10fb47420cc82f42036060ec1053a926fc629c99b2a3650b0bc87bd8292` |
| `tools/assurance/check_memory_write_bypass.py` | `assurance` | `assurance` | 3554 | `12b8d29b38cfcf1ad3eec34b76a966f22a577d1cc6eeecd5695fc5b0294dd4f3` |
| `tools/assurance/check_recursive_alignment.py` | `assurance` | `assurance` | 8589 | `f7a9f26d118d3cf26132c9c4ab327e7155a4b30273a23996a348eec10b427923` |
| `tools/assurance/check_secrets.py` | `assurance` | `assurance` | 4273 | `607016228e456699d2fa4245336d6467b0244cd34f4e9f9ebfef565d1199ff70` |
| `tools/assurance/check_source_quality.py` | `assurance` | `assurance` | 4903 | `9795661c7785def3184ec8f0a9830ec523b7ae6d3de5e8961466bb3df818536a` |
| `tools/assurance/generate_manifest.py` | `assurance` | `assurance` | 7262 | `00bd3f585cb218b04fc5d5524c829957451655ddcb36616c4e44bd6c4684d319` |
| `tools/assurance/generate_validation_evidence.py` | `assurance` | `assurance` | 10184 | `614453eadf3f419cd91b63ecd32573f8cf190f64cf04cb07d5dcb5ddffb649a9` |
| `tools/assurance/validate_adrs.py` | `assurance` | `assurance` | 2559 | `9f7b2f7a247e7d4b32b91adfc576c8ee9d8935a4078a60d406e04fcdb31db0d0` |
| `tools/assurance/validate_harvest_coverage.py` | `assurance` | `assurance` | 4116 | `4a656cae6dbf25721a0cd92d4e6a7b9192a8af87f5100487d3cf91a58e6855a0` |
| `tools/assurance/validate_manifest.py` | `assurance` | `assurance` | 2391 | `a04fae23b1b3c40c4184ad88ea958076a0a247d5eb0334585ce49c80a2bb864b` |
| `validation/SHA256SUMS` | `validation_evidence` | `validation_evidence` | 108 | `85717abcdf739fb07e21b9ac46a48711575140f9e20e58151d18de45353b2bb9` |
| `validation/dist/l9_graphite_memory-2.2.0-py3-none-any.whl` | `validation_evidence` | `validation_evidence` | 132977 | `2f69b2a66b2d9eddaf71dc1bfa5af37463abb81ec915478df590f93bac4e5181` |
| `validation/logs/adr_validation.txt` | `validation_evidence` | `validation_evidence` | 35 | `2a0629a4645d0db1e1f0c8182ea6ee9bc4ba6a45236a53934352be8e097a274a` |
| `validation/logs/bypass_check.txt` | `validation_evidence` | `validation_evidence` | 50 | `7138de56268f741122706f70a72e61409f2729eabf9284d570d69643834ef520` |
| `validation/logs/committed_secrets.txt` | `validation_evidence` | `validation_evidence` | 188 | `55308238e08d6c7ebafa91909a4938c40cecb03da4e468d8b4b8d99410a1211a` |
| `validation/logs/compileall.txt` | `validation_evidence` | `validation_evidence` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `validation/logs/config_drift.txt` | `validation_evidence` | `validation_evidence` | 69 | `f95f19d2a5faa72ea6018d37ed97baee659c49adce45016d7d56ae7f5fe57b2a` |
| `validation/logs/harvest_coverage.txt` | `validation_evidence` | `validation_evidence` | 101 | `a77c2c5914680700e64b06e52391499d845f15b5cd94bb5959a5f91d9a6ba336` |
| `validation/logs/installed_health.txt` | `validation_evidence` | `validation_evidence` | 441 | `e6efd6f0d5c648d23012e5cdc9b750acfb185e57044c4d8cf7633af7e4b72f9a` |
| `validation/logs/installed_mcp.txt` | `validation_evidence` | `validation_evidence` | 74 | `ebf9b42a68c28f17711c394515c4e08e0cda8dfa1148d6f5d03ee03537c0593b` |
| `validation/logs/installed_resolve.txt` | `validation_evidence` | `validation_evidence` | 137 | `eae6487763b5416bca0bd4e711b38b74b9231186d8682cf75cea4615fc74efd2` |
| `validation/logs/l9_meta.txt` | `validation_evidence` | `validation_evidence` | 83 | `e305e6a7e79c48e68745c71dc7b65912068010b67a512ae8498745be7137adf0` |
| `validation/logs/l9_meta_apply.txt` | `validation_evidence` | `validation_evidence` | 27 | `cb9b24685725174c9f8a99ad71c0fb7d83dc50e6759a69da6f09d35e3022e765` |
| `validation/logs/layer_boundaries.txt` | `validation_evidence` | `validation_evidence` | 80 | `3a9e49589664f3aa63e6e470f64d79e8db7957485afb4027533c1c654e07005b` |
| `validation/logs/local_benchmark.txt` | `validation_evidence` | `validation_evidence` | 657 | `ad90ccb4a6529fadde9e3055e7afe5cb980668ce3c409d7cd27da2a8163be275` |
| `validation/logs/manifest_validation.txt` | `validation_evidence` | `validation_evidence` | 64 | `2603726b77a5c384c654be0f8345fc1e17d3812322c0d587a3d5b3d0eeffa0ea` |
| `validation/logs/preflight.txt` | `validation_evidence` | `validation_evidence` | 2229 | `7c2e4f53811f05c612fac7e27275034e2d967881612cc7e0809a998e32e6e3b7` |
| `validation/logs/pytest.txt` | `validation_evidence` | `validation_evidence` | 180 | `8017f6b08716796f46651309f749d58821ff5123d0623623c49ca6a671bce7d8` |
| `validation/logs/recursive_alignment.txt` | `validation_evidence` | `validation_evidence` | 70 | `e5e2d7db7b0c91990f7fdf089e78d343fd212368e0ad3f99c300b5fdd530f993` |
| `validation/logs/shell_syntax.txt` | `validation_evidence` | `validation_evidence` | 23 | `a0c54f351e5a214abe7090433031f08eb3a95539d861058de5c2d7da6309d2d8` |
| `validation/logs/source_quality.txt` | `validation_evidence` | `validation_evidence` | 66 | `4ee0b9f03808701ceb6024a90be5cb685d67cd4314e7a7f2b0b428cd905eb6ee` |
| `validation/logs/validation_evidence.txt` | `validation_evidence` | `validation_evidence` | 62 | `954e4120f0c8aaddebf08bc2b161caeb965bf1546c8c6979930a9e7c1b112c95` |
| `validation/logs/wheel_build.txt` | `validation_evidence` | `validation_evidence` | 1130 | `a483b4627cb5c9baa66770e2117261f147e112659dbfe07c5da66e9c77ab8c41` |
| `validation/logs/wheel_install.txt` | `validation_evidence` | `validation_evidence` | 622 | `26db4aa5754c6546b11a6e29911d9608d887fe3fbfb7c5f1b096f51c07e09d2e` |
| `validation/logs/wiring_audit.txt` | `validation_evidence` | `validation_evidence` | 33 | `24ef1827210d4751cabc9a5dd308aaa749cfb26c20bcc1054136d3217363ab46` |
| `validation/validation_checks.jsonl` | `validation_evidence` | `validation_evidence` | 10074 | `a9ed1f68c13ed6239fa8885418d9904605e0332007455eac8fcceecd2b4bea52` |
| `validation/validation_findings.jsonl` | `validation_evidence` | `validation_evidence` | 2717 | `5f2afa8ba52b03d2451510acc296faaddfc3046e5f787c5d769cc560e7edb700` |
| `validation/validation_report.yaml` | `validation_evidence` | `validation_evidence` | 474 | `2edc819b251c24525bf4ba06510ce1c7ddf1932adb7db52cf4dbbbad51dd39f0` |
