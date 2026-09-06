# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/regression/test_release_version_consistency.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-09-06

"""Every place the release version is written must agree.

A consumer binds to ``PACKAGE_VERSION`` as the installed wheel reports it
(Cursor-Governance's runtime binding refuses any other), so the version in
``pyproject.toml``, the assurance stampers, and the evidence pins drifting
apart would make the released artifact unbindable by construction.
"""

from __future__ import annotations

import re
from pathlib import Path

import tomllib

from l9_graphite_memory.version import PACKAGE_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]


def _constant(path: Path, name: str) -> str:
    match = re.search(
        rf'^{name}(?::\s*Final)?\s*=\s*"([^"]+)"', path.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert match, f"{name} not found in {path}"
    return match.group(1)


def test_release_version_is_written_identically_everywhere() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assurance = REPO_ROOT / "tools" / "assurance"
    seen = {
        "pyproject.toml": pyproject["project"]["version"],
        "version.py": PACKAGE_VERSION,
        "generate_manifest.py": _constant(assurance / "generate_manifest.py", "RELEASE"),
        "apply_l9_meta.py": _constant(assurance / "apply_l9_meta.py", "VERSION"),
        "generate_validation_evidence.py": _constant(
            assurance / "generate_validation_evidence.py", "RELEASE"
        ),
    }
    assert len(set(seen.values())) == 1, seen


def test_validation_evidence_pins_name_the_release_wheel() -> None:
    text = (REPO_ROOT / "tools" / "assurance" / "generate_validation_evidence.py").read_text(
        encoding="utf-8"
    )
    escaped = PACKAGE_VERSION.replace(".", r"\.")
    assert f"l9_graphite_memory-{escaped}-py3-none-any" in text
    assert f"l9-graphite-memory=={escaped}" in text
