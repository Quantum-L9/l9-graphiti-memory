# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_cursor_client_config.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-27

"""Unit coverage for the canonical Cursor client configurator."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from l9_graphite_memory.client_config import (
    MANAGED_SERVER_KEY,
    ClientConfigStatus,
    CursorClientConfigurator,
    managed_server_entry,
)
from l9_graphite_memory.errors import ConfigurationError


def _configurator(tmp_path: Path) -> CursorClientConfigurator:
    return CursorClientConfigurator(tmp_path / "mcp.json")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_managed_entry_is_secret_free_argv() -> None:
    entry = managed_server_entry()
    config = entry.as_config()
    assert config["command"] == sys.executable
    assert config["args"] == [
        "-m",
        "l9_graphite_memory.server",
        "--transport",
        "stdio",
    ]
    assert "env" not in config


def test_managed_entry_rejects_empty_interpreter() -> None:
    with pytest.raises(ConfigurationError):
        managed_server_entry("   ")


def test_install_creates_config_with_only_managed_entry(tmp_path: Path) -> None:
    configurator = _configurator(tmp_path)
    receipt = configurator.install()
    assert receipt.status == ClientConfigStatus.COMPLETE
    assert receipt.changed is True
    assert receipt.pre_sha256 is None
    assert receipt.post_sha256 is not None
    config = _read(configurator.path)
    assert set(config) == {"mcpServers"}
    assert set(config["mcpServers"]) == {MANAGED_SERVER_KEY}
    mode = os.stat(configurator.path).st_mode & 0o777
    assert mode == 0o600


def test_install_is_idempotent(tmp_path: Path) -> None:
    configurator = _configurator(tmp_path)
    first = configurator.install()
    second = configurator.install()
    assert first.status == ClientConfigStatus.COMPLETE
    assert second.status == ClientConfigStatus.UNCHANGED
    assert second.changed is False
    assert second.pre_sha256 == first.post_sha256
    assert second.post_sha256 == first.post_sha256


def test_install_dry_run_writes_nothing(tmp_path: Path) -> None:
    configurator = _configurator(tmp_path)
    receipt = configurator.install(dry_run=True)
    assert receipt.status == ClientConfigStatus.DRY_RUN
    assert receipt.changed is False
    assert not configurator.path.exists()


def test_install_preserves_unmanaged_servers_and_unknown_keys(
    tmp_path: Path,
) -> None:
    target = tmp_path / "mcp.json"
    original = {
        "mcpServers": {
            "other-server": {"command": "other", "args": ["--x"]},
        },
        "customTopLevel": {"keep": True},
    }
    target.write_text(json.dumps(original), encoding="utf-8")
    configurator = CursorClientConfigurator(target)
    receipt = configurator.install()
    assert receipt.status == ClientConfigStatus.COMPLETE
    assert receipt.preserved_server_keys == ("other-server",)
    config = _read(target)
    assert config["customTopLevel"] == {"keep": True}
    assert config["mcpServers"]["other-server"] == original["mcpServers"][
        "other-server"
    ]
    assert MANAGED_SERVER_KEY in config["mcpServers"]


def test_install_repairs_drifted_managed_entry(tmp_path: Path) -> None:
    target = tmp_path / "mcp.json"
    target.write_text(
        json.dumps(
            {
                "mcpServers": {
                    MANAGED_SERVER_KEY: {
                        "command": "stale-python",
                        "args": ["-m", "old.module"],
                        "env": {"LEAKED": "value"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    configurator = CursorClientConfigurator(target)
    receipt = configurator.install()
    assert receipt.status == ClientConfigStatus.COMPLETE
    managed = _read(target)["mcpServers"][MANAGED_SERVER_KEY]
    assert managed == configurator.entry.as_config()
    assert "env" not in managed


def test_install_blocks_on_invalid_json_without_data_loss(tmp_path: Path) -> None:
    target = tmp_path / "mcp.json"
    target.write_text("{not valid json", encoding="utf-8")
    configurator = CursorClientConfigurator(target)
    receipt = configurator.install()
    assert receipt.status == ClientConfigStatus.BLOCKED
    assert any("not valid JSON" in reason for reason in receipt.reasons)
    assert target.read_text(encoding="utf-8") == "{not valid json"


def test_install_blocks_on_non_object_root(tmp_path: Path) -> None:
    target = tmp_path / "mcp.json"
    target.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    receipt = CursorClientConfigurator(target).install()
    assert receipt.status == ClientConfigStatus.BLOCKED


def test_install_blocks_on_non_object_mcp_servers(tmp_path: Path) -> None:
    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"mcpServers": ["bad"]}), encoding="utf-8")
    receipt = CursorClientConfigurator(target).install()
    assert receipt.status == ClientConfigStatus.BLOCKED


def test_install_blocks_on_symlinked_config(tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    link = tmp_path / "mcp.json"
    link.symlink_to(real)
    receipt = CursorClientConfigurator(link).install()
    assert receipt.status == ClientConfigStatus.BLOCKED
    assert any("symlink" in reason for reason in receipt.reasons)


def test_install_creates_digest_bound_backup(tmp_path: Path) -> None:
    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    receipt = CursorClientConfigurator(target).install()
    assert receipt.backup_path is not None
    assert receipt.backup_sha256 == receipt.pre_sha256
    backup = Path(receipt.backup_path)
    assert backup.is_file()
    assert backup.name.endswith(receipt.pre_sha256[:12])


def test_uninstall_removes_only_managed_entry(tmp_path: Path) -> None:
    target = tmp_path / "mcp.json"
    configurator = CursorClientConfigurator(target)
    configurator.install()
    config = _read(target)
    config["mcpServers"]["other"] = {"command": "keep", "args": []}
    target.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    receipt = configurator.uninstall()
    assert receipt.status == ClientConfigStatus.COMPLETE
    assert receipt.preserved_server_keys == ("other",)
    remaining = _read(target)
    assert MANAGED_SERVER_KEY not in remaining["mcpServers"]
    assert "other" in remaining["mcpServers"]


def test_uninstall_when_absent_is_unchanged(tmp_path: Path) -> None:
    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    receipt = CursorClientConfigurator(target).uninstall()
    assert receipt.status == ClientConfigStatus.UNCHANGED
    assert receipt.changed is False


def test_uninstall_restore_verified_backup(tmp_path: Path) -> None:
    target = tmp_path / "mcp.json"
    configurator = CursorClientConfigurator(target)
    original = {"mcpServers": {"other": {"command": "keep", "args": []}}}
    target.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")
    install_receipt = configurator.install()
    assert install_receipt.backup_path is not None
    restore_receipt = configurator.uninstall(
        restore_backup=Path(install_receipt.backup_path)
    )
    assert restore_receipt.status == ClientConfigStatus.COMPLETE
    assert _read(target) == original


def test_restore_rejects_tampered_backup(tmp_path: Path) -> None:
    target = tmp_path / "mcp.json"
    configurator = CursorClientConfigurator(target)
    target.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    receipt = configurator.install()
    assert receipt.backup_path is not None
    backup = Path(receipt.backup_path)
    backup.write_text(json.dumps({"mcpServers": {"evil": {}}}), encoding="utf-8")
    with pytest.raises(ConfigurationError):
        configurator.uninstall(restore_backup=backup)


def test_status_reports_installed_and_missing(tmp_path: Path) -> None:
    configurator = _configurator(tmp_path)
    missing = configurator.status()
    assert missing.status == ClientConfigStatus.UNCHANGED
    assert missing.managed_entry_present is False
    configurator.install()
    present = configurator.status()
    assert present.status == ClientConfigStatus.COMPLETE
    assert present.managed_entry_present is True


def test_status_flags_env_block_as_warning(tmp_path: Path) -> None:
    target = tmp_path / "mcp.json"
    entry = managed_server_entry().as_config()
    entry["env"] = {"SHOULD_NOT": "exist"}
    target.write_text(
        json.dumps({"mcpServers": {MANAGED_SERVER_KEY: entry}}), encoding="utf-8"
    )
    receipt = CursorClientConfigurator(target).status()
    assert receipt.status == ClientConfigStatus.BLOCKED
    assert receipt.warnings


def test_inspect_reports_unmanaged_keys_and_digest(tmp_path: Path) -> None:
    target = tmp_path / "mcp.json"
    target.write_text(
        json.dumps({"mcpServers": {"a": {}, "b": {}}, "theme": "dark"}),
        encoding="utf-8",
    )
    inspection = CursorClientConfigurator(target).inspect()
    assert inspection.unmanaged_server_keys == ("a", "b")
    assert inspection.unknown_top_level_keys == ("theme",)
    assert inspection.config_sha256 is not None
    assert inspection.blockers == ()


def test_receipts_never_contain_secret_env_values(tmp_path: Path) -> None:
    secret = "never-persist-this-secret-value"
    previous = os.environ.get("FAKE_API_KEY")
    os.environ["FAKE_API_KEY"] = secret
    try:
        configurator = _configurator(tmp_path)
        receipt = configurator.install()
        encoded = receipt.model_dump_json() + json.dumps(
            _read(configurator.path)
        )
        assert secret not in encoded
    finally:
        if previous is None:
            os.environ.pop("FAKE_API_KEY", None)
        else:
            os.environ["FAKE_API_KEY"] = previous
