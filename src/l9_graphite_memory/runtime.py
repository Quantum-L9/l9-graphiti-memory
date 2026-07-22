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
from l9_graphite_memory.group_resolver import GroupResolution, resolve_group
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
    service = MemoryService(
        store, projection, projection_required=settings.projection_required
    )
    service.initialize()
    return MemoryRuntime(settings=settings, service=service)


def local_principal_for_resolution(
    settings: MemorySettings,
    resolution: GroupResolution,
    *,
    include_workspace: bool = True,
) -> MemoryPrincipal:
    if not resolution.group_id:
        read_namespaces: tuple[str, ...] = ()
        write_namespaces: tuple[str, ...] = ()
    else:
        read_values = [resolution.group_id]
        if include_workspace and resolution.group_id != settings.workspace_namespace:
            read_values.append(settings.workspace_namespace)
        read_namespaces = tuple(read_values)
        write_namespaces = () if resolution.readonly else (resolution.group_id,)
    principal = build_local_principal(
        settings,
        read_namespaces=read_namespaces,
        write_namespaces=write_namespaces,
        promote_namespaces=write_namespaces,
    )
    return principal.model_copy(update={"is_admin": settings.local_is_admin})


def resolve_local_context(
    settings: MemorySettings,
    *,
    cwd: Path | None = None,
    explicit_group: str | None = None,
) -> tuple[GroupResolution, MemoryPrincipal]:
    resolution = resolve_group(cwd, explicit=explicit_group, settings=settings)
    return resolution, local_principal_for_resolution(settings, resolution)
