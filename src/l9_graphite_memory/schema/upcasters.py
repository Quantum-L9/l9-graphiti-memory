# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/schema/upcasters.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Built-in migrations from legacy episode and v1 memory records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from l9_graphite_memory.admission.normalization import normalize_candidate
from l9_graphite_memory.schema.registry import schema_registry
from l9_graphite_memory.version import MEMORY_SCHEMA_VERSION


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@schema_registry.register("0.2.0-episode", MEMORY_SCHEMA_VERSION)
def episode_to_v2(raw: dict[str, Any]) -> dict[str, Any]:
    content = str(
        raw.get("episode_body") or raw.get("body") or raw.get("content") or ""
    )
    normalization = normalize_candidate(content)
    reference_time = raw.get("reference_time") or raw.get("timestamp") or _now_iso()
    source = str(raw.get("source") or "legacy-episode")
    source_description = str(
        raw.get("source_description") or "legacy episode migration"
    )
    group_id = str(raw.get("group_id") or "legacy")
    name = str(raw.get("name") or f"legacy-{uuid4()}")
    return {
        "record_id": str(raw.get("record_id") or uuid4()),
        "schema_version": MEMORY_SCHEMA_VERSION,
        "tenant_id": str(raw.get("tenant_id") or "legacy"),
        "namespace": group_id,
        "memory_class": str(raw.get("kind") or "observation"),
        "content": normalization.redacted_content,
        "assertion": None,
        "temporal": {
            "valid_from": reference_time,
            "valid_to": None,
            "recorded_at": raw.get("created_at") or _now_iso(),
            "source_observed_at": reference_time,
            "superseded_at": None,
        },
        "provenance": {
            "source": source,
            "source_id": name,
            "source_digest": normalization.original_digest,
            "source_range": None,
            "source_agent_id": None,
            "session_id": None,
            "repository": None,
            "tool": "legacy-migration",
            "model": None,
            "extraction_method": source_description,
            "source_trust": 1.0,
            "transformed_at": _now_iso(),
        },
        "evidence": [],
        "confidence": {
            "score": 1.0,
            "method": "explicit",
            "evidence_count": 0,
            "policy_version": "legacy-migration/v1",
            "calibrated_at": _now_iso(),
        },
        "state": "active",
        "tags": ["legacy"],
        "metadata": {
            "legacy_payload": {
                k: v for k, v in raw.items() if k not in {"episode_body"}
            }
        },
        "normalized_digest": normalization.normalized_digest,
        "original_digest": normalization.original_digest,
        "idempotency_key": f"legacy:{group_id}:{normalization.normalized_digest}",
        "supersedes": [],
        "references": [],
        "consent": None,
        "conflicts_with": [],
        "created_by": "legacy-migration",
        "created_at": raw.get("created_at") or _now_iso(),
    }


@schema_registry.register("1.0.0", MEMORY_SCHEMA_VERSION)
def v1_to_v2(raw: dict[str, Any]) -> dict[str, Any]:
    content = str(raw.get("content") or raw.get("body") or "")
    normalization = normalize_candidate(content)
    raw.setdefault("record_id", str(uuid4()))
    raw["schema_version"] = MEMORY_SCHEMA_VERSION
    raw.setdefault("tenant_id", "legacy")
    raw.setdefault("namespace", str(raw.get("group_id") or "legacy"))
    raw.setdefault("memory_class", str(raw.get("kind") or "observation"))
    raw["content"] = normalization.redacted_content
    raw.setdefault("assertion", None)
    raw.setdefault(
        "temporal",
        {
            "valid_from": raw.get("valid_from") or _now_iso(),
            "valid_to": raw.get("valid_to"),
            "recorded_at": raw.get("recorded_at")
            or raw.get("created_at")
            or _now_iso(),
            "source_observed_at": raw.get("source_observed_at"),
            "superseded_at": raw.get("superseded_at"),
        },
    )
    raw.setdefault(
        "provenance",
        {
            "source": str(raw.get("source") or "legacy-v1"),
            "source_id": raw.get("source_id"),
            "source_digest": normalization.original_digest,
            "source_range": None,
            "source_agent_id": raw.get("agent_id"),
            "session_id": raw.get("session_id"),
            "repository": raw.get("repository"),
            "tool": "legacy-migration",
            "model": None,
            "extraction_method": "legacy-v1-upcast",
            "source_trust": 1.0,
            "transformed_at": _now_iso(),
        },
    )
    raw.setdefault("evidence", [])
    raw.setdefault(
        "confidence",
        {
            "score": float(raw.get("confidence_score", 1.0)),
            "method": "explicit",
            "evidence_count": len(raw.get("evidence") or []),
            "policy_version": "legacy-migration/v1",
            "calibrated_at": _now_iso(),
        },
    )
    raw.setdefault("state", "active")
    raw.setdefault("tags", [])
    raw.setdefault("metadata", {})
    raw["normalized_digest"] = normalization.normalized_digest
    raw["original_digest"] = normalization.original_digest
    raw.setdefault(
        "idempotency_key",
        f"legacy:{raw['namespace']}:{normalization.normalized_digest}",
    )
    raw.setdefault("supersedes", [])
    raw.setdefault("references", [])
    raw.setdefault("consent", None)
    raw.setdefault("conflicts_with", [])
    raw.setdefault("created_by", "legacy-migration")
    raw.setdefault("created_at", _now_iso())
    return raw


@schema_registry.register("2.0.0", "2.1.0")
def v2_0_to_v2_1(raw: dict[str, Any]) -> dict[str, Any]:
    """Add source trust and explicit record references without mutating history."""

    raw = dict(raw)
    raw["schema_version"] = "2.1.0"
    provenance = dict(raw.get("provenance") or {})
    provenance.setdefault("source_trust", 1.0)
    raw["provenance"] = provenance
    raw.setdefault("references", [])
    raw.setdefault("consent", None)
    metadata = dict(raw.get("metadata") or {})
    metadata.setdefault("upcasted_from", "2.0.0")
    raw["metadata"] = metadata
    return raw


@schema_registry.register("2.1.0", MEMORY_SCHEMA_VERSION)
def v2_1_to_v2_2(raw: dict[str, Any]) -> dict[str, Any]:
    """Adopt the structured source_locator contract (ADR-078).

    2.2.0 only adds the optional ``source_locator`` field to provenance and
    evidence entries. A 2.1.0 record never carried one, so the upcast is a pure
    version restamp: absent stays absent and reads back as ``None``.
    """

    raw = dict(raw)
    raw["schema_version"] = MEMORY_SCHEMA_VERSION
    return raw
