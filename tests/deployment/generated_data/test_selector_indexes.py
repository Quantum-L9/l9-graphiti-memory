from __future__ import annotations

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
    / "verify_selector_indexes.py"
)


def create_indexed_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE memory_source_selectors (
                selector_id TEXT PRIMARY KEY,
                record_id TEXT NOT NULL,
                repository TEXT NOT NULL,
                selector_type TEXT NOT NULL,
                selector_value TEXT NOT NULL,
                active INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                deactivated_at TEXT
            );

            CREATE INDEX
                idx_selector_repository_value
            ON memory_source_selectors (
                repository,
                selector_type,
                selector_value,
                active
            );

            CREATE INDEX
                idx_selector_record_active
            ON memory_source_selectors (
                record_id,
                active
            );

            INSERT INTO memory_source_selectors VALUES (
                'selector-1',
                'record-1',
                'Quantum-L9/example',
                'relevant_path_changed',
                'src/a.py',
                1,
                '2026-08-02T00:00:00Z',
                NULL
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


class SelectorIndexTests(unittest.TestCase):
    def test_indexed_schema_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "indexed.sqlite3"
            create_indexed_database(database)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(VERIFIER),
                    "--database",
                    str(database),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        result = json.loads(completed.stdout)
        self.assertTrue(result["passed"])
        self.assertTrue(result["selector_tables"])
        self.assertTrue(result["matching_indexes"])

    def test_unindexed_schema_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "unindexed.sqlite3"
            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    """
                    CREATE TABLE records (
                        record_id TEXT PRIMARY KEY,
                        body TEXT
                    )
                    """
                )
                connection.commit()
            finally:
                connection.close()

            completed = subprocess.run(
                [
                    sys.executable,
                    str(VERIFIER),
                    "--database",
                    str(database),
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
        result = json.loads(completed.stdout)
        self.assertFalse(result["passed"])
        self.assertTrue(result["failures"])

    def test_query_plan_uses_selector_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "indexed.sqlite3"
            create_indexed_database(database)

            connection = sqlite3.connect(database)
            try:
                plan = list(
                    connection.execute(
                        """
                        EXPLAIN QUERY PLAN
                        SELECT record_id
                        FROM memory_source_selectors
                        WHERE
                            repository = ?
                            AND selector_type = ?
                            AND selector_value = ?
                            AND active = 1
                        """,
                        (
                            "Quantum-L9/example",
                            "relevant_path_changed",
                            "src/a.py",
                        ),
                    )
                )
            finally:
                connection.close()

        details = " ".join(str(row) for row in plan)
        self.assertIn(
            "INDEX",
            details.upper(),
        )

    def test_unrelated_selector_is_not_matched(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "indexed.sqlite3"
            create_indexed_database(database)

            connection = sqlite3.connect(database)
            try:
                rows = list(
                    connection.execute(
                        """
                        SELECT record_id
                        FROM memory_source_selectors
                        WHERE
                            repository = ?
                            AND selector_type = ?
                            AND selector_value = ?
                            AND active = 1
                        """,
                        (
                            "Quantum-L9/example",
                            "relevant_path_changed",
                            "src/unrelated.py",
                        ),
                    )
                )
            finally:
                connection.close()

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
