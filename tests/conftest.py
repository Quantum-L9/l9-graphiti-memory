# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/conftest.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-27

from __future__ import annotations

from pathlib import Path

import pytest

from l9_graphite_memory.adapters import (
    InMemoryRecordStore,
    NullProjection,
    SQLiteRecordStore,
)
from l9_graphite_memory.contracts import MemoryPrincipal
from l9_graphite_memory.services import MemoryService

pytest_plugins: list[str] = []


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "asyncio: mark test as asyncio-based (provided by pytest-asyncio)"
    )


@pytest.fixture
def principal() -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id="tester",
        tenant_id="tenant-a",
        read_namespaces=("repo-a", "workspace"),
        write_namespaces=("repo-a",),
        promote_namespaces=("repo-a",),
    )


@pytest.fixture
def admin_principal() -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id="admin",
        tenant_id="tenant-a",
        read_namespaces=("*",),
        write_namespaces=("*",),
        promote_namespaces=("*",),
        is_admin=True,
    )


@pytest.fixture
def memory_service() -> MemoryService:
    store = InMemoryRecordStore()
    service = MemoryService(store, NullProjection())
    service.initialize()
    return service


@pytest.fixture
def sqlite_service(tmp_path: Path) -> MemoryService:
    store = SQLiteRecordStore(tmp_path / "memory.sqlite3")
    service = MemoryService(store, NullProjection())
    service.initialize()
    return service
