# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/topology_publication/conftest.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-23

"""Synthetic bundle builders for the topology publication adapter suites.

The builders mimic the producer's bundle shape (manifest with real sha256
content hashes) so integrity verification passes for well-formed synthetic
plans and adversarial cases can corrupt one property at a time.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from l9_graphite_memory.contracts import MemoryPrincipal

PACKET_ID = "packet:" + "1" * 64
PACKET_SEMANTIC_HASH = "sha256:" + "2" * 64
PLAN_ID = "publication-plan:" + "3" * 64
PLAN_SEMANTIC_HASH = "sha256:" + "4" * 64
NAMESPACE = "l9.constellation/repo-a"
FIXED_TIME = "2026-03-01T00:00:00Z"

ENTITY_IDS = ("repo:alpha", "cap:alpha-serve", "artifact:alpha-spec")
EVIDENCE_IDS = ("evidence:alpha-1", "evidence:alpha-2")
RMP_IDS = ("packet:" + "a" * 64,)


def sha256_of(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def write_bundle(root: Path, documents: dict[str, Any], manifest_extra: dict[str, Any]) -> Path:
    """Write documents plus a manifest whose hashes match their exact bytes."""
    root.mkdir(parents=True, exist_ok=True)
    entries = []
    for relative, document in sorted(documents.items()):
        content = json.dumps(document, sort_keys=True).encode("utf-8") + b"\n"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        entries.append(
            {
                "path": relative,
                "media_type": "application/json",
                "content_hash": sha256_of(content),
                "size_bytes": len(content),
            }
        )
    manifest = {
        "manifest_version": "1.0.0",
        "files": entries,
        "created_at": FIXED_TIME,
        "artifact_hash": "sha256:" + "f" * 64,
        **manifest_extra,
    }
    (root / "manifest.json").write_bytes(
        json.dumps(manifest, sort_keys=True).encode("utf-8") + b"\n"
    )
    return root


def make_topology_bundle(root: Path) -> Path:
    """A minimal topology packet bundle carrying the synthetic id universe."""
    return write_bundle(
        root,
        {
            "packet.json": {
                "packet_id": PACKET_ID,
                "packet_type": "l9.topology-packet",
                "packet_version": "1.1.0",
                "inputs": {
                    "repository_model_packets": [
                        {"packet_id": RMP_IDS[0], "packet_type": "l9.repository-model"}
                    ]
                },
            },
            "payload/repository-records.json": [
                {
                    "repository_id": ENTITY_IDS[0],
                    "artifact_ids": [ENTITY_IDS[2]],
                    "capability_ids": [ENTITY_IDS[1]],
                }
            ],
            "payload/evidence.json": [
                {"evidence_id": EVIDENCE_IDS[0]},
                {"evidence_id": EVIDENCE_IDS[1]},
            ],
        },
        {
            "packet_id": PACKET_ID,
            "packet_type": "l9.topology-packet",
            "packet_version": "1.1.0",
            "semantic_hash": PACKET_SEMANTIC_HASH,
        },
    )


def make_intent(
    *,
    content: str,
    idempotency_key: str,
    namespace: str = NAMESPACE,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "operation": "memory.ingest",
        "request": {
            "namespace": namespace,
            "memory_class": "observation",
            "content": content,
            "provenance": {
                "source": "l9-constellation-topology",
                "source_id": PACKET_ID,
                "extraction_method": "topology-entity-aggregation",
                "transformed_at": FIXED_TIME,
            },
            "confidence": {
                "score": 1.0,
                "method": "explicit",
                "evidence_count": 1,
                "policy_version": "confidence/v1",
                "calibrated_at": FIXED_TIME,
            },
            "valid_from": FIXED_TIME,
            "metadata": metadata
            or {
                "topology_packet_id": PACKET_ID,
                "topology_semantic_hash": PACKET_SEMANTIC_HASH,
            },
            "idempotency_key": idempotency_key,
            "dry_run": False,
        },
    }


def make_candidate(
    *,
    candidate_id: str,
    status: str,
    content: str | None = None,
    idempotency_key: str | None = None,
    intent_key: str | None = None,
    entity_ids: tuple[str, ...] = (ENTITY_IDS[0],),
    evidence_ids: tuple[str, ...] = (),
    rmp_ids: tuple[str, ...] = RMP_IDS,
) -> dict[str, Any]:
    key = idempotency_key or f"l9-topology-publication/v3:{candidate_id}"
    return {
        "candidate_id": candidate_id,
        "candidate_kind": "entity",
        "source_topology_entity_ids": list(entity_ids),
        "source_evidence_ids": list(evidence_ids),
        "source_repository_model_packet_ids": list(rmp_ids),
        "eligibility": {"status": status, "reasons": [f"synthetic.{status}"]},
        "lowering": {
            "source_fields": ["name"],
            "confidence_level": "high",
            "confidence_method": "explicit",
            "conflict_status": "none",
        },
        "memory_intent": make_intent(
            content=content or f"Synthetic fact for {candidate_id}",
            idempotency_key=intent_key if intent_key is not None else key,
        ),
        "idempotency_key": key,
    }


def make_plan_document(
    candidates: list[dict[str, Any]],
    *,
    skipped: int = 0,
    plan_version: str = "1.0.0",
    plan_type: str = "l9.topology-publication-plan",
    plan_id: str = PLAN_ID,
    plan_semantic_hash: str = PLAN_SEMANTIC_HASH,
    source_packet_id: str = PACKET_ID,
    source_semantic_hash: str = PACKET_SEMANTIC_HASH,
) -> dict[str, Any]:
    return {
        "plan_type": plan_type,
        "plan_version": plan_version,
        "plan_id": plan_id,
        "producer": {"name": "l9-constellation-topology", "version": "2.0.0"},
        "source_topology_packet": {
            "packet_id": source_packet_id,
            "packet_type": "l9.topology-packet",
            "packet_version": "1.1.0",
            "uri": f"packet://{source_packet_id}",
            "semantic_hash": source_semantic_hash,
            "validation_status": "passed",
        },
        "source_topology_semantic_hash": source_semantic_hash,
        "policy": {"policy_id": "synthetic/1.0.0"},
        "policy_hash": "sha256:" + "5" * 64,
        "candidates": candidates,
        "skipped_candidates": [
            {
                "source_kind": "relationship",
                "source_id": f"edge:skipped-{index}",
                "reason": "policy.edge_type_not_selected",
            }
            for index in range(skipped)
        ],
        "diagnostics": [],
        "semantic_hash": plan_semantic_hash,
        "published_at": FIXED_TIME,
    }


def make_plan_bundle(
    root: Path,
    candidates: list[dict[str, Any]],
    *,
    skipped: int = 0,
    **plan_overrides: Any,
) -> Path:
    document = make_plan_document(candidates, skipped=skipped, **plan_overrides)
    return write_bundle(
        root,
        {"publication-plan.json": document},
        {
            "packet_id": document["plan_id"],
            "packet_type": document["plan_type"],
            "packet_version": document["plan_version"],
            "semantic_hash": document["semantic_hash"],
        },
    )


@pytest.fixture
def topology_principal() -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id="topology-operator",
        tenant_id="tenant-a",
        read_namespaces=(NAMESPACE,),
        write_namespaces=(NAMESPACE,),
    )
