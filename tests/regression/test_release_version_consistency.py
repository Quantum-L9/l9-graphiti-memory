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

from l9_graphite_memory.version import PACKAGE_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]


def _pyproject_version() -> str:
    # No tomllib: the package supports Python 3.10 (requires-python >= 3.10)
    # and the TOML here is the one line the release must agree on.
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project = re.search(r"^\[project\]\n(.*?)(?=^\[)", text, re.MULTILINE | re.DOTALL)
    assert project, "[project] table not found in pyproject.toml"
    match = re.search(r'^version\s*=\s*"([^"]+)"', project.group(1), re.MULTILINE)
    assert match, "project.version not found in pyproject.toml"
    return match.group(1)


def _constant(path: Path, name: str) -> str:
    match = re.search(
        rf'^{name}(?::\s*Final)?\s*=\s*"([^"]+)"', path.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert match, f"{name} not found in {path}"
    return match.group(1)


def test_release_version_is_written_identically_everywhere() -> None:
    assurance = REPO_ROOT / "tools" / "assurance"
    seen = {
        "pyproject.toml": _pyproject_version(),
        "version.py": PACKAGE_VERSION,
        "generate_manifest.py": _constant(assurance / "generate_manifest.py", "RELEASE"),
        "apply_l9_meta.py": _constant(assurance / "apply_l9_meta.py", "VERSION"),
        "generate_validation_evidence.py": _constant(
            assurance / "generate_validation_evidence.py", "RELEASE"
        ),
        "preflight.sh": _preflight_version(),
    }
    assert len(set(seen.values())) == 1, seen


def _preflight_version() -> str:
    # The release preflight pins the importable version literally; it was the
    # one carrier the 2.3.0 bump missed, so it is checked here with the rest.
    text = (REPO_ROOT / "scripts" / "preflight.sh").read_text(encoding="utf-8")
    match = re.search(r'__version__ == "([^"]+)"', text)
    assert match, "package import gate not found in scripts/preflight.sh"
    return match.group(1)


def test_validation_evidence_pins_name_the_release_wheel() -> None:
    text = (REPO_ROOT / "tools" / "assurance" / "generate_validation_evidence.py").read_text(
        encoding="utf-8"
    )
    escaped = PACKAGE_VERSION.replace(".", r"\.")
    assert f"l9_graphite_memory-{escaped}-py3-none-any" in text
    assert f"l9-graphite-memory=={escaped}" in text


def test_published_optional_dependencies_have_no_direct_url() -> None:
    # PyPI rejects Requires-Dist that name a git/URL source, including extras.
    # Gate_SDK stays a uv dependency-group + [tool.uv.sources], not an extra.
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    extras = re.search(
        r"^\[project\.optional-dependencies\]\n(.*?)(?=^\[)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert extras, "[project.optional-dependencies] not found"
    body = extras.group(1)
    assert "git+" not in body
    assert not re.search(r"https?://", body)
