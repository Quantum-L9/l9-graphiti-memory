#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: scripts/write_cursor_config.py
#   layer: operations
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-27

"""Write a secret-free Cursor MCP entry for the installed memory package.

Compatibility wrapper: the canonical lifecycle lives in
``l9_graphite_memory.client_config`` and is exposed through the CLI as
``l9-memory client cursor install``. This wrapper preserves the historical
``server_entry``/``write_config`` interface pinned by the regression suite
while delegating every mutation to the atomic, evidence-bearing
configurator so there is exactly one write path.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from l9_graphite_memory.client_config import (
    CursorClientConfigurator,
    managed_server_entry,
)


def server_entry() -> dict[str, object]:
    return managed_server_entry().as_config()


def _projected_config(target: Path, entry_key: str) -> dict[str, object]:
    config: dict[str, object] = {}
    if target.is_file():
        try:
            decoded = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(decoded, dict):
                config = decoded
        except (OSError, json.JSONDecodeError):
            config = {}
    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("mcpServers must be a JSON object")  # noqa: TRY004
    servers[entry_key] = server_entry()
    return config


def write_config(
    *, dry_run: bool = False, path: Path | None = None
) -> dict[str, object]:
    configurator = CursorClientConfigurator(path)
    receipt = configurator.install(dry_run=dry_run)
    if receipt.status.value == "blocked":
        raise ValueError(
            "cursor config blocked: " + "; ".join(receipt.reasons)
        )
    config = _projected_config(Path(receipt.path), configurator.entry.key)
    return {"path": receipt.path, "dry_run": dry_run, "config": config}


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
