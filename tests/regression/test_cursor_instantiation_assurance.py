# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/regression/test_cursor_instantiation_assurance.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-27

"""Regression pins for the Cursor instantiation control plane."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLIENT_CONFIG_DIR = REPO_ROOT / "src" / "l9_graphite_memory" / "client_config"
FORBIDDEN_IMPORT_MARKERS = (
    "l9_graphite_memory.store",
    "l9_graphite_memory.projection",
    "l9_graphite_memory.services",
    "sqlite3",
    "graphiti",
    "zep",
)


def _imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_client_config_never_imports_store_or_projection_layers() -> None:
    for path in sorted(CLIENT_CONFIG_DIR.glob("*.py")):
        for name in _imports_of(path):
            for marker in FORBIDDEN_IMPORT_MARKERS:
                assert not name.startswith(marker), f"{path.name} imports forbidden layer {name}"


def test_legacy_writer_interface_is_preserved() -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        import write_cursor_config

        entry = write_cursor_config.server_entry()
    finally:
        sys.path.remove(str(REPO_ROOT / "scripts"))
    assert entry["command"] == sys.executable
    assert entry["args"] == [
        "-m",
        "l9_graphite_memory.server",
        "--transport",
        "stdio",
    ]
    assert "env" not in entry


def test_legacy_writer_output_shape_unchanged(tmp_path: Path) -> None:
    target = tmp_path / "mcp.json"
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "write_cursor_config.py"),
            "--dry-run",
            "--path",
            str(target),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert set(payload) == {"path", "dry_run", "config"}
    assert payload["dry_run"] is True
    assert payload["path"] == str(target)
    servers = payload["config"]["mcpServers"]
    assert "l9-graphite-memory" in servers
    assert not target.exists()


def test_example_config_matches_canonical_generator() -> None:
    from l9_graphite_memory.client_config import managed_server_entry

    example = json.loads((REPO_ROOT / "config" / "mcp.json.example").read_text(encoding="utf-8"))
    entry = example["mcpServers"]["l9-graphite-memory"]
    canonical = managed_server_entry().as_config()
    canonical["command"] = "python3"
    assert entry == canonical


def test_manifest_covers_client_config_package() -> None:
    manifest = json.loads((REPO_ROOT / "manifest.json").read_text(encoding="utf-8"))
    listed = {item["path"] for item in manifest["files"]}
    expected = {
        "src/l9_graphite_memory/client_config/__init__.py",
        "src/l9_graphite_memory/client_config/contracts.py",
        "src/l9_graphite_memory/client_config/cursor.py",
        "src/l9_graphite_memory/client_config/mcp_probe.py",
        "docs/adr/ADR-064-cursor-client-instantiation-and-proof-boundary.md",
        "docs/CURSOR_INSTANTIATION.md",
    }
    missing = expected - listed
    assert not missing, f"manifest missing {sorted(missing)}"


def test_client_config_files_carry_l9_meta() -> None:
    for path in sorted(CLIENT_CONFIG_DIR.glob("*.py")):
        head = path.read_text(encoding="utf-8").splitlines()[:12]
        assert any("L9_META" in line for line in head), path.name


def test_cli_exposes_client_command_group() -> None:
    from l9_graphite_memory.cli import build_parser

    parser = build_parser()
    result = parser.parse_args(["client", "cursor", "install", "--dry-run", "--path", "x.json"])
    assert result.command == "client"
    assert result.client_target == "cursor"
    assert result.cursor_action == "install"
    assert result.dry_run is True
