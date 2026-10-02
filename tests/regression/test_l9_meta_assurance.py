# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/regression/test_l9_meta_assurance.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-10-02

"""Structural L9 metadata identity and manifest check purity.

Every test works on a throwaway fixture tree; none touches real repository
files. The tools under test are loaded from ``tools/assurance`` the way the
release scripts run them.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE = ROOT / "tools" / "assurance"


def _load(name: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ASSURANCE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(ASSURANCE))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(ASSURANCE))
    return module


l9_meta = _load("l9_meta")
apply_l9_meta = _load("apply_l9_meta")
check_l9_meta = _load("check_l9_meta")
generate_manifest = _load("generate_manifest")

FIXTURE_FILES: dict[str, str] = {
    "src/pkg/core.py": '"""core"""\n\nVALUE = 1\n',
    "src/pkg/contracts/memory.py": "X = 1\n",
    "src/pkg/client/contracts.py": "Y = 2\n",
    "src/pkg/adapters/store.py": "Z = 3\n",
    "tests/test_core.py": "def test_ok() -> None:\n    assert True\n",
    "tools/check.py": "#!/usr/bin/env python3\nimport sys\n",
    "scripts/run.sh": "#!/usr/bin/env bash\nset -e\n",
    "hooks/hook.sh": "echo hi\n",
    ".github/workflows/ci.yml": "name: CI\non: push\n",
    "docs/adr/ADR-001-first.md": "# ADR-001: First\n\n## Status\n\nAccepted\n",
    "docs/guide.md": "# Guide\n\nText.\n",
    "config/settings.yaml": "a: 1\n",
    "rules/rule.mdc": "---\ndescription: d\n---\n\n# Rule\n",
    "skill/SKILL.md": "---\nname: s\n---\n\n# Skill\n",
    "pyproject.toml": "[project]\nname = 'x'\n",
    ".gitignore": "build/\n",
    "README.md": "# Readme\n",
    "LICENSE": "MIT\n",
    "data.json": '{"k": 1}\n',
}


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative, text in FIXTURE_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _prepared(tmp_path: Path) -> Path:
    """A fixture tree after explicit preparation: metadata applied, manifest generated."""

    root = _fixture(tmp_path)
    assert apply_l9_meta.apply(root, check=False) == 0
    assert generate_manifest.generate(root) == 0
    return root


def _set_field(path: Path, field: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        stripped = line.lstrip("#").strip()
        if stripped.startswith(f"{field}:"):
            prefix = line[: len(line) - len(line.lstrip("#").lstrip())]
            lines[index] = f"{prefix}{field}: {value}"
            break
    else:
        raise AssertionError(f"{field} not in {path}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- layer derivation -----------------------------------------------------------


@pytest.mark.parametrize(
    ("relative", "layer"),
    [
        ("src/pkg/contracts/memory.py", "contract"),
        ("src/pkg/client/contracts.py", "contract"),
        ("src/pkg/ports/store.py", "port"),
        ("src/pkg/integrations/gate.py", "integration"),
        ("src/pkg/adapters/store.py", "adapter"),
        ("src/pkg/services/svc.py", "service"),
        ("src/pkg/core.py", "package"),
        ("tests/test_core.py", "test"),
        ("tools/check.py", "assurance"),
        ("tools/phase6/README.md", "repository"),
        ("scripts/run.sh", "operations"),
        ("hooks/hook.sh", "hook"),
        (".github/workflows/ci.yml", "ci"),
        ("docs/adr/ADR-001-first.md", "adr"),
        ("docs/guide.md", "documentation"),
        ("config/settings.yaml", "configuration"),
        ("rules/rule.mdc", "configuration"),
        ("skill/SKILL.md", "skill"),
        ("README.md", "repository"),
        ("release-work/review/INDEX.md", "repository"),
    ],
)
def test_layer_derivation_preserves_repository_semantics(relative: str, layer: str) -> None:
    assert l9_meta.layer_for(relative) == layer


def test_structural_identity_is_derived_from_location() -> None:
    identity = l9_meta.structural_identity(".github/workflows/foo.yml")
    assert identity == {
        "l9_schema": "1",
        "repo": "Quantum-L9/l9-graphiti-memory",
        "path": ".github/workflows/foo.yml",
        "layer": "ci",
        "owner": "memory-control-plane",
    }


def test_strict_json_carriers_are_not_inline_capable() -> None:
    assert not l9_meta.is_inline_capable("manifest.json")
    assert not l9_meta.is_inline_capable(".github/governance/policy.yaml")
    assert not l9_meta.is_inline_capable(
        "docs/WIP/l9-bot-memory-integration-pr-pack/PACK_CONTRACT.yaml"
    )
    assert l9_meta.is_inline_capable("docs/WIP/other.yaml")
    assert l9_meta.is_inline_capable(".gitignore")
    assert not l9_meta.is_inline_capable("LICENSE")


# --- inline metadata identity ---------------------------------------------------


def test_prepared_fixture_passes_structural_check(tmp_path: Path) -> None:
    root = _prepared(tmp_path)
    assert check_l9_meta.validate(root) == ()
    # Every inline-capable file now carries exactly one block at its real path.
    for relative in FIXTURE_FILES:
        if l9_meta.is_inline_capable(relative):
            meta = l9_meta.parse_inline((root / relative).read_text(encoding="utf-8"), relative)
            assert meta is not None, relative
            assert l9_meta.compare(meta, relative) == ()


def test_preparation_is_idempotent(tmp_path: Path) -> None:
    root = _prepared(tmp_path)
    before = _snapshot(root)
    assert apply_l9_meta.apply(root, check=False) == 0
    assert generate_manifest.generate(root) == 0
    assert _snapshot(root) == before


def test_missing_inline_metadata_fails(tmp_path: Path) -> None:
    root = _prepared(tmp_path)
    target = root / "docs" / "guide.md"
    lines = target.read_text(encoding="utf-8").splitlines()
    end = lines.index("/L9_META -->") + 1
    target.write_text("\n".join(lines[end:]).lstrip("\n") + "\n", encoding="utf-8")
    failures = check_l9_meta.validate(root)
    assert any(f.startswith("missing inline L9_META: docs/guide.md") for f in failures), failures


@pytest.mark.parametrize(
    ("field", "wrong"),
    [
        ("repo", "Quantum-L9/other-repo"),
        ("path", "docs/WIP/pack/files/.github/workflows/ci.yml"),
        ("layer", "documentation"),
        ("owner", "someone-else"),
    ],
)
def test_wrong_structural_field_fails_naming_file_and_field(
    tmp_path: Path, field: str, wrong: str
) -> None:
    root = _prepared(tmp_path)
    _set_field(root / ".github" / "workflows" / "ci.yml", field, wrong)
    failures = check_l9_meta.validate(root)
    matching = [
        f for f in failures if f.startswith("stale inline L9_META: .github/workflows/ci.yml")
    ]
    assert matching, failures
    assert f"{field}={wrong!r}" in matching[0]


def test_copied_wip_header_at_active_workflow_path_fails(tmp_path: Path) -> None:
    root = _prepared(tmp_path)
    target = root / ".github" / "workflows" / "ci.yml"
    _set_field(target, "path", "docs/WIP/pack/repos/x/files/.github/workflows/ci.yml")
    _set_field(target, "layer", "documentation")
    failures = check_l9_meta.validate(root)
    stale = [f for f in failures if ".github/workflows/ci.yml" in f and "stale inline" in f]
    assert stale, failures
    assert "path=" in stale[0] and "layer='documentation' expected 'ci'" in stale[0]


def test_malformed_block_fails_closed(tmp_path: Path) -> None:
    root = _prepared(tmp_path)
    target = root / "docs" / "guide.md"
    text = target.read_text(encoding="utf-8").replace("/L9_META -->\n", "")
    target.write_text(text, encoding="utf-8")
    failures = check_l9_meta.validate(root)
    assert any(f.startswith("malformed inline L9_META: docs/guide.md") for f in failures), failures
    # Preparation refuses to guess as well, in both modes, and writes nothing.
    before = _snapshot(root)
    assert apply_l9_meta.apply(root, check=True) == 1
    assert _snapshot(root) == before
    assert apply_l9_meta.apply(root, check=False) == 1
    assert _snapshot(root) == before


def test_duplicate_block_fails_closed(tmp_path: Path) -> None:
    root = _prepared(tmp_path)
    target = root / "tools" / "check.py"
    text = target.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = lines.index("# L9_META")
    block = lines[start : start + 9]
    lines[start + 9 : start + 9] = block
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    failures = check_l9_meta.validate(root)
    assert any(
        f.startswith("malformed inline L9_META: tools/check.py") and "duplicate" in f
        for f in failures
    ), failures
    with pytest.raises(l9_meta.MetaError):
        l9_meta.parse_inline(target.read_text(encoding="utf-8"), "tools/check.py")


def test_apply_reconciles_stale_structural_fields_and_keeps_artifact_fields(
    tmp_path: Path,
) -> None:
    root = _prepared(tmp_path)
    target = root / ".github" / "workflows" / "ci.yml"
    _set_field(target, "path", "docs/WIP/pack/files/.github/workflows/ci.yml")
    _set_field(target, "layer", "documentation")
    _set_field(target, "version", "1.2.3")
    _set_field(target, "updated", "2020-01-01")
    body_before = target.read_text(encoding="utf-8").split("\n\n", 1)[1]
    assert check_l9_meta.validate(root) != ()

    assert apply_l9_meta.apply(root, check=False) == 0
    text = target.read_text(encoding="utf-8")
    meta = l9_meta.parse_inline(text, ".github/workflows/ci.yml")
    assert meta is not None
    assert l9_meta.compare(meta, ".github/workflows/ci.yml") == ()
    # Artifact fields are not rewritten from location; file body is untouched.
    assert meta.get("version") == "1.2.3"
    assert meta.get("updated") == "2020-01-01"
    assert text.split("\n\n", 1)[1] == body_before


def test_reconcile_preserves_extra_fields_and_markdown_placement(tmp_path: Path) -> None:
    root = _prepared(tmp_path)
    target = root / "rules" / "rule.mdc"
    text = target.read_text(encoding="utf-8")
    text = text.replace("layer: configuration\n", "layer: wrong\n").replace(
        "/L9_META -->", "generated_by: someone\n/L9_META -->"
    )
    target.write_text(text, encoding="utf-8")
    assert apply_l9_meta.apply(root, check=False) == 0
    fixed = target.read_text(encoding="utf-8")
    assert fixed.startswith("---\ndescription: d\n---\n\n<!-- L9_META\n")
    meta = l9_meta.parse_inline(fixed, "rules/rule.mdc")
    assert meta is not None
    assert meta.get("layer") == "configuration"
    assert meta.get("generated_by") == "someone"
    # Only the block changed: the body after it is the original body.
    assert fixed.split("/L9_META -->", 1)[1].lstrip("\n") == "# Rule\n"


def test_check_mode_detects_drift_and_never_rewrites_input(tmp_path: Path) -> None:
    root = _prepared(tmp_path)
    _set_field(root / "scripts" / "run.sh", "layer", "documentation")
    (root / "docs" / "new.md").write_text("# New\n", encoding="utf-8")
    before = _snapshot(root)
    assert apply_l9_meta.apply(root, check=True) == 1
    assert _snapshot(root) == before
    changes, failures = apply_l9_meta.plan(root)
    assert failures == []
    assert {(p.relative_to(root).as_posix(), action) for p, action, _ in changes} == {
        ("scripts/run.sh", "reconcile"),
        ("docs/new.md", "insert"),
    }


def test_valid_block_renders_back_to_identical_bytes(tmp_path: Path) -> None:
    root = _prepared(tmp_path)
    for relative in ("tools/check.py", "docs/adr/ADR-001-first.md", "rules/rule.mdc"):
        text = (root / relative).read_text(encoding="utf-8")
        assert l9_meta.reconcile_text(text, relative) == text


# --- manifest check purity ----------------------------------------------------


def test_manifest_check_passes_when_bytes_match_and_writes_nothing(tmp_path: Path) -> None:
    root = _prepared(tmp_path)
    before = _snapshot(root)
    assert generate_manifest.check(root) == 0
    assert _snapshot(root) == before


def test_manifest_check_fails_when_tracked_input_changes_without_rewriting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _prepared(tmp_path)
    (root / "README.md").write_text("# Readme\n\nchanged\n", encoding="utf-8")
    manifest_before = (root / "manifest.json").read_bytes()
    markdown_before = (root / "MANIFEST.md").read_bytes()
    assert generate_manifest.check(root) == 1
    out = capsys.readouterr().out
    assert "manifest.json entry drifted: README.md" in out
    assert (root / "manifest.json").read_bytes() == manifest_before
    assert (root / "MANIFEST.md").read_bytes() == markdown_before


def test_manifest_check_fails_on_added_and_removed_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _prepared(tmp_path)
    (root / "LICENSE").unlink()
    (root / "extra.txt").write_text("x\n", encoding="utf-8")
    assert generate_manifest.check(root) == 1
    out = capsys.readouterr().out
    assert "manifest.json lists a file the tree does not have: LICENSE" in out
    assert "manifest.json is missing a tracked file: extra.txt" in out


def test_manifest_carries_structural_identity_and_no_release_verdict(tmp_path: Path) -> None:
    root = _prepared(tmp_path)
    markdown = (root / "MANIFEST.md").read_text(encoding="utf-8")
    assert "Local validation outcome" not in markdown
    assert "Production release outcome" not in markdown
    assert "BLOCKED_ON_EXTERNAL_VALIDATION" not in markdown
    assert markdown.startswith("<!-- L9_META\nl9_schema: 1\n")
    assert "path: MANIFEST.md\nlayer: repository\n" in markdown
    import json

    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "l9.release-manifest/v2"
    assert manifest["l9_meta"]["layer"] == "repository"
    by_path = {entry["path"]: entry for entry in manifest["files"]}
    assert by_path["src/pkg/client/contracts.py"]["l9_meta"]["layer"] == "contract"
    assert by_path["tests/test_core.py"]["l9_meta"]["layer"] == "test"
    assert by_path["LICENSE"]["l9_meta"]["layer"] == "repository"
    assert by_path["LICENSE"]["category"] == "repository_root"
    digest = hashlib.sha256((root / "MANIFEST.md").read_bytes()).hexdigest()
    assert by_path["MANIFEST.md"]["sha256"] == digest
    assert "manifest.json" not in by_path


def test_manifest_meta_mismatch_is_reported_by_checker(tmp_path: Path) -> None:
    import json

    root = _prepared(tmp_path)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        if entry["path"] == "LICENSE":
            entry["l9_meta"]["layer"] = "documentation"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    failures = check_l9_meta.validate(root)
    assert any(
        f.startswith("invalid manifest l9_meta: LICENSE") and "layer='documentation'" in f
        for f in failures
    ), failures
