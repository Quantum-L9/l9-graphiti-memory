#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/generate_validation_evidence.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-27

"""Generate evidence-bearing validation records from executed release logs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPOSITORY: Final = "Quantum-L9/l9-graphiti-memory"
RELEASE: Final = "2.2.0"


@dataclass(frozen=True, slots=True)
class CheckSpec:
    check_id: str
    check_class: str
    target_artifact: str
    method: str
    log_path: str
    expected_result: str
    success_pattern: str | None = None
    allow_empty_log: bool = False
    severity: str = "high"


CHECKS: Final[tuple[CheckSpec, ...]] = (
    CheckSpec(
        "V-001",
        "execution",
        "tests/",
        "pytest -q",
        "logs/pytest.txt",
        # 498 is the count CI produces: the postgres service is present so the
        # shared-backend matrix runs, while the four cross-repo contract tests
        # skip because CI checks out only this repository, and the constellation-SDK
        # contract tests skip because CI omits the constellation extra. A workspace with a
        # sibling Cursor-Governance checkout reports 502 instead; point
        # CURSOR_GOVERNANCE_ROOT at a nonexistent path to reproduce CI.
        "498 tests pass",
        r"498 passed",
    ),
    CheckSpec(
        "V-002",
        "structural",
        "src tests tools scripts",
        "python -m compileall",
        "logs/compileall.txt",
        "Python sources compile",
        allow_empty_log=True,
    ),
    CheckSpec(
        "V-003",
        "contract",
        "docs/adr/",
        "validate_adrs.py",
        "logs/adr_validation.txt",
        "78 ADRs complete and indexed",
        r"PASS: 78 ADRs",
    ),
    CheckSpec(
        "V-004",
        "contract",
        "docs/harvest_decisions.yaml",
        "validate_harvest_coverage.py",
        "logs/harvest_coverage.txt",
        "51 harvest decisions closed",
        r"PASS: 51 harvest decisions",
    ),
    CheckSpec(
        "V-005",
        "structural",
        "repository files",
        "check_l9_meta.py",
        "logs/l9_meta.txt",
        "all tracked files carry L9_META",
        r"PASS: all tracked files carry L9_META",
    ),
    CheckSpec(
        "V-006",
        "contract",
        "src/l9_graphite_memory",
        "check_layer_boundaries.py",
        "logs/layer_boundaries.txt",
        "dependency directions aligned",
        r"PASS: core, adapter, service, and integration",
    ),
    CheckSpec(
        "V-007",
        "regression",
        "repository",
        "check_recursive_alignment.py",
        "logs/recursive_alignment.txt",
        "all ten recursive passes satisfied",
        r"PASS: recursive L9 alignment",
    ),
    CheckSpec(
        "V-008",
        "security",
        "canonical writes",
        "check_memory_write_bypass.py",
        "logs/bypass_check.txt",
        "zero write bypasses",
        r"PASS: no canonical memory write bypasses",
    ),
    CheckSpec(
        "V-009",
        "contract",
        "configuration",
        "check_config_drift.py",
        "logs/config_drift.txt",
        "zero configuration drift findings",
        r"PASS: canonical configuration defaults",
    ),
    CheckSpec(
        "V-010",
        "structural",
        "src/l9_graphite_memory",
        "audit_package_wiring.py",
        "logs/wiring_audit.txt",
        "zero unexplained orphans",
        r"orphans=0",
    ),
    CheckSpec(
        "V-011",
        "structural",
        "production Python",
        "check_source_quality.py",
        "logs/source_quality.txt",
        "118 production files pass",
        r"PASS: 118 production Python files",
    ),
    CheckSpec(
        "V-012",
        "security",
        "tracked source",
        "check_secrets.py",
        "logs/committed_secrets.txt",
        "zero high-confidence secret findings",
        r'"finding_count": 0',
    ),
    CheckSpec(
        "V-013",
        "execution",
        "in-memory canonical path",
        "benchmark_local.py --iterations 40",
        "logs/local_benchmark.txt",
        "local SLO thresholds pass",
        r'"status": "PASS"',
    ),
    CheckSpec(
        "V-014",
        "operator",
        "repository",
        "scripts/preflight.sh",
        "logs/preflight.txt",
        "27 preflight gates pass",
        r"Preflight complete: 27 gates passed",
    ),
    CheckSpec(
        "V-015",
        "structural",
        "hooks and scripts",
        "bash -n",
        "logs/shell_syntax.txt",
        "all shell files parse",
        r"All shell files parse",
    ),
    CheckSpec(
        "V-016",
        "execution",
        "Python wheel",
        "python -m build --wheel",
        "logs/wheel_build.txt",
        "v2.2.0 wheel builds",
        r"Successfully built l9_graphite_memory-2\.2\.0-py3-none-any\.whl",
    ),
    CheckSpec(
        "V-017",
        "execution",
        "installed wheel",
        "uv pip install --target (or pip --target)",
        "logs/wheel_install.txt",
        "isolated wheel installs",
        r"l9-graphite-memory==2\.2\.0",
    ),
    CheckSpec(
        "V-018",
        "execution",
        "installed registry",
        "python -m l9_graphite_memory resolve",
        "logs/installed_resolve.txt",
        "registry resolution succeeds",
        r'"group_id": "l9-graphiti-memory"',
    ),
    CheckSpec(
        "V-019",
        "execution",
        "installed CLI",
        "python -m l9_graphite_memory health",
        "logs/installed_health.txt",
        "installed health is complete",
        r'"status": "complete"',
    ),
    CheckSpec(
        "V-020",
        "execution",
        "installed MCP/resources/entrypoints",
        "installed smoke script",
        "logs/installed_mcp.txt",
        "30 tools and required surfaces load",
        r"30 tools loaded",
    ),
    CheckSpec(
        "V-021",
        "execution",
        "installed Cursor client lifecycle",
        "python -m l9_graphite_memory.cli client cursor install",
        "logs/installed_cursor_client.txt",
        "managed entry installed under isolated HOME",
        r'"managed_entry_present": true',
    ),
    CheckSpec(
        "V-022",
        "execution",
        "installed Cursor instantiation probe",
        "python -m l9_graphite_memory.cli client cursor verify",
        "logs/installed_cursor_probe.txt",
        "stdio handshake, tool inventory, and health prove instantiation",
        r'"status": "complete"',
    ),
)

EXTERNAL_BLOCKERS: Final[tuple[dict[str, str], ...]] = (
    {
        "id": "B-001",
        "check": "canonical TransportPacket and Gate integration",
        "reason": "canonical package import path, constructor, and production Gate receipt schema are unavailable in this pack",
        "required_evidence": "credentialed staging dispatch of root and follow-up packets with trace and lineage proof",
    },
    {
        "id": "B-002",
        "check": "live Graphiti and Zep lifecycle",
        "reason": "requires disposable authenticated providers and credentials",
        "required_evidence": "add, search, supersede, delete, outbox replay, and provider locator confirmation",
    },
    {
        "id": "B-003",
        "check": "production migration and rollback",
        "reason": "requires production-like legacy data and an authorized environment",
        "required_evidence": "rehearsal report with record counts, temporal equivalence, rollback, and data-loss checks",
    },
    {
        "id": "B-004",
        "check": "hosted repository controls",
        "reason": "requires GitHub-hosted Ruff, mypy, CodeQL, branch protection, and release environment execution",
        "required_evidence": "successful hosted workflow runs and repository-settings evidence",
    },
    {
        "id": "B-005",
        "check": "external secret loading and rotation",
        "reason": "requires an authorized secret manager and provider credentials",
        "required_evidence": "load, rotation, revocation, and no-plaintext-persistence evidence",
    },
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _evaluate(root: Path, spec: CheckSpec) -> dict[str, object]:
    evidence_path = root / "validation" / spec.log_path
    if not evidence_path.is_file():
        status = "UNKNOWN"
        actual = "evidence log missing"
        digest = None
    else:
        content = evidence_path.read_text(encoding="utf-8", errors="replace")
        matched = (
            bool(re.search(spec.success_pattern, content))
            if spec.success_pattern
            else spec.allow_empty_log or bool(content.strip())
        )
        status = "PASS" if matched else "FAIL"
        actual = (
            "expected evidence present"
            if matched
            else "expected evidence pattern absent"
        )
        digest = _sha256(evidence_path)
    return {
        "actual_result": actual,
        "check_class": spec.check_class,
        "check_id": spec.check_id,
        "evidence": {
            "path": f"validation/{spec.log_path}",
            "sha256": digest,
        },
        "expected_result": spec.expected_result,
        "method": spec.method,
        "remediation_if_failed": f"Rerun {spec.method} and correct the underlying failure before release.",
        "severity": spec.severity,
        "status": status,
        "target_artifact": spec.target_artifact,
    }


def _write_jsonl(
    path: Path, rows: tuple[dict[str, object], ...] | list[dict[str, object]]
) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def generate(root: Path) -> int:
    validation = root / "validation"
    validation.mkdir(parents=True, exist_ok=True)
    checks = [_evaluate(root, spec) for spec in CHECKS]
    failed = [row for row in checks if row["status"] == "FAIL"]
    unknown = [row for row in checks if row["status"] == "UNKNOWN"]
    status = "BLOCKED_ON_VALIDATION" if failed or unknown else "APPROVED_WITH_FINDINGS"

    findings: list[dict[str, object]] = []
    for blocker in EXTERNAL_BLOCKERS:
        findings.append(
            {
                "blocks_production_release": True,
                "confidence": "confirmed",
                "evidence": "external execution not available in the local pack",
                "finding_id": blocker["id"],
                "finding_type": "external_validation_blocker",
                "impact": "production release cannot be claimed from local evidence alone",
                "reason": blocker["reason"],
                "required_evidence": blocker["required_evidence"],
                "severity": "high",
                "target_check": blocker["check"],
            }
        )

    report = {
        "blocked_external_checks": len(findings),
        "checks_failed": len(failed),
        "checks_passed": sum(1 for row in checks if row["status"] == "PASS"),
        "checks_unknown": len(unknown),
        "generated_from": "executed files under validation/logs and explicit external blocker declarations",
        "local_deterministic_status": "PASS" if not failed and not unknown else "FAIL",
        "production_release_status": "BLOCKED_ON_EXTERNAL_VALIDATION"
        if not failed and not unknown
        else "BLOCKED_ON_VALIDATION",
        "release": RELEASE,
        "repository": REPOSITORY,
        "review_package_status": status,
        "schema": "l9.validation-report/v1",
    }
    (validation / "validation_report.yaml").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_jsonl(validation / "validation_checks.jsonl", checks)
    _write_jsonl(validation / "validation_findings.jsonl", findings)

    if failed or unknown:
        sys.stdout.write(
            f"FAIL: checks_failed={len(failed)} checks_unknown={len(unknown)}\n"
        )
        return 1
    sys.stdout.write(
        f"PASS: {len(checks)} local checks evidenced; {len(findings)} external blockers recorded\n"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    return generate(parser.parse_args().repo_root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
