# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_graph_intelligence_factory.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Graph-intelligence configuration, composition, and optional dependency (ADR-085)."""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest
from pydantic import ValidationError

from l9_graphite_memory.adapters import NullGraphIntelligence, build_graph_intelligence
from l9_graphite_memory.adapters import neo4j_graph_intelligence as adapter_module
from l9_graphite_memory.config import MemorySettings, load_settings
from l9_graphite_memory.errors import ConfigurationError
from l9_graphite_memory.graph.ports import DEFAULT_RELATIONSHIP_ALLOWLIST


def test_default_is_the_explicit_null_backend() -> None:
    adapter = build_graph_intelligence(MemorySettings())
    assert isinstance(adapter, NullGraphIntelligence)
    assert adapter.capabilities() == ()
    health = adapter.health()
    assert health.enabled is False and health.healthy is True


def test_neo4j_backend_requires_a_uri() -> None:
    with pytest.raises(ValidationError, match="graph_neo4j_uri"):
        MemorySettings(graph_intelligence_backend="neo4j")


def test_relationship_allowlist_rejects_non_type_tokens() -> None:
    with pytest.raises(ValidationError, match="relationship type"):
        MemorySettings(graph_relationship_allowlist=("RELATES_TO", "x]-()-[:Y"))
    assert MemorySettings().graph_relationship_allowlist == DEFAULT_RELATIONSHIP_ALLOWLIST


def test_environment_binds_every_graph_setting(monkeypatch, tmp_path) -> None:
    for key, value in {
        "L9_MEMORY_DATA_DIR": str(tmp_path),
        "L9_MEMORY_STATE_DIR": str(tmp_path),
        "L9_MEMORY_GRAPH_BACKEND": "neo4j",
        "L9_MEMORY_GRAPH_REQUIRED": "true",
        "L9_MEMORY_GRAPH_NEO4J_URI": "bolt://graph.invalid:7687",
        "L9_MEMORY_GRAPH_NEO4J_DATABASE": "graphiti",
        "L9_MEMORY_GRAPH_NEO4J_USER": "l9_graph_reader",
        "L9_MEMORY_GRAPH_NEO4J_PASSWORD": "reader-secret",
        "L9_MEMORY_GRAPH_QUERY_TIMEOUT_MS": "1500",
        "L9_MEMORY_GRAPH_GDS_MAX_NODES": "1000",
        "L9_MEMORY_GRAPH_RELATIONSHIP_ALLOWLIST": "RELATES_TO, MENTIONS",
        "L9_MEMORY_GRAPH_SCHEMA_FINGERPRINT": "a" * 64,
        "L9_MEMORY_GRAPH_LINK_PREDICTION": "yes",
        "L9_MEMORY_GRAPH_MATURITY_CEILING": "beta",
    }.items():
        monkeypatch.setenv(key, value)
    settings = load_settings()
    assert settings.graph_intelligence_backend == "neo4j"
    assert settings.graph_intelligence_required is True
    assert settings.graph_neo4j_database == "graphiti"
    assert settings.graph_query_timeout_ms == 1500
    assert settings.graph_gds_max_nodes == 1000
    assert settings.graph_relationship_allowlist == ("RELATES_TO", "MENTIONS")
    assert settings.graph_expected_schema_fingerprint == "a" * 64
    assert settings.graph_link_prediction_enabled is True
    assert settings.graph_algorithm_maturity_ceiling == "beta"
    assert "reader-secret" not in repr(settings)

    adapter = build_graph_intelligence(settings)
    assert adapter.name == "neo4j"
    assert adapter.config.database == "graphiti"  # type: ignore[attr-defined]
    adapter.close()


def test_selecting_neo4j_without_the_driver_is_a_configuration_error(monkeypatch) -> None:
    monkeypatch.setattr(adapter_module, "_neo4j_module", None)
    settings = MemorySettings(
        graph_intelligence_backend="neo4j", graph_neo4j_uri="bolt://graph.invalid:7687"
    )
    with pytest.raises(ConfigurationError, match="graph-intelligence"):
        build_graph_intelligence(settings)


def test_package_runs_without_the_optional_driver(tmp_path) -> None:
    script = textwrap.dedent(
        f"""
        import os, sys
        sys.modules["neo4j"] = None  # make `import neo4j` raise ImportError
        os.environ["L9_MEMORY_DATA_DIR"] = {str(tmp_path)!r}
        os.environ["L9_MEMORY_STATE_DIR"] = {str(tmp_path)!r}
        from l9_graphite_memory.runtime import build_runtime
        from l9_graphite_memory.adapters import neo4j_graph_intelligence as module
        assert module._neo4j_module is None
        runtime = build_runtime()
        assert runtime.graph_intelligence.name == "none"
        runtime.close()
        print("ok")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
