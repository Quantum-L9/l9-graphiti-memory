# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_config.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from l9_graphite_memory.config import load_settings


def test_local_namespace_claims_parse_from_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("L9_MEMORY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("L9_MEMORY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("L9_MEMORY_LOCAL_READ_NAMESPACES", "repo-a, workspace")
    monkeypatch.setenv("L9_MEMORY_LOCAL_WRITE_NAMESPACES", "repo-a")
    monkeypatch.setenv("L9_MEMORY_LOCAL_PROMOTE_NAMESPACES", "")
    monkeypatch.setenv("L9_MEMORY_LOCAL_IS_ADMIN", "true")

    settings = load_settings()
    assert settings.local_read_namespaces == ("repo-a", "workspace")
    assert settings.local_write_namespaces == ("repo-a",)
    assert settings.local_promote_namespaces == ()
    assert settings.local_is_admin is True
