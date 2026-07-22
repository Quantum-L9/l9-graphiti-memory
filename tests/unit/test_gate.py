# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_gate.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from l9_graphite_memory import graphiti_gate_lib as compatibility
from l9_graphite_memory import memory_guard as guard


def _write_evidence(tmp_path, conversation_id: str = "x", **updates: object) -> None:
    state = {
        "schema_version": 3,
        "namespace": "repo",
        "hydrated_at": datetime.now(timezone.utc).isoformat(),
        "hydration_digest": "a" * 64,
        "hydration_status": "complete",
        "task_signature": "task-a",
        "verified_task_signatures": ["task-a"],
        "ttl_minutes": 30,
        "phase_lock_granted": False,
    }
    state.update(updates)
    (tmp_path / f"{conversation_id}.json").write_text(
        json.dumps(state), encoding="utf-8"
    )


def test_guard_off_allows(monkeypatch) -> None:
    monkeypatch.setenv("L9_MEMORY_WRITE_GATES", "0")
    assert guard.pre_tool_use('{"tool_name":"Write"}')["permission"] == "allow"


def test_guard_denies_mutation_without_evidence(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("L9_MEMORY_WRITE_GATES", "1")
    monkeypatch.setenv("L9_MEMORY_STATE_DIR", str(tmp_path))
    result = guard.pre_tool_use('{"tool_name":"Write","conversation_id":"x"}')
    assert result["permission"] == "deny"


def test_guard_allows_with_fresh_evidence(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("L9_MEMORY_WRITE_GATES", "1")
    monkeypatch.setenv("L9_MEMORY_STATE_DIR", str(tmp_path))
    _write_evidence(tmp_path)
    result = guard.pre_tool_use('{"tool_name":"Write","conversation_id":"x"}')
    assert result["permission"] == "allow"


def test_read_only_tool_bypasses_guard(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("L9_MEMORY_WRITE_GATES", "1")
    monkeypatch.setenv("L9_MEMORY_STATE_DIR", str(tmp_path))
    assert guard.pre_tool_use('{"tool_name":"Read"}')["permission"] == "allow"


def test_phase_lock_requires_current_matching_receipt(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("L9_MEMORY_STATE_DIR", str(tmp_path))
    _write_evidence(
        tmp_path,
        phase_lock_granted=True,
        phase_lock_task_signature="task-a",
        phase_lock_expires_at=(
            datetime.now(timezone.utc) + timedelta(minutes=5)
        ).isoformat(),
    )
    assert guard.phase_lock_ok(guard.load_evidence("x"))

    _write_evidence(
        tmp_path,
        phase_lock_granted=True,
        phase_lock_task_signature="task-b",
        phase_lock_expires_at=(
            datetime.now(timezone.utc) + timedelta(minutes=5)
        ).isoformat(),
    )
    assert not guard.phase_lock_ok(guard.load_evidence("x"))


def test_stale_hydration_does_not_satisfy_guard(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("L9_MEMORY_STATE_DIR", str(tmp_path))
    _write_evidence(tmp_path, hydrated_at="2000-01-01T00:00:00+00:00")
    evidence = guard.load_evidence("x")
    assert not guard.memory_ok(evidence)
    assert not guard.memory_ok(evidence, "task-a")


def test_shell_guard_uses_read_only_allowlist(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("L9_MEMORY_WRITE_GATES", "1")
    monkeypatch.setenv("L9_MEMORY_STATE_DIR", str(tmp_path))
    assert (
        guard.shell_guard('{"command":"git status","conversation_id":"x"}')[
            "permission"
        ]
        == "allow"
    )
    assert (
        guard.shell_guard('{"command":"find . -delete","conversation_id":"x"}')[
            "permission"
        ]
        == "deny"
    )


def test_compatibility_module_is_a_thin_alias() -> None:
    assert compatibility.pre_tool_use is guard.pre_tool_use
    assert compatibility.shell_gate is guard.shell_guard
