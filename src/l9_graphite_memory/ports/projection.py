# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/ports/projection.py
#   layer: port
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Optional graph/semantic projection contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from l9_graphite_memory.contracts import MemoryRecord, RetirementMode

if TYPE_CHECKING:
    from l9_graphite_memory.projections.render import RenderedProjection


class ProjectionHit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: UUID
    score: float = Field(ge=0.0, le=1.0)
    excerpt: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectionEntityHit(BaseModel):
    """An entity-node search hit, before canonical support is bound.

    Graphiti entity search returns entities, not episodes. ``record_id`` is set
    only when the provider already names the canonical record; otherwise the
    graph backend binds support through the entity's episodes (ADR-093).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_uuid: UUID | None = None
    record_id: UUID | None = None
    score: float = Field(ge=0.0, le=1.0)
    #: Position in the provider's own ranking (0 = best). Orders hits whose
    #: scores tie, as when Graphiti's node search returns no score at all.
    rank: int = Field(default=0, ge=0)
    name: str = ""
    namespace: str


class ProjectionAdapter(Protocol):
    name: str
    capabilities: tuple[str, ...]
    # Whether this provider can deactivate a projected record or only remove
    # it. Declared rather than inferred, so the ceiling is machine-readable and
    # a caller can tell whether retirement is reversible at the provider
    # (ADR-076).
    retirement_mode: RetirementMode

    def health(self) -> dict[str, Any]: ...

    def project(self, record: MemoryRecord) -> dict[str, Any]: ...

    def retire(
        self,
        record_id: UUID,
        namespace: str,
        *,
        locator: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """Withdraw a projection because the record is no longer current.

        Retirement and erasure are different operations with different
        authority and different consequences. Retirement says the canonical
        record has been superseded or archived, so the derived projection must
        stop surfacing it; the canonical record keeps its content, its
        lifecycle history, and its evidence. Erasure says the content itself
        must cease to exist, and is driven by a verified deletion receipt.

        Implementations must never redact canonical state or produce deletion
        semantics here (ADR-074).
        """
        ...

    def erase(
        self,
        record_id: UUID,
        namespace: str,
        *,
        locator: str | None = None,
    ) -> dict[str, Any]:
        """Destroy the projected copy under verified privacy erasure."""
        ...

    def search_strategy(
        self,
        strategy: str,
        query: str,
        namespaces: tuple[str, ...],
        *,
        limit: int,
        tenant_id: str,
    ) -> list[ProjectionHit]:
        """Search one strategy inside the tenant-bound scope of ``namespaces``.

        ``tenant_id`` is server-derived from the authenticated principal and
        ``namespaces`` are already authorized. A provider that partitions its
        graph by group must derive each group from both components through
        GraphScopeKey v1 (``graph.scope``) and never from the namespace alone
        (ADR-085).
        """
        ...

    def search_entities(
        self,
        query: str,
        namespaces: tuple[str, ...],
        *,
        limit: int,
        tenant_id: str,
    ) -> list[ProjectionEntityHit]:
        """Entity-node search inside the tenant-bound scope of ``namespaces``.

        Unlike ``search_strategy("graph-search")`` it keeps hits that carry
        no canonical record id, so ``graph.search`` can bind their support
        through the graph backend instead of dropping them (ADR-093).
        """
        ...

    def search(
        self,
        query: str,
        namespaces: tuple[str, ...],
        *,
        limit: int,
        tenant_id: str,
    ) -> list[ProjectionHit]: ...


@runtime_checkable
class RenderedProjectionAdapter(Protocol):
    """A provider adapter that can deliver a compiled render contract.

    In manifest mode the bytes written to a provider are the deterministic
    rendering of the declared canonical fields, produced by the one renderer
    the compiler owns, so the link's ``render_contract_digest`` attests the
    contract that actually produced them (ADR-063, ADR-084). A delivering
    manifest target must bind an adapter with this operation; ``project``
    remains the legacy scalar delivery and renders nothing.
    """

    def project_rendered(
        self, record: MemoryRecord, rendered: RenderedProjection
    ) -> dict[str, Any]:
        """Write ``rendered`` for ``record`` and return a result with a stable ``locator``.

        The provider must receive the rendering as produced, with no fields
        added, dropped, or reshaped by the adapter; the canonical record is
        passed only for identity, namespace, and provider metadata.
        """
