# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_distillation_profiles_sdk.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from l9_graphite_memory.contracts import (
    MemoryClass,
    MemorySearchRequest,
    MemoryWriteRequest,
    Provenance,
)
from l9_graphite_memory.extraction import SourceDistiller
from l9_graphite_memory.integrations import (
    ContextRestorer,
    SessionEvent,
    SessionIngestor,
)
from l9_graphite_memory.sdk import MemorySDK


def test_source_distillation_writes_atomic_records(memory_service, principal) -> None:
    receipt = SourceDistiller(memory_service).distill_text(
        principal,
        "The canonical store is SQLite.\nMemory writes require receipts.",
        source_id="architecture.md",
        namespace="repo-a",
        repository="Quantum-L9/l9-graphiti-memory",
    )

    assert receipt.candidate_count == 2
    assert receipt.written_count == 2
    assert receipt.status.value == "complete"
    records = memory_service.store.list_records("tenant-a", "repo-a")
    assert all(
        record.provenance.source_digest == receipt.source_digest for record in records
    )
    assert all(record.evidence[0].source_range is not None for record in records)


def test_sdk_and_session_integrations_share_canonical_service(
    memory_service, principal
) -> None:
    sdk = MemorySDK(memory_service, principal)
    receipt = sdk.write(
        MemoryWriteRequest(
            namespace="repo-a",
            memory_class=MemoryClass.DECISION,
            content="Use one canonical MemoryService",
            provenance=Provenance(source="sdk-test"),
        )
    )
    session_receipt = SessionIngestor(memory_service).ingest(
        principal,
        SessionEvent(session_id="s1", sequence=1, content="Continue the rewrite"),
        namespace="repo-a",
    )
    search = sdk.search(MemorySearchRequest(query="canonical", namespaces=("repo-a",)))
    restored = ContextRestorer(memory_service).restore(
        principal,
        task="continue rewrite",
        namespaces=("repo-a",),
        session_id="s1",
    )

    assert receipt.record_id is not None
    assert session_receipt.record_id is not None
    assert search.hits
    assert restored.status.value in {"complete", "partial"}
