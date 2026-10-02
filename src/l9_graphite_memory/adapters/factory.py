# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/adapters/factory.py
#   layer: adapter
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Construct configured stores and projections without silent fallback."""

from __future__ import annotations

from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.errors import ConfigurationError
from l9_graphite_memory.ports import ProjectionAdapter, RecordStore
from l9_graphite_memory.projections import (
    CompiledProjectionTarget,
    ProjectionRuntime,
    TargetMode,
    compile_projection,
    load_projection_manifest,
)

from .null_projection import NullProjection
from .sqlite_store import SQLiteRecordStore

#: The only target name bound to the process's provider credentials. Further
#: targets of one provider type would need their own credentials, which this
#: configuration does not yet carry, so they fail closed.
_CREDENTIALED_TARGET = "primary"


def build_store(settings: MemorySettings) -> RecordStore:
    """Construct the configured canonical store. There is no silent fallback."""

    store: RecordStore
    if settings.store_backend == "sqlite":
        store = SQLiteRecordStore(settings.resolved_database_path)
    elif settings.store_backend == "postgres":
        if not settings.postgres_dsn:
            raise ConfigurationError(
                "L9_MEMORY_POSTGRES_DSN is required for the postgres store backend"
            )
        from .postgres_store import PostgresRecordStore

        store = PostgresRecordStore(
            settings.postgres_dsn,
            statement_timeout_ms=settings.postgres_statement_timeout_ms,
        )
    else:
        raise ConfigurationError(f"unsupported store backend: {settings.store_backend}")
    store.initialize()

    # A freshly initialized store reports itself healthy with zero records.
    # Refuse to start quietly in that state when a prior ledger still holds
    # this deployment's memory (ADR-077).
    from l9_graphite_memory.migration.backend_transition import (
        detect_backend_transition,
    )

    report = detect_backend_transition(settings, store)
    if report.blocking:
        store.close()
        raise ConfigurationError(report.describe())
    return store


def build_projection(settings: MemorySettings) -> ProjectionAdapter:
    if settings.projection_backend == "none":
        return NullProjection()
    if settings.projection_backend == "http":
        if not settings.graphiti_mcp_url:
            raise ConfigurationError("GRAPHITI_MCP_URL is required for http projection")
        from l9_graphite_memory.transport import HttpMcpTransport

        from .graphiti_projection import GraphitiProjection

        return GraphitiProjection(
            HttpMcpTransport(url=settings.graphiti_mcp_url, token=settings.graphiti_mcp_token)
        )
    if settings.projection_backend == "zep":
        if not settings.zep_api_key:
            raise ConfigurationError("ZEP_API_KEY is required for zep projection")
        from l9_graphite_memory.zep_transport import ZepCloudTransport

        from .graphiti_projection import GraphitiProjection

        return GraphitiProjection(
            ZepCloudTransport(api_key=settings.zep_api_key, base_url=settings.zep_api_url)
        )
    raise ConfigurationError(f"unsupported projection backend: {settings.projection_backend}")


def build_target_adapter(
    settings: MemorySettings, target: CompiledProjectionTarget
) -> ProjectionAdapter | None:
    """Construct the one-provider adapter for one compiled target.

    A delivering target whose provider is not configured fails startup. A
    disabled target that is not configured yields None: it receives nothing
    new, and lifecycle work against copies it already holds fails explicitly
    until it is configured again.
    """

    disabled = target.mode == TargetMode.DISABLED

    def unconfigured(reason: str) -> None:
        if disabled:
            return
        raise ConfigurationError(f"projection target {target.identity}: {reason}")

    if target.target != _CREDENTIALED_TARGET:
        return unconfigured(
            f"only the '{_CREDENTIALED_TARGET}' target binds to configured provider credentials"
        )
    if target.provider_type == "graphiti_mcp":
        if not settings.graphiti_mcp_url:
            return unconfigured("GRAPHITI_MCP_URL is required")
        from l9_graphite_memory.transport import HttpMcpTransport

        from .graphiti_projection import GraphitiProjection

        return GraphitiProjection(
            HttpMcpTransport(url=settings.graphiti_mcp_url, token=settings.graphiti_mcp_token)
        )
    if target.provider_type == "zep":
        if not settings.zep_api_key:
            return unconfigured("ZEP_API_KEY is required")
        from l9_graphite_memory.zep_transport import ZepCloudTransport

        from .graphiti_projection import GraphitiProjection

        return GraphitiProjection(
            ZepCloudTransport(api_key=settings.zep_api_key, base_url=settings.zep_api_url)
        )
    raise ConfigurationError(f"unsupported projection provider type: {target.provider_type}")


def build_projection_runtime(settings: MemorySettings) -> ProjectionRuntime:
    """Compose the configured projection runtime (ADR-084).

    Legacy mode wraps the scalar adapter as a one-target runtime. Manifest mode
    loads and compiles the manifest, then binds one adapter per compiled
    target; the compiled artifact, not the raw manifest, is what the runtime
    receives.
    """

    if settings.projection_runtime == "legacy":
        return ProjectionRuntime.legacy(
            build_projection(settings), required=settings.projection_required
        )
    if settings.projection_manifest is None:
        raise ConfigurationError("projection_runtime 'manifest' requires projection_manifest")
    compiled = compile_projection(load_projection_manifest(settings.projection_manifest))
    adapters = {
        target.identity: build_target_adapter(settings, target) for target in compiled.targets
    }
    return ProjectionRuntime.from_compiled(compiled, adapters)
