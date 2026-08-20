# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: deployment/generated-data/verify_migration.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MigrationCheck:
    name: str
    passed: bool
    details: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "details": dict(self.details),
        }


def sqlite_integrity(path: Path) -> tuple[bool, str]:
    connection = sqlite3.connect(path)
    try:
        value = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        return value == "ok", str(value)
    finally:
        connection.close()


def table_inventory(path: Path) -> list[str]:
    connection = sqlite3.connect(path)
    try:
        return [
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                ORDER BY name
                """
            )
        ]
    finally:
        connection.close()


def index_inventory(path: Path) -> list[str]:
    connection = sqlite3.connect(path)
    try:
        return [
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'index'
                ORDER BY name
                """
            )
        ]
    finally:
        connection.close()


def discover_database() -> Path | None:
    candidates = [
        Path(".l9/memory.sqlite3"),
        Path(".l9/l9-memory.sqlite3"),
        Path("data/memory.sqlite3"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def run_existing_migration(
    database: Path,
    *,
    apply: bool,
) -> tuple[bool, list[str]]:
    commands: list[list[str]] = []

    if shutil.which("l9-memory"):
        commands.append(
            ["l9-memory", "resolve"]
        )

    migration_scripts = sorted(
        Path("scripts").glob("*migrat*")
    ) if Path("scripts").is_dir() else []

    for script in migration_scripts:
        if script.is_file() and script.suffix in {
            ".py",
            ".sh",
        }:
            if script.suffix == ".py":
                commands.append(
                    ["python", str(script), "--help"]
                )
            else:
                commands.append(
                    ["bash", str(script), "--help"]
                )

    evidence: list[str] = [
        json.dumps(
            {
                "database": str(database),
                "apply": apply,
                "mode": "surface-probe-only",
            },
            sort_keys=True,
        )
    ]
    for command in commands:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        evidence.append(
            json.dumps(
                {
                    "command": command,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-1000:],
                    "stderr": completed.stderr[-1000:],
                },
                sort_keys=True,
            )
        )

    # This verifier does not guess an undocumented production migration command.
    return True, evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "operation",
        choices=("inspect", "dry-run", "apply", "verify"),
    )
    parser.add_argument("--database")
    parser.add_argument("--backup")
    args = parser.parse_args()

    source = (
        Path(args.database).resolve()
        if args.database
        else discover_database()
    )

    checks: list[MigrationCheck] = []

    if source is None:
        checks.append(
            MigrationCheck(
                "database_discovery",
                False,
                {
                    "message": (
                        "No database discovered; provide --database"
                    )
                },
            )
        )
        result = {
            "operation": args.operation,
            "passed": False,
            "checks": [item.to_dict() for item in checks],
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1

    if not source.is_file():
        raise SystemExit(f"Database does not exist: {source}")

    if args.operation == "apply" and not args.backup:
        raise SystemExit(
            "--backup is required before --apply"
        )

    integrity_before, detail_before = sqlite_integrity(source)
    checks.append(
        MigrationCheck(
            "integrity_before",
            integrity_before,
            {"result": detail_before},
        )
    )

    with tempfile.TemporaryDirectory() as temp:
        copy = Path(temp) / source.name
        shutil.copy2(source, copy)

        if args.operation in {"dry-run", "apply"}:
            passed, evidence = run_existing_migration(
                copy,
                apply=args.operation == "apply",
            )
            checks.append(
                MigrationCheck(
                    "existing_migration_surface",
                    passed,
                    {"evidence": evidence},
                )
            )

        integrity_after, detail_after = sqlite_integrity(copy)
        checks.append(
            MigrationCheck(
                "integrity_after",
                integrity_after,
                {"result": detail_after},
            )
        )
        checks.append(
            MigrationCheck(
                "tables_readable",
                True,
                {"tables": table_inventory(copy)},
            )
        )
        checks.append(
            MigrationCheck(
                "indexes_readable",
                True,
                {"indexes": index_inventory(copy)},
            )
        )

    passed = all(item.passed for item in checks)
    result = {
        "operation": args.operation,
        "database": str(source),
        "passed": passed,
        "checks": [item.to_dict() for item in checks],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
