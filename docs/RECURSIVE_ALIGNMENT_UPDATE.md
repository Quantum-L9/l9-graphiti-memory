# Recursive Alignment Update

## Alignment Summary

The v2.1 pack was a strong memory replatform but not fully aligned to the active L9 architecture contract. It described the constellation boundary without implementing it, used Gate terminology for a local stateful hook guard, lacked `L9_META`, retained one deprecated transport reference in accepted architecture law, and had no recursive-alignment gate. v2.2 corrects those defects while preserving the repository's dependency-package identity.

Local deterministic alignment is complete. Credentialed Gate, Graphiti, Zep, hosted CI, and production migration proof remain external blockers and are not represented as passed.

## Source Authority Used

1. Latest user instruction to execute the alignment update
2. Supplied recursive-alignment kernel
3. Accepted repository ADRs as corrected by ADR-059 through ADR-062
4. Executable contracts and tests
5. Older pack material only where consistent with the authorities above

## Critical Violations

| ID | Severity | Rule broken | Evidence before correction | Impact | Correction | Owner layer | Blocks release |
|---|---|---|---|---|---|---|---:|
| RAA-001 | critical | TransportPacket-only inter-node boundary and Gate-only egress | ADR-026 had no executable bridge | Node consumers could invent direct routing or duplicate the shared packet model | Added injected packet/factory/Gate ports and immutable `GateMemoryBridge` | integration | true |
| RAA-002 | critical | Gate owns routing/admission, not workflow state | `graphiti_gate_lib.py` read and interpreted local state | Local hooks appeared to be a second Gate with workflow ownership | Replaced implementation with typed `memory_guard`; retained a thin compatibility shim only | hook adapter | true |

## High Violations

| ID | Severity | Rule broken | Evidence before correction | Impact | Correction | Owner layer | Blocks release |
|---|---|---|---|---|---|---|---:|
| RAA-003 | high | Every tracked file carries L9 metadata | Zero v2.1 files contained `L9_META` | Ownership and layer provenance could not be verified from the ZIP | Added inline metadata for comment-safe source plus manifest metadata for every packaged file | repository | true |
| RAA-004 | high | Deprecated inter-node envelope rejected | Accepted ADR text still named and considered the retired model | Architecture law contradicted the active transport contract | Removed all references and added a deterministic absence test | architecture | true |
| RAA-005 | high | No print-based production or assurance output | CLI, server, worker, scripts, and assurance tools called `print` | Structured output policy was not enforceable | Replaced calls with explicit stdout/stderr writes and added an AST gate | all executable layers | true |
| RAA-006 | high | CI gates match claimed contracts | No recursive alignment or layer-direction checker existed | Future changes could silently reintroduce drift | Added alignment, layer, metadata, and behavior gates to preflight and release validation | assurance | true |

## Medium Violations

| ID | Severity | Rule broken | Evidence before correction | Impact | Correction | Owner layer | Blocks release |
|---|---|---|---|---|---|---|---:|
| RAA-007 | medium | No generated cache artifacts | Source ZIP contained `__pycache__` and `.pyc` files | Dirty and non-reproducible source pack | Removed caches and made the alignment scanner reject them | packaging | true |
| RAA-008 | medium | Canonical snake_case schema fields | Hook parser accepted camel-case field aliases | Boundary schema drift remained hidden | Hook request now accepts canonical snake_case only | hook adapter | false |
| RAA-009 | medium | Engine does not import chassis or infra surfaces | Boundary was documented but not mechanically enforced | Future dependency inversion remained possible | Added AST layer-boundary audit | assurance | true |
| RAA-010 | medium | Manifested metadata and provenance | Release manifest carried hashes only | Non-commentable files had no metadata carrier | Advanced manifest to v2 with per-file `l9_meta` | packaging | true |

## Unknowns

- Canonical Python import path and exact constructor contract for the shared TransportPacket model: **Unknown**
- Canonical Gate client package and production dispatch receipt schema: **Unknown**
- Production routing policy and authorized node inventory: owned by Gate, unavailable here
- Credentialed provider and production migration outcomes: externally blocked

## Boundary Map

| Concern | Owner | This repository behavior |
|---|---|---|
| Memory contracts, admission, temporal state, receipts | memory core | owned |
| Canonical persistence | `RecordStore` adapter | owned through port and conformance tests |
| Provider graph/vector state | Graphiti/Zep projection adapters | optional and rebuildable |
| Inter-node packet model | external constellation contract owner | injected, never duplicated |
| Routing, destination resolution, inter-node admission | Gate | invoked through `GateClientPort` only |
| Workflow orchestration | external orchestrator | explicitly not owned |
| HTTP authentication and server lifecycle | optional service adapter | isolated from core |
| Editor mutation check | local receipt guard | verifies evidence only |
| CI and packaging | repository root | owns validation, not runtime behavior |

## Transport Packet Compliance

- Canonical packet model is not redefined in this package.
- Root packets are created by an injected factory.
- Follow-up packets use `derive_or_with_hop`.
- Parent mutation, trace drift, and missing lineage growth fail closed.
- Typed memory intents are the payload boundary.
- No raw dictionary fallback exists in the constellation bridge.

## Gate Routing Compliance

- `GateMemoryBridge` has no destination argument.
- No peer URL or node registry exists at the constellation boundary.
- Every root or follow-up dispatch goes through `GateClientPort.dispatch`.
- Gate receipts must match packet and trace identifiers.
- Provider transports are explicitly classified as non-node adapters.

## Authority Boundary Compliance

- Core memory modules cannot import CLI, server, provider transport, secret loader, authenticator, or integration surfaces.
- Service authentication establishes `MemoryPrincipal`; domain authorization remains in memory core.
- Optional worker behavior is bounded to outbox processing and does not own orchestration.
- The local receipt guard owns no routing or workflow graph.

## File Structure Compliance

Allowed root structure is enforced by `check_recursive_alignment.py`. Generated caches are forbidden. Contracts, ports, integrations, adapters, services, hooks, rules, tests, and assurance tools are placed under explicit owner paths. All packaged files receive manifest metadata; comment-safe tracked files also carry inline `L9_META`.

## Schema Field Compliance

- Domain models use snake_case and Pydantic `extra="forbid"` where persistence or authority is involved.
- Field aliases are rejected by the recursive checker.
- YAML is loaded only with `yaml.safe_load` and validated through typed models at runtime boundaries.
- Shared transport types are injected rather than duplicated.
- Platform-owned YAML schemas such as GitHub Actions are not redefined as domain models.

## Security Observability Compliance

- Builtin `eval`, `exec`, `compile`, and `print` calls are forbidden by AST scan.
- YAML unsafe loaders are forbidden.
- Structured logs supplement immutable receipts and are not the audit source of truth.
- Sensitive content is redacted before canonical storage and is not emitted as structured log fields.
- Replay and lifecycle evidence remain append-only.
- In-memory stores are test adapters; production canonical state is bounded by SQLite persistence and configured query limits.

## Testing Validation Compliance

- Constellation bridge behavior tests prove Gate-only dispatch, immutable derivation, trace preservation, and lineage growth.
- Guard behavior tests cover disabled, missing, fresh, stale, read-only, and phase-lock cases.
- Recursive regression tests scan transport, metadata, layer, field, security, and file-structure invariants.
- Existing store, service, projection, privacy, recovery, extraction, schema, CLI, MCP, and installed-wheel tests remain active.

## Overbuilt Versus Underbuilt

| Classification | Finding | Resolution |
|---|---|---|
| overbuilt | Local hook component was described as a Gate | Reduced to a receipt verifier |
| overbuilt | Compatibility naming implied constellation ownership | Kept only as thin shims |
| underbuilt | Inter-node transport decision lacked code | Added generic injected bridge |
| underbuilt | File provenance was absent | Added dual inline and manifest carriers |
| underbuilt | Alignment law was not executable | Added deterministic assurance and behavior tests |
| intentionally absent | Canonical packet model and Gate implementation | Remain with their authoritative repositories |

## Correction Roadmap

1. **Completed:** classify artifact and lock ownership boundaries.
2. **Completed:** add Gate-only TransportPacket bridge and behavior tests.
3. **Completed:** separate local receipt guard from constellation Gate.
4. **Completed:** remove deprecated transport references and field aliases.
5. **Completed:** add L9 metadata carriers and manifest v2.
6. **Completed:** enforce layer, security, schema, file, and test invariants.
7. **Completed:** rerun local tests, preflight, wheel, manifest, and clean-room validation.
8. **External:** execute credentialed Gate and provider staging tests.
9. **External:** rehearse production migration and rollback.

## Remaining Production Proof

The authoritative consolidated statement is in `docs/REMAINING_PRODUCTION_PROOF.md`. The injected Gate boundary is intentionally generic because the canonical Gate and TransportPacket APIs were unavailable inside the pack. The remaining work is decomposed into issue-pack IDs `RP-001` through `RP-009` and remains release-blocking until evidence is attached and reviewed.

## Minimum Safe Next Action

Complete `RP-001` and `RP-002`, then execute `RP-003` in a disposable staging consumer while capturing packet, trace, lineage, authorization, destination-resolution, receipt-correlation, failure, replay, and rollback evidence.

## Convergence Block

```yaml
convergence:
  recursive_passes_completed: 10
  local_violations_remaining: 0
  local_alignment_score: 100
  external_alignment_status: blocked_on_canonical_gate_and_provider_evidence
  scope_expansion_required: false
  stop_condition: all_in_pack_rules_enforced_and_two_adversarial_scans_stable
```
