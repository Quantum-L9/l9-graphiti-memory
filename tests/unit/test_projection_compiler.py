# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_projection_compiler.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-26
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from l9_graphite_memory.errors import ConfigurationError
from l9_graphite_memory.projections import (
    compile_projection,
    compiled_projection_json,
    load_projection_manifest,
    parse_projection_manifest_data,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "config" / "projections" / "facts-v8.yaml"


def valid_manifest_data() -> dict[str, object]:
    return {
        "api_version": "memory.quantum-l9.dev/v1",
        "kind": "Projection",
        "metadata": {
            "name": "facts",
            "version": 8,
            "status": "shadow",
        },
        "spec": {
            "providers": [
                {
                    "id": "graphiti-primary",
                    "type": "graphiti_mcp",
                    "target": "primary",
                    "required": False,
                },
                {
                    "id": "zep-primary",
                    "type": "zep",
                    "target": "primary",
                    "required": False,
                },
            ],
            "source": {
                "event_types": [
                    "memory.record.project",
                    "memory.record.supersede",
                    "memory.record.erase",
                ],
                "minimum_schema_version": "2.1.0",
            },
            "authority": {
                "record_store": "canonical",
                "vector_is_authoritative": False,
            },
            "render": {
                "template": "facts.render.v3",
                "fields": [
                    "record_id",
                    "tenant_id",
                    "namespace",
                    "content",
                ],
                "normalization": "unicode-nfc",
                "chunk_policy": "atomic-record-v1",
            },
            "embedding": {
                "ownership": "provider",
                "model": "embedding-model@revision-1",
                "dimensions": 1536,
                "distance": "cosine",
                "similarity_space": "facts-v8-test",
                "cache_policy": "content-addressed-v1",
            },
            "scope": {
                "required": ["tenant_id", "namespace"],
                "fail_closed": True,
            },
            "replay": {
                "ordering": "tenant-subject-stream-sequence",
                "strategy": "partitioned",
                "partition_key": "tenant_id",
                "side_effects": "prohibited",
            },
            "determinism": {
                "structural": "exact",
                "render": "exact",
                "embedding_mode": "provider-managed",
                "retrieval_mode": "bounded-equivalence",
            },
            "deletion": {
                "propagation": [
                    "projection",
                    "vector_index",
                    "cache",
                    "summary",
                ],
                "attestation_required": True,
            },
            "slo": {
                "incremental_lag_warning_seconds": 30,
                "incremental_lag_critical_seconds": 120,
                "query_p95_milliseconds": 250,
                "query_p99_milliseconds": 750,
                "rebuild_maximum_seconds": 21600,
                "deletion_attestation_deadline_seconds": 86400,
                "dead_letter_maximum_count": 0,
            },
        },
    }


def test_example_manifest_compiles_deterministically() -> None:
    manifest = load_projection_manifest(MANIFEST_PATH)
    first = compile_projection(manifest)
    second = compile_projection(manifest)
    assert compiled_projection_json(first) == compiled_projection_json(second)
    assert first.compiled_artifact_digest == second.compiled_artifact_digest
    assert [target.identity for target in first.targets] == [
        "facts:v8:graphiti_mcp:primary",
        "facts:v8:zep:primary",
    ]


def test_manifest_rejects_unknown_fields() -> None:
    value = valid_manifest_data()
    value["unexpected"] = True
    with pytest.raises(ConfigurationError, match="extra"):
        parse_projection_manifest_data(value)


def test_manifest_rejects_authoritative_vector_state() -> None:
    value = deepcopy(valid_manifest_data())
    spec = value["spec"]
    assert isinstance(spec, dict)
    authority = spec["authority"]
    assert isinstance(authority, dict)
    authority["vector_is_authoritative"] = True
    with pytest.raises(ConfigurationError, match="cannot be authoritative"):
        parse_projection_manifest_data(value)


@pytest.mark.parametrize("missing_scope", ["tenant_id", "namespace"])
def test_manifest_rejects_missing_required_scope(
    missing_scope: str,
) -> None:
    value = deepcopy(valid_manifest_data())
    spec = value["spec"]
    assert isinstance(spec, dict)
    scope = spec["scope"]
    assert isinstance(scope, dict)
    scope["required"] = [
        item
        for item in scope["required"]
        if item != missing_scope
    ]
    with pytest.raises(ConfigurationError, match="scope is missing"):
        parse_projection_manifest_data(value)


def test_manifest_rejects_duplicate_provider_target_identity() -> None:
    value = deepcopy(valid_manifest_data())
    spec = value["spec"]
    assert isinstance(spec, dict)
    providers = spec["providers"]
    assert isinstance(providers, list)
    duplicate = deepcopy(providers[0])
    duplicate["id"] = "graphiti-secondary-id"
    providers.append(duplicate)
    with pytest.raises(ConfigurationError, match="identities must be unique"):
        parse_projection_manifest_data(value)


def test_manifest_rejects_unpinned_embedding_model() -> None:
    value = deepcopy(valid_manifest_data())
    spec = value["spec"]
    assert isinstance(spec, dict)
    embedding = spec["embedding"]
    assert isinstance(embedding, dict)
    embedding["model"] = "embedding-model"
    with pytest.raises(ConfigurationError, match="pinned revision"):
        parse_projection_manifest_data(value)
