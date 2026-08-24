# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_cli_parser.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from l9_graphite_memory.cli import build_parser


def test_cli_exposes_consent_deletion_and_legacy_drain_surfaces() -> None:
    parser = build_parser()
    write = parser.parse_args(
        [
            "write",
            "user-1 prefers concise answers",
            "--kind",
            "preference",
            "--consent-subject-id",
            "user-1",
            "--consent-purpose",
            "remember communication preferences",
            "--consent-evidence",
            "explicit user request",
        ]
    )
    deletion = parser.parse_args(
        ["delete", "00000000-0000-0000-0000-000000000001", "request", "ticket-1"]
    )
    drain = parser.parse_args(["drain-legacy-write-queue"])

    assert write.consent_subject_id == "user-1"
    assert deletion.command == "delete"
    assert drain.command == "drain-legacy-write-queue"
    assert drain.dry_run is False


def test_cli_exposes_topology_plan_ingestion_with_preflight_default() -> None:
    parser = build_parser()
    preflight = parser.parse_args(
        [
            "ingest-topology-plan",
            "--plan",
            "/bundles/plan",
            "--topology-bundle",
            "/bundles/topology",
        ]
    )
    applied = parser.parse_args(
        [
            "ingest-topology-plan",
            "--plan",
            "/bundles/plan",
            "--topology-bundle",
            "/bundles/topology",
            "--apply",
        ]
    )
    assert preflight.command == "ingest-topology-plan"
    assert preflight.apply is False
    assert applied.apply is True
