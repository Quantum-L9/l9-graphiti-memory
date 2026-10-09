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

from collections.abc import Callable

from l9_graphite_memory.active.client import ActiveMemoryBinding
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.errors import ConfigurationError
from l9_graphite_memory.graph.ports import GraphIntelligencePort
from l9_graphite_memory.ports import ProjectionAdapter, RecordStore
from l9_graphite_memory.projections import (
    CompiledProjection,
    CompiledProjectionTarget,
    ProjectionRuntime,
    TargetMode,
    compile_projection,
    load_projection_manifest,
)

from .null_graph_intelligence import NullGraphIntelligence
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
            HttpMcpTransport(url=settings.graphiti_mcp_url, token=settings.graphiti_mcp_token),
            episode_lookup_limit=settings.graphiti_episode_lookup_limit,
        )
    if settings.projection_backend == "zep":
        if not settings.zep_api_key:
            raise ConfigurationError("ZEP_API_KEY is required for zep projection")
        from l9_graphite_memory.zep_transport import ZepCloudTransport

        from .graphiti_projection import GraphitiProjection

        return GraphitiProjection(
            ZepCloudTransport(api_key=settings.zep_api_key, base_url=settings.zep_api_url),
            episode_lookup_limit=settings.graphiti_episode_lookup_limit,
        )
    raise ConfigurationError(f"unsupported projection backend: {settings.projection_backend}")


def build_graph_intelligence(settings: MemorySettings) -> GraphIntelligencePort:
    """Construct the configured graph-intelligence backend (ADR-086).

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


def build_active_memory(
    settings: MemorySettings,
    *,
    secret_provider: Callable[[str], str] | None = None,
) -> ActiveMemoryBinding:
    """Construct the configured active-memory binding (ADR-065 .. ADR-068).

    ``none`` binds the null adapters, which refuse every operation
    explicitly; ``redis`` resolves exactly one ADR-066 credential source at
    construction time and binds the Redis store and the Redis awareness bus
    to one deployment identity. The credential never enters settings,
    receipts, or logs: only its source name is recorded. An unreachable
    server is not a construction error (connections open lazily); the
    binding's ``health()`` probe and the runtime readiness report say so.
    """

    from l9_graphite_memory.active.deployment import ActiveDeployment, DeploymentEnvironment

    if settings.active_memory_backend == "none":
        from l9_graphite_memory.active.null_adapters import NullActiveStore, NullAwarenessBus

        return ActiveMemoryBinding(
            backend="none",
            enabled=False,
            required=settings.active_memory_required,
            deployment_id=settings.active_deployment_id or "active-memory-disabled",
            trust_domain=settings.active_trust_domain or "active-memory-disabled",
            environment=settings.active_environment,
            store=NullActiveStore(),
            bus=NullAwarenessBus(),
            heartbeat_interval_seconds=settings.active_heartbeat_interval_seconds,
            lease_ttl_seconds=settings.active_lease_ttl_seconds,
            heartbeat_failure_threshold=settings.active_heartbeat_failure_threshold,
        )
    if settings.active_memory_backend != "redis":
        raise ConfigurationError(
            f"unsupported active memory backend: {settings.active_memory_backend}"
        )
    from l9_graphite_memory.active.credentials import (
        CredentialResolutionError,
        RedisCredentialSettings,
        resolve_redis_credential,
    )
    from l9_graphite_memory.active.deployment import DeploymentIdentityError
    from l9_graphite_memory.active.errors import ActiveMemoryUnavailableError
    from l9_graphite_memory.active.redis_adapters import RedisActiveStore, RedisAwarenessBus

    try:
        deployment = ActiveDeployment(
            deployment_id=str(settings.active_deployment_id),
            trust_domain=str(settings.active_trust_domain),
            environment=DeploymentEnvironment(settings.active_environment),
        )
    except DeploymentIdentityError as exc:
        raise ConfigurationError(f"active memory deployment identity rejected: {exc}") from exc
    try:
        credential = resolve_redis_credential(
            RedisCredentialSettings(
                username=settings.active_redis_username,
                password_file=settings.active_redis_password_file,
                url_file=settings.active_redis_url_file,
                url_env=settings.active_redis_url_env,
                secret_provider_reference=settings.active_redis_secret_reference,
                host=settings.active_redis_host,
                port=settings.active_redis_port,
                database=settings.active_redis_database,
                tls=settings.active_redis_tls,
            ),
            secret_provider=secret_provider,
        )
    except CredentialResolutionError as exc:
        raise ConfigurationError(f"active memory credential unresolved: {exc}") from exc
    try:
        store = RedisActiveStore(
            credential.redis_url,
            deployment,
            key_prefix=settings.active_key_prefix,
            context_ttl_seconds=settings.active_context_ttl_seconds,
            presence_ttl_seconds=settings.active_presence_ttl_seconds,
        )
        bus = RedisAwarenessBus(
            credential.redis_url, deployment, channel_prefix=settings.active_key_prefix
        )
    except ActiveMemoryUnavailableError as exc:
        raise ConfigurationError(
            f"active memory backend 'redis' needs the optional dependency: {exc}"
        ) from exc
    return ActiveMemoryBinding(
        backend="redis",
        enabled=True,
        required=settings.active_memory_required,
        deployment_id=deployment.deployment_id,
        trust_domain=deployment.trust_domain,
        environment=deployment.environment.value,
        store=store,
        bus=bus,
        credential_source=credential.credential_source,
        heartbeat_interval_seconds=settings.active_heartbeat_interval_seconds,
        lease_ttl_seconds=settings.active_lease_ttl_seconds,
        heartbeat_failure_threshold=settings.active_heartbeat_failure_threshold,
    )


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
        unconfigured(
            f"only the '{_CREDENTIALED_TARGET}' target binds to configured provider credentials"
        )
        return None
    if target.provider_type == "graphiti_mcp":
        if not settings.graphiti_mcp_url:
            unconfigured("GRAPHITI_MCP_URL is required")
            return None
        from l9_graphite_memory.transport import HttpMcpTransport

        from .graphiti_projection import GraphitiProjection

        return GraphitiProjection(
            HttpMcpTransport(url=settings.graphiti_mcp_url, token=settings.graphiti_mcp_token),
            episode_lookup_limit=settings.graphiti_episode_lookup_limit,
        )
    if target.provider_type == "zep":
        if not settings.zep_api_key:
            unconfigured("ZEP_API_KEY is required")
            return None
        from l9_graphite_memory.zep_transport import ZepCloudTransport

        from .graphiti_projection import GraphitiProjection

        return GraphitiProjection(
            ZepCloudTransport(api_key=settings.zep_api_key, base_url=settings.zep_api_url),
            episode_lookup_limit=settings.graphiti_episode_lookup_limit,
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
    # Earlier manifest revisions whose targets may still hold copies or own
    # queued lifecycle events. Their targets are bound lifecycle-only: they
    # never deliver or retrieve, so an unconfigured one yields no adapter
    # rather than failing startup, exactly like a disabled target (ADR-084).
    current = {target.identity for target in compiled.targets}
    retained: list[tuple[CompiledProjection, dict[str, ProjectionAdapter | None]]] = []
    for path in settings.projection_manifest_history:
        previous = compile_projection(load_projection_manifest(path))
        retained.append(
            (
                previous,
                {
                    target.identity: build_target_adapter(
                        settings,
                        target.model_copy(update={"mode": TargetMode.DISABLED, "required": False}),
                    )
                    for target in previous.targets
                    if target.identity not in current
                },
            )
        )
    return ProjectionRuntime.from_compiled(compiled, adapters, retained=retained)
