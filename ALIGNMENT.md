# L9 Recursive Alignment

## Classification

- Artifact: dependency package with an SDK facade and optional service, provider, hook, and constellation adapters
- Repository: `Quantum-L9/l9-graphiti-memory`
- Release: `2.2.0`
- Canonical state owner: `MemoryService` plus `RecordStore`
- Inter-node authority: external canonical TransportPacket owner plus Gate
- Provider state: rebuildable projection only

## Binding boundaries

1. Internal memory operations use typed memory contracts, never shared transport as a substitute for domain law.
2. Inter-node memory intent uses the injected canonical packet model and `GateMemoryBridge`. The authoritative implementation is `constellation-node-sdk` (`Quantum-L9/Gate_SDK` `v1.0.1`) via `CanonicalTransportPacketFactory` and `CanonicalGateClient`.
3. Follow-up packets are derived immutably through `derive_or_with_hop` and preserve trace and lineage.
4. Gate alone resolves destination. The bridge has no peer URL, destination field, or node registry.
5. The local editor component is a receipt guard, not constellation Gate. It owns no routing or workflow.
6. Core memory modules do not import CLI, HTTP server, provider transport, secret loading, or integration surfaces.
7. Every packaged file carries `L9_META` through inline metadata, the cryptographic manifest, or both.

## Validation

```bash
python tools/assurance/check_recursive_alignment.py
python tools/assurance/check_layer_boundaries.py
python tools/assurance/check_l9_meta.py
pytest -q
bash scripts/validate_release.sh
```

Production alignment proof remains blocked on the external evidence defined in `docs/REMAINING_PRODUCTION_PROOF.md` and issue-pack IDs `RP-003` through `RP-009`. RP-001 binds TransportPacket; RP-002 binds `GateClient` from the same package. A live Gate smoke is still required for release closure.
