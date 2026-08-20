# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/conformance/test_shared_canonical_store.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""SP-05 / SP-06: a shared canonical backend exists; SQLite stays local."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from l9_graphite_memory.adapters import NullProjection, SQLiteRecordStore, build_store
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import (
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryWriteRequest,
    Provenance,
)
from l9_graphite_memory.errors import ConfigurationError
from l9_graphite_memory.services import MemoryService
from tests.conftest import make_postgres_store


def _request(content: str) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        namespace="repo-a",
        memory_class=MemoryClass.SEMANTIC,
        content=content,
        provenance=Provenance(source="shared-store-test"),
        evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="test"),),
    )


def test_settings_expose_a_shared_backend_selector() -> None:
    """SP-05: production canonical state can be configured as shared."""

    local = MemorySettings()
    assert local.store_backend == "sqlite"
    assert local.is_shared_store is False

    shared = MemorySettings(
        store_backend="postgres", postgres_dsn="postgresql:///example"
    )
    assert shared.is_shared_store is True


def test_shared_backend_requires_an_explicit_dsn() -> None:
    """A shared backend never silently degrades to a process-local file."""

    with pytest.raises(ValueError, match="postgres_dsn"):
        MemorySettings(store_backend="postgres")


def test_factory_rejects_a_shared_backend_without_a_dsn() -> None:
    settings = MemorySettings.model_construct(
        store_backend="postgres", postgres_dsn=None
    )
    with pytest.raises(ConfigurationError, match="POSTGRES_DSN"):
        build_store(settings)


def test_sqlite_remains_supported_for_local_operation(tmp_path: Path, principal) -> None:
    """SP-06: SQLite still works locally and is still not shared."""

    settings = MemorySettings(
        store_backend="sqlite", database_path=tmp_path / "local.sqlite3"
    )
    store = build_store(settings)
    try:
        assert isinstance(store, SQLiteRecordStore)
        assert store.name == "sqlite"
        assert settings.is_shared_store is False
        service = MemoryService(store, NullProjection())
        receipt = service.write(principal, _request("local ledger record"))
        assert service.get(principal, receipt.record_id) is not None
    finally:
        store.close()


def test_two_sqlite_files_are_independent_authorities(tmp_path: Path, principal) -> None:
    """SP-06: a runner-local SQLite file cannot be a distributed authority."""

    first = SQLiteRecordStore(tmp_path / "runner-a.sqlite3")
    second = SQLiteRecordStore(tmp_path / "runner-b.sqlite3")
    try:
        service_a = MemoryService(first, NullProjection())
        service_b = MemoryService(second, NullProjection())
        service_a.initialize()
        service_b.initialize()

        receipt = service_a.write(principal, _request("written on runner a"))

        assert service_a.get(principal, receipt.record_id) is not None
        assert service_b.get(principal, receipt.record_id) is None
    finally:
        first.close()
        second.close()


def test_shared_backend_is_one_authority_for_independent_clients(principal) -> None:
    """SP-05: separate clients of the shared store observe one canonical state."""

    schema = f"l9_shared_{uuid.uuid4().hex}"
    writer = make_postgres_store(schema)
    reader = make_postgres_store(schema)
    try:
        writer.initialize()
        reader.initialize()

        # Two independent store instances, two independent connections.
        assert writer._connection() is not reader._connection()

        service = MemoryService(writer, NullProjection())
        receipt = service.write(principal, _request("written by agent one"))

        # The second client sees the committed canonical record without any
        # file synchronization, which is what "shared" has to mean.
        observed = reader.get_record(receipt.record_id)
        assert observed is not None
        assert observed.content == "written by agent one"
        assert reader.stats()["records"] == 1
    finally:
        writer.close()
        reader.close()
