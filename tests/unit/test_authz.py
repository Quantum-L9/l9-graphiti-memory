# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_authz.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

import pytest

from l9_graphite_memory.authz import NamespacePolicy, TokenAuthenticator
from l9_graphite_memory.config import TokenPrincipalConfig
from l9_graphite_memory.contracts import AuthorizationAction, MemoryPrincipal
from l9_graphite_memory.errors import AuthenticationError, AuthorizationError


def test_namespace_glob_grant() -> None:
    principal = MemoryPrincipal(
        principal_id="p",
        tenant_id="t",
        read_namespaces=("repo-*",),
        write_namespaces=("repo-a",),
    )
    policy = NamespacePolicy()
    assert policy.require(principal, AuthorizationAction.READ, "repo-b").allowed
    with pytest.raises(AuthorizationError):
        policy.require(principal, AuthorizationAction.WRITE, "repo-b")


def test_token_authenticator_uses_server_claims() -> None:
    config = TokenPrincipalConfig(
        principal_id="agent",
        tenant_id="tenant",
        read_namespaces=("repo-a",),
    )
    principal = TokenAuthenticator({"secret-token": config}).authenticate("Bearer secret-token")
    assert principal.principal_id == "agent"
    assert principal.auth_method == "bearer"


def test_token_authenticator_carries_every_configured_grant() -> None:
    """F-01: a bearer principal must not lose a configured grant in transit."""

    config = TokenPrincipalConfig(
        principal_id="nightly",
        tenant_id="tenant",
        read_namespaces=("repo-a",),
        write_namespaces=("repo-w",),
        promote_namespaces=("repo-p",),
        maintain_namespaces=("repo-a",),
    )
    principal = TokenAuthenticator({"tok": config}).authenticate("Bearer tok")

    for field in (
        "read_namespaces",
        "write_namespaces",
        "promote_namespaces",
        "maintain_namespaces",
    ):
        assert getattr(principal, field) == getattr(config, field), field
    assert NamespacePolicy().evaluate(principal, AuthorizationAction.MAINTAIN, "repo-a").allowed


def test_token_authenticator_rejects_invalid_token() -> None:
    auth = TokenAuthenticator({})
    with pytest.raises(AuthenticationError):
        auth.authenticate("Bearer invalid")
