#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/generate_validation_evidence.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-10-02

"""Generate evidence-bearing validation records from executed release logs.

Logs are read from, and reports written to, one explicit evidence root
(``--evidence-dir``). The default is the untracked release workspace
``build/release-validation``; the generator never targets the tracked
``validation/`` tree, so release validation emits evidence without rewriting
the candidate it inspects.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, TypeVar
from xml.etree import ElementTree

REPOSITORY: Final = "Quantum-L9/l9-graphiti-memory"
RELEASE: Final = "3.0.0"
DEFAULT_EVIDENCE_DIR: Final = Path("build") / "release-validation"


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
    derived_suite: bool = False


CHECKS: Final[tuple[CheckSpec, ...]] = (
    CheckSpec(
        "V-001",
        "execution",
        "tests/",
        # Derived, not pinned (ADR-101): the suite is judged from the run's
        # JUnit report and the collected node ids at HEAD and at the merge-base
        # with origin/main, against the committed skip allow-list and
        # declared-removals files. No pass count is maintained by hand.
        "pytest -q --junitxml; pytest --collect-only -q at HEAD and at the merge-base",
        "logs/pytest.txt",
        "0 failed and 0 errors; every collected test passed or skipped; every skip "
        "reason declared; no undeclared test removed against the merge-base",
        derived_suite=True,
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
        # parity). Re-pinned 83 -> 84 for ADR-084 (projection runtime and
        # target-aware lifecycle).
        # Re-pinned 84 -> 85 for ADR-085 (tenant-safe graph scope key).
        # Re-pinned 85 -> 86 for ADR-086 (graph intelligence port, Neo4j).
        # Re-pinned 86 -> 87 for ADR-087 (graph contracts and evidence).
        # Re-pinned 87 -> 88 for ADR-088 (bounded structural operations).
        # Re-pinned 88 -> 89 for ADR-089 (stream-only GDS analytics).
        # Re-pinned 89 -> 90 for ADR-090 (graph public surfaces, metrics).
        # Re-pinned 90 -> 91 for ADR-091 (Graphiti episode identity).
        # Re-pinned 91 -> 92 for ADR-092 (campaign audit remediation).
        # Re-pinned 92 -> 93 for ADR-093 (graph intelligence V1 closure).
        # Re-pinned 93 -> 94 for ADR-094 (product topology and release
        # governance). Re-pinned 94 -> 95 for ADR-095 (structured source
        # invalidation lifecycle). Re-pinned 95 -> 96 for ADR-096 (canonical
        # repository corpus authority binding). Re-pinned 96 -> 97 for ADR-097
        # (active-memory runtime composition and full-capability readiness).
        # Re-pinned 97 -> 98 for ADR-098 (remote MCP transport and
        # signed-agent HTTP identity). Re-pinned 98 -> 99 for ADR-099
        # (retired repository inventory and L9_META enforcement).
        # Re-pinned 99 -> 100 for ADR-100 (native OAuth MCP full cutover).
        # Re-pinned 100 -> 101 for ADR-101 (derived V-001 suite validation).
        # Re-pinned 101 -> 102 for ADR-102 (OAuth resource server).
        # Re-pinned 102 -> 103 for ADR-103 (OAuth actor binding).
        "103 ADRs complete and indexed",
        r"PASS: 103 ADRs",
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
    # V-005 (check_l9_meta.py) retired with per-file L9_META enforcement
    # (ADR-099). The id is not reused.
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
        #
        # Re-pinned 127 -> 128 for ADR-084: projections/runtime.py carries the
        # projection runtime.
        #
        # Re-pinned 127 -> 129 for ADR-085: graph/__init__.py and
        # graph/scope.py carry the GraphScopeKey v1 derivation.
        # Re-pinned 129 -> 133 for ADR-086: graph/ports.py,
        # adapters/null_graph_intelligence.py, adapters/neo4j_query_policy.py,
        # adapters/neo4j_graph_intelligence.py.
        # Re-pinned 133 -> 137 for ADR-087: graph/contracts.py,
        # graph/algorithm_policy.py, graph/evidence.py, graph/service.py.
        # Re-pinned 137 -> 138 for ADR-088: adapters/neo4j_graph_templates.py.
        # Re-pinned 138 -> 139 for ADR-089: adapters/neo4j_gds_templates.py.
        # Re-pinned 139 -> 140 for ADR-090: observability/graph_metrics.py.
        # Re-pinned 128 -> 141 when the campaign merged over ADR-084: main's 128
        # plus the campaign's 13 graph-intelligence files.
        # Re-pinned 141 -> 142 for ADR-096: src/l9_graphite_memory/
        # repository_corpus.py joins the production surface.
        # Re-pinned 142 -> 143 for ADR-098: authz/remote_agent.py.
        # Re-pinned 143 -> 144 for the ADR-082 2026-10-16 amendment:
        # remote_client.py.
        # Re-pinned 144 -> 145 for ADR-102: authz/oauth.py.
        "145 production files pass",
        r"PASS: 145 production Python files",
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
        # Re-pinned 27 -> 25 for ADR-099: the "L9 metadata coverage" and
        # "release manifest" gates are retired.
        "25 preflight gates pass",
        r"Preflight complete: 25 gates passed",
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
        "release artifact set",
        # The artifact set is built once (self-contained mode) or supplied
        # already built (publication mode); either way the validated set is
        # recorded by digest, and the release wheel must be in it.
        "sha256sum over the validated release artifact directory",
        "logs/release_artifacts.txt",
        "v3.0.0 wheel present in the validated artifact set",
        r"l9_graphite_memory-3\.0\.0-py3-none-any\.whl",
    ),
    CheckSpec(
        "V-017",
        "execution",
        "installed wheel",
        "uv pip install --target (or pip --target)",
        "logs/wheel_install.txt",
        "isolated wheel installs",
        r"l9-graphite-memory==3\.0\.0",
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
        # Re-pinned 33 -> 44 for ADR-090: ten memory.graph.<operation> tools
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
    CheckSpec(
        "V-023",
        "execution",
        "installed wheel identity",
        "sha256sum of the installed wheel against the validated artifact set",
        "logs/installed_wheel_digest.txt",
        "the wheel proven by installed smoke is the wheel in the artifact set",
        r"installed wheel digest matches validated artifact set",
    ),
    CheckSpec(
        "V-024",
        "structural",
        "release candidate",
        # ADR-099: the retired metadata and inventory tools no longer run;
        # integrity is the tracked-byte digest compared before and after
        # substantive validation.
        "candidate digest comparison after substantive validation",
        "logs/candidate_integrity_post.txt",
        "tracked candidate unchanged by validation",
        r"PASS: candidate integrity",
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


def _evidence_label(root: Path, evidence_path: Path) -> str:
    try:
        return evidence_path.relative_to(root).as_posix()
    except ValueError:
        return evidence_path.as_posix()


# --- V-001: derived suite check (ADR-101) -------------------------------------
#
# Inputs, all written by scripts/validate_release.sh into the evidence root:
#   logs/pytest.txt               terminal output of the full run (-ra summary)
#   logs/pytest_junit.xml         per-test outcomes of that same run
#   logs/pytest_collect.txt       `pytest --collect-only -q` at the candidate
#   logs/suite_base.txt           the resolved merge-base, or UNRESOLVED: <why>
#   logs/pytest_collect_base.txt  `pytest --collect-only -q` at the merge-base
# and two committed declarations read from the candidate itself:
#   tools/assurance/suite_skip_allowlist.json
#   tools/assurance/suite_declared_removals.json
#
# A rule that is violated is FAIL. An input that is missing, unreadable,
# malformed, or undeterminable is UNKNOWN. Neither is ever PASS.

SUITE_SUMMARY_LOG: Final = "logs/pytest.txt"
SUITE_JUNIT: Final = "logs/pytest_junit.xml"
SUITE_COLLECT: Final = "logs/pytest_collect.txt"
SUITE_BASE: Final = "logs/suite_base.txt"
SUITE_BASE_COLLECT: Final = "logs/pytest_collect_base.txt"
SKIP_ALLOWLIST: Final = Path("tools") / "assurance" / "suite_skip_allowlist.json"
DECLARED_REMOVALS: Final = Path("tools") / "assurance" / "suite_declared_removals.json"
SKIP_ALLOWLIST_SCHEMA: Final = "l9.suite-skip-allowlist/v1"
DECLARED_REMOVALS_SCHEMA: Final = "l9.suite-declared-removals/v1"
# `ci` is the default and the strict profile: it admits only the skips CI's
# service-backed environment is expected to produce, which is what the old
# exact pin protected. `local` additionally admits skips that only a machine
# without the CI services produces; it is an explicit opt-in for diagnosis.
SUITE_PROFILES: Final = ("ci", "local")
SUITE_PROFILE_ENV: Final = "L9_SUITE_PROFILE"
_REPORT_LIMIT: Final = 10
_SUMMARY_COUNT = re.compile(
    r"(\d+) (passed|failed|skipped|xfailed|xpassed|errors?|warnings?|deselected|rerun)"
)
# pytest 9 reports unittest ``subTest`` and ``subtests`` results as their own
# summary items ("11 subtests passed"). They are counted under a separate
# "subtests <outcome>" key, never folded into the test-case counts that rule 2
# compares with JUnit.
_SUBTEST_COUNT = re.compile(r"(\d+) subtests (passed|failed|skipped|xfailed|xpassed)")
# One count, then ", count" repeats: linear, no nested optional quantifier. A
# count's label is one word, or "subtests" and one word (pytest 9).
_SUMMARY_LINE = re.compile(
    r"^=*\s*\d+ (?:subtests )?[a-z]+(?:, \d+ (?:subtests )?[a-z]+)* in [0-9.]+s\b"
)
_COLLECT_SUMMARY = re.compile(
    r"^(?:(?P<count>\d+) tests? collected|no tests collected)(?P<rest>.*?) in [0-9.]+s\b"
)


_T = TypeVar("_T")


class SuiteEvidenceError(Exception):
    """A V-001 input is missing, unreadable, malformed, or undeterminable."""


@dataclass(frozen=True, slots=True)
class SkipAllowance:
    entry_id: str
    kind: str
    pattern: re.Pattern[str]
    profiles: frozenset[str]
    justification: str


@dataclass(frozen=True, slots=True)
class SuiteCase:
    key: tuple[str, str]
    outcome: str  # passed | skipped | xfailed | failed | error
    reason: str = ""
    collection_skip: bool = False


@dataclass(slots=True)
class SuiteVerdict:
    violations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.violations:
            return "FAIL"
        if self.unknowns:
            return "UNKNOWN"
        return "PASS"


def _read_input(path: Path, label: str) -> str:
    if not path.is_file():
        raise SuiteEvidenceError(f"{label} missing: {path.name}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SuiteEvidenceError(f"{label} unreadable: {exc}") from exc


def _read_json(path: Path, label: str, schema: str) -> dict[str, object]:
    try:
        data = json.loads(_read_input(path, label))
    except json.JSONDecodeError as exc:
        raise SuiteEvidenceError(f"{label} is not JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != schema:
        raise SuiteEvidenceError(f"{label} does not declare schema {schema}")
    return data


def _required_text(entry: dict[str, object], key: str, label: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SuiteEvidenceError(f"{label}: {key} must be a non-empty string")
    return value


def load_skip_allowlist(path: Path) -> tuple[SkipAllowance, ...]:
    data = _read_json(path, "skip allow-list", SKIP_ALLOWLIST_SCHEMA)
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise SuiteEvidenceError("skip allow-list: entries must be a list")
    allowances: list[SkipAllowance] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        label = f"skip allow-list entry {index}"
        if not isinstance(entry, dict):
            raise SuiteEvidenceError(f"{label} is not an object")
        entry_id = _required_text(entry, "id", label)
        if entry_id in seen:
            raise SuiteEvidenceError(f"skip allow-list: duplicate id {entry_id}")
        seen.add(entry_id)
        kind = _required_text(entry, "kind", label)
        if kind not in {"skip", "xfail"}:
            raise SuiteEvidenceError(f"{label}: kind must be skip or xfail")
        profiles = entry.get("profiles")
        if (
            not isinstance(profiles, list)
            or not profiles
            or not set(profiles) <= set(SUITE_PROFILES)
        ):
            raise SuiteEvidenceError(
                f"{label}: profiles must be a non-empty subset of {SUITE_PROFILES}"
            )
        try:
            pattern = re.compile(_required_text(entry, "pattern", label))
        except re.error as exc:
            raise SuiteEvidenceError(f"{label}: pattern does not compile: {exc}") from exc
        allowances.append(
            SkipAllowance(
                entry_id,
                kind,
                pattern,
                frozenset(str(item) for item in profiles),
                _required_text(entry, "justification", label),
            )
        )
    return tuple(allowances)


def load_declared_removals(path: Path) -> dict[str, str]:
    data = _read_json(path, "declared removals", DECLARED_REMOVALS_SCHEMA)
    removals = data.get("removals")
    if not isinstance(removals, list):
        raise SuiteEvidenceError("declared removals: removals must be a list")
    declared: dict[str, str] = {}
    for index, entry in enumerate(removals):
        label = f"declared removal {index}"
        if not isinstance(entry, dict):
            raise SuiteEvidenceError(f"{label} is not an object")
        node_id = _required_text(entry, "node_id", label)
        if node_id in declared:
            raise SuiteEvidenceError(f"declared removals: duplicate node id {node_id}")
        declared[node_id] = _required_text(entry, "reason", label)
    return declared


def parse_collect_only(text: str, label: str) -> tuple[tuple[str, ...], int]:
    """Return the collected node ids and the collection error count.

    The ids are the first contiguous block of node-id lines that `pytest
    --collect-only -q` prints; its count must equal the summary line's.
    """

    lines = text.splitlines()
    summary = None
    for line in reversed(lines):
        summary = _COLLECT_SUMMARY.match(line.strip())
        if summary:
            break
    if summary is None:
        raise SuiteEvidenceError(f"{label}: no collection summary line")
    errors_match = re.search(r"(\d+) errors?", summary.group("rest"))
    errors = int(errors_match.group(1)) if errors_match else 0
    expected = int(summary.group("count") or 0)
    ids: list[str] = []
    started = False
    for line in lines:
        if not started:
            if "::" in line and not line[:1].isspace():
                started = True
            else:
                continue
        if not line.strip():
            break
        if "::" not in line or line[:1].isspace():
            raise SuiteEvidenceError(f"{label}: unexpected line in node-id block: {line!r}")
        ids.append(line.rstrip())
    if len(ids) != expected or len(set(ids)) != len(ids):
        raise SuiteEvidenceError(
            f"{label}: {len(ids)} node ids listed ({len(set(ids))} distinct), "
            f"summary says {expected}"
        )
    return tuple(ids), errors


def junit_key(node_id: str) -> tuple[str, str]:
    """Map a node id to the (classname, name) pair pytest's JUnit writer uses."""

    path, bracket, params = node_id.partition("[")
    names = path.split("::")
    names[0] = re.sub(r"\.py$", "", names[0].replace("/", "."))
    names[-1] += bracket + params
    return ".".join(names[:-1]), names[-1]


def _collection_skip_reason(text: str) -> str:
    # A module-level skip is written as str(longrepr), i.e. the repr of a
    # (path, lineno, "Skipped: <reason>") tuple.
    try:
        value = ast.literal_eval(text.strip())
    except (ValueError, SyntaxError) as exc:
        raise SuiteEvidenceError(f"JUnit collection skip has no readable reason: {text!r}") from exc
    if not (isinstance(value, tuple) and len(value) == 3 and isinstance(value[2], str)):
        raise SuiteEvidenceError(f"JUnit collection skip has no readable reason: {text!r}")
    return value[2].removeprefix("Skipped: ")


class _DoctypeRefusingBuilder(ElementTree.TreeBuilder):
    """Tree builder that refuses any DOCTYPE before its internal subset is read.

    Entity expansion (XXE, "billion laughs") needs a DTD, and a pytest JUnit
    report never declares one, so a report that does is refused outright: the
    same protection defusedxml's ``forbid_dtd`` gives, without the dependency.
    """

    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        raise SuiteEvidenceError(f"JUnit report declares a DOCTYPE ({name!r}); refused")


def parse_junit(path: Path) -> tuple[SuiteCase, ...]:
    report = _read_input(path, "JUnit report")
    parser = ElementTree.XMLParser(target=_DoctypeRefusingBuilder())
    try:
        # The report is this run's own pytest output; a DTD is refused anyway.
        parser.feed(report)
        root = parser.close()
    except ElementTree.ParseError as exc:
        raise SuiteEvidenceError(f"JUnit report is not well-formed XML: {exc}") from exc
    cases: list[SuiteCase] = []
    for case in root.iter("testcase"):
        key = (case.get("classname") or "", case.get("name") or "")
        children = {child.tag: child for child in case}
        if "failure" in children:
            cases.append(SuiteCase(key, "failed"))
        elif "error" in children:
            cases.append(SuiteCase(key, "error"))
        elif "skipped" in children:
            skipped = children["skipped"]
            message = skipped.get("message") or ""
            if skipped.get("type") == "pytest.xfail":
                cases.append(SuiteCase(key, "xfailed", message))
            elif skipped.get("type") is None and message == "collection skipped":
                reason = _collection_skip_reason(skipped.text or "")
                cases.append(SuiteCase(key, "skipped", reason, collection_skip=True))
            else:
                cases.append(SuiteCase(key, "skipped", message))
        else:
            cases.append(SuiteCase(key, "passed"))
    if not cases:
        raise SuiteEvidenceError("JUnit report holds no test cases")
    return tuple(cases)


def parse_terminal_summary(text: str) -> dict[str, int]:
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if _SUMMARY_LINE.match(stripped):
            counts: dict[str, int] = {}
            for number, word in _SUMMARY_COUNT.findall(stripped):
                name = {"error": "errors", "warning": "warnings"}.get(word, word)
                counts[name] = counts.get(name, 0) + int(number)
            for number, word in _SUBTEST_COUNT.findall(stripped):
                name = f"subtests {word}"
                counts[name] = counts.get(name, 0) + int(number)
            return counts
    raise SuiteEvidenceError("pytest log has no final summary line")


def _listed(items: list[str]) -> str:
    shown = "; ".join(items[:_REPORT_LIMIT])
    more = len(items) - _REPORT_LIMIT
    return shown + (f"; ... {more} more" if more > 0 else "")


def _parse_base(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("UNRESOLVED:"):
            raise SuiteEvidenceError(f"merge-base {line}")
    sha = re.search(r"(?m)^base sha: ([0-9a-f]{40})$", text)
    status = re.search(r"(?m)^base collection exit status: (\d+)$", text)
    if sha is None:
        raise SuiteEvidenceError("merge-base unresolved: no base sha recorded")
    if status is None or status.group(1) != "0":
        raise SuiteEvidenceError(
            "merge-base collection did not complete "
            f"(exit status {status.group(1) if status else 'unrecorded'})"
        )
    return sha.group(1)


def evaluate_suite(root: Path, evidence_dir: Path, profile: str) -> SuiteVerdict:
    verdict = SuiteVerdict()
    if profile not in SUITE_PROFILES:
        verdict.unknowns.append(
            f"unknown suite profile {profile!r}; expected one of {SUITE_PROFILES}"
        )
        return verdict
    verdict.facts.append(f"profile={profile}")

    def attempt(load: Callable[[], _T]) -> _T | None:
        try:
            return load()
        except SuiteEvidenceError as exc:
            verdict.unknowns.append(str(exc))
            return None

    allowances = attempt(lambda: load_skip_allowlist(root / SKIP_ALLOWLIST))
    removals = attempt(lambda: load_declared_removals(root / DECLARED_REMOVALS))
    summary = attempt(
        lambda: parse_terminal_summary(_read_input(evidence_dir / SUITE_SUMMARY_LOG, "pytest log"))
    )
    cases = attempt(lambda: parse_junit(evidence_dir / SUITE_JUNIT))
    collected = attempt(
        lambda: parse_collect_only(
            _read_input(evidence_dir / SUITE_COLLECT, "collection log"), "collection log"
        )
    )

    # 1. Zero failures and zero errors, in every view of the run.
    if summary is not None:
        for name in ("failed", "errors", "xpassed", "subtests failed", "subtests xpassed"):
            if summary.get(name, 0):
                verdict.violations.append(f"pytest summary reports {summary[name]} {name}")
    if cases is not None:
        bad = [f"{'::'.join(c.key)} {c.outcome}" for c in cases if c.outcome in {"failed", "error"}]
        if bad:
            verdict.violations.append(f"{len(bad)} failed or errored test cases: {_listed(bad)}")
    if collected is not None and collected[1]:
        verdict.violations.append(f"collection reported {collected[1]} errors")

    # 2. Accounting closes: each collected test is reported exactly as passed
    # or skipped by the same run, and the terminal summary agrees.
    if cases is not None and collected is not None:
        ids = collected[0]
        if not ids:
            verdict.violations.append("no tests collected")
        keys = {junit_key(node_id): node_id for node_id in ids}
        if len(keys) != len(ids):
            verdict.unknowns.append("collected node ids do not map one-to-one onto JUnit names")
        reported: dict[tuple[str, str], list[SuiteCase]] = {}
        for case in cases:
            reported.setdefault(case.key, []).append(case)
        unreported = [node_id for key, node_id in keys.items() if key not in reported]
        if unreported:
            verdict.violations.append(
                f"{len(unreported)} collected tests have no reported outcome: {_listed(unreported)}"
            )
        stray = ["::".join(c.key) for c in cases if c.key not in keys and not c.collection_skip]
        if stray:
            verdict.violations.append(
                f"{len(stray)} reported tests were not collected: {_listed(stray)}"
            )
        tally = {
            outcome: sum(1 for case in cases if case.outcome == outcome)
            for outcome in ("passed", "skipped", "xfailed")
        }
        verdict.facts.append(
            f"collected={len(ids)} passed={tally['passed']} skipped={tally['skipped']} "
            f"xfailed={tally['xfailed']}"
        )
        if summary is not None:
            disagree = [
                f"{name} summary={summary.get(name, 0)} junit={tally[name]}"
                for name in tally
                if summary.get(name, 0) != tally[name]
            ]
            if disagree:
                verdict.violations.append(
                    f"pytest summary disagrees with the JUnit report: {_listed(disagree)}"
                )

    # 3. Every skip (and xfail) reason is on the declared allow-list for this
    # profile.
    if cases is not None and allowances is not None:
        undeclared: dict[str, list[str]] = {}
        for case in cases:
            if case.outcome not in {"skipped", "xfailed"}:
                continue
            kind = "skip" if case.outcome == "skipped" else "xfail"
            if not any(
                allowance.kind == kind
                and profile in allowance.profiles
                and allowance.pattern.fullmatch(case.reason)
                for allowance in allowances
            ):
                undeclared.setdefault(f"{kind}: {case.reason!r}", []).append("::".join(case.key))
        if undeclared:
            verdict.violations.append(
                "undeclared skip reasons: "
                + _listed(
                    [
                        f"{reason} ({len(nodes)}, e.g. {nodes[0]})"
                        for reason, nodes in undeclared.items()
                    ]
                )
            )

    # 4. The collected set does not shrink against the merge-base, except by
    # declared removal.
    base_sha = attempt(lambda: _parse_base(_read_input(evidence_dir / SUITE_BASE, "base record")))
    base = None
    if base_sha is not None:
        base = attempt(
            lambda: parse_collect_only(
                _read_input(evidence_dir / SUITE_BASE_COLLECT, "base collection log"),
                "base collection log",
            )
        )
    if base is not None:
        if base[1]:
            verdict.unknowns.append(f"base collection reported {base[1]} errors")
        elif not base[0]:
            verdict.unknowns.append("base collection is empty; the comparison is undeterminable")
        elif collected is not None and removals is not None:
            current = set(collected[0])
            lost = sorted(set(base[0]) - current)
            undeclared_loss = [node_id for node_id in lost if node_id not in removals]
            verdict.facts.append(
                f"base={base_sha[:12] if base_sha else '?'} base_collected={len(base[0])} "
                f"removed={len(lost)} declared={len(lost) - len(undeclared_loss)}"
            )
            if undeclared_loss:
                verdict.violations.append(
                    f"{len(undeclared_loss)} tests collected at the merge-base are gone "
                    f"without a declared removal: {_listed(undeclared_loss)}"
                )
    return verdict


def _suite_profile() -> str:
    return os.environ.get(SUITE_PROFILE_ENV, "").strip() or "ci"


def _evaluate_suite_spec(root: Path, evidence_dir: Path, spec: CheckSpec) -> dict[str, object]:
    verdict = evaluate_suite(root, evidence_dir, _suite_profile())
    inputs = {
        rel: (_sha256(evidence_dir / rel) if (evidence_dir / rel).is_file() else None)
        for rel in (SUITE_SUMMARY_LOG, SUITE_JUNIT, SUITE_COLLECT, SUITE_BASE, SUITE_BASE_COLLECT)
    }
    for rel in (SKIP_ALLOWLIST, DECLARED_REMOVALS):
        inputs[rel.as_posix()] = _sha256(root / rel) if (root / rel).is_file() else None
    parts = verdict.facts + [f"FAIL: {item}" for item in verdict.violations]
    parts += [f"UNKNOWN: {item}" for item in verdict.unknowns]
    evidence_path = evidence_dir / spec.log_path
    return {
        "actual_result": "; ".join(parts) if parts else "no facts recorded",
        "check_class": spec.check_class,
        "check_id": spec.check_id,
        "evidence": {
            "inputs": inputs,
            "path": _evidence_label(root, evidence_path),
            "sha256": inputs[SUITE_SUMMARY_LOG],
        },
        "expected_result": spec.expected_result,
        "method": spec.method,
        "remediation_if_failed": (
            "Fix the failing or errored tests; declare a new skip reason in "
            f"{SKIP_ALLOWLIST.as_posix()} or a removed test in {DECLARED_REMOVALS.as_posix()} "
            "with its justification; resolve the merge-base (fetch origin/main or set "
            "L9_SUITE_BASE_REF) and rerun scripts/validate_release.sh (ADR-101)."
        ),
        "severity": spec.severity,
        "status": verdict.status,
        "target_artifact": spec.target_artifact,
    }


def _evaluate(root: Path, evidence_dir: Path, spec: CheckSpec) -> dict[str, object]:
    if spec.derived_suite:
        return _evaluate_suite_spec(root, evidence_dir, spec)
    evidence_path = evidence_dir / spec.log_path
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
            "path": _evidence_label(root, evidence_path),
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


def generate(root: Path, evidence_dir: Path) -> int:
    validation = evidence_dir
    validation.mkdir(parents=True, exist_ok=True)
    checks = [_evaluate(root, evidence_dir, spec) for spec in CHECKS]
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
        "generated_from": (
            f"executed files under {_evidence_label(root, evidence_dir / 'logs')} "
            "and explicit external blocker declarations"
        ),
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
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=None,
        help=(
            "evidence root holding logs/ as input and receiving the reports "
            f"(default: <repo-root>/{DEFAULT_EVIDENCE_DIR.as_posix()})"
        ),
    )
    args = parser.parse_args()
    root = args.repo_root.resolve()
    evidence_dir = (
        args.evidence_dir.resolve()
        if args.evidence_dir is not None
        else root / DEFAULT_EVIDENCE_DIR
    )
    return generate(root, evidence_dir)


if __name__ == "__main__":
    raise SystemExit(main())
