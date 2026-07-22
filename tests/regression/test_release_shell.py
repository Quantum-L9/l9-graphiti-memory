# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/regression/test_release_shell.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import json
import os
import subprocess
import sys
from importlib.resources import files
from pathlib import Path


def test_packaged_registry_exists() -> None:
    registry = files("l9_graphite_memory").joinpath("resources/group_registry.yaml")
    assert registry.is_file()
    assert "l9-graphiti-memory" in registry.read_text(encoding="utf-8")


def _dry_run(script: str, tmp_path: Path) -> dict:
    env = os.environ.copy()
    env.update(
        {
            "INFISICAL_CLIENT_SECRET": "never-persist-this-infisical-secret",
            "ZEP_API_KEY": "never-persist-this-zep-secret",
            "GRAPHITI_MCP_TOKEN": "never-persist-this-graphiti-token",
        }
    )
    result = subprocess.run(
        [sys.executable, script, "--dry-run", "--path", str(tmp_path / "mcp.json")],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(result.stdout)


def test_cursor_config_writer_does_not_persist_secrets(tmp_path: Path) -> None:
    payload = _dry_run("scripts/write_cursor_config.py", tmp_path)
    encoded = json.dumps(payload)
    assert "never-persist" not in encoded
    assert "env" not in payload["config"]["mcpServers"]["l9-graphite-memory"]


def test_claude_config_writer_does_not_persist_secrets(tmp_path: Path) -> None:
    payload = _dry_run("scripts/write_claude_config.py", tmp_path)
    encoded = json.dumps(payload)
    assert "never-persist" not in encoded
    assert "env" not in payload["config"]["mcpServers"]["l9-graphite-memory"]


def test_mark_ok_requires_current_fresh_hydration(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_path = state_dir / "hook-test.json"
    state = {
        "schema_version": 3,
        "namespace": "repo",
        "hydrated_at": datetime.now(timezone.utc).isoformat(),
        "hydration_digest": "a" * 64,
        "hydration_status": "complete",
        "task_signature": "task-a",
        "verified_task_signatures": [],
        "ttl_minutes": 30,
        "phase_lock_granted": False,
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    env = os.environ.copy()
    env.update({"L9_MEMORY_STATE_DIR": str(state_dir), "L9_SESSION_ID": "hook-test"})

    subprocess.run(
        ["bash", "hooks/graphiti-mark-ok.sh", "task-a"],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )
    updated = json.loads(state_path.read_text(encoding="utf-8"))
    assert updated["verified_task_signatures"] == ["task-a"]

    wrong = subprocess.run(
        ["bash", "hooks/graphiti-mark-ok.sh", "other-task"],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )
    assert wrong.returncode != 0


def test_release_build_sets_reproducible_epoch() -> None:
    script = Path("scripts/validate_release.sh").read_text(encoding="utf-8")
    assert "SOURCE_DATE_EPOCH" in script
    assert "1784592000" in script
