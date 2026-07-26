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
| `architecture_decisions` | 64 |
| `assurance` | 16 |
| `ci` | 5 |
| `configuration` | 10 |
| `documentation` | 10 |
| `hooks` | 9 |
| `operations` | 8 |
| `production_source` | 95 |
| `repository_root` | 49 |
| `skill` | 2 |
| `tests` | 37 |
| `validation_evidence` | 29 |

- Hashed inventory files below: **334**
- `MANIFEST.md` is hashed by `manifest.json`.
- `manifest.json` excludes its own digest to avoid self-reference.
- Every manifest entry carries canonical `l9_meta`, including non-commentable files.

## File inventory

| Path | Category | Layer | Bytes | SHA-256 |
|---|---|---|---:|---|
| `.github/issues.json` | `ci` | `ci` | 5755 | `23cbdff3ae0c9491c419771321766af4f510cd954dc671404994e7c7e3771d28` |
| `.github/labels.json` | `ci` | `ci` | 1530 | `3e30b86079a28b0ca4b7e704c436f4e4364ea084465b35d5a5f039ec0c8827fd` |
| `.github/workflows/ci.yml` | `ci` | `ci` | 964 | `d366e14b0d6e605958cc0a2f5ae59eca47810dcbc168cc8a08777ab5b3c462b5` |
| `.github/workflows/codeql.yml` | `ci` | `ci` | 589 | `5366c6d30a7c4b66b898ae32737c99d7520351f1d9196079d1ab7ac13e5c33bf` |
| `.github/workflows/publish.yml` | `ci` | `ci` | 1131 | `fc0c1d03146e25d7ddf704c8d7b434a6ff1491d06ed7862c8ff591238f8638ff` |
| `.gitignore` | `repository_root` | `repository_root` | 859 | `5742eda9df58ea637c68e20e6fb7897c70c010795171f867acdcf01dcd80d670` |
| `.mypy_cache/.gitignore` | `repository_root` | `repository_root` | 251 | `05d5de6cfad8105c667dc81c54a3ea5f231af609db1eac5d6febdd593677b6b8` |
| `.mypy_cache/3.10/cache.db` | `repository_root` | `repository_root` | 9768960 | `62d58607c47f1d5d7255401d35ba426b104ba031ab13e64e76f67935062a4739` |
| `.mypy_cache/CACHEDIR.TAG` | `repository_root` | `repository_root` | 190 | `f1c13afc555358c9033b0f1f30aaa177fe88bda40f4b8a24598400d547876adc` |
| `.pre-commit-config.yaml` | `repository_root` | `repository_root` | 505 | `f7d6670a379d5978d660479a51a80b86b2ad0ae1acde826f1b474d17952051a8` |
| `.ruff_cache/.gitignore` | `repository_root` | `repository_root` | 252 | `97dcad36113408e98357a7a41cf584b43944c86194a4fcaf55ee146f2e21dd0b` |
| `.ruff_cache/0.16.0/10429412380179331488` | `repository_root` | `repository_root` | 276 | `c19d714cedd51410383d9626839e0c22d90361f17e55203384932727136d2bb7` |
| `.ruff_cache/0.16.0/12751293278614387707` | `repository_root` | `repository_root` | 1396 | `1ca747413496d7405212014eeaba63fbb58530805b131d5a292fc09b45451927` |
| `.ruff_cache/0.16.0/16054431094664067017` | `repository_root` | `repository_root` | 180 | `5a8f88ace70c295a77a8e736225129f37f83f8c182a5846c4073e1d46263211f` |
| `.ruff_cache/0.16.0/16079579219017933816` | `repository_root` | `repository_root` | 164 | `1872cd17d23ee56795288a5441d9a6298850821b02a5e4dddf0ca0e59073bd6a` |
| `.ruff_cache/0.16.0/16548515552740709585` | `repository_root` | `repository_root` | 348 | `1daecb721785ff6f67c2649743c319df2a4df9da556296c4840d98cd969176b2` |
| `.ruff_cache/0.16.0/17538307559772964363` | `repository_root` | `repository_root` | 1052 | `9d3dec559c3594ee006e17350d1722b2b0530dce534f664b275fd92d99441c14` |
| `.ruff_cache/0.16.0/4199481189510131854` | `repository_root` | `repository_root` | 636 | `e5546554e503a6e7931e3975a0b83b08a2289a5ac2e5ffcc1b0f72df1c6d25d2` |
| `.ruff_cache/0.16.0/90306441165669623` | `repository_root` | `repository_root` | 5276 | `26bafe03236ee6a015c7b2494331c6d4658f8b040b9708926e2cdba1f7c3bb17` |
| `.ruff_cache/CACHEDIR.TAG` | `repository_root` | `repository_root` | 43 | `5953156d7e0c564a427251316eaf26f8870e6483ae2197f916b630e4f93e31ae` |
| `AGENTS.md` | `repository_root` | `repository_root` | 1100 | `e5eddd9d67c1514b9794c64b14df4e9638ed379d0028d08f73d77f08fd7c465b` |
| `ALIGNMENT.md` | `repository_root` | `repository_root` | 1675 | `5ce57067860473dbc010cc8ab7ab5ea65d5ff66d9cc02f567745c1eb350cf255` |
| `ARCHITECTURE.md` | `repository_root` | `repository_root` | 7164 | `e50a1d7fe1081241b14fac9d2aa4e5e2ac80e6b080573a0807f4f9f4212a4238` |
| `CHANGE_SUMMARY.md` | `repository_root` | `repository_root` | 2213 | `cde3be8fe41714379bb3c92a683533a2bc874b8425a47143695315cf456b6de9` |
| `CONTRIBUTING.md` | `repository_root` | `repository_root` | 666 | `052f310924cad01f2f4735d476f54b1b75058b15249bc2ad0b4a42d467acaf67` |
| `CONVERGENCE_REPORT.yaml` | `repository_root` | `repository_root` | 2369 | `1b049f9264b7fa1ffbbf65ee663c10ccad1a3ed15b9bd1d457e1965baf66bc49` |
| `DELTA_REPORT.md` | `repository_root` | `repository_root` | 2642 | `6a387ff4ea95b5cc034deed28cc3cc8255c85595d07364842c19b347df579b22` |
| `IMPROVEMENT_REPORT.md` | `repository_root` | `repository_root` | 3181 | `351078f7327e2579509baec85a809b9a636f02636cc76612f0f598d33d4b9876` |
| `LICENSE` | `repository_root` | `repository_root` | 4658 | `40480115927c1985499925b32072e1bcb4f48e86432af9bffbf9d2a718e28a2d` |
| `MANIFEST.in` | `repository_root` | `repository_root` | 624 | `0b09fe70fcf48900117c6dfd3a56a4037d93e3b1c50f2dad9cfa1e5286b54986` |
| `MIGRATION.md` | `repository_root` | `repository_root` | 3306 | `07f086cc8f907cc98ac550198bfd65f25038e566abc77f755b7d0ea36688fc49` |
| `QUICKSTART.md` | `repository_root` | `repository_root` | 1211 | `4e24f79cb5bf490fa7aec8e9a8cac13bb71811fc0d83d8d172ac953bad8dd4d6` |
| `README.md` | `repository_root` | `repository_root` | 5642 | `df770b5339da5d75f4bdc334e9de0aba0917186a7abf8d74ce503238964e3f09` |
| `ROADMAP.md` | `repository_root` | `repository_root` | 2054 | `f6a75e296999b40744e0a16e5456700a318f5d40aab7d647dd1222d17e7c2ad3` |
| `RUNBOOK.md` | `repository_root` | `repository_root` | 6834 | `cad9ad8d19b1c4be2de687e85728c37a22a6eee7630a2845bb37772d7d6ee9a3` |
| `SECURITY.md` | `repository_root` | `repository_root` | 1718 | `8eb44c129daf83b389343dcf462662b6c6282a63cac6048cf084e10d2b964980` |
| `VALIDATION.md` | `repository_root` | `repository_root` | 5960 | `7aec6fa09a4f0ce29a5451fef82b9501067fa37be717f555600868fcf55a97d8` |
| `config/auth_tokens.json.example` | `configuration` | `configuration` | 405 | `7e2e9993115d39c1c1df3d45ce781fa157646a09c40de6cd737910bc5864d357` |
| `config/group_registry.yaml` | `configuration` | `configuration` | 1319 | `5ea0bc2e12ae50fe624d597f6ad808e09546f9b6cd6fc5c5cc9631b633662fec` |
| `config/mcp.json.example` | `configuration` | `configuration` | 162 | `3e755f7a79643d9900569b3cf82d8f58d264300540bceeb1426090a69e26915f` |
| `config/memory.yaml.example` | `configuration` | `configuration` | 1015 | `c4bbb5d9962c51dc1229cec65fe44ff54f07996540696ccc28d94c76fbe36303` |
| `config/projections/facts-v8.yaml` | `configuration` | `configuration` | 2054 | `bee363a9736f2731f6e79b027e5213d383041f5b323a48f534da5c9fc4db6257` |
| `docs/COMPATIBILITY_MATRIX.md` | `documentation` | `documentation` | 2490 | `8b9981ff9e7fab2d503365c7076701696b8187360145e3245712e482dabcc1ed` |
| `docs/CONSOLIDATED_REMAINING_PROOF.md` | `documentation` | `documentation` | 2093 | `cbe9f35b804ff8969d790f5d6b4a990e40cd661bda4ff6e8ae18434b6342eeca` |
| `docs/HARVEST_MAP.md` | `documentation` | `documentation` | 2774 | `4904b15f0558b79cfd8f113a505d0d7a2f0ac50b9df46ea14859a2f9a525c205` |
| `docs/ISSUE_INDEX.md` | `documentation` | `documentation` | 3171 | `3dbb53d13495932005b3a88510f00d55e30b90ca35f9547ebe67c8546e23ee4f` |
| `docs/RECURSIVE_ALIGNMENT_UPDATE.md` | `documentation` | `documentation` | 10670 | `692b41643f4f81d6c70606bf9b5decb1f5f03173035ca881683991c0b4104703` |
| `docs/RECURSIVE_HARVEST_AUDIT.md` | `documentation` | `documentation` | 4921 | `370cb913d5117345bd2355672c86115d1d4f6b875539e3cdd0e30aa55de1b393` |
| `docs/REMAINING_PRODUCTION_PROOF.md` | `documentation` | `documentation` | 2088 | `dafdd5c6268d2cdb89ccc183b7c127f4fa7a0d8a21cd6b1587bdd0f71406426e` |
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
| `docs/adr/ADR-063-projection-manifest-compiler-and-control-plane-boundaries.md` | `architecture_decisions` | `architecture_decisions` | 7240 | `3733406fe059b0293f73fdeccff78221f0f1d7c62f121aa452b5871dd478781e` |
| `docs/adr/README.md` | `architecture_decisions` | `architecture_decisions` | 8092 | `91fd6a573d358fa384aa12dd0fd531e0ba63a34badc1ab9ac99e34f7cfcd290f` |
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
| `pyproject.toml` | `repository_root` | `repository_root` | 3131 | `ee98fc1c2af43153cc026117348e8d081b29f086471cd2dfbdbd4c842ee18bcc` |
| `release-work/repository-review/INDEX.md` | `repository_root` | `repository_root` | 2795 | `860cdfa56635dcb9d659c6f6191831f19b18adfd09d49068249636e4eb3ee903` |
| `release-work/repository-review/architecture-summary.md` | `repository_root` | `repository_root` | 7805 | `2e3e394ee3b5ce496ae45416b769603ed329f7671c259fa0924a05032f480bdf` |
| `release-work/repository-review/authority-map.md` | `repository_root` | `repository_root` | 6055 | `a861a54da602b1b042de2cb63df95f5129a140d39eca54920196a6fde84d54db` |
| `release-work/repository-review/document-index.json` | `repository_root` | `repository_root` | 16556 | `89ec20b1d4b3c0472df6a8e9081de81944250edba1991a3d07582c951a072835` |
| `release-work/repository-review/open-questions.md` | `repository_root` | `repository_root` | 5463 | `6d16535ea49b1958bc5822fb49a6fb4789b213372a3edd65ae22474cf9b43367` |
| `release-work/repository-review/persistence-map.md` | `repository_root` | `repository_root` | 5705 | `9a0cc764aadd21db988e94c71fffb89b2d01a4ed331d6d48a451ccf5e19806e3` |
| `release-work/repository-review/projection-control-reconciliation.json` | `repository_root` | `repository_root` | 2201 | `f6fd8f74d9fa1775fd60974fd253134a0113aad40f7791bfc484297a07e9c12e` |
| `release-work/repository-review/projection-control-reconciliation.md` | `repository_root` | `repository_root` | 4205 | `9b93cf59b0309efc261c38718ffce4d8f4ad8d94f84d4fd8107802a9f8e4014a` |
| `release-work/repository-review/provider-capability-matrix.md` | `repository_root` | `repository_root` | 4722 | `046cc99b872986f3f1b7a50b9b8c022781a6966ca7988aa5f0e0d7077efd8844` |
| `release-work/repository-review/reconciliation-ledger.json` | `repository_root` | `repository_root` | 6018 | `b0f66ff4c766d157cdca5543aa51917916f29c5cd4bf3d7c77ba09efa4b1c400` |
| `release-work/repository-review/runtime-dependency-map.md` | `repository_root` | `repository_root` | 5649 | `2fbcd40b9a2aa2500fac1563b99b713a7ca5fda3959519c02fadcb55330c8715` |
| `release-work/repository-review/source-citations.json` | `repository_root` | `repository_root` | 11593 | `063b6e1a19f4d5ad38af515438b86efb04f657943e4b43117c6093381f8da414` |
| `release-work/repository-review/supersession-map.md` | `repository_root` | `repository_root` | 6234 | `dfbbff339dec837a4a2f4d70e1721b26963d3c1c86c131325c8ecfaa00c2abee` |
| `release-work/repository-review/validation-map.md` | `repository_root` | `repository_root` | 5817 | `1ac32caa1b8e54a248e2f087380ae60da993cb178ec5205ce6ef2ed8254a4ff9` |
| `ruff.toml` | `repository_root` | `repository_root` | 341 | `7e426bd138f1d6088d5d2a5cae729ec7e5329d70f24d3fa21801baf67c7f409a` |
| `rules/03-graphiti-memory.mdc` | `configuration` | `configuration` | 603 | `20e03434589675053d739e5fa182eb650aaf821acf0cf757a913e60df7c879a6` |
| `rules/97-graph-engine-architecture.mdc` | `configuration` | `configuration` | 508 | `54defdb3c1813f10a6d102a94cf13b2979059db3ddfcc33d717bfc512ba72be8` |
| `rules/97-graph-layer-boundary.mdc` | `configuration` | `configuration` | 517 | `4ed80a718c926d7a87dad490e339c845a2efc2fa66af2ecdad7cf0c9dd5ffd24` |
| `rules/98-memory-receipt-guard.mdc` | `configuration` | `configuration` | 629 | `e9574ade26a2a38fdc2f1b6bf2613be00e6f906a0a9217c0e30531f413c09c09` |
| `rules/99-graphiti-temporal.mdc` | `configuration` | `configuration` | 436 | `349fb67ba2f191316fb1ebf7be7aeaecde3919a61af19bb507e8804f5688ef27` |
| `scripts/activate_gate.sh` | `operations` | `operations` | 461 | `3300ee59d612adaf379d07bc8b508bc2b8decb66bb680bc3ac5152e98a9d0340` |
| `scripts/activate_guard.sh` | `operations` | `operations` | 838 | `43c1cf62e97af8543a357547ac4bd87aacc6b62693d537596bad02b13a690491` |
| `scripts/create_issues.py` | `operations` | `operations` | 3038 | `472a78e1f7aa4c65722f60581112959a3524349eaeff2cf2b80b62fa5255c0c1` |
| `scripts/install.sh` | `operations` | `operations` | 728 | `355df98cbde85f73aa78627afc3a4131cdf142271e1dbc410c929e41d0536d74` |
| `scripts/preflight.sh` | `operations` | `operations` | 3435 | `3c746e3cbd546e55d74f5b20f5912eeb083916df77c0cc5d92b599c8bf5eb18f` |
| `scripts/validate_release.sh` | `operations` | `operations` | 5054 | `783314a15abcaa48c160fbc2a97d52d59cac68a036d1f7fe404253cde6671a00` |
| `scripts/write_claude_config.py` | `operations` | `operations` | 2447 | `bbdd9d4ece937b24c8c1b15d0d2dce1a1139802c100ad68fc1e8bf5e47f2bb20` |
| `scripts/write_cursor_config.py` | `operations` | `operations` | 1917 | `14be8e8ee2eb7f5c4288ec65a0dcaa17bd52e203cf55dccb05f1a1d51283333d` |
| `skill/SKILL.md` | `skill` | `skill` | 4860 | `9e9af67d407d1448176abf32b476f88d586f7b13d1618fd8f56ced15a2ee3d01` |
| `skill/agents/openai.yaml` | `skill` | `skill` | 344 | `24dde8236b9e5eb99ae579cce0b06185f11da542b5b151bbbbd8f1792a21cb59` |
| `src/l9_graphite_memory/__init__.py` | `production_source` | `production_source` | 1047 | `bdaaeca4c8c5fd919afca78994458087e700b8eabf151320a9d8cbcc1fe259a1` |
| `src/l9_graphite_memory/__main__.py` | `production_source` | `production_source` | 340 | `3eedfcbce155174df8ff657ebd9bead64d6e063f25711bf682bbd00b55293c2f` |
| `src/l9_graphite_memory/adapters/__init__.py` | `production_source` | `adapter` | 680 | `5ff15b8007bc30de3ee38897910e660a2e7c774f3324bc07982bffcaf698a3ea` |
| `src/l9_graphite_memory/adapters/factory.py` | `production_source` | `adapter` | 1973 | `25a93e1579393726cf791f6d274f639cabfba1099844faea929a16a81b7bd05a` |
| `src/l9_graphite_memory/adapters/graphiti_projection.py` | `production_source` | `adapter` | 9385 | `6c85cbbff93bdada12b0eaceb9910beec2ec2171322aa28758709f11c56e4938` |
| `src/l9_graphite_memory/adapters/in_memory_store.py` | `production_source` | `adapter` | 11465 | `6870ce95aebcdb2e3bc0c1e321d48b361c2abec2e4445b361a47accd36879629` |
| `src/l9_graphite_memory/adapters/null_projection.py` | `production_source` | `adapter` | 1633 | `adb60414aa8b0791ed1f9fe5e1a4739b81cde1ac03f858b709c093444749d084` |
| `src/l9_graphite_memory/adapters/sqlite_store.py` | `production_source` | `adapter` | 35159 | `b664b6f25dedc90f39a2ab3a1df35c741b768d3c44fb8fba2f5d460f826a413e` |
| `src/l9_graphite_memory/admission/__init__.py` | `production_source` | `production_source` | 559 | `f2971a2efc56e707a4218e67c8b699910a960734ff4816733da9f9ff7ab974ab` |
| `src/l9_graphite_memory/admission/engine.py` | `production_source` | `production_source` | 5267 | `6179d6043d235d443ae241e24cd4c48cff1e6f86fcd26c9805a41acba60d2e16` |
| `src/l9_graphite_memory/admission/normalization.py` | `production_source` | `production_source` | 3724 | `4229113ab73238f852539ecceffa5aac470d53db84ba39ff549cdd36139470df` |
| `src/l9_graphite_memory/admission/policy.py` | `production_source` | `production_source` | 1062 | `e8113e40824d4cbd5b5e072c177e328dc1a8f1d85d92c8e944795537b1e05cae` |
| `src/l9_graphite_memory/authz/__init__.py` | `production_source` | `production_source` | 466 | `b079cd2be5c21827a96efb4615e4e21018d3461a6c05ef5747d4005155a2ef36` |
| `src/l9_graphite_memory/authz/authenticator.py` | `production_source` | `production_source` | 3010 | `3683a178623628382254d026a6cc41c3bc810ab11377cb5dbda240cb95fe2991` |
| `src/l9_graphite_memory/authz/policy.py` | `production_source` | `production_source` | 2736 | `ea59f525c6a8468b300f2d81ad1e85c3c1e5a159f1b87e1ac818b02617ec8b0d` |
| `src/l9_graphite_memory/circuit_breaker.py` | `production_source` | `production_source` | 2784 | `48348de22f97e017768d47ac47930ed19167e290eeb614d79f474c4bdc7d7499` |
| `src/l9_graphite_memory/cli.py` | `production_source` | `production_source` | 31723 | `ef75aa07b5171308048b1f72fa363d41c0a8f9de4a96a0ebf65e40ab7c24596d` |
| `src/l9_graphite_memory/config/__init__.py` | `production_source` | `production_source` | 448 | `ca7aaaa346d76faa176d150b1fe24a6c29318c3bece0bb48c7c419ef56fcae7f` |
| `src/l9_graphite_memory/config/loader.py` | `production_source` | `production_source` | 5971 | `4289aa930e752341c8f16d2e7149b26343774df296a71f6c049931d2b33fdb55` |
| `src/l9_graphite_memory/config/models.py` | `production_source` | `production_source` | 3777 | `4f427897fa03f26a1fac88ec6014810b54d13e380e5f0021e476644f0ac4b1ca` |
| `src/l9_graphite_memory/contracts/__init__.py` | `production_source` | `contract` | 2663 | `2a7e7fb5ca1372ad6511281db55e06c7102ff5587a432e596216cb3281462b10` |
| `src/l9_graphite_memory/contracts/enums.py` | `production_source` | `contract` | 2303 | `1153fbc9db7437184a79b5b946af07c77a602ee34d73061c5e8d1b79e634a1d9` |
| `src/l9_graphite_memory/contracts/evidence.py` | `production_source` | `contract` | 2887 | `d28ad47ee2b3b83743de8cc57caef44e104335447399f962faadfc197753daf6` |
| `src/l9_graphite_memory/contracts/identity.py` | `production_source` | `contract` | 1348 | `f1f4a7467acd2f60bc40828eea561cbef83bf17dc4aa7b3d0ee844c38410ae98` |
| `src/l9_graphite_memory/contracts/memory.py` | `production_source` | `contract` | 3213 | `fffc735bc5592d03e81451909ed19520357224baa87ae59a35302549d62b71f3` |
| `src/l9_graphite_memory/contracts/privacy.py` | `production_source` | `contract` | 1817 | `2cf69d83577bd96d51e3d54adf20ab394d47fd3f1fd8987c837c7023950b2696` |
| `src/l9_graphite_memory/contracts/profiles.py` | `production_source` | `contract` | 3235 | `ba1550aa91af50829129325fa14af66711f84ee57fdb09085e3859e33de18a54` |
| `src/l9_graphite_memory/contracts/projection.py` | `production_source` | `contract` | 1275 | `1c86e80efef6e4a98e497cec7a421b1678aa6e69ef153521212d5e5d55d999dc` |
| `src/l9_graphite_memory/contracts/receipts.py` | `production_source` | `contract` | 8679 | `f81d04f838440ff3527e29322782fc873b45f8e60c9d004a959c9a873500d8e2` |
| `src/l9_graphite_memory/contracts/requests.py` | `production_source` | `contract` | 4352 | `5413d62fcdd071c9945cad04b2238ea1a3f28258978010cd13d3676fadc206ef` |
| `src/l9_graphite_memory/contracts/temporal.py` | `production_source` | `contract` | 1578 | `6af6a8efd0b8132ef8b7b5d66f1565751fe7ad617be84863ebb94535b6b62951` |
| `src/l9_graphite_memory/curation/__init__.py` | `production_source` | `production_source` | 485 | `b575c39efbe3e37381594714c2057bedc927a42edb868e133506119634d421df` |
| `src/l9_graphite_memory/curation/procedural.py` | `production_source` | `production_source` | 7094 | `270a6095fefbd045b6ea566387df710aa31003c1ed0ba3520803b0570956f9d9` |
| `src/l9_graphite_memory/curation/promotion.py` | `production_source` | `production_source` | 2237 | `327db56e6c19b5e103b0e941348bb31130f3bf1d2da3a5971b32205f0651721e` |
| `src/l9_graphite_memory/curation/retention.py` | `production_source` | `production_source` | 4034 | `1f5fa08bd356fa1dfe0da7ac8a8a8504ab1c82f919a5fb7885d6f8b708beae89` |
| `src/l9_graphite_memory/episode_contract.py` | `production_source` | `production_source` | 2287 | `eb026a581d20ec920a2abe335639eb359b4d5bedd4b72746c69b1d7b1addfab4` |
| `src/l9_graphite_memory/errors.py` | `production_source` | `production_source` | 1356 | `53fd533bae1f5597868bb3a2744f5026532564ae945697e181ae34eb7242a840` |
| `src/l9_graphite_memory/extraction/__init__.py` | `production_source` | `production_source` | 773 | `46a4c59ee8f9aa3efca42c7d301071508946e0053be01a59787bbee200a59ad1` |
| `src/l9_graphite_memory/extraction/atomic.py` | `production_source` | `production_source` | 8945 | `3ba049927a68de4535f5e987f9a6cd0d1d16d962d4d8a876bccee91549a61b49` |
| `src/l9_graphite_memory/extraction/distiller.py` | `production_source` | `production_source` | 4602 | `863de8913dfe0355beec35d641fd6f6177b7527cd4c9a5f23662caf0c642a230` |
| `src/l9_graphite_memory/graphiti_gate_lib.py` | `production_source` | `production_source` | 1409 | `00a4dd1fc7a6462974c78d0ac0e95ece49e2f91ad6375d3c905e7a2c39415c8e` |
| `src/l9_graphite_memory/graphiti_memory_client.py` | `production_source` | `production_source` | 441 | `1d52faf2979e368428395634d1828d55e35603c997cc06158b28f3162d0cdd52` |
| `src/l9_graphite_memory/group_resolver.py` | `production_source` | `production_source` | 5095 | `db2e2aed3150d423e3f2692b9c44fe7d0ae678c51a2fd27d6389e8c39b8421c7` |
| `src/l9_graphite_memory/ingestion/__init__.py` | `production_source` | `production_source` | 525 | `c3982ac8145222069581fba494fa46cedb3e7593114b605e4db2677b57e5cb49` |
| `src/l9_graphite_memory/ingestion/document.py` | `production_source` | `production_source` | 4834 | `216e04a277935884d1c4fcddd2e1b60ffefae674fad0abf68576ed3211476dbd` |
| `src/l9_graphite_memory/ingestion/profiles.py` | `production_source` | `production_source` | 7680 | `35ce6a9a003fd69d214ccde9da9a6dd6d8cce19ac68a40ee7e8634cf1a7efae9` |
| `src/l9_graphite_memory/ingestion/repository.py` | `production_source` | `production_source` | 2769 | `ddb858dc0408d4e8485d6c56868c3e260810b17b175967fa2e9f86692bfb43dc` |
| `src/l9_graphite_memory/integrations/__init__.py` | `production_source` | `integration` | 837 | `af4b8ad2e3de1060882ad621befc78bc98cdc887c174c88d0cd4496a1c8938fb` |
| `src/l9_graphite_memory/integrations/constellation.py` | `production_source` | `integration` | 4822 | `848c4cc5ce0e365c9c56f08252a01e074a20714db7126c27302b0b23f5218721` |
| `src/l9_graphite_memory/integrations/session.py` | `production_source` | `integration` | 4929 | `9e5b0f7c94ba138eb17453a4fefc7d0db44a5e24cd3064f4f69480dec64b6d36` |
| `src/l9_graphite_memory/integrity/__init__.py` | `production_source` | `production_source` | 414 | `a861f632d5719324d1a819ea8b93826d827f742fb6abaa797937a4ae5f821fdd` |
| `src/l9_graphite_memory/integrity/checkpoint.py` | `production_source` | `production_source` | 3000 | `74dbf4dbb31a8dbb17c000870f2e9b4205a92c3cc37873b18a3f68d253276e16` |
| `src/l9_graphite_memory/lineage/__init__.py` | `production_source` | `production_source` | 401 | `3fe9728159d495dc16e043b7200e5f8b1d58a78c80aa30fa17984cbcd86aa6d4` |
| `src/l9_graphite_memory/lineage/replay.py` | `production_source` | `production_source` | 3877 | `152bc47eb4677fb51b26339e904a6bedacfe006b609679b0bd89b2416247bd31` |
| `src/l9_graphite_memory/mcp_tools.py` | `production_source` | `production_source` | 24014 | `d078b6f36187fcb106c55275e0cd75d34209f38a6bfc5756c1d2a14c0ebe9d78` |
| `src/l9_graphite_memory/memory_guard.py` | `production_source` | `production_source` | 8162 | `33a50457fa4694e300e2ca98c97e8447d0ac31e849dfeca98ae949f44d41cb60` |
| `src/l9_graphite_memory/observability/__init__.py` | `production_source` | `production_source` | 373 | `2584326a5b626b9415d794c630aa2df323129384bb6cfe822b9cc3536cd6c6ec` |
| `src/l9_graphite_memory/observability/logging.py` | `production_source` | `production_source` | 2202 | `00dc62ce8a59e14a3b7adaa2ac8cce778ee1355578c7a2534498bdffdd490615` |
| `src/l9_graphite_memory/ports/__init__.py` | `production_source` | `port` | 889 | `e1de907e7bce7dfe72aecb8d88b1066f099c4ffc58c34eb2937802249a631225` |
| `src/l9_graphite_memory/ports/clock.py` | `production_source` | `port` | 542 | `41677121a8599f45abe3b0ce0d02a3893833048e33eb25f6f1ee3be61a651b85` |
| `src/l9_graphite_memory/ports/constellation.py` | `production_source` | `port` | 1839 | `05ae33baee7318cd153cf0a8f4ab27013b9149d75b63419892e1db5ae5a2d1ea` |
| `src/l9_graphite_memory/ports/projection.py` | `production_source` | `port` | 1407 | `b263357f8c75c8148f9f8589ddeaa1e67f6f50c4839f20d7780e6a022f472d43` |
| `src/l9_graphite_memory/ports/record_store.py` | `production_source` | `port` | 3300 | `1a6efa61c6fd99cdd5bf16ccdacc0671b4b03a9d09cdf9ff004a7e52ec106a95` |
| `src/l9_graphite_memory/ports/synthesis.py` | `production_source` | `port` | 931 | `91ab07322c108f0836fe76ddf4bc1adb68a884ade1b1a90511e195202ea756b8` |
| `src/l9_graphite_memory/projections/__init__.py` | `production_source` | `production_source` | 1071 | `5ccda5a5778d3b022bae47d309045018349e55cd5b58c8ad2b4b0834f86cb4df` |
| `src/l9_graphite_memory/projections/compiler.py` | `production_source` | `production_source` | 4117 | `771995f9849309a0a7950edcccf06788b5201d346400b99953405ef642f33733` |
| `src/l9_graphite_memory/projections/contracts.py` | `production_source` | `production_source` | 9433 | `6360805fd2e76ef00ca4c24cdf8b2f394341fc2a02bdfee4e236d31920d181a7` |
| `src/l9_graphite_memory/projections/manifest.py` | `production_source` | `production_source` | 1906 | `5db04dab939b37816ba3458842f927a51163e1dd7f695d97c701946b47cc915a` |
| `src/l9_graphite_memory/projections/render.py` | `production_source` | `production_source` | 3436 | `60e63f65776f9ee28e92f506840a13b9beaaf8a81277bbc500471e1e96218997` |
| `src/l9_graphite_memory/prune.py` | `production_source` | `production_source` | 1471 | `14275d14e1ecfab70c036ee095b01b38d4a61ee639e51f1558aeef092fa7b341` |
| `src/l9_graphite_memory/rate_limiter.py` | `production_source` | `production_source` | 2443 | `3e8f5bf2eb62284f1514d5f4211ff8efddcd3e7f02ad7f0576ae46012c070a5f` |
| `src/l9_graphite_memory/recovery/__init__.py` | `production_source` | `production_source` | 520 | `1cf5cd83050380dc590eb81674e9e02d5c9092aca1661ed43050e2f78dd83433` |
| `src/l9_graphite_memory/recovery/write_queue.py` | `production_source` | `production_source` | 6280 | `8c0f6a71217daa86a619c54c71dc6fb8fb5bd5e15d12ccb7b7680706d0e2610a` |
| `src/l9_graphite_memory/resources/defaults.yaml` | `production_source` | `production_source` | 568 | `0d1e8d2d520504a197af9885d7d7d08797ef3f4bf1b11f24b1fee417c9bd3ff0` |
| `src/l9_graphite_memory/resources/group_registry.yaml` | `production_source` | `production_source` | 1339 | `104626fb987d50bf6ca63902ca4abb16b810db70fa272ab0cc8e0875fe51b825` |
| `src/l9_graphite_memory/resources/memory_contract.yaml` | `production_source` | `production_source` | 947 | `f01e8c8307cf923bbc16981cfda2862f93c5f0968a624ff460cd9f748f989030` |
| `src/l9_graphite_memory/resources/projections/schema.json` | `production_source` | `production_source` | 10204 | `e2aca10d7f45010ba218e2c594dbfa015d03c60a2215928ae3e6ca86eb25ecbe` |
| `src/l9_graphite_memory/retrieval/__init__.py` | `production_source` | `production_source` | 634 | `090e3caf5486287a3e9d187e3803c6388be3a4a30b90b7f97ca2b58e99bc5350` |
| `src/l9_graphite_memory/retrieval/budget.py` | `production_source` | `production_source` | 3497 | `a68b7388f63e7aa30b37ef31828a459977fa43d40fa3d3b14df1703a606b551e` |
| `src/l9_graphite_memory/retrieval/planner.py` | `production_source` | `production_source` | 7115 | `19d5220ceb506ccb4ad858045e1c7d8eea9c9d96d25d888a6c668e32b1d49333` |
| `src/l9_graphite_memory/retrieval/query_classifier.py` | `production_source` | `production_source` | 3000 | `1b284ba33567302de353328f20ac4e7a5823ec4e5d8f6fd0e0b22ef0169eefe7` |
| `src/l9_graphite_memory/retrieval/ranking.py` | `production_source` | `production_source` | 5421 | `aa8f23ab1e0dd7a4292c1a0c248b1088209550610bf15cbcb011c88daea92bb3` |
| `src/l9_graphite_memory/runtime.py` | `production_source` | `production_source` | 2674 | `8899e41bfc73f90acaf9397b0e8868a73c59170e5f072bb34cf1ad6e63cc1a6e` |
| `src/l9_graphite_memory/schema/__init__.py` | `production_source` | `production_source` | 463 | `bf15b09553664252c7252825a423e57db0bcf11bdb33b581db24c845db397af3` |
| `src/l9_graphite_memory/schema/registry.py` | `production_source` | `production_source` | 3525 | `a1affd46713d6d642fae2ea877233c909f0ad219c5fb0013a95d4b7686873738` |
| `src/l9_graphite_memory/schema/upcasters.py` | `production_source` | `production_source` | 6510 | `3cddb07d4008b26357fdccee226cfafc50d233cf873c2ef7ba98bda8568b07a1` |
| `src/l9_graphite_memory/sdk.py` | `production_source` | `production_source` | 1742 | `2787d2190dbdff713e732402848458af8fbc4752926fde00edbb420570ad021f` |
| `src/l9_graphite_memory/secrets.py` | `production_source` | `production_source` | 6790 | `09ae550d20ee1e0e9e84cc938a24b189a7cc031d8ef626cff358bd693ae6771d` |
| `src/l9_graphite_memory/server.py` | `production_source` | `production_source` | 10912 | `aebec0f3b8c4b9054dddfc62800df428eefddb0938bddc6d96a775de55da2296` |
| `src/l9_graphite_memory/services/__init__.py` | `production_source` | `service` | 401 | `a612ba4493e84650ac3df695bd3d459ae188b7d345a0ab743284c29475383fd4` |
| `src/l9_graphite_memory/services/memory_service.py` | `production_source` | `service` | 31439 | `6389f7544da1920e7d9d1bcfbc96e6b25843204f5bd93d88dacc2d4f73eb8e6c` |
| `src/l9_graphite_memory/services/outbox_worker.py` | `production_source` | `service` | 7217 | `a430a3844f33b9173c617c210fc8a2c80bab65a89c05ca541ff6f6786deee7b1` |
| `src/l9_graphite_memory/transport.py` | `production_source` | `production_source` | 8401 | `f1bf70775c259398ec118b99fc89c799bb12e6c81cd2e35c671fcc7596eccb78` |
| `src/l9_graphite_memory/version.py` | `production_source` | `production_source` | 660 | `21b884e090a4bd09a8af9f46d6fbfd4cf4dbb68eec68f9b604e3c3351d522c9b` |
| `src/l9_graphite_memory/zep_transport.py` | `production_source` | `production_source` | 9054 | `3edbd2c790d6da7f62f91ed4fdc817dbd18b88b422b7038a28cb40716f820972` |
| `tests/conformance/test_store_contract.py` | `tests` | `tests` | 5760 | `47ab61ae615a37037fbad5e5fbfd27fc26205e5ec27d7f73bc325a1a723e31c6` |
| `tests/conftest.py` | `tests` | `tests` | 1474 | `41758ad266277cb2e3e90d5af70807336191f79def1771f5ee4a59c86a5e3f8e` |
| `tests/integration/test_distillation_profiles_sdk.py` | `tests` | `tests` | 2407 | `fca4145c36a9423a061467a5248003acfc0a0d5875342abdc310eeda9cc320f0` |
| `tests/integration/test_mcp.py` | `tests` | `tests` | 985 | `59a76e3c3115b80f4f93be740667268778b67cb8eb084d190ea51c62e528b718` |
| `tests/integration/test_mcp_harvest_tools.py` | `tests` | `tests` | 1474 | `dcee8d7134e19b2a5448eb0589b5ebbd5b60752406dd9fbbea1176e014eee2c1` |
| `tests/integration/test_memory_service.py` | `tests` | `tests` | 9023 | `d3837f71971f36de0c730802fae238bcb1e9d455cf5f7109ea53971236806915` |
| `tests/integration/test_outbox.py` | `tests` | `tests` | 2603 | `d46d574516bda00ea7488314a1edcf4566c0d7b21b86987b1be71e7ab7579c37` |
| `tests/integration/test_privacy_deletion.py` | `tests` | `tests` | 5988 | `f843f9f33dfec07ec4caafdadb353dc95a979daabd6c852a9675f2121cc8beec` |
| `tests/integration/test_procedural_synthesis.py` | `tests` | `tests` | 1878 | `e806d3e67b181dc8f1e1ba538e28c7844466ebdfd9d229aed64670bebd27e458` |
| `tests/integration/test_retention_lineage_phase_lock.py` | `tests` | `tests` | 2824 | `8c7c49b8e02491ec2c62dd2207db9f1436e01fed100148d1fc8178f3be2279bb` |
| `tests/integration/test_write_recovery.py` | `tests` | `tests` | 1491 | `5cdc6ebbd63ccf915fafbeb8b52157f9e42603747b951b00b72a3dda20d29695` |
| `tests/regression/test_assurance_tools.py` | `tests` | `tests` | 1982 | `79f0cb7dae4814c1a6ed73858b9ab47d05518c0dcb6d975d998902e62f6908ef` |
| `tests/regression/test_recursive_alignment.py` | `tests` | `tests` | 1725 | `d111bf628b3e97200b941a596fe9aaf62e728fd33a44974bb956d2842f7893f3` |
| `tests/regression/test_release_shell.py` | `tests` | `tests` | 3274 | `ad6b14c1ae2a8dc7374d4e44175f45a9d8b243d153235026582d03dc10b00888` |
| `tests/regression/test_skill_pack.py` | `tests` | `tests` | 1031 | `9c4348e93021b99d60e6b74e0a115dce2ccf52e2ad25eb3c11891b3ab4d9c61b` |
| `tests/unit/test_atomic_extraction.py` | `tests` | `tests` | 1896 | `36fc3da3c860259f994fe130b15748712ac662983b335974117ca4e7cc0cf58a` |
| `tests/unit/test_authz.py` | `tests` | `tests` | 1534 | `5f6ec6bf799bf3067e06f2c34575fc5d23344b38d67f1f6abaa183554c3f38cb` |
| `tests/unit/test_checkpoint_integrity.py` | `tests` | `tests` | 963 | `b34e5b74b79dad9049724517a940f4264dbd2cf92532b7a12f58041ed6e6468b` |
| `tests/unit/test_cli_parser.py` | `tests` | `tests` | 1101 | `b183fdf21ba4025f79d50b9acd139e5a3cb417df90ad179957c0bec54a2977cd` |
| `tests/unit/test_cli_state.py` | `tests` | `tests` | 1729 | `32c921770c9bb5d5e4aa43f4a0910920779d0317a7e9dbb7869494820822130e` |
| `tests/unit/test_config.py` | `tests` | `tests` | 1056 | `a6a297235c00aa7ba3c755a825b66c33fa54a8bd011ad9aec34bc577229fef9e` |
| `tests/unit/test_constellation_bridge.py` | `tests` | `tests` | 3732 | `ec34116ae031868ac68d2acf4c973fb598b0b2c4e11a3152c67f65a3108d1c44` |
| `tests/unit/test_contracts.py` | `tests` | `tests` | 1735 | `fb770ff175b1807a96e481a76fd7f0950a476f23a479796a343c099e2b329514` |
| `tests/unit/test_gate.py` | `tests` | `tests` | 3890 | `91b48c23861becaf4471836500f4b12021ccd7b4aa20ab21dc3e3cf6c75e4bbd` |
| `tests/unit/test_group_resolver.py` | `tests` | `tests` | 1775 | `415aeeaff0582a2fa75dccde8319e7928394a6330821cf97baa897f20f5fe3b3` |
| `tests/unit/test_http_transport_dialect.py` | `tests` | `tests` | 1582 | `b903e799b4ac9b269e901f81857f89cd29f4fad72f968e47e951e842a5e0713f` |
| `tests/unit/test_ingestion.py` | `tests` | `tests` | 852 | `1ffd2c304764e6c96267741719019d71f01475dfd431dd8485848a3cc90f753a` |
| `tests/unit/test_normalization.py` | `tests` | `tests` | 1226 | `c4abbe50fd9977e44b42350855cf7e2f3ae1a74a163ab4148e67e41bc7e31711` |
| `tests/unit/test_profiles.py` | `tests` | `tests` | 3459 | `ad9ec8611e29eeb4d91ff619a5fb729d53611a2f53985b5cee93dc8994d20f67` |
| `tests/unit/test_projection_compiler.py` | `tests` | `tests` | 6352 | `272445f7505ce477fa0f3e6494a3615e5233bf398b53af1fd1cb8cc248eafb59` |
| `tests/unit/test_projection_manifest_assurance.py` | `tests` | `tests` | 1432 | `20b6060034aa3a91eaccba84a9f529b33444856900715140f2164634df679385` |
| `tests/unit/test_projection_render.py` | `tests` | `tests` | 2881 | `ed4fefb583eb1d8c6e2a4d8d6b72d0de6a8577de30cd54039b40da0d03e8ccfd` |
| `tests/unit/test_projection_strategies.py` | `tests` | `tests` | 5412 | `c5ea7864c623326d599861e15e2a5ab60783b3e7497776ac944b4574de5876ef` |
| `tests/unit/test_query_classifier.py` | `tests` | `tests` | 1133 | `69a8f10343af4f7374db596db852b1b2f0782acbaa1b3eca6feb7249fa3b8cfe` |
| `tests/unit/test_schema_registry.py` | `tests` | `tests` | 964 | `008703c05aeabf16c0f6c03eb16d96cdeea72e7ed24958ffb51bd58a66e775ee` |
| `tests/unit/test_server_principal.py` | `tests` | `tests` | 870 | `ee90435a75d372007b48334e9cbe8b16e05af6a370e4c43af04d34cd9262c982` |
| `tests/unit/test_zep_transport.py` | `tests` | `tests` | 2594 | `130bd0c3c2dd41d9abdb37c1b4e87a4a81d7e0e00c42de25af52ab76915d6dda` |
| `tools/assurance/apply_l9_meta.py` | `assurance` | `assurance` | 5563 | `023c4b21dab4df78ce9835378f4e625d45073ead12477c420a11cf00a1a880bd` |
| `tools/assurance/audit_package_wiring.py` | `assurance` | `assurance` | 3717 | `a3393169a076dfffeca5de396a341737283c4c2e757d3e45bda836324fe8f3e3` |
| `tools/assurance/benchmark_local.py` | `assurance` | `assurance` | 4785 | `b42d3c76d88af1a6337869c8bb988bcd36bfa202b026a66aa139db894ce223e1` |
| `tools/assurance/check_config_drift.py` | `assurance` | `assurance` | 2097 | `e01af6e0cbd31580254bc563be3a4e693acafd981708635b2b80588d07875d11` |
| `tools/assurance/check_l9_meta.py` | `assurance` | `assurance` | 3655 | `29b93ec38c9a77ba05e891b39d700f4b15c51565a9145066376e9fbca7879903` |
| `tools/assurance/check_layer_boundaries.py` | `assurance` | `assurance` | 3341 | `c504e3864969a96f7474641d31dc9d8e25008c871a940ca157c27f5b43e27f92` |
| `tools/assurance/check_memory_write_bypass.py` | `assurance` | `assurance` | 3987 | `54e61339090f56420312a9d6edf63f011e1edb2ad4db4dbb0cc4eed7b24cedbd` |
| `tools/assurance/check_recursive_alignment.py` | `assurance` | `assurance` | 12074 | `90b6f4243fad944323bf11746d6db164c44cdda54670882fed1acf33cff28eca` |
| `tools/assurance/check_secrets.py` | `assurance` | `assurance` | 4482 | `53a76213ff055197716ac304cd8b6dc36152e68070f65dc38fff0975abb332da` |
| `tools/assurance/check_source_quality.py` | `assurance` | `assurance` | 6055 | `1c7f93a3324c77d46e778f2ea776c05ea96cc612efdeb7835f9bdb67f0482266` |
| `tools/assurance/generate_manifest.py` | `assurance` | `assurance` | 7324 | `4fdf809c64dd89bc0a1d299438bd8982dcd87734e26bf10eb3386c8ff7b613ef` |
| `tools/assurance/generate_validation_evidence.py` | `assurance` | `assurance` | 11649 | `565a4408b116097531ba7b598c9642843671cf69df518dd0b6c43d222eb01f68` |
| `tools/assurance/validate_adrs.py` | `assurance` | `assurance` | 2624 | `f1d462e4812c810439e5cd599d594c89ed044b3553e011795dbefe7a3b59777f` |
| `tools/assurance/validate_harvest_coverage.py` | `assurance` | `assurance` | 4282 | `dfb473fea080bb880ff9de2f5e9101bc616d2a4a8ed4a1f17be927d7aae75100` |
| `tools/assurance/validate_manifest.py` | `assurance` | `assurance` | 2418 | `b7a0e2d83cf5a9b4c09d2f83662a719c4c0dd4f91082fc743561f9f191943d56` |
| `tools/assurance/validate_projection_manifests.py` | `assurance` | `assurance` | 2490 | `70679727acfc136b4463e406b9d32ca094e5e2d50a3c151ecdad5fd9819d0a21` |
| `validation/SHA256SUMS` | `validation_evidence` | `validation_evidence` | 108 | `e95dc5e2f3ed08e2565ec0a92976f572f0f84cf66669f71540674c8d85196876` |
| `validation/dist/l9_graphite_memory-2.2.0-py3-none-any.whl` | `validation_evidence` | `validation_evidence` | 145069 | `1c1a737af794562cd92bbdfa42944d37884cd2b3604d443c54bd5968cfa47313` |
| `validation/logs/adr_validation.txt` | `validation_evidence` | `validation_evidence` | 35 | `fd97b964d1e774c0207f8518832b2f6260b8005c655c30ae713b90e0b28bf0c5` |
| `validation/logs/bypass_check.txt` | `validation_evidence` | `validation_evidence` | 50 | `7138de56268f741122706f70a72e61409f2729eabf9284d570d69643834ef520` |
| `validation/logs/committed_secrets.txt` | `validation_evidence` | `validation_evidence` | 188 | `55308238e08d6c7ebafa91909a4938c40cecb03da4e468d8b4b8d99410a1211a` |
| `validation/logs/compileall.txt` | `validation_evidence` | `validation_evidence` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `validation/logs/config_drift.txt` | `validation_evidence` | `validation_evidence` | 69 | `f95f19d2a5faa72ea6018d37ed97baee659c49adce45016d7d56ae7f5fe57b2a` |
| `validation/logs/harvest_coverage.txt` | `validation_evidence` | `validation_evidence` | 101 | `a77c2c5914680700e64b06e52391499d845f15b5cd94bb5959a5f91d9a6ba336` |
| `validation/logs/installed_health.txt` | `validation_evidence` | `validation_evidence` | 441 | `5fc55bfe2bcecd23bdf4b5341638a839067f965dc3259f7f8ea1a90f60f35cbd` |
| `validation/logs/installed_mcp.txt` | `validation_evidence` | `validation_evidence` | 74 | `ebf9b42a68c28f17711c394515c4e08e0cda8dfa1148d6f5d03ee03537c0593b` |
| `validation/logs/installed_resolve.txt` | `validation_evidence` | `validation_evidence` | 137 | `eae6487763b5416bca0bd4e711b38b74b9231186d8682cf75cea4615fc74efd2` |
| `validation/logs/l9_meta.txt` | `validation_evidence` | `validation_evidence` | 83 | `e305e6a7e79c48e68745c71dc7b65912068010b67a512ae8498745be7137adf0` |
| `validation/logs/l9_meta_apply.txt` | `validation_evidence` | `validation_evidence` | 27 | `556b9cc2f4c7d8107d2080dba4a20dceae69c42e1120d86e80222266ac52e3e8` |
| `validation/logs/layer_boundaries.txt` | `validation_evidence` | `validation_evidence` | 80 | `3a9e49589664f3aa63e6e470f64d79e8db7957485afb4027533c1c654e07005b` |
| `validation/logs/local_benchmark.txt` | `validation_evidence` | `validation_evidence` | 659 | `f9c7c643d53920f2a5614900282c19cf07eb76cee39de3ad73bb20f12edc8444` |
| `validation/logs/manifest_validation.txt` | `validation_evidence` | `validation_evidence` | 64 | `884c86b740c839df5e6248bc639d5161d267a149f94b71d80b6d9308d3fad730` |
| `validation/logs/preflight.txt` | `validation_evidence` | `validation_evidence` | 2229 | `9024f92af1af25f7e3de14237695387fb7e994e9df799907d6dd0d4abc32157d` |
| `validation/logs/projection_manifests.txt` | `validation_evidence` | `validation_evidence` | 511 | `69fa3ce535fa3fc7d9a6e71446b6b4209dc4f1e8c728d0e7a22096933703a6ab` |
| `validation/logs/pytest.txt` | `validation_evidence` | `validation_evidence` | 180 | `2d55bbc45910a09de246e06ccadfd9d926f661e890f565c0f9be6c31d6c5a6f4` |
| `validation/logs/recursive_alignment.txt` | `validation_evidence` | `validation_evidence` | 70 | `e5e2d7db7b0c91990f7fdf089e78d343fd212368e0ad3f99c300b5fdd530f993` |
| `validation/logs/shell_syntax.txt` | `validation_evidence` | `validation_evidence` | 23 | `a0c54f351e5a214abe7090433031f08eb3a95539d861058de5c2d7da6309d2d8` |
| `validation/logs/source_quality.txt` | `validation_evidence` | `validation_evidence` | 66 | `03c3a01b1784e4f0533a95c297f690bd1cec3c4b2fcd1efaa86071140de8ac34` |
| `validation/logs/validation_evidence.txt` | `validation_evidence` | `validation_evidence` | 62 | `954e4120f0c8aaddebf08bc2b161caeb965bf1546c8c6979930a9e7c1b112c95` |
| `validation/logs/wheel_build.txt` | `validation_evidence` | `validation_evidence` | 688 | `b7003cb5fe7b93f46c915e7b296d8beee184387947138f3260c28b1941694085` |
| `validation/logs/wheel_install.txt` | `validation_evidence` | `validation_evidence` | 169 | `e7c770a6553f6bda8d0985bf4d9785c89e69630d1a4d8670a7e1030ea1389441` |
| `validation/logs/wiring_audit.txt` | `validation_evidence` | `validation_evidence` | 33 | `668bcca746b179065a9a180b000db04bee513432976676cff0d3c246f44effa0` |
| `validation/validation_checks.jsonl` | `validation_evidence` | `validation_evidence` | 10074 | `58f478f5c10ba61adaa46f31d1421aa893ecd0980a12014abdf71ee7721fe701` |
| `validation/validation_findings.jsonl` | `validation_evidence` | `validation_evidence` | 2717 | `5f2afa8ba52b03d2451510acc296faaddfc3046e5f787c5d769cc560e7edb700` |
| `validation/validation_report.yaml` | `validation_evidence` | `validation_evidence` | 474 | `2edc819b251c24525bf4ba06510ce1c7ddf1932adb7db52cf4dbbbad51dd39f0` |
