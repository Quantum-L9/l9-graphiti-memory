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
from l9_graphite_memory.graph.ports import GraphIntelligencePort
from l9_graphite_memory.ports import ProjectionAdapter, RecordStore

from .null_graph_intelligence import NullGraphIntelligence
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


def build_graph_intelligence(settings: MemorySettings) -> GraphIntelligencePort:
    """Construct the configured graph-intelligence backend (ADR-085).

    ``none`` is an explicit adapter that serves nothing. Selecting ``neo4j``
    without a URI or without the optional driver is a configuration error,
    never a silent fallback. An unreachable server is not a construction
    error: health and capabilities report it, and canonical memory and the
    Graphiti projection keep working.
    """

    if settings.graph_intelligence_backend == "none":
        return NullGraphIntelligence()
    if settings.graph_intelligence_backend == "neo4j":
        if not settings.graph_neo4j_uri:
            raise ConfigurationError(
                "L9_MEMORY_GRAPH_NEO4J_URI is required for the neo4j graph intelligence backend"
            )
        from .neo4j_graph_intelligence import (
            Neo4jGraphIntelligence,
            Neo4jGraphIntelligenceConfig,
        )

        return Neo4jGraphIntelligence(
            Neo4jGraphIntelligenceConfig(
                uri=settings.graph_neo4j_uri,
                database=settings.graph_neo4j_database,
                user=settings.graph_neo4j_user,
                password=settings.graph_neo4j_password,
                query_timeout_ms=settings.graph_query_timeout_ms,
                gds_max_nodes=settings.graph_gds_max_nodes,
                relationship_allowlist=settings.graph_relationship_allowlist,
                expected_schema_fingerprint=settings.graph_expected_schema_fingerprint,
                link_prediction_enabled=settings.graph_link_prediction_enabled,
            )
        )
    raise ConfigurationError(
        f"unsupported graph intelligence backend: {settings.graph_intelligence_backend}"
    )
