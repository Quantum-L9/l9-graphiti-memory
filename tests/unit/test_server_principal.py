# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_server_principal.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.server import _stdio_principal


def test_stdio_principal_uses_configured_claims_without_implicit_admin() -> None:
    settings = MemorySettings(
        local_read_namespaces=("repo-a", "workspace"),
        local_write_namespaces=("repo-a",),
        local_promote_namespaces=(),
    )
    principal = _stdio_principal(settings)
    assert principal.read_namespaces == ("repo-a", "workspace")
    assert principal.write_namespaces == ("repo-a",)
    assert principal.promote_namespaces == ()
    assert principal.is_admin is False
