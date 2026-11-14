"""ADR-101: V-001 is a derived suite check, not a hand-maintained pass count.

Each case below is built so that it discriminates: the clean run would FAIL
under the retired ``r"1959 passed"`` pin, and every broken run is one the
derived check must refuse -- several of them while still printing the old
pinned count, which the pin would have accepted.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType
from xml.sax.saxutils import quoteattr

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "tools" / "assurance" / "generate_validation_evidence.py"
VALIDATOR = REPO_ROOT / "scripts" / "validate_release.sh"
RETIRED_PIN = r"1959 passed"
BASE_SHA = "0123456789abcdef0123456789abcdef01234567"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("v001_validation_evidence", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load()
V001 = next(spec for spec in MODULE.CHECKS if spec.check_id == "V-001")

DECLARED_SKIP = "L9_MEMORY_TEST_NEO4J_URI is not set; live graph tests need Neo4j"
LOCAL_ONLY_SKIP = "L9_MEMORY_TEST_POSTGRES_DSN is not set; the matrix needs PostgreSQL"
ALLOWLIST = {
    "schema": "l9.suite-skip-allowlist/v1",
    "entries": [
        {
            "id": "T-1",
            "kind": "skip",
            "pattern": r"L9_MEMORY_TEST_NEO4J_URI is not set; .*",
            "profiles": ["ci", "local"],
            "justification": "no Neo4j in the validate job",
        },
        {
            "id": "T-2",
            "kind": "skip",
            "pattern": r"L9_MEMORY_TEST_POSTGRES_DSN is not set; .*",
            "profiles": ["local"],
            "justification": "CI provides PostgreSQL",
        },
    ],
}

Case = tuple[str, str, str]  # node id, outcome, reason


def _mangle(node_id: str) -> tuple[str, str]:
    # Written independently of the generator: what pytest's JUnit writer emits.
    head, bracket, params = node_id.partition("[")
    parts = head.split("::")
    module = parts[0][: -len(".py")].replace("/", ".")
    return ".".join([module, *parts[1:-1]]), parts[-1] + bracket + params


def _junit(cases: Iterable[Case]) -> str:
    rows = []
    for node_id, outcome, reason in cases:
        classname, name = _mangle(node_id)
        body = {
            "passed": "",
            "failed": '<failure message="assert 0">assert 0</failure>',
            "error": '<error message="failed on setup">boom</error>',
            "skipped": f'<skipped type="pytest.skip" message={quoteattr(reason)}>s</skipped>',
            "xfailed": f'<skipped type="pytest.xfail" message={quoteattr(reason)} />',
        }[outcome]
        rows.append(
            f"<testcase classname={quoteattr(classname)} name={quoteattr(name)}>{body}</testcase>"
        )
    return (
        '<?xml version="1.0"?><testsuites><testsuite>' + "".join(rows) + "</testsuite></testsuites>"
    )


def _summary(cases: Iterable[Case]) -> str:
    counts: dict[str, int] = {}
    for _, outcome, _ in cases:
        counts[outcome] = counts.get(outcome, 0) + 1
    words = {"error": "errors"}
    parts = [f"{n} {words.get(k, k)}" for k, n in counts.items()]
    return ", ".join(parts) + " in 1.23s"


def _collect(ids: Iterable[str]) -> str:
    ids = list(ids)
    return "\n".join(ids) + f"\n\n{len(ids)} tests collected in 0.10s\n"


def _base_record(status: int = 0) -> str:
    return (
        "base ref: origin/main\n"
        f"head sha: {'f' * 40}\nbase sha: {BASE_SHA}\nshallow: false\n"
        f"base collection exit status: {status}\n"
    )


def _clean_cases() -> list[Case]:
    return [
        ("tests/unit/test_a.py::test_ok", "passed", ""),
        ("tests/unit/test_a.py::TestB::test_method[x/y]", "passed", ""),
        ("tests/integration/test_live.py::test_graph", "skipped", DECLARED_SKIP),
    ]


def _write(
    tmp_path: Path,
    cases: list[Case],
    *,
    summary: str | None = None,
    collected: list[str] | None = None,
    base: list[str] | None = None,
    base_record: str | None = None,
    removals: list[dict[str, str]] | None = None,
    allowlist: dict[str, object] | None = None,
) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    evidence = tmp_path / "evidence"
    (root / "tools" / "assurance").mkdir(parents=True)
    (evidence / "logs").mkdir(parents=True)
    (root / MODULE.SKIP_ALLOWLIST).write_text(json.dumps(allowlist or ALLOWLIST), encoding="utf-8")
    (root / MODULE.DECLARED_REMOVALS).write_text(
        json.dumps({"schema": "l9.suite-declared-removals/v1", "removals": removals or []}),
        encoding="utf-8",
    )
    ids = [node_id for node_id, _, _ in cases] if collected is None else collected
    logs = {
        MODULE.SUITE_SUMMARY_LOG: "....s\n" + (summary or _summary(cases)) + "\n",
        MODULE.SUITE_JUNIT: _junit(cases),
        MODULE.SUITE_COLLECT: _collect(ids),
        MODULE.SUITE_BASE: _base_record() if base_record is None else base_record,
        MODULE.SUITE_BASE_COLLECT: _collect(ids if base is None else base),
    }
    for rel, text in logs.items():
        (evidence / rel).write_text(text, encoding="utf-8")
    return root, evidence


def _status(root: Path, evidence: Path) -> tuple[str, str]:
    row = MODULE._evaluate(root, evidence, V001)
    return str(row["status"]), str(row["actual_result"])


@pytest.fixture(autouse=True)
def _ci_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(MODULE.SUITE_PROFILE_ENV, raising=False)


# --- the pin is gone ----------------------------------------------------------


def test_v001_is_derived_and_carries_no_count_pin() -> None:
    assert V001.derived_suite
    assert V001.success_pattern is None
    source = GENERATOR.read_text(encoding="utf-8")
    assert not re.search(r'r"\d+ passed"', source)
    assert "Re-pinned" not in source.split('"V-002"', 1)[0]


def test_clean_run_passes_where_the_retired_pin_would_fail(tmp_path: Path) -> None:
    root, evidence = _write(tmp_path, _clean_cases())
    assert not re.search(RETIRED_PIN, (evidence / MODULE.SUITE_SUMMARY_LOG).read_text())
    status, actual = _status(root, evidence)
    assert status == "PASS", actual
    assert "collected=3 passed=2 skipped=1" in actual
    assert "profile=ci" in actual


# --- 1. zero failures and zero errors ----------------------------------------


def _pinned_run(extra: Case) -> list[Case]:
    # 1959 passing tests: the retired pin's regex matches this summary.
    return [(f"tests/unit/test_bulk.py::test_{i}", "passed", "") for i in range(1959)] + [extra]


@pytest.mark.parametrize(
    ("extra", "word"),
    [
        (("tests/unit/test_x.py::test_broken", "failed", ""), "failed"),
        (("tests/unit/test_x.py::test_setup", "error", ""), "errors"),
    ],
)
def test_a_failure_or_error_fails_even_with_the_pinned_count(
    tmp_path: Path, extra: Case, word: str
) -> None:
    root, evidence = _write(tmp_path, _pinned_run(extra))
    log = (evidence / MODULE.SUITE_SUMMARY_LOG).read_text()
    assert re.search(RETIRED_PIN, log), "the old pin would have passed this run"
    status, actual = _status(root, evidence)
    assert status == "FAIL"
    assert f"pytest summary reports 1 {word}" in actual
    assert "failed or errored test cases" in actual


def test_an_unexpected_xpass_fails(tmp_path: Path) -> None:
    # Non-strict xpass is a "passed" JUnit case; only the summary shows it.
    cases = _clean_cases()
    summary = "1 passed, 1 xpassed, 1 skipped in 1.00s"
    root, evidence = _write(tmp_path, cases, summary=summary)
    status, actual = _status(root, evidence)
    assert status == "FAIL"
    assert "1 xpassed" in actual


def test_a_pytest9_summary_with_subtests_is_read(tmp_path: Path) -> None:
    # pytest 9 reports unittest subTest results as their own summary item.
    summary = "2 passed, 1 skipped, 11 subtests passed in 1.00s"
    root, evidence = _write(tmp_path, _clean_cases(), summary=summary)
    status, actual = _status(root, evidence)
    assert status == "PASS", actual
    counts = MODULE.parse_terminal_summary(summary)
    assert counts == {"passed": 2, "skipped": 1, "subtests passed": 11}


@pytest.mark.parametrize("word", ["failed", "xpassed"])
def test_a_failed_or_xpassed_subtest_fails(tmp_path: Path, word: str) -> None:
    summary = f"2 passed, 1 skipped, 1 subtests {word}, 10 subtests passed in 1.00s"
    root, evidence = _write(tmp_path, _clean_cases(), summary=summary)
    status, actual = _status(root, evidence)
    assert status == "FAIL"
    assert f"pytest summary reports 1 subtests {word}" in actual


def test_an_undeclared_xfail_fails(tmp_path: Path) -> None:
    cases = [*_clean_cases(), ("tests/unit/test_a.py::test_known_bug", "xfailed", "bug 12")]
    root, evidence = _write(tmp_path, cases)
    status, actual = _status(root, evidence)
    assert status == "FAIL"
    assert "xfail: 'bug 12'" in actual


# --- 2. accounting closes ----------------------------------------------------


def test_a_collected_test_without_an_outcome_fails(tmp_path: Path) -> None:
    cases = _clean_cases()
    collected = [node_id for node_id, _, _ in cases] + ["tests/unit/test_a.py::test_vanished"]
    root, evidence = _write(tmp_path, cases, collected=collected, base=collected)
    status, actual = _status(root, evidence)
    assert status == "FAIL"
    assert (
        "1 collected tests have no reported outcome: tests/unit/test_a.py::test_vanished" in actual
    )


def test_a_summary_that_disagrees_with_junit_fails(tmp_path: Path) -> None:
    root, evidence = _write(tmp_path, _clean_cases(), summary="5 passed, 1 skipped in 1.00s")
    status, actual = _status(root, evidence)
    assert status == "FAIL"
    assert "passed summary=5 junit=2" in actual


# --- 3. skip reasons are declared ---------------------------------------------


def test_an_undeclared_skip_reason_fails(tmp_path: Path) -> None:
    cases = [*_clean_cases(), ("tests/unit/test_a.py::test_new", "skipped", "flaky, skip for now")]
    root, evidence = _write(tmp_path, cases)
    status, actual = _status(root, evidence)
    assert status == "FAIL"
    assert "undeclared skip reasons: skip: 'flaky, skip for now'" in actual


def test_a_local_only_skip_fails_in_the_ci_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = [*_clean_cases(), ("tests/unit/test_pg.py::test_leg", "skipped", LOCAL_ONLY_SKIP)]
    root, evidence = _write(tmp_path, cases)
    assert _status(root, evidence)[0] == "FAIL"
    monkeypatch.setenv(MODULE.SUITE_PROFILE_ENV, "local")
    status, actual = _status(root, evidence)
    assert status == "PASS", actual
    assert "profile=local" in actual


# --- 4. the collected set does not shrink -------------------------------------


def test_a_dropped_test_without_declaration_fails(tmp_path: Path) -> None:
    cases = _clean_cases()
    base = [node_id for node_id, _, _ in cases] + ["tests/unit/test_gone.py::test_lost"]
    root, evidence = _write(tmp_path, cases, base=base)
    status, actual = _status(root, evidence)
    assert status == "FAIL"
    assert "without a declared removal: tests/unit/test_gone.py::test_lost" in actual


def test_a_dropped_test_with_declaration_passes(tmp_path: Path) -> None:
    cases = _clean_cases()
    base = [node_id for node_id, _, _ in cases] + ["tests/unit/test_gone.py::test_lost"]
    removals = [{"node_id": "tests/unit/test_gone.py::test_lost", "reason": "feature retired"}]
    root, evidence = _write(tmp_path, cases, base=base, removals=removals)
    status, actual = _status(root, evidence)
    assert status == "PASS", actual
    assert "removed=1 declared=1" in actual


# --- fail closed ---------------------------------------------------------------


@pytest.mark.parametrize(
    "missing",
    [
        "logs/pytest.txt",
        "logs/pytest_junit.xml",
        "logs/pytest_collect.txt",
        "logs/suite_base.txt",
        "logs/pytest_collect_base.txt",
        "tools/assurance/suite_skip_allowlist.json",
        "tools/assurance/suite_declared_removals.json",
    ],
)
def test_a_missing_input_is_never_pass(tmp_path: Path, missing: str) -> None:
    root, evidence = _write(tmp_path, _clean_cases())
    target = (root if missing.startswith("tools/") else evidence) / missing
    target.unlink()
    status, actual = _status(root, evidence)
    assert status == "UNKNOWN", actual
    assert "missing" in actual


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (
            (
                "base ref: origin/main\nUNRESOLVED: no git work tree; the merge-base with "
                "origin/main cannot be determined\n"
            ),
            "no git work tree",
        ),
        (_base_record(status=2), "exit status 2"),
        ("base ref: origin/main\n", "no base sha recorded"),
    ],
)
def test_an_undeterminable_base_is_never_pass(tmp_path: Path, record: str, expected: str) -> None:
    root, evidence = _write(tmp_path, _clean_cases(), base_record=record)
    status, actual = _status(root, evidence)
    assert status == "UNKNOWN"
    assert expected in actual


@pytest.mark.parametrize(
    "corrupt",
    [
        {"schema": "wrong", "entries": []},
        {"schema": "l9.suite-skip-allowlist/v1", "entries": [{"id": "X", "kind": "skip"}]},
        {
            "schema": "l9.suite-skip-allowlist/v1",
            "entries": [
                {
                    "id": "X",
                    "kind": "skip",
                    "pattern": "(",
                    "profiles": ["ci"],
                    "justification": "j",
                }
            ],
        },
    ],
)
def test_a_malformed_allowlist_is_never_pass(tmp_path: Path, corrupt: dict[str, object]) -> None:
    root, evidence = _write(tmp_path, _clean_cases(), allowlist=corrupt)
    assert _status(root, evidence)[0] == "UNKNOWN"


def test_a_truncated_collection_is_never_pass(tmp_path: Path) -> None:
    root, evidence = _write(tmp_path, _clean_cases())
    (evidence / MODULE.SUITE_COLLECT).write_text(
        "tests/unit/test_a.py::test_ok\n", encoding="utf-8"
    )
    status, actual = _status(root, evidence)
    assert status == "UNKNOWN"
    assert "no collection summary line" in actual


def test_an_unknown_profile_is_never_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, evidence = _write(tmp_path, _clean_cases())
    monkeypatch.setenv(MODULE.SUITE_PROFILE_ENV, "lenient")
    assert _status(root, evidence)[0] == "UNKNOWN"


def test_the_generator_exits_nonzero_without_suite_evidence(tmp_path: Path) -> None:
    assert MODULE.generate(REPO_ROOT, tmp_path / "evidence") == 1
    rows = [
        json.loads(line)
        for line in (tmp_path / "evidence" / "validation_checks.jsonl").read_text().splitlines()
    ]
    assert next(row for row in rows if row["check_id"] == "V-001")["status"] == "UNKNOWN"


# --- the committed declarations -------------------------------------------------


def test_committed_declarations_are_well_formed() -> None:
    allowances = MODULE.load_skip_allowlist(REPO_ROOT / MODULE.SKIP_ALLOWLIST)
    assert allowances
    assert all(item.justification.strip() for item in allowances)
    assert any("ci" in item.profiles for item in allowances)
    assert isinstance(MODULE.load_declared_removals(REPO_ROOT / MODULE.DECLARED_REMOVALS), dict)


# --- real pytest output ---------------------------------------------------------


def _pytest(project: Path, *args: str) -> str:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-ra", *args],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return completed.stdout + completed.stderr


def _project(path: Path, tests: str) -> Path:
    (path / "tests").mkdir(parents=True)
    (path / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")
    (path / "tests" / "test_sample.py").write_text(tests, encoding="utf-8")
    (path / "tests" / "test_module_skip.py").write_text(
        "import pytest\n"
        'pytest.importorskip("l9_absent_module_for_v001", reason="L9_MEMORY_TEST_NEO4J_URI '
        'is not set; module needs Neo4j")\n'
        "def test_never():\n    pass\n",
        encoding="utf-8",
    )
    return path


SAMPLE = """
import pytest
import unittest

def test_ok():
    pass

@pytest.mark.parametrize("value", ["a/b", "c::d", "e.f"])
def test_param(value):
    assert value

def test_skip():
    pytest.skip("L9_MEMORY_TEST_NEO4J_URI is not set; live graph tests need Neo4j")

class TestGroup:
    def test_member(self):
        pass

class LegacyCase(unittest.TestCase):
    def test_legacy(self):
        pass
"""


def _real_evidence(tmp_path: Path, base_tests: str, head_tests: str) -> tuple[Path, Path]:
    root, evidence = _write(tmp_path, _clean_cases())
    head = _project(tmp_path / "head", head_tests)
    base = _project(tmp_path / "base", base_tests)
    junit = evidence / MODULE.SUITE_JUNIT
    (evidence / MODULE.SUITE_SUMMARY_LOG).write_text(
        _pytest(head, "-q", f"--junitxml={junit}"), encoding="utf-8"
    )
    (evidence / MODULE.SUITE_COLLECT).write_text(
        _pytest(head, "--collect-only", "-q"), encoding="utf-8"
    )
    (evidence / MODULE.SUITE_BASE_COLLECT).write_text(
        _pytest(base, "--collect-only", "-q"), encoding="utf-8"
    )
    return root, evidence


def test_real_pytest_output_is_accounted_for(tmp_path: Path) -> None:
    root, evidence = _real_evidence(tmp_path, SAMPLE, SAMPLE)
    status, actual = _status(root, evidence)
    assert status == "PASS", actual
    assert "collected=7 passed=6 skipped=2" in actual  # 7 + the module-level skip


def test_real_pytest_output_with_a_failure_and_a_lost_test_fails(tmp_path: Path) -> None:
    head = SAMPLE.replace("def test_ok():\n    pass", "def test_ok():\n    assert False")
    head = head.replace('"c::d", ', "")
    root, evidence = _real_evidence(tmp_path, SAMPLE, head)
    status, actual = _status(root, evidence)
    assert status == "FAIL"
    assert "pytest summary reports 1 failed" in actual
    assert "tests/test_sample.py::test_param[c::d]" in actual


# --- the release script supplies the inputs -------------------------------------


def test_release_script_writes_the_derived_inputs() -> None:
    script = VALIDATOR.read_text(encoding="utf-8")
    assert 'run pytest pytest -q --junitxml="$OUT/logs/pytest_junit.xml"' in script
    assert "run pytest_collect pytest --collect-only -q" in script
    assert 'ref="${L9_SUITE_BASE_REF:-origin/main}"' in script
    assert "\nsuite_base_collection\n" in script


def _suite_base_function() -> str:
    script = VALIDATOR.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^suite_base_collection\(\) \{\n.*?^\}\n", script)
    assert match, "suite_base_collection not found"
    return match.group(0)


def _run_suite_base(tmp_path: Path, root: Path, ref: str | None = None) -> str:
    out = tmp_path / "out"
    (out / "logs").mkdir(parents=True)
    (tmp_path / "tmproot").mkdir()
    env = {
        **os.environ,
        # The base collection runs `pytest` from PATH, as the release script does.
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}",
        "ROOT": str(root),
        "OUT": str(out),
        "TMP_ROOT": str(tmp_path / "tmproot"),
    }
    env.pop("L9_SUITE_BASE_REF", None)
    if ref is not None:
        env["L9_SUITE_BASE_REF"] = ref
    subprocess.run(
        ["bash", "-c", "set -euo pipefail\n" + _suite_base_function() + "suite_base_collection\n"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return (out / "logs" / "suite_base.txt").read_text(encoding="utf-8")


def test_without_git_history_the_base_is_unresolved_not_passed(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    record = _run_suite_base(tmp_path, plain)
    assert "UNRESOLVED: no git work tree" in record
    with pytest.raises(MODULE.SuiteEvidenceError):
        MODULE._parse_base(record)


def test_a_resolved_base_is_exported_and_collected(tmp_path: Path) -> None:
    repo = _project(tmp_path / "repo", SAMPLE)
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    for args in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "base"]):
        subprocess.run(["git", *args], cwd=repo, env=git_env, check=True)
    missing = _run_suite_base(tmp_path / "a", repo, ref="origin/main")
    assert "UNRESOLVED: base ref origin/main is not a commit" in missing
    record = _run_suite_base(tmp_path / "b", repo, ref="HEAD")
    assert MODULE._parse_base(record)
    base_log = tmp_path / "b" / "out" / "logs" / "pytest_collect_base.txt"
    ids, errors = MODULE.parse_collect_only(base_log.read_text(), "base")
    assert errors == 0
    assert "tests/test_sample.py::test_param[c::d]" in ids


def test_every_workflow_running_release_validation_checks_out_full_history() -> None:
    """V-001 rule 4 needs origin/main; a shallow checkout makes it UNKNOWN.

    publish.yml once checked out the release tag shallowly, which would have
    blocked every release (review finding on PR #109).
    """
    import yaml

    workflows = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
    checked = []
    for path in workflows:
        doc = yaml.safe_load(path.read_text())
        for name, job in (doc.get("jobs") or {}).items():
            steps = job.get("steps") or []
            if not any("validate_release.sh" in str(step.get("run", "")) for step in steps):
                continue
            checkouts = [
                step
                for step in steps
                if str(step.get("uses", "")).startswith("actions/checkout@")
                and not (step.get("with") or {}).get("repository")
            ]
            assert checkouts, f"{path.name}:{name} runs release validation without a checkout"
            depth = (checkouts[0].get("with") or {}).get("fetch-depth")
            assert depth == 0, f"{path.name}:{name} must check out with fetch-depth: 0 (ADR-101)"
            checked.append(f"{path.name}:{name}")
    assert checked, "no workflow runs scripts/validate_release.sh"
