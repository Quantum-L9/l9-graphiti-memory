"""ADR-099: the repository file inventory and L9_META enforcement are retired.

These tests prove the retirement is complete and that it removed nothing else:
no gate regenerates or checks the root inventory, missing or stale metadata
headers fail nothing, a reintroduced inventory is rejected, and the exact
artifact and admission controls the inventory never carried are still wired.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE = ROOT / "tools" / "assurance"
VALIDATOR = ROOT / "scripts" / "validate_release.sh"
PREFLIGHT = ROOT / "scripts" / "preflight.sh"
PUBLISH = ROOT / ".github" / "workflows" / "publish.yml"
BINDING = ROOT / "release-work" / "product-release-binding.yaml"
TOPOLOGY = ROOT / "product-topology.yaml"

RETIRED_TOOLS = (
    "apply_l9_meta.py",
    "check_l9_meta.py",
    "generate_manifest.py",
    "validate_manifest.py",
    "l9_meta.py",
)
INVENTORY = ("MANIFEST.md", "manifest.json")


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    return module


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=retirement-test",
            "-c",
            "user.email=retirement-test@invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        check=True,
        text=True,
    )


def _tracked(root: Path) -> set[str]:
    return set(_git(root, "ls-files", "-z").stdout.split("\0")) - {""}


# --- the retired surfaces are gone -------------------------------------------


def test_retired_tools_and_root_inventory_are_not_tracked() -> None:
    tracked = _tracked(ROOT)
    for tool in RETIRED_TOOLS:
        assert f"tools/assurance/{tool}" not in tracked, tool
    for inventory in INVENTORY:
        assert inventory not in tracked, inventory


@pytest.mark.parametrize(
    "surface",
    [
        "scripts/validate_release.sh",
        "scripts/preflight.sh",
        ".github/workflows/ci.yml",
        ".github/workflows/publish.yml",
        ".pre-commit-config.yaml",
        "pyproject.toml",
        "release-work/product-release-binding.yaml",
        "tools/assurance/check_recursive_alignment.py",
        "tools/assurance/generate_validation_evidence.py",
        "tools/authority/project_l9_repository_corpus.py",
    ],
)
def test_no_gate_or_generator_invokes_a_retired_tool(surface: str) -> None:
    text = (ROOT / surface).read_text(encoding="utf-8")
    # Comment lines may record the retirement; executable lines may not name it.
    executable = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for tool in RETIRED_TOOLS:
        assert tool not in executable, f"{surface} still names {tool}"


def test_preflight_no_longer_enforces_the_retired_contract() -> None:
    text = PREFLIGHT.read_text(encoding="utf-8")
    assert "L9 metadata coverage" not in text
    assert '"release manifest"' not in text
    # Every remaining assurance gate points at a tool that exists, so the
    # retirement left no dangling gate behind.
    gates = re.findall(r'"\$ROOT/(tools/assurance/[a-z_]+\.py)"', text)
    assert gates, "preflight lost its assurance gates"
    for gate in gates:
        assert (ROOT / gate).is_file(), gate


def test_release_output_carries_no_root_inventory() -> None:
    validator = VALIDATOR.read_text(encoding="utf-8")
    for inventory in INVENTORY:
        assert inventory not in validator, inventory
    upload = next(
        step
        for step in yaml.safe_load(PUBLISH.read_text(encoding="utf-8"))["jobs"][
            "validate-and-publish"
        ]["steps"]
        if str(step.get("uses", "")).startswith("actions/upload-artifact")
    )
    uploaded = upload["with"]["path"].split()
    assert "MANIFEST.md" not in uploaded
    assert "dist/" in uploaded and "build/release-validation/" in uploaded
    sdist_rules = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "MANIFEST.md" not in sdist_rules
    topology = yaml.safe_load(TOPOLOGY.read_text(encoding="utf-8"))
    assert topology["build"]["generated_surfaces"] == []


# --- metadata headers and inventories no longer gate anything -----------------


@pytest.fixture
def alignment_tree(tmp_path: Path) -> Path:
    """A tracked copy of everything the recursive-alignment scan reads."""

    root = tmp_path / "repo"
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info")
    for directory in ("src", "tools", "scripts"):
        shutil.copytree(ROOT / directory, root / directory, ignore=ignore)
    for test in (
        "tests/unit/test_constellation_bridge.py",
        "tests/unit/test_gate.py",
        "tests/regression/test_recursive_alignment.py",
    ):
        (root / test).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / test, root / test)
    _git(root.parent, "init", "-q", str(root))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


def _scan(root: Path) -> tuple[object, ...]:
    module = _load("retirement_alignment_check", ASSURANCE / "check_recursive_alignment.py")
    return module.scan(root)


def test_fixture_scan_is_clean_before_any_change(alignment_tree: Path) -> None:
    assert _scan(alignment_tree) == ()


def test_missing_and_stale_l9_meta_headers_fail_nothing(alignment_tree: Path) -> None:
    stripped = alignment_tree / "src" / "l9_graphite_memory" / "errors.py"
    text = stripped.read_text(encoding="utf-8")
    assert text.startswith("# L9_META")
    body = text.split("\n\n", 1)[1]
    stripped.write_text(body, encoding="utf-8")
    stale = alignment_tree / "src" / "l9_graphite_memory" / "version.py"
    stale.write_text(
        stale.read_text(encoding="utf-8").replace("#   path: ", "#   path: wrong/", 1)
        + "\n# L9_META\n#   malformed\n",
        encoding="utf-8",
    )
    new_file = alignment_tree / "src" / "l9_graphite_memory" / "retirement_probe.py"
    new_file.write_text('"""No metadata header."""\n\nVALUE = 1\n', encoding="utf-8")
    _git(alignment_tree, "add", "-A")
    assert _scan(alignment_tree) == ()


def test_reintroduced_root_inventory_is_a_forbidden_entry(alignment_tree: Path) -> None:
    for inventory in INVENTORY:
        (alignment_tree / inventory).write_text("{}\n", encoding="utf-8")
    _git(alignment_tree, "add", "-A")
    findings = {(item.rule, item.path) for item in _scan(alignment_tree)}
    assert findings == {
        ("file_structure", "MANIFEST.md"),
        ("file_structure", "manifest.json"),
    }


def test_parallel_source_changes_merge_without_inventory_churn(alignment_tree: Path) -> None:
    # Two branches change different source files. With no root inventory to
    # regenerate, they merge cleanly, neither touches a root file, and the
    # merged tree still satisfies the alignment contract unchanged.
    package = alignment_tree / "src" / "l9_graphite_memory"
    base = _git(alignment_tree, "rev-parse", "HEAD").stdout.strip()
    _git(alignment_tree, "checkout", "-q", "-b", "left")
    (package / "errors.py").write_text(
        (package / "errors.py").read_text(encoding="utf-8") + "\nLEFT = 1\n", encoding="utf-8"
    )
    _git(alignment_tree, "commit", "-q", "-am", "left")
    _git(alignment_tree, "checkout", "-q", "-b", "right", base)
    (package / "version.py").write_text(
        (package / "version.py").read_text(encoding="utf-8") + "\nRIGHT = 1\n", encoding="utf-8"
    )
    _git(alignment_tree, "commit", "-q", "-am", "right")
    _git(alignment_tree, "merge", "-q", "--no-edit", "left")
    changed = set(_git(alignment_tree, "diff", "--name-only", base, "HEAD").stdout.split())
    assert changed == {"src/l9_graphite_memory/errors.py", "src/l9_graphite_memory/version.py"}
    assert changed.isdisjoint(INVENTORY)
    assert _scan(alignment_tree) == ()


# --- what the inventory never carried stays enforced --------------------------


def test_exact_artifact_identity_and_admission_remain_enforced() -> None:
    validator = VALIDATOR.read_text(encoding="utf-8")
    assert 'sha256sum -- *) > "$OUT/SHA256SUMS"' in validator
    assert "installed wheel digest is not in the validated artifact set" in validator
    assert "publication mode requires L9_SEMANTIC_AUTHORITY_ROOT" in validator
    assert "generate_product_manifest.py" in validator
    steps = yaml.safe_load(PUBLISH.read_text(encoding="utf-8"))["jobs"]["validate-and-publish"][
        "steps"
    ]
    runs = [str(step.get("run", "")) for step in steps]
    assert any("tools/assurance/verify_release_admission.py" in run for run in runs)
    assert any("sha256sum dist/* | diff - build-digests.txt" in run for run in runs)
    binding = yaml.safe_load(BINDING.read_text(encoding="utf-8"))
    assert binding["product_manifest"]["ref"] == "release-work/product-manifest.json"
    assert binding["product_manifest"]["resolved_manifest_gate"] == "pass"
    assert binding["release_identity"]["identity_tuple"] == [
        "PACKAGE_VERSION",
        "exact source revision",
        "wheel sha256",
        "sdist sha256",
    ]
    assert "verify_release_admission.py" in binding["publication"]["admission_gate"]


# --- evidence never claims what did not run -----------------------------------


def _evidence_module() -> ModuleType:
    return _load("retirement_validation_evidence", ASSURANCE / "generate_validation_evidence.py")


def test_evidence_has_no_check_for_a_retired_tool() -> None:
    module = _evidence_module()
    for spec in module.CHECKS:
        for tool in RETIRED_TOOLS:
            assert tool not in spec.method, (spec.check_id, tool)
    assert "V-005" not in {spec.check_id for spec in module.CHECKS}


@pytest.mark.parametrize(
    ("log", "status"),
    [
        ("candidate digest post: abc\nPASS: candidate integrity (post)\n", "PASS"),
        ("UNVERIFIED: candidate integrity (post): no git work tree to enumerate\n", "FAIL"),
        (None, "UNKNOWN"),
    ],
)
def test_candidate_integrity_evidence_requires_an_executed_comparison(
    tmp_path: Path, log: str | None, status: str
) -> None:
    module = _evidence_module()
    spec = next(item for item in module.CHECKS if item.check_id == "V-024")
    assert spec.success_pattern and not spec.allow_empty_log
    if log is not None:
        path = tmp_path / spec.log_path
        path.parent.mkdir(parents=True)
        path.write_text(log, encoding="utf-8")
    assert module._evaluate(tmp_path, tmp_path, spec)["status"] == status
