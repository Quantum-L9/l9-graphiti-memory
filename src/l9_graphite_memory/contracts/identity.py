# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/identity.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Authenticated principal and namespace ownership contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MemoryPrincipal(BaseModel):
    """Server-derived identity used for every authorization decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str = Field(min_length=1, max_length=200)
    tenant_id: str = Field(min_length=1, max_length=200)
    organization_id: str = Field(default="default", min_length=1, max_length=200)
    workspace_id: str = Field(default="default", min_length=1, max_length=200)
    user_id: str | None = Field(default=None, max_length=200)
    agent_id: str | None = Field(default=None, max_length=200)
    roles: tuple[str, ...] = ()
    read_namespaces: tuple[str, ...] = ()
    write_namespaces: tuple[str, ...] = ()
    promote_namespaces: tuple[str, ...] = ()
    is_admin: bool = False
    auth_method: str = "local"

    @property
    def audit_subject(self) -> str:
        """Stable subject string for receipts and logs."""

        return f"{self.tenant_id}:{self.principal_id}"
