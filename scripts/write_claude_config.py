#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: scripts/write_claude_config.py
#   layer: operations
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Write a secret-free Claude Desktop MCP entry for the installed package."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path


def default_path() -> Path:
    system = platform.system()
    if system == "Darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    if system == "Windows":
        return Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def server_entry() -> dict[str, object]:
    return {
        "command": sys.executable,
        "args": ["-m", "l9_graphite_memory.server", "--transport", "stdio"],
    }


def write_config(*, dry_run: bool = False, path: Path | None = None) -> dict[str, object]:
    target = path or default_path()
    existing: dict[str, object] = {}
    if target.is_file():
        try:
            decoded = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(decoded, dict):
                existing = decoded
        except (OSError, json.JSONDecodeError):
            existing = {}
    servers = existing.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("mcpServers must be a JSON object")  # noqa: TRY004
    servers["l9-graphite-memory"] = server_entry()
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    return {"path": str(target), "dry_run": dry_run, "config": existing}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--path", type=Path, default=None)
    args = parser.parse_args()
    sys.stdout.write(
        json.dumps(write_config(dry_run=args.dry_run, path=args.path), indent=2) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
