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

from .null_projection import NullProjection
from .sqlite_store import SQLiteRecordStore


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
        raise ConfigurationError(
            f"unsupported store backend: {settings.store_backend}"
        )
    store.initialize()
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
            HttpMcpTransport(
                url=settings.graphiti_mcp_url, token=settings.graphiti_mcp_token
            )
        )
    if settings.projection_backend == "zep":
        if not settings.zep_api_key:
            raise ConfigurationError("ZEP_API_KEY is required for zep projection")
        from l9_graphite_memory.zep_transport import ZepCloudTransport

        from .graphiti_projection import GraphitiProjection

        return GraphitiProjection(
            ZepCloudTransport(
                api_key=settings.zep_api_key, base_url=settings.zep_api_url
            )
        )
    raise ConfigurationError(
        f"unsupported projection backend: {settings.projection_backend}"
    )
