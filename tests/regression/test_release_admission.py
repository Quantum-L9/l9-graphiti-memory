# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/regression/test_release_admission.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 3.0.0
#   updated: 2026-10-15

"""Publication requires the admission of the exact release (ADR-094; ADR-022, 2026-10-15).

The ``release`` environment approval names no version or digest, so it cannot
be the admission decision. ``publish.yml`` therefore refuses PyPI unless the
receipt on the protected default branch admits this exact version, source
revision, wheel sha256 and sdist sha256. Every positive here is paired with the
mismatches that must stop an otherwise valid ``v3.0.0`` release.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "assurance" / "verify_release_admission.py"
PUBLISH = ROOT / ".github" / "workflows" / "publish.yml"
RECEIPT_2_6_0 = ROOT / "docs" / "receipts" / "l9-memory-release-2.6.0.md"
VERSION = "3.0.0"
TAG = f"v{VERSION}"
SOURCE = "c9d413ad11fbff2baa23515f6133a2ed014c5bd8"
WHEEL = f"l9_graphite_memory-{VERSION}-py3-none-any.whl"
SDIST = f"l9_graphite_memory-{VERSION}.tar.gz"


def _tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_release_admission", TOOL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TOOL_MODULE = _tool()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _receipt(**overrides: str) -> str:
    rows = {
        "Package": f"`l9-graphite-memory` `{VERSION}`",
        "Admitted source": f"`{SOURCE}`",
        "Wheel": f"`{WHEEL}`",
        "Wheel sha256": f"`{_digest(b'wheel bytes')}`",
        "Sdist": f"`{SDIST}`",
        "Sdist sha256": f"`{_digest(b'sdist bytes')}`",
    }
    rows.update(overrides)
    table = "".join(f"| {key} | {value} |\n" for key, value in rows.items() if value != "")
    return f"# l9-graphite-memory {VERSION} release admission\n\n| Coordinate | Value |\n|---|---|\n{table}"


@pytest.fixture
def release(tmp_path: Path) -> dict[str, Path]:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / WHEEL).write_bytes(b"wheel bytes")
    (dist / SDIST).write_bytes(b"sdist bytes")
    root = tmp_path / "default-branch"
    receipts = root / "docs" / "receipts"
    receipts.mkdir(parents=True)
    receipt = receipts / f"l9-memory-release-{VERSION}.md"
    receipt.write_text(_receipt(), encoding="utf-8")
    return {"dist": dist, "receipt": receipt, "root": root}


def _verify(release: dict[str, Path], **kw: Any) -> list[str]:
    args = {"version": VERSION, "source_revision": SOURCE, "tag": TAG, **kw}
    failures, _ = TOOL_MODULE.verify(release["root"], release["dist"], **args)
    return list(failures)


def test_an_exactly_admitted_release_passes(release):
    assert _verify(release) == []


def test_a_valid_v3_tag_without_a_receipt_cannot_publish(release):
    release["receipt"].unlink()
    failures = _verify(release)
    assert any("no release admission receipt" in f for f in failures), failures


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"Package": "`l9-graphite-memory` `2.9.9`"}, "receipt admits"),
        ({"Package": "`another-distribution` `3.0.0`"}, "receipt admits"),
        ({"Admitted source": f"`{'0' * 40}`"}, "receipt admits source"),
        ({"Wheel sha256": f"`{_digest(b'other wheel')}`"}, "wheel sha256"),
        ({"Sdist sha256": f"`{_digest(b'other sdist')}`"}, "sdist sha256"),
        ({"Wheel": "`l9_graphite_memory-3.0.0-py3-none-linux_x86_64.whl`"}, "receipt admits wheel"),
        ({"Sdist": "`l9_graphite_memory-3.0.0.zip`"}, "receipt admits sdist"),
        ({"Sdist sha256": "`pending`"}, "not a sha256 digest"),
        ({"Wheel sha256": ""}, "does not name 'Wheel sha256'"),
        ({"Admitted source": ""}, "does not name 'Admitted source'"),
    ],
)
def test_a_receipt_for_anything_else_does_not_admit(release, override, expected):
    release["receipt"].write_text(_receipt(**override), encoding="utf-8")
    failures = _verify(release)
    assert any(expected in f for f in failures), failures


def test_a_duplicated_coordinate_fails_closed(release):
    text = release["receipt"].read_text(encoding="utf-8")
    release["receipt"].write_text(text + f"| Wheel sha256 | `{'f' * 64}` |\n", encoding="utf-8")
    failures = _verify(release)
    assert any("more than once" in f for f in failures), failures


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        ({"tag": "v3.0.1"}, "is not v3.0.0"),
        ({"tag": "3.0.0"}, "is not v3.0.0"),
        ({"source_revision": "main"}, "not a 40-hex commit"),
        ({"version": "3.0.1", "tag": "v3.0.1"}, "no release admission receipt"),
    ],
)
def test_the_published_coordinates_must_be_the_admitted_ones(release, kw, expected):
    failures = _verify(release, **kw)
    assert any(expected in f for f in failures), failures


def test_a_receipt_filed_under_another_version_does_not_admit_it(release):
    other = release["receipt"].with_name("l9-memory-release-3.0.1.md")
    other.write_text(release["receipt"].read_text(encoding="utf-8"), encoding="utf-8")
    failures = _verify(release, version="3.0.1", tag="v3.0.1")
    assert any("receipt admits 'l9-graphite-memory 3.0.0'" in f for f in failures), failures


@pytest.mark.parametrize("source", [SOURCE + "\n", SOURCE.upper(), SOURCE[:39]])
def test_a_source_revision_must_be_exactly_40_lowercase_hex(release, source):
    failures = _verify(release, source_revision=source)
    assert any("not a 40-hex commit" in f for f in failures), failures


def test_rebuilt_bytes_are_not_the_admitted_bytes(release):
    (release["dist"] / SDIST).write_bytes(b"sdist bytes rebuilt elsewhere")
    failures = _verify(release)
    assert any("sdist sha256" in f for f in failures), failures


@pytest.mark.parametrize("extra", ["l9_graphite_memory-3.0.0-py2-none-any.whl", "notes.txt"])
def test_an_unadmitted_extra_artifact_fails_closed(release, extra):
    (release["dist"] / extra).write_bytes(b"extra")
    assert _verify(release)


@pytest.mark.parametrize(
    "version", ["../../../candidate/3.0.0", "3.0.0/../../x", "3.0", "3.0.0rc1", "3.0.0\n"]
)
def test_a_version_never_locates_a_receipt_outside_the_admission_root(release, version):
    failures = _verify(release, version=version, tag=f"v{version}")
    assert any("does not name a receipt" in f for f in failures), failures


def test_a_receipt_resolving_outside_the_admission_root_is_refused(release, tmp_path):
    forged = tmp_path / "candidate-tree-receipt.md"
    forged.write_text(release["receipt"].read_text(encoding="utf-8"), encoding="utf-8")
    release["receipt"].unlink()
    release["receipt"].symlink_to(forged)
    failures = _verify(release)
    assert any("does not name a receipt" in f for f in failures), failures


def test_a_missing_sdist_fails_closed(release):
    (release["dist"] / SDIST).unlink()
    failures = _verify(release)
    assert any("exactly one sdist" in f for f in failures), failures


def test_the_cli_exits_non_zero_and_admits_nothing(release, capsys, monkeypatch):
    release["receipt"].unlink()
    argv = [
        "verify_release_admission.py",
        "--admission-root",
        str(release["root"]),
        "--artifact-dir",
        str(release["dist"]),
        "--version",
        VERSION,
        "--source-revision",
        SOURCE,
        "--tag",
        TAG,
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert TOOL_MODULE.main() == 1
    out = capsys.readouterr().out
    assert "FAIL: no release admission receipt" in out
    assert "observed release (admits nothing)" in out


def test_the_established_2_6_0_receipt_is_the_parsed_format():
    rows, failures = TOOL_MODULE.parse_receipt(RECEIPT_2_6_0.read_text(encoding="utf-8"))
    assert failures == []
    assert rows["Package"] == "l9-graphite-memory 2.6.0"
    assert rows["Admitted source"] == "846f283f7dade101b324b87008ab4f5901f97074"
    assert rows["Wheel sha256"] == (
        "d493573254cecedafb66ad3e1ccc380841ec8c617e9501adb5d993c989653d15"
    )
    assert rows["Sdist sha256"] == (
        "537ff040a096a5adbc075fa3871cd1099d2bf93315e4ec3b5e5987acb638ff98"
    )


def _steps() -> list[dict[str, Any]]:
    workflow = yaml.safe_load(PUBLISH.read_text(encoding="utf-8"))
    steps: list[dict[str, Any]] = workflow["jobs"]["validate-and-publish"]["steps"]
    return steps


def test_publication_is_gated_by_the_admission_verifier():
    steps = _steps()
    names = [step.get("name") for step in steps]
    publish = [i for i, s in enumerate(steps) if "gh-action-pypi-publish" in str(s.get("uses"))]
    assert len(publish) == 1
    record = names.index("Check out the release admission record (default branch)")
    verify = names.index("Verify the exact-release admission")
    proof = names.index("Prove the validated artifact set is the publication set")
    assert proof < record < verify < publish[0]
    # The record comes from the protected default branch, never the candidate.
    checkout = steps[record]["with"]
    assert checkout["ref"] == "${{ github.event.repository.default_branch }}"
    assert checkout["path"] == "build/release-admission"
    # The verifier runs whenever publication would, and can never be skipped.
    assert steps[verify]["if"] == steps[publish[0]]["if"] == steps[record]["if"]
    assert "verify_release_admission.py" in steps[verify]["run"]
    assert "--admission-root build/release-admission" in steps[verify]["run"]
    assert not any(step.get("continue-on-error") for step in steps)
    # The tag reaches the shell through env, never inline expression text.
    assert "${{" not in steps[verify]["run"]
