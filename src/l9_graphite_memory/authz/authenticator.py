# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/authz/authenticator.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Server-side bearer token authentication."""

from __future__ import annotations

import hashlib
import hmac

from l9_graphite_memory.config import MemorySettings, TokenPrincipalConfig
from l9_graphite_memory.contracts import MemoryPrincipal
from l9_graphite_memory.errors import AuthenticationError


def _principal_from_config(
    config: TokenPrincipalConfig, *, auth_method: str
) -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id=config.principal_id,
        tenant_id=config.tenant_id,
        organization_id=config.organization_id,
        workspace_id=config.workspace_id,
        user_id=config.user_id,
        agent_id=config.agent_id,
        roles=config.roles,
        read_namespaces=config.read_namespaces,
        write_namespaces=config.write_namespaces,
        promote_namespaces=config.promote_namespaces,
        is_admin=config.is_admin,
        is_global_admin=config.is_global_admin,
        auth_method=auth_method,
    )


class TokenAuthenticator:
    """Compare tokens in constant time and return configured principal claims."""

    def __init__(self, tokens: dict[str, TokenPrincipalConfig]) -> None:
        self._entries = tuple(tokens.items())

    def authenticate(self, authorization_header: str | None) -> MemoryPrincipal:
        if not authorization_header:
            raise AuthenticationError("missing Authorization header")
        scheme, _, supplied = authorization_header.partition(" ")
        if scheme.lower() != "bearer" or not supplied:
            raise AuthenticationError("Authorization must use Bearer scheme")
        for configured_token, config in self._entries:
            if hmac.compare_digest(supplied, configured_token):
                return _principal_from_config(config, auth_method="bearer")
        fingerprint = hashlib.sha256(supplied.encode("utf-8")).hexdigest()[:12]
        raise AuthenticationError(f"invalid bearer token fingerprint={fingerprint}")


def build_local_principal(
    settings: MemorySettings,
    *,
    read_namespaces: tuple[str, ...],
    write_namespaces: tuple[str, ...],
    promote_namespaces: tuple[str, ...] | None = None,
    maintain_namespaces: tuple[str, ...] = (),
) -> MemoryPrincipal:
    """Create the trusted local principal used by CLI and stdio MCP."""

    return MemoryPrincipal(
        principal_id=settings.local_principal_id,
        tenant_id=settings.local_tenant_id,
        organization_id=settings.local_organization_id,
        workspace_id=settings.local_workspace_id,
        user_id=settings.local_user_id,
        agent_id=settings.local_agent_id,
        roles=("local-operator",),
        read_namespaces=read_namespaces,
        write_namespaces=write_namespaces,
        promote_namespaces=write_namespaces
        if promote_namespaces is None
        else promote_namespaces,
        maintain_namespaces=maintain_namespaces,
        auth_method="local",
    )
