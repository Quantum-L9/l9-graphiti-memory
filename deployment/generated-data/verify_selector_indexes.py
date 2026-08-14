from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

REQUIRED_SELECTOR_COLUMNS = {
    "record_id",
    "selector_type",
    "selector_value",
}


def inventories(
    database: Path,
) -> tuple[dict[str, set[str]], dict[str, str]]:
    connection = sqlite3.connect(database)
    try:
        tables: dict[str, set[str]] = {}
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ):
            name = row[0]
            columns = {
                column[1]
                for column in connection.execute(
                    f'PRAGMA table_info("{name}")'
                )
            }
            tables[name] = columns

        indexes = {
            row[0]: row[1]
            for row in connection.execute(
                """
                SELECT name, sql
                FROM sqlite_master
                WHERE type = 'index'
                AND sql IS NOT NULL
                """
            )
        }
        return tables, indexes
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    args = parser.parse_args()

    database = Path(args.database).resolve()
    if not database.is_file():
        raise SystemExit(
            f"Database not found: {database}"
        )

    tables, indexes = inventories(database)

    selector_tables = {
        name: columns
        for name, columns in tables.items()
        if REQUIRED_SELECTOR_COLUMNS <= columns
    }

    matching_indexes = {
        name: sql
        for name, sql in indexes.items()
        if "selector_type" in sql
        and "selector_value" in sql
    }

    passed = bool(selector_tables) and bool(matching_indexes)

    result: dict[str, Any] = {
        "database": str(database),
        "passed": passed,
        "selector_tables": {
            name: sorted(columns)
            for name, columns in selector_tables.items()
        },
        "matching_indexes": matching_indexes,
        "full_scan_for_ordinary_selector_lookup_allowed": False,
        "failures": [],
    }

    if not selector_tables:
        result["failures"].append(
            "No table contains record_id, selector_type "
            "and selector_value"
        )
    if not matching_indexes:
        result["failures"].append(
            "No index covers selector_type and selector_value"
        )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
