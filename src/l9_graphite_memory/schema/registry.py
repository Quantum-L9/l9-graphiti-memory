# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/schema/registry.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Deterministic schema migration graph for persisted memory records."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from copy import deepcopy
from itertools import pairwise
from typing import Any

from l9_graphite_memory.contracts import MemoryRecord
from l9_graphite_memory.errors import UnsupportedSchemaVersion
from l9_graphite_memory.version import MEMORY_SCHEMA_VERSION

Upcaster = Callable[[dict[str, Any]], dict[str, Any]]


class SchemaRegistry:
    def __init__(self, current_version: str = MEMORY_SCHEMA_VERSION) -> None:
        self.current_version = current_version
        self._upcasters: dict[tuple[str, str], Upcaster] = {}
        self._edges: dict[str, list[str]] = {}

    def register(self, from_version: str, to_version: str) -> Callable[[Upcaster], Upcaster]:
        def decorator(function: Upcaster) -> Upcaster:
            key = (from_version, to_version)
            if key in self._upcasters:
                raise ValueError(f"duplicate upcaster: {from_version} -> {to_version}")
            self._upcasters[key] = function
            self._edges.setdefault(from_version, []).append(to_version)
            return function

        return decorator

    @staticmethod
    def detect_version(raw: dict[str, Any]) -> str:
        version = raw.get("schema_version")
        if isinstance(version, str) and version:
            return version
        metadata = raw.get("metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("schema_version"), str):
            return str(metadata["schema_version"])
        if "episode_body" in raw:
            return "0.2.0-episode"
        return "1.0.0"

    def migration_path(self, from_version: str, to_version: str | None = None) -> tuple[str, ...]:
        target = to_version or self.current_version
        if from_version == target:
            return (from_version,)
        queue: deque[tuple[str, tuple[str, ...]]] = deque([(from_version, (from_version,))])
        visited = {from_version}
        while queue:
            current, path = queue.popleft()
            for next_version in self._edges.get(current, []):
                if next_version == target:
                    return (*path, next_version)
                if next_version not in visited:
                    visited.add(next_version)
                    queue.append((next_version, (*path, next_version)))
        raise UnsupportedSchemaVersion(f"no migration path from {from_version} to {target}")

    def upcast(self, raw: dict[str, Any], target_version: str | None = None) -> dict[str, Any]:
        source = self.detect_version(raw)
        target = target_version or self.current_version
        if source == target:
            return deepcopy(raw)
        result = deepcopy(raw)
        path = self.migration_path(source, target)
        for from_version, to_version in pairwise(path):
            result = self._upcasters[(from_version, to_version)](result)
        return result

    def read_record(self, raw: dict[str, Any]) -> MemoryRecord:
        return MemoryRecord.model_validate(self.upcast(raw))


schema_registry = SchemaRegistry()
