# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/runtime.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Composition root for CLI, MCP server, and workers."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from l9_graphite_memory.active.client import ActiveMemoryBinding
from l9_graphite_memory.adapters import (
    NullGraphIntelligence,
    build_active_memory,
    build_graph_intelligence,
    build_store,
)
from l9_graphite_memory.adapters.factory import build_projection_runtime
from l9_graphite_memory.authz import build_local_principal
from l9_graphite_memory.config import MemorySettings, load_settings
from l9_graphite_memory.contracts import (
    MemoryPrincipal,
    OperationStatus,
    ReadinessFamily,
    ReadinessReport,
)
from l9_graphite_memory.graph.algorithm_policy import AlgorithmMaturity, AlgorithmPolicy
from l9_graphite_memory.graph.ports import GraphIntelligencePort
from l9_graphite_memory.graph.service import GraphIntelligenceService, GraphServiceConfig
from l9_graphite_memory.group_resolver import GroupResolution, resolve_group
from l9_graphite_memory.observability import configure_logging
from l9_graphite_memory.projections.runtime import graph_projection_adapter
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.version import MEMORY_SCHEMA_VERSION, PACKAGE_VERSION

#: The capability families a full-capability deployment proves independently.
READINESS_FAMILIES: tuple[str, ...] = (
    "canonical",
    "projection",
    "graph",
    "active_store",
    "awareness_bus",
)


def _disabled_active_memory() -> ActiveMemoryBinding:
    return build_active_memory(MemorySettings())


def _run_sync(coroutine: Coroutine[Any, Any, Any]) -> None:
    """Run adapter teardown from a synchronous close, inside or outside a loop."""

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coroutine)
        return
    loop.create_task(coroutine)


@dataclass
class MemoryRuntime:
    settings: MemorySettings
    service: MemoryService
    # Structural graph intelligence is a sibling of the projection adapter,
    # composed here and never reached around MemoryService authority (ADR-086).
    graph_intelligence: GraphIntelligencePort = field(default_factory=NullGraphIntelligence)
    graph_service: GraphIntelligenceService | None = None
    # Ephemeral multi-agent state (presence, leases, context, awareness) is
    # composed beside canonical memory and never inside it (ADR-065..068);
    # active-memory degradation never reaches a canonical read or write.
    active_memory: ActiveMemoryBinding = field(default_factory=_disabled_active_memory)

    async def readiness(self) -> ReadinessReport:
        """Report every capability family on its own evidence (ADR-097).

        Canonical, projection, graph, active store and awareness bus are
        probed independently. A family marked required that is absent or
        unproven fails the aggregate; an optional family only degrades it.
        """

        health = self.service.health()
        families: list[ReadinessFamily] = []
        reasons: list[str] = []

        store_healthy = bool(health.store.get("healthy"))
        families.append(
            _family(
                "canonical",
                selected=True,
                required=True,
                healthy=store_healthy,
                detail=dict(health.store),
                reasons=reasons,
            )
        )

        projection_selected = self.service.projections.enabled
        projection_healthy = bool(health.projection.get("healthy", True))
        projection_detail = dict(health.projection)
        projection_detail["outbox_backlog"] = health.outbox_backlog
        # An enabled projection is a selected capability: its failure keeps
        # the process from reporting ready, exactly as the health status
        # ``partial`` already did for ``/readyz`` before families existed.
        families.append(
            _family(
                "projection",
                selected=projection_selected,
                required=projection_selected,
                healthy=projection_selected and projection_healthy,
                detail=projection_detail,
                reasons=reasons,
            )
        )

        if self.graph_service is not None:
            graph = self.graph_service.capability_report(refresh=True)
            graph_detail = graph.model_dump(mode="json")
            graph_selected = bool(graph.backend.get("enabled"))
            graph_healthy = graph_selected and bool(graph.backend.get("healthy"))
            families.append(
                _family(
                    "graph",
                    selected=graph_selected,
                    required=self.settings.graph_intelligence_required,
                    healthy=graph_healthy,
                    detail=graph_detail,
                    reasons=reasons,
                    ready=graph.ready,
                )
            )
        else:
            families.append(
                _family(
                    "graph",
                    selected=False,
                    required=self.settings.graph_intelligence_required,
                    healthy=False,
                    detail={"enabled": False},
                    reasons=reasons,
                )
            )

        active = await self.active_memory.health()
        families.append(
            _family(
                "active_store",
                selected=active.enabled,
                required=self.active_memory.required,
                healthy=active.enabled and "error" not in active.store,
                detail={**active.deployment, **active.store},
                reasons=reasons,
            )
        )
        families.append(
            _family(
                "awareness_bus",
                selected=active.enabled,
                required=self.active_memory.required,
                healthy=active.enabled and "error" not in active.bus,
                detail={**active.deployment, **active.bus},
                reasons=reasons,
            )
        )

        ready = all(family.ready for family in families)
        if not ready:
            status = OperationStatus.FAILED
        elif any(family.selected and not family.healthy for family in families):
            status = OperationStatus.PARTIAL
        else:
            status = OperationStatus.COMPLETE
        return ReadinessReport(
            status=status,
            ready=ready,
            full_capability=all(family.selected and family.healthy for family in families),
            package_version=PACKAGE_VERSION,
            schema_version=MEMORY_SCHEMA_VERSION,
            families=tuple(families),
            degraded_reasons=tuple(reasons),
            checked_at=self.service.clock.now(),
        )

    def close(self) -> None:
        try:
            self.graph_intelligence.close()
        finally:
            try:
                _run_sync(self.active_memory.close())
            finally:
                self.service.store.close()


def _family(
    name: str,
    *,
    selected: bool,
    required: bool,
    healthy: bool,
    detail: dict[str, Any],
    reasons: list[str],
    ready: bool | None = None,
) -> ReadinessFamily:
    family_reasons: list[str] = []
    if required and not selected:
        family_reasons.append(f"{name} is required but not configured")
    elif selected and not healthy:
        family_reasons.append(f"{name} is unhealthy")
    if ready is None:
        ready = (selected and healthy) if required else True
    reasons.extend(family_reasons)
    return ReadinessFamily(
        name=name,
        selected=selected,
        required=required,
        healthy=healthy,
        ready=ready,
        detail=detail,
        reasons=tuple(family_reasons),
    )


def build_runtime(config_path: str | Path | None = None) -> MemoryRuntime:
    settings = load_settings(config_path)
    configure_logging(settings.log_level, json_output=settings.json_logs)
    store = build_store(settings)
    # Legacy settings yield the one scalar adapter as a one-target runtime;
    # manifest settings yield every compiled target. Either way the service
    # receives the runtime, never a raw manifest (ADR-084).
    try:
        projections = build_projection_runtime(settings)
        graph_intelligence = build_graph_intelligence(settings)
        active_memory = build_active_memory(settings)
    except Exception:
        store.close()
        raise
    service = MemoryService(store, projections)
    service.initialize()
    return MemoryRuntime(
        settings=settings,
        service=service,
        graph_intelligence=graph_intelligence,
        graph_service=build_graph_service(settings, service, graph_intelligence),
        active_memory=active_memory,
    )


def build_graph_service(
    settings: MemorySettings,
    service: MemoryService,
    port: GraphIntelligencePort,
) -> GraphIntelligenceService:
    """Compose graph intelligence over the same store and namespace policy (ADR-087)."""

    return GraphIntelligenceService(
        service.store,
        port,
        namespace_policy=service.namespace_policy,
        projection=graph_projection_adapter(service.projections),
        config=GraphServiceConfig(
            max_runtime_ms=settings.graph_query_timeout_ms,
            relationship_allowlist=settings.graph_relationship_allowlist,
            algorithm_policy=AlgorithmPolicy(
                maturity_ceiling=AlgorithmMaturity(settings.graph_algorithm_maturity_ceiling),
                link_prediction_enabled=settings.graph_link_prediction_enabled,
            ),
            required=settings.graph_intelligence_required,
        ),
    )


def _local_namespaces_configured(settings: MemorySettings) -> bool:
    """True when YAML/env supplied explicit local ACL claims (ADR-006)."""

    return any(
        (
            settings.local_read_namespaces,
            settings.local_write_namespaces,
            settings.local_promote_namespaces,
            settings.local_maintain_namespaces,
        )
    )


def local_principal_for_resolution(
    settings: MemorySettings,
    resolution: GroupResolution,
    *,
    include_workspace: bool = True,
) -> MemoryPrincipal:
    """Build the CLI/stdio principal for a resolved group.

    When ``local_*_namespaces`` are configured, those claims are the sole ACL
    source — caller-supplied ``--group-id`` / resolved group must still match
    the grant (ADR-006). Unconfigured local mode stays repository-scoped from
    the resolution only (no implicit administrator).
    """

    if _local_namespaces_configured(settings):
        principal = build_local_principal(
            settings,
            read_namespaces=settings.local_read_namespaces,
            write_namespaces=settings.local_write_namespaces,
            promote_namespaces=settings.local_promote_namespaces,
            maintain_namespaces=settings.local_maintain_namespaces,
        )
    elif not resolution.group_id:
        principal = build_local_principal(
            settings,
            read_namespaces=(),
            write_namespaces=(),
            promote_namespaces=(),
            maintain_namespaces=(),
        )
    else:
        read_values = [resolution.group_id]
        if include_workspace and resolution.group_id != settings.workspace_namespace:
            read_values.append(settings.workspace_namespace)
        write_namespaces = () if resolution.readonly else (resolution.group_id,)
        principal = build_local_principal(
            settings,
            read_namespaces=tuple(read_values),
            write_namespaces=write_namespaces,
            promote_namespaces=write_namespaces,
            maintain_namespaces=write_namespaces,
        )
    return principal.model_copy(
        update={
            "is_admin": settings.local_is_admin,
            "is_global_admin": settings.local_is_global_admin,
        }
    )


def resolve_local_context(
    settings: MemorySettings,
    *,
    cwd: Path | None = None,
    explicit_group: str | None = None,
) -> tuple[GroupResolution, MemoryPrincipal]:
    resolution = resolve_group(cwd, explicit=explicit_group, settings=settings)
    return resolution, local_principal_for_resolution(settings, resolution)
