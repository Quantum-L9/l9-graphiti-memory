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


def test_a_top_level_client_id_argument_is_refused_before_a_tool_runs() -> None:
    # A public OAuth client id is not an actor; a caller must not be able to
    # name one in tool arguments. The principal here is not OAuth and not
    # admin, so the only refusal available is the caller-identity argument.
    assert caller_identity_argument({"client_id": "client-public"}) == "client_id"
    service = MemoryService(InMemoryRecordStore(), NullProjection())
    tools = MCPToolApplication(service)
    principal = MemoryPrincipal(
        principal_id="agent",
        tenant_id="tenant",
        auth_method="signed-agent",
    )
    with pytest.raises(AuthorizationError, match="cannot set client_id"):
        tools.call(principal, "memory.health", {"client_id": "client-public"})


def _consequential_tools() -> list[str]:
    from l9_graphite_memory.mcp_tools import (
        _CANONICAL_HANDLER_METHODS,
        _READ_ONLY_HANDLERS,
    )

    return sorted(
        name
        for name, handler in _CANONICAL_HANDLER_METHODS.items()
        if handler not in _READ_ONLY_HANDLERS
    )


def test_the_read_only_allowlist_names_only_real_handlers() -> None:
    from l9_graphite_memory.mcp_tools import (
        _CANONICAL_HANDLER_METHODS,
        _READ_ONLY_HANDLERS,
    )

    # A stale or misspelled entry would silently gate nothing and hide a
    # mutating handler that was meant to be listed as consequential.
    assert set(_READ_ONLY_HANDLERS) <= set(_CANONICAL_HANDLER_METHODS.values())
    for state_changing in (
        "_close",
        "_record_reuse",
        "_invalidate_source",
        "_phase_lock",
        "_retention",
        "_delete",
        "_promote",
        "_synthesize_procedures",
    ):
        assert state_changing not in _READ_ONLY_HANDLERS


@pytest.mark.parametrize("tool", _consequential_tools())
def test_every_consequential_tool_refuses_an_unproven_oauth_actor(tool: str) -> None:
    class _NoService:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"MemoryService.{name} must not be reached")

    tools = MCPToolApplication(_NoService())  # type: ignore[arg-type]
    principal = MemoryPrincipal(
        principal_id="client-public",
        tenant_id="tenant",
        auth_method="oauth",
        agent_id="client-public",
        write_namespaces=("repo",),
    )
    with pytest.raises(AuthorizationError, match="not an actor"):
        tools.call(principal, tool, {"namespace": "repo"})
