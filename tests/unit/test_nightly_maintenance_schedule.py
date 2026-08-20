# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_nightly_maintenance_schedule.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""SP-15 / SP-16: nightly scheduling is 02:00 America/New_York, and the runner
is a caller of the control plane rather than an owner of canonical state."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "nightly-maintenance.yml"
GATE_PATH = ROOT / "tools" / "ci" / "nightly_maintenance_gate.py"
TZ = ZoneInfo("America/New_York")


def _load_gate():
    spec = importlib.util.spec_from_file_location("nightly_gate", GATE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


# -- SP-15: the schedule ------------------------------------------------------


def test_workflow_is_scheduled_on_both_candidate_utc_instants(workflow) -> None:
    """02:00 America/New_York is 06:00 UTC in EDT and 07:00 UTC in EST."""

    schedule = workflow[True]["schedule"]
    assert [entry["cron"] for entry in schedule] == ["0 6,7 * * *"]


def test_workflow_declares_the_maintenance_timezone(gate) -> None:
    assert gate.MAINTENANCE_TIMEZONE == "America/New_York"
    assert gate.MAINTENANCE_HOUR == 2


@pytest.mark.parametrize(
    ("utc", "expected"),
    [
        # Standard time: 07:00 UTC is 02:00 EST.
        ("2026-01-15T07:00:00+00:00", True),
        ("2026-01-15T06:00:00+00:00", False),
        # Daylight time: 06:00 UTC is 02:00 EDT.
        ("2026-06-15T06:00:00+00:00", True),
        ("2026-06-15T07:00:00+00:00", False),
    ],
)
def test_exactly_one_firing_is_admitted_per_day(gate, utc: str, expected: bool) -> None:
    should_run, _ = gate.decide(datetime.fromisoformat(utc))
    assert should_run is expected


def test_spring_forward_still_runs_once(gate) -> None:
    """On the date 02:00 local does not exist, the run is not skipped."""

    day = datetime(2026, 3, 8, tzinfo=timezone.utc)
    assert gate.decide(day.replace(hour=6))[0] is False
    should_run, reason = gate.decide(day.replace(hour=7))
    assert should_run is True
    assert "does not exist" in reason


def test_fall_back_runs_once(gate) -> None:
    """On the date 01:00 local happens twice, the run is not duplicated."""

    day = datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert gate.decide(day.replace(hour=6))[0] is False
    assert gate.decide(day.replace(hour=7))[0] is True


def test_every_day_of_the_year_admits_exactly_one_run(gate) -> None:
    """SP-15 as a property, not a spot check: 365 days, one run each."""

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for offset in range(365):
        day = start + timedelta(days=offset)
        admitted = [
            hour
            for hour in (6, 7)
            if gate.decide(day.replace(hour=hour))[0]
        ]
        local_date = day.replace(hour=7).astimezone(TZ).date()
        assert len(admitted) == 1, f"{local_date}: admitted firings {admitted}"


def test_gate_reports_its_decision_as_json(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(GATE_PATH),
            "--now",
            "2026-06-15T06:00:00+00:00",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "GITHUB_OUTPUT": str(tmp_path / "out")},
    )
    assert result.returncode == 0
    assert '"should_run": true' in result.stdout
    assert "should_run=true" in (tmp_path / "out").read_text(encoding="utf-8")


def test_manual_dispatch_bypasses_the_gate(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(GATE_PATH),
            "--now",
            "2026-06-15T15:00:00+00:00",
            "--force",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "GITHUB_OUTPUT": str(tmp_path / "out")},
    )
    assert result.returncode == 0
    assert '"should_run": true' in result.stdout


# -- SP-16: the runner is a caller, not an owner ------------------------------


def _job(workflow: dict) -> dict:
    return workflow["jobs"]["maintain"]


def test_workflow_invokes_the_control_plane_cli(workflow) -> None:
    steps = _job(workflow)["steps"]
    run_step = next(
        step for step in steps if step.get("name") == "Run canonical memory maintenance"
    )
    assert "l9-memory maintain" in run_step["run"]


def test_workflow_targets_the_shared_backend(workflow) -> None:
    """SP-16: canonical state is the shared store, reached over the network."""

    steps = _job(workflow)["steps"]
    run_step = next(
        step for step in steps if step.get("name") == "Run canonical memory maintenance"
    )
    env = run_step["env"]
    assert env["L9_MEMORY_STORE_BACKEND"] == "postgres"
    assert "L9_MEMORY_POSTGRES_DSN" in env
    assert "secrets.L9_MEMORY_POSTGRES_DSN" in env["L9_MEMORY_POSTGRES_DSN"]


def test_workflow_grants_only_maintain_authority(workflow) -> None:
    """SP-10 at the deployment boundary: no write, promote, or admin grant."""

    steps = _job(workflow)["steps"]
    run_step = next(
        step for step in steps if step.get("name") == "Run canonical memory maintenance"
    )
    env = run_step["env"]
    assert "L9_MEMORY_LOCAL_MAINTAIN_NAMESPACES" in env
    for forbidden in (
        "L9_MEMORY_LOCAL_WRITE_NAMESPACES",
        "L9_MEMORY_LOCAL_PROMOTE_NAMESPACES",
        "L9_MEMORY_LOCAL_IS_ADMIN",
    ):
        assert forbidden not in env


def test_workflow_never_owns_or_synchronizes_a_database_file(workflow) -> None:
    """SP-16: no DB file is created, cached, uploaded, downloaded, or committed."""

    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    forbidden_markers = (
        "L9_MEMORY_DATABASE_PATH",
        "memory.sqlite3",
        ".sqlite",
        "sqlite3 ",
        "download-artifact",
        "actions/cache",
        "git push",
        "git commit",
        "rsync",
        "scp ",
    )
    for marker in forbidden_markers:
        assert marker not in text, f"workflow must not reference {marker!r}"

    steps = _job(workflow)["steps"]
    # The only artifact leaving the runner is the maintenance receipt.
    uploads = [
        step for step in steps if "upload-artifact" in str(step.get("uses", ""))
    ]
    assert len(uploads) == 1
    assert uploads[0]["with"]["path"] == "maintenance-*.json"


def test_workflow_is_least_privilege_and_serialized(workflow) -> None:
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["group"] == "nightly-memory-maintenance"
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert _job(workflow)["timeout-minutes"] == 30


def test_workflow_carries_a_run_identity(workflow) -> None:
    steps = _job(workflow)["steps"]
    run_step = next(
        step for step in steps if step.get("name") == "Run canonical memory maintenance"
    )
    assert "github.run_id" in run_step["run"]


def test_scheduled_runs_apply_and_manual_runs_default_to_dry_run(workflow) -> None:
    steps = _job(workflow)["steps"]
    run_step = next(
        step for step in steps if step.get("name") == "Run canonical memory maintenance"
    )
    body = run_step["run"]
    assert "APPLY='--apply'" in body
    assert "workflow_dispatch" in body
    assert workflow[True]["workflow_dispatch"]["inputs"]["apply"]["default"] is False
