# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_scan_finding_statements.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.1
#   updated: 2026-11-13
"""Statements restructured to clear code-scanning findings keep their exact behavior.

Covers the SQLite schema statements that are now module constants instead of
being formatted at the call site, the JUnit parser that refuses a DOCTYPE, and
the Git blob id that must stay SHA-1 because Git defines it that way.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from l9_graphite_memory.adapters import SQLiteRecordStore, sqlite_store

REPO_ROOT = Path(__file__).resolve().parents[2]
ASSURANCE = REPO_ROOT / "tools" / "assurance"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


EVIDENCE = _load("scan_validation_evidence", ASSURANCE / "generate_validation_evidence.py")


def test_lease_column_statements_match_the_previous_rendering() -> None:
    assert [column for column, _ in sqlite_store._OUTBOX_LEASE_COLUMN_DDL] == [
        "lease_id",
        "lease_owner",
        "lease_expires_at",
    ]
    for column, statement in sqlite_store._OUTBOX_LEASE_COLUMN_DDL:
        assert statement == f"ALTER TABLE outbox_events ADD COLUMN {column} TEXT"


def test_v8_links_statement_matches_the_previous_rendering() -> None:
    assert sqlite_store._PROJECTION_LINKS_V8_DDL == sqlite_store._PROJECTION_LINKS_DDL.format(
        table="projection_links_v8"
    )


def test_missing_lease_columns_are_added_by_the_constant_statements(tmp_path: Path) -> None:
    # lease_expires_at stays: idx_outbox_lease is created before the lease
    # columns are added, so a store without it cannot open at all (a separate,
    # pre-existing ordering defect). Dropping the other two exercises the
    # restructured ALTER statements on the path that is reachable today.
    database = tmp_path / "memory.sqlite3"
    store = SQLiteRecordStore(database)
    store.initialize()
    with store._transaction() as tx:
        tx.execute("ALTER TABLE outbox_events DROP COLUMN lease_id")
        tx.execute("ALTER TABLE outbox_events DROP COLUMN lease_owner")
    pre_lease = {row[1] for row in store._connection().execute("PRAGMA table_info(outbox_events)")}
    assert not {"lease_id", "lease_owner"} & pre_lease
    store.close()

    reopened = SQLiteRecordStore(database)
    reopened.initialize()
    try:
        columns = {
            row[1]: row[2]
            for row in reopened._connection().execute("PRAGMA table_info(outbox_events)")
        }
        for column in ("lease_id", "lease_owner", "lease_expires_at"):
            assert columns[column] == "TEXT"
    finally:
        reopened.close()


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_junit_report_parses_every_outcome(tmp_path: Path) -> None:
    report = _write(
        tmp_path / "junit.xml",
        '<?xml version="1.0" encoding="utf-8"?>'
        "<testsuites><testsuite>"
        '<testcase classname="tests.a" name="ok"/>'
        '<testcase classname="tests.a" name="bad"><failure message="x"/></testcase>'
        '<testcase classname="tests.a" name="boom"><error message="x"/></testcase>'
        '<testcase classname="tests.a" name="skip"><skipped message="why"/></testcase>'
        "</testsuite></testsuites>",
    )
    cases = EVIDENCE.parse_junit(report)
    assert [(case.key[1], case.outcome) for case in cases] == [
        ("ok", "passed"),
        ("bad", "failed"),
        ("boom", "error"),
        ("skip", "skipped"),
    ]


def test_junit_report_with_a_doctype_is_refused(tmp_path: Path) -> None:
    report = _write(
        tmp_path / "junit.xml",
        '<?xml version="1.0"?>'
        '<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>'
        '<testsuites><testcase classname="tests.a" name="&lol2;"/></testsuites>',
    )
    with pytest.raises(EVIDENCE.SuiteEvidenceError, match="DOCTYPE"):
        EVIDENCE.parse_junit(report)


def test_junit_report_with_an_external_entity_is_refused(tmp_path: Path) -> None:
    secret = _write(tmp_path / "secret.txt", "do-not-read")
    report = _write(
        tmp_path / "junit.xml",
        f'<!DOCTYPE r [<!ENTITY x SYSTEM "file://{secret}">]>'
        '<testsuites><testcase classname="tests.a" name="&x;"/></testsuites>',
    )
    with pytest.raises(EVIDENCE.SuiteEvidenceError, match="DOCTYPE"):
        EVIDENCE.parse_junit(report)


def test_malformed_junit_report_is_still_evidence_error(tmp_path: Path) -> None:
    report = _write(tmp_path / "junit.xml", "<testsuites><testcase></testsuites>")
    with pytest.raises(EVIDENCE.SuiteEvidenceError, match="not well-formed"):
        EVIDENCE.parse_junit(report)


def test_blob_id_is_the_git_blob_id(tmp_path: Path) -> None:
    topology = _load("scan_product_topology", ASSURANCE / "validate_product_topology.py")
    for data in (b"", b"hello\n", bytes(range(256))):
        blob = tmp_path / "blob"
        blob.write_bytes(data)
        expected = subprocess.run(
            ["git", "hash-object", "--no-filters", str(blob)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert topology.blob_id(data) == expected
