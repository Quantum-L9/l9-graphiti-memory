# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_cursor_mcp_instantiation.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-27

"""End-to-end proof of instantiation over the generated stdio command."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from l9_graphite_memory.client_config import (
    REQUIRED_TOOL_NAMES,
    ClientConfigStatus,
    probe_generated_server,
)
from l9_graphite_memory.client_config.mcp_probe import redact_stderr


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "L9_MEMORY_DATA_DIR": str(tmp_path / "data"),
            "L9_MEMORY_STATE_DIR": str(tmp_path / "state"),
            "L9_MEMORY_PROJECTION_BACKEND": "none",
        }
    )
    src = Path(__file__).resolve().parents[2] / "src"
    env["PYTHONPATH"] = f"{src}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
    return env


def test_probe_generated_server_full_handshake(tmp_path: Path) -> None:
    receipt = probe_generated_server(env=_isolated_env(tmp_path), timeout_seconds=60.0)
    assert receipt.status == ClientConfigStatus.COMPLETE, receipt.reasons
    assert receipt.protocol_version == "2024-11-05"
    assert receipt.server_name == "l9-graphite-memory"
    assert receipt.required_tools_present is True
    assert receipt.missing_tools == ()
    assert receipt.tool_count >= len(REQUIRED_TOOL_NAMES)
    assert receipt.health_status in {"complete", "partial"}
    assert receipt.timed_out is False
    methods = [step.method for step in receipt.steps]
    assert methods == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call memory.health",
    ]
    assert all(step.ok for step in receipt.steps)


def test_probe_fails_closed_on_broken_interpreter(tmp_path: Path) -> None:
    broken = tmp_path / "missing-python"
    receipt = probe_generated_server(
        interpreter=str(broken),
        env=_isolated_env(tmp_path),
        timeout_seconds=10.0,
    )
    assert receipt.status == ClientConfigStatus.FAILED
    assert receipt.reasons


def test_probe_redacts_secret_values_from_stderr() -> None:
    env = {"MY_SERVICE_TOKEN": "super-secret-token-value", "PATH": "/usr/bin"}
    text = "failure while using super-secret-token-value in request"
    cleaned = redact_stderr(text, env)
    assert "super-secret-token-value" not in cleaned
    assert "[REDACTED]" in cleaned


def test_cli_client_cursor_verify_returns_receipt_json(tmp_path: Path) -> None:
    env = _isolated_env(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "l9_graphite_memory.cli",
            "client",
            "cursor",
            "verify",
            "--timeout",
            "60",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    payload = json.loads(result.stdout)
    assert payload["status"] == "complete"
    assert payload["policy_version"] == "client-config/v1"


def test_cli_client_cursor_lifecycle_round_trip(tmp_path: Path) -> None:
    env = _isolated_env(tmp_path)
    config_path = tmp_path / "cursor" / "mcp.json"

    def run(*args: str) -> dict:
        result = subprocess.run(
            [sys.executable, "-m", "l9_graphite_memory.cli", "client", "cursor", *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return json.loads(result.stdout)

    installed = run("install", "--path", str(config_path))
    assert installed["status"] == "complete"
    status = run("status", "--path", str(config_path))
    assert status["status"] == "complete"
    again = run("install", "--path", str(config_path))
    assert again["status"] == "unchanged"
    removed = run("uninstall", "--path", str(config_path))
    assert removed["status"] == "complete"
    final = run("status", "--path", str(config_path))
    assert final["managed_entry_present"] is False


def test_cli_client_cursor_verify_probes_the_installed_entry(tmp_path: Path) -> None:
    """verify --path launches what the file names, and says so in the receipt."""

    env = _isolated_env(tmp_path)
    config_path = tmp_path / "cursor" / "mcp.json"

    def run(*args: str, check: bool = True) -> tuple[int, dict]:
        result = subprocess.run(
            [sys.executable, "-m", "l9_graphite_memory.cli", "client", "cursor", *args],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert not check or result.returncode == 0, result.stderr
        return result.returncode, json.loads(result.stdout)

    # No entry yet: an explicit --path is a claim about the file, so it fails.
    code, missing = run("verify", "--path", str(config_path), "--timeout", "20", check=False)
    assert code == 1
    assert missing["status"] == "failed" and missing["argv_source"] == "installed"
    assert any("not installed" in reason for reason in missing["reasons"])

    _, installed = run("install", "--path", str(config_path))
    assert installed["status"] == "complete"
    _, verified = run("verify", "--path", str(config_path), "--timeout", "60")
    assert verified["status"] == "complete"
    assert verified["argv_source"] == "installed"
    assert verified["config_path"] == str(config_path)
    assert list(verified["command_argv"]) == list(installed["command_argv"])


def test_verify_without_a_config_falls_back_to_the_generated_entry(tmp_path: Path) -> None:
    receipt = probe_generated_server(env=_isolated_env(tmp_path), timeout_seconds=60.0)
    assert receipt.argv_source == "generated" and receipt.config_path is None


def test_probe_installed_entry_refuses_a_symlinked_config(tmp_path: Path) -> None:
    from l9_graphite_memory.client_config import probe_installed_entry

    real = tmp_path / "real.json"
    real.write_text('{"mcpServers": {}}', encoding="utf-8")
    link = tmp_path / "mcp.json"
    link.symlink_to(real)
    receipt = probe_installed_entry(link, env=_isolated_env(tmp_path), timeout_seconds=5.0)
    assert receipt.status == ClientConfigStatus.FAILED
    assert receipt.command_argv == ()
    assert "target path is a symlink" in receipt.reasons
