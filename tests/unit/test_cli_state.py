# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_cli_state.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast

from l9_graphite_memory import cli
from l9_graphite_memory.contracts import ConflictReport, PhaseLockReceipt


def _runtime(tmp_path: Any) -> Any:
    return cast(Any, SimpleNamespace(settings=SimpleNamespace(state_dir=tmp_path)))


def test_phase_lock_receipt_is_mirrored_and_denial_clears_marker(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("L9_SESSION_ID", "phase-test")
    now = datetime.now(timezone.utc)
    runtime = _runtime(tmp_path)
    granted = PhaseLockReceipt(
        tenant_id="tenant-a",
        namespace="repo-a",
        task_signature="task-signature",
        granted=True,
        conflict_report=ConflictReport(namespace="repo-a"),
        expires_at=now + timedelta(minutes=30),
        principal_id="tester",
        created_at=now,
    )

    path = cli._mark_phase_lock_state(runtime, granted)
    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["phase_lock_granted"] is True
    assert state["phase_lock_task_signature"] == "task-signature"
    assert state["task_signature"] == "task-signature"
    assert state["verified_task_signatures"] == []

    denied = granted.model_copy(update={"granted": False})
    cli._mark_phase_lock_state(runtime, denied)
    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["phase_lock_granted"] is False
    assert state["verified_task_signatures"] == []
