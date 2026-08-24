# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/generated_data/test_migration_verifier.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERIFIER = ROOT / "deployment" / "generated-data" / "verify_migration.py"


def create_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE memory_records (
                record_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                body TEXT NOT NULL
            );

            INSERT INTO memory_records (
                record_id,
                state,
                body
            ) VALUES
                ('active-1', 'active', 'a'),
                ('quarantine-1', 'quarantined', 'b'),
                ('archive-1', 'archived', 'c'),
                ('deleted-1', 'deleted', 'd');

            CREATE TABLE schema_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT INTO schema_metadata (
                key,
                value
            ) VALUES ('version', 'previous');
            """
        )
        connection.commit()
    finally:
        connection.close()


def invoke(
    operation: str,
    database: Path,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            operation,
            "--database",
            str(database),
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


class MigrationVerifierTests(unittest.TestCase):
    def test_inspect_preserves_source_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "memory.sqlite3"
            create_database(database)
            before = database.read_bytes()

            completed = invoke(
                "inspect",
                database,
            )

            after = database.read_bytes()

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        self.assertEqual(before, after)
        result = json.loads(completed.stdout)
        self.assertTrue(result["passed"])

    def test_dry_run_uses_copy_and_preserves_source(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "memory.sqlite3"
            create_database(database)
            before = database.read_bytes()

            completed = invoke(
                "dry-run",
                database,
            )

            after = database.read_bytes()

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        self.assertEqual(before, after)

    def test_apply_requires_backup_argument(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "memory.sqlite3"
            create_database(database)

            completed = invoke(
                "apply",
                database,
            )

        self.assertNotEqual(
            completed.returncode,
            0,
        )
        self.assertIn(
            "--backup is required",
            completed.stderr,
        )

    def test_mixed_lifecycle_rows_remain_readable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "memory.sqlite3"
            create_database(database)

            completed = invoke(
                "verify",
                database,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr,
            )

            connection = sqlite3.connect(database)
            try:
                states = {row[0] for row in connection.execute("SELECT state FROM memory_records")}
            finally:
                connection.close()

        self.assertEqual(
            states,
            {
                "active",
                "quarantined",
                "archived",
                "deleted",
            },
        )

    def test_missing_database_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "missing.sqlite3"

            completed = invoke(
                "inspect",
                database,
            )

        self.assertNotEqual(
            completed.returncode,
            0,
        )
        self.assertIn(
            "Database does not exist",
            completed.stderr,
        )


if __name__ == "__main__":
    unittest.main()
