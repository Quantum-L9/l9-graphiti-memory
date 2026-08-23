# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_group_resolver.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from pathlib import Path

from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.group_resolver import load_registry, resolve_group


def test_packaged_registry_is_available() -> None:
    registry = load_registry(MemorySettings())
    assert "l9-graphiti-memory" in registry["repos"]


def test_explicit_group_is_deterministic(tmp_path: Path) -> None:
    result = resolve_group(tmp_path, explicit="repo-a", settings=MemorySettings())
    assert result.group_id == "repo-a"
    assert not result.readonly


def test_forbidden_group_is_readonly(tmp_path: Path) -> None:
    result = resolve_group(tmp_path, explicit="main", settings=MemorySettings())
    assert result.group_id is None
    assert result.readonly


def test_local_resolution_does_not_grant_admin_by_default(tmp_path: Path) -> None:
    from l9_graphite_memory.runtime import local_principal_for_resolution

    settings = MemorySettings()
    resolution = resolve_group(tmp_path, explicit="repo-a", settings=settings)
    principal = local_principal_for_resolution(settings, resolution)
    assert principal.write_namespaces == ("repo-a",)
    assert principal.is_admin is False


def test_local_admin_requires_explicit_setting(tmp_path: Path) -> None:
    from l9_graphite_memory.runtime import local_principal_for_resolution

    settings = MemorySettings(local_is_admin=True)
    resolution = resolve_group(tmp_path, explicit="repo-a", settings=settings)
    principal = local_principal_for_resolution(settings, resolution)
    assert principal.is_admin is True


def test_configured_local_namespaces_constrain_explicit_group_id(
    tmp_path: Path,
) -> None:
    """Issue #20: --group-id must not widen configured local_write_namespaces."""
    import pytest

    from l9_graphite_memory.authz import NamespacePolicy
    from l9_graphite_memory.contracts import AuthorizationAction
    from l9_graphite_memory.errors import AuthorizationError
    from l9_graphite_memory.runtime import local_principal_for_resolution

    settings = MemorySettings(
        local_principal_id="restricted-agent",
        local_agent_id="restricted-agent",
        local_is_admin=False,
        local_read_namespaces=("l9-graphiti-memory",),
        local_write_namespaces=("l9-graphiti-memory",),
        local_promote_namespaces=(),
    )
    resolution = resolve_group(tmp_path, explicit="some-disallowed-namespace", settings=settings)
    principal = local_principal_for_resolution(settings, resolution)

    assert principal.is_admin is False
    assert principal.write_namespaces == ("l9-graphiti-memory",)
    assert principal.read_namespaces == ("l9-graphiti-memory",)
    assert "some-disallowed-namespace" not in principal.write_namespaces

    policy = NamespacePolicy()
    denied = policy.evaluate(principal, AuthorizationAction.WRITE, "some-disallowed-namespace")
    assert denied.allowed is False
    assert "principal is administrator" not in denied.reasons
    assert any("did not match" in reason for reason in denied.reasons)

    allowed = policy.require(principal, AuthorizationAction.WRITE, "l9-graphiti-memory")
    assert allowed.allowed is True

    with pytest.raises(AuthorizationError):
        policy.require(principal, AuthorizationAction.WRITE, "some-disallowed-namespace")
