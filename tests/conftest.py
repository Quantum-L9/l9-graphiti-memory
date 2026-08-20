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

import os
import uuid
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

POSTGRES_DSN_ENV = "L9_MEMORY_TEST_POSTGRES_DSN"

# Every canonical store the contract suites exercise. "postgres" is the shared
# production backend (ADR-072); it runs whenever a test DSN is configured and
# skips loudly otherwise so a missing database narrows the matrix visibly.
STORE_BACKENDS = ("memory", "sqlite", "postgres")


def postgres_test_dsn() -> str:
    dsn = os.environ.get(POSTGRES_DSN_ENV, "").strip()
    if not dsn:
        pytest.skip(
            f"{POSTGRES_DSN_ENV} is not set; the shared-backend matrix requires "
            "a PostgreSQL test database"
        )
    return dsn


def make_postgres_store(schema: str | None = None):
    """Build a PostgresRecordStore isolated in its own schema.

    Passing an existing ``schema`` binds a second, independent client to the
    same tables, which is how the shared-backend and concurrency cases model
    two separate agents or workers.

    The schema is carried in the DSN rather than set with a session ``SET``.
    The store opens one connection per thread, so a session-scoped setting
    applied on one thread would not reach the others -- exactly the situation
    the concurrency cases create.
    """

    from l9_graphite_memory.adapters import PostgresRecordStore

    base_dsn = postgres_test_dsn()
    schema = schema or f"l9_test_{uuid.uuid4().hex}"

    bootstrap = PostgresRecordStore(base_dsn)
    try:
        connection = bootstrap._connection()
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        connection.commit()
    finally:
        bootstrap.close()

    store = PostgresRecordStore(f"{base_dsn} options=-csearch_path={schema}")
    store.test_schema = schema
    return store


def make_store(backend: str, tmp_path: Path):
    """Construct one conforming canonical store for the named backend."""

    if backend == "memory":
        return InMemoryRecordStore()
    if backend == "sqlite":
        return SQLiteRecordStore(tmp_path / f"store-{uuid.uuid4().hex}.sqlite3")
    if backend == "postgres":
        return make_postgres_store()
    raise AssertionError(f"unknown store backend: {backend}")


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
