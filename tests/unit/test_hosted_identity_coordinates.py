"""Hosted identity coordinates fail closed without server-verified evidence.

An OAuth client id is not an actor and not a surface. Constellation identity
does not apply to this hosted service. These tests do not claim a live Auth0
audience grant.
"""

from __future__ import annotations

import pytest

from l9_graphite_memory.adapters import InMemoryRecordStore, NullProjection
from l9_graphite_memory.contracts import MemoryPrincipal
from l9_graphite_memory.contracts.identity import (
    MEMORY_PRODUCT_REF,
    caller_identity_argument,
    hosted_coordinates_from_oauth,
    oauth_actor_ref,
    oauth_grant_claims_operator,
)
from l9_graphite_memory.errors import AuthorizationError
from l9_graphite_memory.mcp_tools import MCPToolApplication
from l9_graphite_memory.services import MemoryService


def test_client_id_alone_does_not_resolve_an_actor_or_a_surface() -> None:
    coordinates = hosted_coordinates_from_oauth(
        product_ref=MEMORY_PRODUCT_REF,
        release_digest=None,
        runtime_id=None,
        verified_actor_ref="client-public",
        evidence_refs=("client-public",),
        oauth_client_id="client-public",
        surface_evidence_ref="client-public",
    )
    assert coordinates.actor_ref is None
    assert coordinates.surface_ref is None
    assert coordinates.constellation == "not_applicable"
    assert coordinates.product_ref == MEMORY_PRODUCT_REF


def test_verified_evidence_distinct_from_the_client_resolves_the_actor() -> None:
    assert (
        oauth_actor_ref(
            verified_actor_ref="l9.actor-registry/global@1#agent",
            evidence_refs=("sha256:" + "ab" * 32,),
            oauth_client_id="client-public",
        )
        == "l9.actor-registry/global@1#agent"
    )


def test_caller_supplied_actor_arguments_are_named() -> None:
    assert caller_identity_argument({"actor": "forged"}) == "actor"
    assert caller_identity_argument({"namespace": "repo"}) is None


def test_an_oauth_admin_bit_is_not_an_operator_grant() -> None:
    assert oauth_grant_claims_operator("oauth", is_admin=True, is_global_admin=False)
    assert not oauth_grant_claims_operator("signed-agent", is_admin=True, is_global_admin=False)


def test_oauth_consequential_write_fails_closed_without_actor_evidence() -> None:
    service = MemoryService(InMemoryRecordStore(), NullProjection())
    tools = MCPToolApplication(service)
    principal = MemoryPrincipal(
        principal_id="client-public",
        tenant_id="tenant",
        auth_method="oauth",
        agent_id="client-public",
        write_namespaces=("repo",),
    )
    with pytest.raises(AuthorizationError, match="not an actor"):
        tools.call(
            principal,
            "memory.write_agent",
            {"namespace": "repo", "content": "hello"},
        )


def test_oauth_admin_principal_is_refused_before_a_tool_runs() -> None:
    service = MemoryService(InMemoryRecordStore(), NullProjection())
    tools = MCPToolApplication(service)
    principal = MemoryPrincipal(
        principal_id="client-public",
        tenant_id="tenant",
        auth_method="oauth",
        is_admin=True,
    )
    with pytest.raises(AuthorizationError, match="not an operator"):
        tools.call(principal, "memory.health", {})
