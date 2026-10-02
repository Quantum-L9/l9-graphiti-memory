# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_projection_render.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-26
from __future__ import annotations

from pathlib import Path

import pytest

from l9_graphite_memory.errors import ProjectionError
from l9_graphite_memory.projections import (
    compile_projection,
    load_projection_manifest,
    render_projection,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "config" / "projections" / "facts-v8.yaml"


def canonical_record() -> dict[str, object]:
    return {
        "record_id": "5c689173-a564-43f8-a0fe-cffba19dc7b8",
        "schema_version": "2.2.0",
        "tenant_id": "tenant-a",
        "namespace": "repo-a",
        "memory_class": "decision",
        "content": "Cafe\u0301 projection output must be deterministic.",
        "assertion": {
            "subject": "projection",
            "predicate": "must_be",
            "object": "deterministic",
        },
        "temporal": {
            "valid_from": "2026-07-26T00:00:00Z",
            "valid_to": None,
            "recorded_at": "2026-07-26T00:00:00Z",
        },
        "provenance": {
            "source": "unit-test",
            "source_digest": "a" * 64,
        },
        "confidence": {
            "score": 1.0,
        },
        "tags": ["projection", "determinism"],
    }


def test_render_is_deterministic_and_unicode_normalized() -> None:
    projection = compile_projection(load_projection_manifest(MANIFEST_PATH))
    record = canonical_record()
    first = render_projection(projection, record)
    second = render_projection(projection, record)
    assert first == second
    assert first.content_digest == second.content_digest
    assert first.embedding_cache_key == second.embedding_cache_key
    assert "Café projection output" in first.normalized_text
    assert "Cafe\u0301 projection output" not in first.normalized_text


def test_render_changes_when_declared_content_changes() -> None:
    projection = compile_projection(load_projection_manifest(MANIFEST_PATH))
    first_record = canonical_record()
    second_record = canonical_record()
    second_record["content"] = "Different canonical content."
    first = render_projection(projection, first_record)
    second = render_projection(projection, second_record)
    assert first.content_digest != second.content_digest
    assert first.embedding_cache_key != second.embedding_cache_key


def test_render_rejects_missing_declared_field() -> None:
    projection = compile_projection(load_projection_manifest(MANIFEST_PATH))
    record = canonical_record()
    del record["namespace"]
    with pytest.raises(ProjectionError, match="namespace"):
        render_projection(projection, record)


class RecordingTransport:
    name = "recording"

    def __init__(self) -> None:
        self.writes: list[tuple[str, str, dict[str, object]]] = []

    def health(self) -> dict[str, object]:
        return {"healthy": True}

    def write(self, body: str, group_id: str, kind: str = "observation", **kwargs: object):
        self.writes.append((body, group_id, dict(kwargs)))
        return {"episode_uuid": f"episode-{len(self.writes)}"}

    def call_tool(self, name: str, arguments: dict[str, object] | None = None) -> object:
        return {}

    def list_tools(self) -> list[str]:
        return ["add_memory"]


def test_graphiti_adapter_delivers_the_rendering_byte_for_byte() -> None:
    from l9_graphite_memory.adapters import GraphitiProjection
    from l9_graphite_memory.contracts import (
        EvidenceKind,
        EvidenceRef,
        MemoryClass,
        MemoryRecord,
        Provenance,
    )

    projection = compile_projection(load_projection_manifest(MANIFEST_PATH))
    record = MemoryRecord(
        tenant_id="tenant-a",
        namespace="repo-a",
        memory_class=MemoryClass.DECISION,
        content="Café projection output must be deterministic.",
        provenance=Provenance(source="unit-test"),
        evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="t"),),
        normalized_digest="a" * 64,
        original_digest="b" * 64,
        idempotency_key="k",
        created_by="test",
        tags=("projection",),
    )
    rendered = render_projection(projection, record)
    transport = RecordingTransport()
    adapter = GraphitiProjection(transport)

    result = adapter.project_rendered(record, rendered)

    (body, group_id, kwargs) = transport.writes[0]
    assert body == rendered.normalized_text
    assert group_id == "repo-a"
    assert kwargs["source"] == "text"
    assert kwargs["metadata"]["render_contract_digest"] == projection.render_contract_digest
    assert kwargs["metadata"]["content_digest"] == rendered.content_digest
    assert result["locator"] == "episode-1"
    assert result["render_contract_digest"] == rendered.template_digest
    # Legacy delivery is untouched: the adapter's own JSON payload.
    adapter.project(record)
    legacy_body, _, legacy_kwargs = transport.writes[1]
    assert legacy_kwargs["source"] == "json" and legacy_body.startswith("{")
    assert "tenant_id" not in legacy_body and "tenant_id" in body
    # A hit whose text is the rendering still resolves to the record.
    assert GraphitiProjection._extract_record_id({"content": body}) == record.record_id
    assert GraphitiProjection._extract_record_id({"content": legacy_body}) == record.record_id
