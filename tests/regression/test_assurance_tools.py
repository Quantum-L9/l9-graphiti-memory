# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/regression/test_assurance_tools.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_tool(name: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "assurance" / name),
            "--repo-root",
            str(ROOT),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_no_memory_write_bypasses() -> None:
    result = run_tool("check_memory_write_bypass.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_no_config_default_drift() -> None:
    result = run_tool("check_config_drift.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_adr_ledger_is_complete() -> None:
    result = run_tool("validate_adrs.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_package_has_no_unexplained_orphans() -> None:
    result = run_tool("audit_package_wiring.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_source_quality_rules_pass() -> None:
    result = run_tool("check_source_quality.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_no_high_confidence_committed_secrets() -> None:
    result = run_tool("check_secrets.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_local_slo_benchmark_passes() -> None:
    result = run_tool("benchmark_local.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_harvest_coverage_is_closed() -> None:
    result = run_tool("validate_harvest_coverage.py")
    assert result.returncode == 0, result.stdout + result.stderr
