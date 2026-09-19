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

from dataclasses import dataclass
from pathlib import Path

from l9_graphite_memory.adapters import build_projection, build_store
from l9_graphite_memory.authz import build_local_principal
from l9_graphite_memory.config import MemorySettings, load_settings
from l9_graphite_memory.contracts import MemoryPrincipal
from l9_graphite_memory.group_resolver import (
    GroupResolution,
    resolve_group,
    resolve_namespace_request,
)
from l9_graphite_memory.observability import configure_logging
from l9_graphite_memory.services import MemoryService


@dataclass
class MemoryRuntime:
    settings: MemorySettings
    service: MemoryService

    def close(self) -> None:
        self.service.store.close()


def build_runtime(config_path: str | Path | None = None) -> MemoryRuntime:
    settings = load_settings(config_path)
    configure_logging(settings.log_level, json_output=settings.json_logs)
    store = build_store(settings)
    projection = build_projection(settings)
    service = MemoryService(store, projection, projection_required=settings.projection_required)
    service.initialize()
    return MemoryRuntime(settings=settings, service=service)


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


def resolve_local_context_for_namespace(
    settings: MemorySettings,
    namespace: str | None,
    *,
    cwd: Path | None = None,
) -> tuple[GroupResolution, MemoryPrincipal]:
    """Resolve the local context for the namespace a request names.

    The operator CLI resolves authorization once per invocation, against the
    ``--workspace`` it was given, so it can address any repository. A long-lived
    local transport must do the same thing per request, or it can only ever
    serve the repository it was launched in — the caller's ``namespace``
    argument becomes decorative and every other root in the session is
    unwritable for the life of the process.

    Widening is deliberately narrow:

    * Configured ``local_*_namespaces`` remain the sole ACL source (ADR-006).
      They are an explicit operator grant and are never widened by a request.
    * Only a *registered repository* slug resolves. Empty, forbidden, and
      unregistered namespaces fall through to cwd resolution, which keeps read
      access to the workspace namespace working and leaves every previously
      observable outcome unchanged.

    This is not a new authority. Tier 3 is the unauthenticated local-operator
    fallback, and ``resolve_group`` already honours ``L9_MEMORY_NAMESPACE`` for
    *any* non-forbidden value; requiring registry membership is strictly
    stricter than that existing path.
    """

    if _local_namespaces_configured(settings):
        return resolve_local_context(settings, cwd=cwd)

    requested = resolve_namespace_request(namespace, settings=settings)
    if requested.group_id:
        return requested, local_principal_for_resolution(settings, requested)

    return resolve_local_context(settings, cwd=cwd)
