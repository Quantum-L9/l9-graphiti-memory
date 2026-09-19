# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/group_resolver.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Deterministically map a repository to its configured memory namespace."""

from __future__ import annotations

import os
import subprocess
from fnmatch import fnmatch
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.errors import ConfigurationError


class GroupResolution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    group_id: str | None
    method: str
    readonly: bool
    error: str | None = None
    warning: str | None = None
    matches: tuple[str, ...] = ()


def registry_path(settings: MemorySettings | None = None) -> Path:
    configured = settings.registry_path if settings else None
    env_path = os.environ.get("L9_MEMORY_REGISTRY_PATH")
    if configured:
        return configured.expanduser()
    if env_path:
        return Path(env_path).expanduser()
    return Path(str(files("l9_graphite_memory.resources").joinpath("group_registry.yaml")))


def load_registry(settings: MemorySettings | None = None) -> dict[str, Any]:
    path = registry_path(settings)
    if not path.is_file():
        raise ConfigurationError(f"group registry not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigurationError("group registry root must be a mapping")
    return dict(raw)


def _git_remote_url(cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "remote", "get-url", "origin"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def resolve_group(
    cwd: Path | None = None,
    *,
    explicit: str | None = None,
    settings: MemorySettings | None = None,
) -> GroupResolution:
    registry = load_registry(settings)
    forbidden = {str(value) for value in registry.get("forbidden_groups") or []}
    workspace = str(
        registry.get("workspace_group")
        or (settings.workspace_namespace if settings else "l9-workspace")
    )
    current = (cwd or Path.cwd()).resolve()

    selected = (
        explicit or os.environ.get("L9_MEMORY_NAMESPACE") or os.environ.get("GRAPHITI_GROUP_ID")
    )
    if selected:
        selected = selected.strip()
        if selected in forbidden:
            return GroupResolution(
                group_id=None,
                method="explicit",
                readonly=True,
                error=f"forbidden namespace: {selected}",
            )
        return GroupResolution(group_id=selected, method="explicit", readonly=False)

    repositories = registry.get("repos") or {}
    if not isinstance(repositories, dict):
        raise ConfigurationError("registry repos must be a mapping")
    remote = _git_remote_url(current)
    path_text = str(current)
    matches: list[str] = []
    for slug, raw_config in repositories.items():
        if not isinstance(raw_config, dict):
            continue
        patterns = raw_config.get("remote_patterns") or []
        hints = raw_config.get("path_hints") or []
        if remote and any(fnmatch(remote, str(pattern)) for pattern in patterns):
            matches.append(str(slug))
            continue
        if any(str(hint).casefold() in path_text.casefold() for hint in hints):
            matches.append(str(slug))

    unique = tuple(sorted(set(matches)))
    if len(unique) == 1:
        return GroupResolution(
            group_id=unique[0], method="registry", readonly=False, matches=unique
        )
    if len(unique) > 1:
        return GroupResolution(
            group_id=None,
            method="registry",
            readonly=True,
            error=f"ambiguous namespace match: {list(unique)}",
            matches=unique,
        )

    on_failure = str(
        (registry.get("resolution") or {}).get("on_failure") or "abort_write_allow_readonly"
    )
    if on_failure == "abort_write_allow_readonly":
        return GroupResolution(
            group_id=workspace,
            method="fallback_readonly",
            readonly=True,
            warning=f"no repository match for {current}",
        )
    return GroupResolution(
        group_id=None, method="unresolved", readonly=True, error="no namespace match"
    )


def _registered_in(registry: dict[str, Any]) -> frozenset[str]:
    """Registered, non-forbidden slugs of an already-loaded registry.

    Takes the loaded mapping rather than settings so a caller that has already
    read the registry does not read and parse the YAML a second time — which
    matters now that :func:`resolve_namespace_request` runs per request.
    """

    repositories = registry.get("repos") or {}
    if not isinstance(repositories, dict):
        raise ConfigurationError("registry repos must be a mapping")
    forbidden = {str(value) for value in registry.get("forbidden_groups") or []}
    return frozenset(str(slug) for slug in repositories if str(slug) not in forbidden)


def registered_namespaces(settings: MemorySettings | None = None) -> frozenset[str]:
    """Namespace slugs the registry registers as repositories.

    A registry slug *is* a namespace, so this is the reverse of
    :func:`resolve_group`: it answers "does this namespace name a repository?"
    without needing that repository to be the process's working directory.
    """

    return _registered_in(load_registry(settings))


def resolve_namespace_request(
    namespace: str | None,
    *,
    settings: MemorySettings | None = None,
) -> GroupResolution:
    """Resolve a namespace the caller addressed explicitly, ignoring cwd.

    Repository identity is a property of the namespace, not of the directory a
    process was launched in. A long-lived server handling requests for several
    roots must therefore be able to resolve the namespace it was *asked* about;
    resolving only its own cwd is what froze the stdio principal to whichever
    repository the host happened to start it in.

    ``group_id`` is ``None`` with ``error`` set when the namespace is empty,
    forbidden, or not a registered repository. That is not a failure to be
    papered over: the caller decides whether to fall back to cwd resolution
    (which is what preserves read access to the workspace namespace and to any
    namespace a custom registry does not list).
    """

    candidate = (namespace or "").strip()
    if not candidate:
        return GroupResolution(
            group_id=None,
            method="namespace_request",
            readonly=True,
            error="no namespace supplied",
        )

    registry = load_registry(settings)
    forbidden = {str(value) for value in registry.get("forbidden_groups") or []}
    if candidate in forbidden:
        return GroupResolution(
            group_id=None,
            method="namespace_request",
            readonly=True,
            error=f"forbidden namespace: {candidate}",
        )

    if candidate not in _registered_in(registry):
        return GroupResolution(
            group_id=None,
            method="namespace_request",
            readonly=True,
            error=f"namespace is not a registered repository: {candidate}",
        )

    return GroupResolution(
        group_id=candidate,
        method="namespace_request",
        readonly=False,
        matches=(candidate,),
    )


def resolve_group_id(
    cwd: Path | None = None,
    explicit: str | None = None,
    settings: MemorySettings | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper returning the v1 dictionary shape."""

    return resolve_group(cwd, explicit=explicit, settings=settings).model_dump(mode="json")
