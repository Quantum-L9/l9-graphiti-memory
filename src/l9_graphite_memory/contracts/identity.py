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

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Local realization of the global ``l9.identity-assertion/v1`` schema.
#: This is evidence of ActorIdentity resolution. It grants no role or namespace.
IDENTITY_ASSERTION_SCHEMA = "l9.identity-assertion/v1"
MEMORY_PRODUCT_REF = "l9-graphiti-memory:product/l9-graphite-memory"
ACTOR_REGISTRY_PREFIX = "l9.actor-registry/global@1#"
SURFACE_REGISTRY_PREFIX = "l9.surface-registry/global@1#"
IdentityAssertionResult = Literal["resolved", "unknown", "ambiguous", "invalid"]

#: Provenance a resolved assertion must carry (global contract
#: ``l9.contract/provenance-and-coordinate@1``). Memory consumes the assertion;
#: it never re-derives ActorIdentity, fetches ``.github``, or reads the
#: Cursor-Governance registry. These coordinates pin which producer and which
#: authority revision the consumed evidence must come from.
IDENTITY_RESOLVER_REF = "l9.cursor-governance/resolver/runtime-agent-identity@1"
IDENTITY_PROJECTION_REF = "l9.projection/cursor-governance-identity@1"
IDENTITY_BINDING_REF = "l9.cursor-governance/identity-binding@1"
AGENT_BINDINGS_REF = "l9.cursor-governance/agent-bindings@2"
#: Exact ``Quantum-L9/.github`` main revision the consumed identity projection
#: must have been generated from. Bumped only when the global identity
#: authority is re-projected; a stale or candidate revision is rejected.
GLOBAL_IDENTITY_AUTHORITY_REVISION = "9b27869dd893fcd28f76f99c9184a90435542c76"
#: ``governing_coordinates`` keys a resolved assertion must carry.
REQUIRED_GOVERNING_COORDINATES: tuple[str, ...] = (
    "global_identity_authority_revision",
    "identity_projection_ref",
    "identity_projection_digest",
    "actor_registry_digest",
    "surface_registry_digest",
    "identity_binding_ref",
    "agent_bindings_ref",
)
#: Governing coordinates that must carry a ``sha256:<64 lowercase hex>`` digest.
SEMANTIC_DIGEST_COORDINATES: tuple[str, ...] = (
    "identity_projection_digest",
    "actor_registry_digest",
    "surface_registry_digest",
)


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
    maintain_namespaces: tuple[str, ...] = ()
    is_admin: bool = False
    is_global_admin: bool = False
    auth_method: str = "local"

    @property
    def can_cross_tenant(self) -> bool:
        """Whether this principal may act on records outside its own tenant.

        Tenant isolation (ADR-006, ADR-024) applies to every access. ``is_admin``
        grants elevated authority *within* the principal's tenant only; crossing
        the tenant boundary requires the distinct, explicitly modelled
        ``is_global_admin`` claim so tenant-admin and global-superadmin
        semantics are never collapsed into a single boolean.
        """

        return self.is_global_admin

    @property
    def audit_subject(self) -> str:
        """Stable subject string for receipts and logs."""

        return f"{self.tenant_id}:{self.principal_id}"


class IdentityResolvedDimensions(BaseModel):
    """Identity dimensions carried by ``l9.identity-assertion/v1``.

    The global schema names these members and does not mark each one required.
    Consequential Tier-2 checks live with the signed-agent door, not here.
    """

    model_config = ConfigDict(extra="allow")

    release_identity: str | None = None
    runtime_identity: str | None = None
    constellation_identity: str | None = None
    actor_identity: str | None = None
    surface_identity: str | None = None


class IdentityAssertion(BaseModel):
    """Typed ``l9.identity-assertion/v1`` evidence. Not an authorization grant.

    Required members are the global schema's required fields. Optional global
    members stay optional. Unknown keys are ignored so a smuggled role or
    namespace cannot become a claim this model exposes.
    """

    model_config = ConfigDict(extra="ignore")

    schema_name: str = Field(min_length=1)
    subject_ref: str = Field(min_length=1)
    product_ref: str = Field(min_length=1)
    resolved_dimensions: IdentityResolvedDimensions
    evidence_refs: list[str]
    resolver_ref: str = Field(min_length=1)
    governing_coordinates: dict[str, Any]
    result: IdentityAssertionResult
    assertion_digest: str = Field(min_length=1)
    bindings: list[str] | None = None
    governance_profile_ref: str | None = None
    unknowns: list[Any] | None = None
    provenance: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def _lift_schema_coordinate(cls, data: Any) -> Any:
        """Accept the global wire key ``schema`` as ``schema_name``.

        Pydantic reserves ``schema`` on BaseModel, and this repository forbids
        field aliases, so the coordinate is renamed before validation. The
        wire object itself is unchanged.
        """

        if not isinstance(data, dict) or "schema" not in data:
            return data
        lifted = dict(data)
        lifted["schema_name"] = lifted.pop("schema")
        return lifted
