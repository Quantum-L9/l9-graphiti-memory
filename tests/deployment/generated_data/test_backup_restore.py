# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/generated_data/test_backup_restore.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERIFIER = (
    ROOT
    / "deployment"
    / "generated-data"
    / "verify_backup_restore.py"
)


def create_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE records (
                id TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT INTO records VALUES (
                'record-1',
                'canonical'
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


def sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


class BackupRestoreTests(unittest.TestCase):
    def test_backup_restore_is_byte_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = root / "source.sqlite3"
            output = root / "output"
            create_database(database)

            before = sha256(database)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(VERIFIER),
                    "--database",
                    str(database),
                    "--output-dir",
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )

            after = sha256(database)

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        self.assertEqual(before, after)

        result = json.loads(completed.stdout)
        self.assertTrue(result["passed"])
        self.assertEqual(
            result["source"]["sha256"],
            result["backup"]["sha256"],
        )
        self.assertEqual(
            result["backup"]["sha256"],
            result["restored"]["sha256"],
        )
        self.assertFalse(
            result["source_modified"]
        )

    def test_source_database_is_not_modified(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = root / "source.sqlite3"
            output = root / "output"
            create_database(database)
            before = database.read_bytes()

            subprocess.run(
                [
                    sys.executable,
                    str(VERIFIER),
                    "--database",
                    str(database),
                    "--output-dir",
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )

            after = database.read_bytes()

        self.assertEqual(before, after)

    def test_missing_database_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(VERIFIER),
                    "--database",
                    str(root / "missing.sqlite3"),
                    "--output-dir",
                    str(root / "output"),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )

        self.assertNotEqual(
            completed.returncode,
            0,
        )
        self.assertIn(
            "Database not found",
            completed.stderr,
        )


if __name__ == "__main__":
    unittest.main()
