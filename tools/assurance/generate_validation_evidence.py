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
RELEASE: Final = "2.5.0"


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
        # 608 is the count CI produces: the postgres service is present so the
        # shared-backend matrix runs, while the five cross-repo contract tests
        # skip because CI checks out only this repository, and the constellation-SDK
        # contract tests skip because CI omits the constellation extra. A workspace
        # that can reach a Cursor-Governance checkout runs some or all of those five
        # and reports more; point CURSOR_GOVERNANCE_ROOT at a nonexistent path to
        # reproduce CI. The five are not discovered uniformly:
        # test_cross_repo_contract.py path-sniffs for a sibling checkout, while
        # test_runtime_status_protocol.py runs only on an explicit
        # CURSOR_GOVERNANCE_ROOT -- so a bare sibling checkout yields 612, and a
        # sibling plus the exported variable yields 613.
        #
        # Re-pinned 602 -> 608 for ADR-079: test_phase_lock_write_atomicity.py
        # adds two cases across the three STORE_BACKENDS. All six run in CI --
        # the postgres leg included, which is where the advisory-lock path is
        # actually exercised, since a local run without
        # L9_MEMORY_TEST_POSTGRES_DSN skips it.
        #
        # Re-pinned 608 -> 649 for the publication-identity work: 41 cases added
        # across test_publication_identity.py, test_identity_golden_vectors.py,
        # test_locator_future_conformance.py and the v2 end-to-end suite. The
        # arithmetic is the same one that produced 608 -- collected minus the
        # fifteen CI skips (ten constellation-SDK, five cross-repo) -- and it
        # reproduces the old pin exactly on main: 623 collected - 15 = 608.
        # This branch collects 664, so 664 - 15 = 649.
        #
        # Re-pinned 649 -> 715 for the 2026-09-04 forensic repair: 66 cases
        # added across test_lifecycle_projection_consistency.py,
        # test_phase_lock_snapshot_scale.py, test_temporal_law.py,
        # test_idempotency_race_and_drift.py,
        # test_retrieval_projection_hydration.py, test_probe_redaction.py,
        # test_graphiti_http_projection_loop.py, the active-store conformance
        # suite, and test_authz.py. Same arithmetic: this branch collects 730,
        # so 730 - 15 = 715. Locally, export L9_MEMORY_TEST_POSTGRES_DSN to
        # reproduce the CI figure; without it the postgres legs skip.
        #
        # Re-pinned 715 -> 797 for GMP-001: quarantine review (ADR-080),
        # conflict links (ADR-081), and the Redis leg of the active-store
        # conformance suite, which CI now runs against a redis:7 service.
        # Same arithmetic: this branch collects 812, so 812 - 15 = 797. Export
        # both L9_MEMORY_TEST_POSTGRES_DSN and L9_MEMORY_TEST_REDIS_URL to
        # reproduce the CI figure locally.
        #
        # Re-pinned 797 -> 813 for ADR-082 (consumer control-plane transport
        # parity): 16 cases in test_control_plane_transport_parity.py, none
        # backend-parameterized. Same arithmetic: this branch collects 828,
        # so 828 - 15 = 813.
        #
        # Re-pinned 813 -> 836 for release 2.3.0 (campaign stage M2, consumer
        # conformance hardening): 15 cases in test_consumer_conformance.py,
        # 3 in test_installed_wheel_lifecycle.py, 3 more in
        # test_cursor_mcp_instantiation.py, 2 in
        # test_release_version_consistency.py. Same arithmetic: this branch
        # collects 851, so 851 - 15 = 836.
        #
        # Re-pinned 836 -> 840 for release 2.3.0 audit closure (ADR-082
        # amendment: governed-candidate supersession and close replay
        # forensics): 4 cases in test_control_plane_transport_parity.py.
        # Same arithmetic: this branch collects 855, so 855 - 15 = 840.
        #
        # Re-pinned 840 -> 841 for 2.3.1: one new case in
        # test_release_version_consistency.py (published extras must not
        # carry a git/URL Requires-Dist). Same arithmetic: 856 - 15 = 841.
        #
        # Re-pinned 841 -> 855 for MEM-P2-01 (search receipts bind every
        # result-affecting selector and a request digest): 14 cases in
        # test_search_request_identity.py stacked on 2.3.1. Same arithmetic:
        # 856 + 14 = 870 collected, 870 - 15 = 855.
        #
        # Re-pinned 855 -> 860 for the MCP tool-handler parity guard (PR #61,
        # ADR-014 invariants "every listed tool has exactly one handler" and
        # the unknown-tool error test): 5 cases in
        # test_release_b_capability.py, none backend-parameterized. Same
        # arithmetic: 870 + 5 = 875 collected, 875 - 15 = 860.
        #
        # Re-pinned 855 -> 1014 for 2.5.0 on the #63/#64 branch, before the
        # parity merge. Both terms are measured, not estimated: 1030
        # collected, and CI skips 16 (10 constellation_node_sdk,
        # 4 "Cursor-Governance checkout unavailable", 1 CURSOR_GOVERNANCE_ROOT,
        # 1 agent-lane identity), so 1030 - 16 = 1014. The added cases are the
        # signed-agent door's (ADR-0031), ADR-083's vocabulary and namespace
        # suites, and F-AUTH-1's typed-grant negative cases.
        #
        # This pin is CI's number, and the count is a property of the
        # ENVIRONMENT as much as of the suite. Three environments, all observed:
        #
        #   no postgres/redis                       867 passed, 107 skipped
        #   postgres + redis, governance sibling   1018 passed,  12 skipped
        #   CI (services, no governance sibling)   1014 passed,  16 skipped
        #
        # Only `collected` (1024 on this head) is invariant. So do not "fix" a local V-001
        # miss by pinning the local count: bring the environment to CI's shape
        # instead -- start postgres and redis, and run from a checkout with no
        # Cursor-Governance sibling, which is what makes the four cross-repo
        # contract tests skip as they do in CI.
        #
        # Re-pinned 1014 -> 1008 on the combined #61/#62 + #63/#64 head
        # (open-PR audit 2026-09-24): +5 handler-parity cases, and ADR-083's
        # namespace suite rewritten for F-64-AUTHZ-001 (26 cases -> 15). Same
        # arithmetic: 1030 + 5 - 26 + 15 = 1024 collected, 1024 - 16 = 1008.
        #
        # Re-pinned 1008 -> 1026 for ADR-084 (GraphScopeKey v1, graph
        # intelligence campaign PR-A): 13 cases in test_graph_scope_key.py
        # and 5 in tests/security/test_graph_tenant_isolation.py, none
        # skipped in CI. Same arithmetic: 1024 + 18 = 1042 collected,
        # 1042 - 16 = 1026.
        #
        # Re-pinned 1026 -> 1069 for ADR-085 (graph-intelligence port and
        # read-only Neo4j adapter, campaign PR-B): 43 unit cases
        # (test_graph_query_policy.py, test_neo4j_graph_intelligence_adapter.py,
        # test_graph_intelligence_factory.py) plus 2 live Neo4j cases that CI
        # skips without L9_MEMORY_TEST_NEO4J_URI. 1042 + 45 = 1087 collected,
        # CI skips 16 + 2 = 18, so 1087 - 18 = 1069.
        #
        # Re-pinned 1069 -> 1120 for ADR-086 (graph-intelligence contracts,
        # algorithm policy, evidence binding, service; campaign PR-C): 51
        # cases across test_graph_contracts.py, test_graph_algorithm_policy.py,
        # test_graph_evidence_linking.py, test_graph_service.py and
        # conformance/test_graph_intelligence_port.py, none skipped in CI.
        # 1087 + 51 = 1138 collected, 1138 - 18 = 1120.
        #
        # Re-pinned 1120 -> 1134 for ADR-087 (bounded structural graph
        # operations, campaign PR-D): 10 cases in
        # test_neo4j_structural_operations.py and 4 in test_graph_service.py
        # (search operations and the cap regression), plus 10 live cases in
        # integration/test_neo4j_graph_traversal.py that CI skips without
        # L9_MEMORY_TEST_NEO4J_URI. 1138 + 24 = 1162 collected, CI skips
        # 18 + 10 = 28, so 1162 - 28 = 1134.
        #
        # Re-pinned 1134 -> 1147 for ADR-088 (stream-only GDS analytics,
        # campaign PR-E): 13 cases in test_neo4j_gds_operations.py plus 11
        # live cases in integration/test_neo4j_gds_analytics.py that CI
        # skips without L9_MEMORY_TEST_NEO4J_URI. 1162 + 24 = 1186 collected,
        # CI skips 28 + 11 = 39, so 1186 - 39 = 1147.
        #
        # Re-pinned 1147 -> 1160 for ADR-089 (graph-intelligence public
        # surfaces and observability, campaign PR-F): 13 cases in
        # test_graph_public_surfaces.py, none skipped in CI.
        # 1186 + 13 = 1199 collected, 1199 - 39 = 1160.
        #
        # Re-pinned 1160 -> 1173 for ADR-090 (Graphiti episode identity and
        # live qualification, campaign PR-G): 13 cases in
        # test_graphiti_projection_episode_identity.py, none skipped in CI.
        # The live module tests/qualification/ skips as a whole without
        # graphiti_core, adding one CI skip: 39 + 1 = 40.
        #
        # Re-pinned 1173 -> 1195 for ADR-091 (campaign audit remediation,
        # PR-H): 6 cases in security/test_legacy_projection_erasure.py, 3 in
        # test_graph_evidence_linking.py, 13 in
        # test_graph_request_budget_and_policy.py; none skipped in CI.
        # Re-pinned 1195 -> 1201 for the #72 review fixes: 2 stale-link window
        # cases and 3 store-matrix release cases (memory, sqlite, postgres) in
        # test_legacy_projection_erasure.py, 1 stalled-search case.
        # Re-pinned 1201 -> 1217 for the second PR-H audit (PR-I): 6 store-matrix
        # failure-injection/restart and stale-plan cases, 6 path-hop binding
        # cases, 4 wall-clock request-ceiling cases.
        "1217 tests pass",
        r"1217 passed",
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
        # Re-pinned 79 -> 81 for GMP-001: ADR-080 (automated quarantine
        # review) and ADR-081 (canonical conflict links) join the ledger.
        # Re-pinned 81 -> 82 for ADR-082 (consumer control-plane transport
        # parity).
        # Re-pinned 83 -> 84 for ADR-084 (tenant-safe graph scope key).
        # Re-pinned 84 -> 85 for ADR-085 (graph intelligence port, Neo4j).
        # Re-pinned 85 -> 86 for ADR-086 (graph contracts and evidence).
        # Re-pinned 86 -> 87 for ADR-087 (bounded structural operations).
        # Re-pinned 87 -> 88 for ADR-088 (stream-only GDS analytics).
        # Re-pinned 88 -> 89 for ADR-089 (graph public surfaces, metrics).
        # Re-pinned 89 -> 90 for ADR-090 (Graphiti episode identity).
        # Re-pinned 90 -> 91 for ADR-091 (campaign audit remediation).
        "91 ADRs complete and indexed",
        r"PASS: 91 ADRs",
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
        # Re-pinned 120 -> 121: ingestion/publication_identity.py is a new
        # production module on this branch.
        #
        # Re-pinned 121 -> 124 for GMP-001: contracts/review.py, ports/review.py,
        # and curation/quarantine.py carry the quarantine review contract, port,
        # and evidence-bound reviewer (ADR-080).
        #
        # Re-pinned 124 -> 125 for ADR-082: contracts/capabilities.py carries
        # the control-plane capability receipt.
        # Re-pinned 127 -> 129 for ADR-084: graph/__init__.py and
        # graph/scope.py carry the GraphScopeKey v1 derivation.
        # Re-pinned 129 -> 133 for ADR-085: graph/ports.py,
        # adapters/null_graph_intelligence.py, adapters/neo4j_query_policy.py,
        # adapters/neo4j_graph_intelligence.py.
        # Re-pinned 133 -> 137 for ADR-086: graph/contracts.py,
        # graph/algorithm_policy.py, graph/evidence.py, graph/service.py.
        # Re-pinned 137 -> 138 for ADR-087: adapters/neo4j_graph_templates.py.
        # Re-pinned 138 -> 139 for ADR-088: adapters/neo4j_gds_templates.py.
        # Re-pinned 139 -> 140 for ADR-089: observability/graph_metrics.py.
        "140 production files pass",
        r"PASS: 140 production Python files",
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
        "v2.5.0 wheel builds",
        r"Successfully built l9_graphite_memory-2\.5\.0-py3-none-any\.whl",
    ),
    CheckSpec(
        "V-017",
        "execution",
        "installed wheel",
        "uv pip install --target (or pip --target)",
        "logs/wheel_install.txt",
        "isolated wheel installs",
        r"l9-graphite-memory==2\.5\.0",
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
        # Re-pinned 30 -> 31 for ADR-082: memory.capabilities joins the
        # canonical tool inventory.
        # Re-pinned 33 -> 44 for ADR-089: ten memory.graph.<operation> tools
        # plus memory.graph.capabilities join the canonical inventory.
        "44 tools and required surfaces load",
        r"44 tools loaded",
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
        actual = "expected evidence present" if matched else "expected evidence pattern absent"
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


def _write_jsonl(path: Path, rows: tuple[dict[str, object], ...] | list[dict[str, object]]) -> None:
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
        sys.stdout.write(f"FAIL: checks_failed={len(failed)} checks_unknown={len(unknown)}\n")
        return 1
    sys.stdout.write(
        f"PASS: {len(checks)} local checks evidenced; {len(findings)} external blockers recorded\n"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    return generate(parser.parse_args().repo_root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
