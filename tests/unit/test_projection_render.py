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
    projection = compile_projection(
        load_projection_manifest(MANIFEST_PATH)
    )
    record = canonical_record()
    first = render_projection(projection, record)
    second = render_projection(projection, record)
    assert first == second
    assert first.content_digest == second.content_digest
    assert first.embedding_cache_key == second.embedding_cache_key
    assert "Café projection output" in first.normalized_text
    assert "Cafe\u0301 projection output" not in first.normalized_text


def test_render_changes_when_declared_content_changes() -> None:
    projection = compile_projection(
        load_projection_manifest(MANIFEST_PATH)
    )
    first_record = canonical_record()
    second_record = canonical_record()
    second_record["content"] = "Different canonical content."
    first = render_projection(projection, first_record)
    second = render_projection(projection, second_record)
    assert first.content_digest != second.content_digest
    assert first.embedding_cache_key != second.embedding_cache_key


def test_render_rejects_missing_declared_field() -> None:
    projection = compile_projection(
        load_projection_manifest(MANIFEST_PATH)
    )
    record = canonical_record()
    del record["namespace"]
    with pytest.raises(ProjectionError, match="namespace"):
        render_projection(projection, record)
