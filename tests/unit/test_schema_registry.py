# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_schema_registry.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from l9_graphite_memory.schema import schema_registry
from l9_graphite_memory.schema import upcasters as _upcasters  # noqa: F401
from l9_graphite_memory.version import MEMORY_SCHEMA_VERSION


def test_legacy_episode_upcasts_to_v2() -> None:
    record = schema_registry.read_record(
        {
            "name": "legacy-name",
            "episode_body": "A durable lesson",
            "source": "text",
            "source_description": "legacy",
            "reference_time": "2026-01-01T00:00:00+00:00",
            "group_id": "repo-a",
            "kind": "observation",
        }
    )
    assert record.schema_version == MEMORY_SCHEMA_VERSION
    assert record.namespace == "repo-a"
    assert record.content == "A durable lesson"
