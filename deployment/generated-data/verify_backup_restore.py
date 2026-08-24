# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: deployment/generated-data/verify_backup_restore.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def integrity(path: Path) -> str:
    connection = sqlite3.connect(path)
    try:
        return str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    source = Path(args.database).resolve()
    output = Path(args.output_dir).resolve()

    if not source.is_file():
        raise SystemExit(f"Database not found: {source}")

    if source == output or output in source.parents:
        raise SystemExit("Output directory must not be the source database")

    output.mkdir(parents=True, exist_ok=True)

    backup = output / f"{source.name}.backup"
    restored = output / f"{source.name}.restored"

    shutil.copy2(source, backup)
    shutil.copy2(backup, restored)

    source_hash = sha256(source)
    backup_hash = sha256(backup)
    restored_hash = sha256(restored)

    source_integrity = integrity(source)
    backup_integrity = integrity(backup)
    restored_integrity = integrity(restored)

    passed = (
        source_hash == backup_hash == restored_hash
        and source_integrity == "ok"
        and backup_integrity == "ok"
        and restored_integrity == "ok"
    )

    result: dict[str, Any] = {
        "passed": passed,
        "source": {
            "path": str(source),
            "sha256": source_hash,
            "integrity": source_integrity,
        },
        "backup": {
            "path": str(backup),
            "sha256": backup_hash,
            "integrity": backup_integrity,
        },
        "restored": {
            "path": str(restored),
            "sha256": restored_hash,
            "integrity": restored_integrity,
        },
        "source_modified": False,
        "replay_required_for_post_backup_operations": True,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
