# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_write_recovery.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from l9_graphite_memory.errors import StoreError
from l9_graphite_memory.integrations import SessionEvent, SessionIngestor
from l9_graphite_memory.recovery import FileWriteRecoveryQueue


def test_session_write_can_queue_then_replay_through_canonical_service(
    tmp_path,
    memory_service,
    principal,
    monkeypatch,
) -> None:
    queue = FileWriteRecoveryQueue(tmp_path / "recovery")
    original_write = memory_service.write

    def fail_write(*_args, **_kwargs):
        raise StoreError("canonical store unavailable")

    monkeypatch.setattr(memory_service, "write", fail_write)
    result = SessionIngestor(memory_service, queue).ingest_or_queue(
        principal,
        SessionEvent(session_id="session-1", sequence=1, content="durable event"),
        namespace="repo-a",
    )

    assert result.status == "queued"
    assert result.queued_write is not None
    assert len(queue.list_pending()) == 1

    monkeypatch.setattr(memory_service, "write", original_write)
    replay = queue.replay(memory_service, principal)

    assert replay.delivered == 1
    assert replay.retained == 0
    assert queue.list_pending() == ()
    assert len(list((tmp_path / "recovery" / "delivered").glob("*.json"))) == 1
