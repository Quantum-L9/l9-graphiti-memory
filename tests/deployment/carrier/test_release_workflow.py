# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/carrier/test_release_workflow.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 3.0.0
#   updated: 2026-10-26

"""The container release is one thin, admission-gated call to l9-ci-core.

l9-ci-core's container-release action is the only OCI publisher and the only
producer of ``l9.deployment-request/v2``. This file proves the Memory caller
reaches it once, at the pinned v2 producer revision, only after the exact
release is admitted, the carrier proof has run and the same-run Core analysis
gate has passed, and that nothing else in the repository builds, pushes or
dispatches an image.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.deployment.carrier.profile_contract import IMAGE, ROOT

WORKFLOWS = ROOT / ".github" / "workflows"
RELEASE = WORKFLOWS / "release-container.yml"
DOCKERFILE = ROOT / "Dockerfile"
ADMISSION_TOOL = ROOT / "tools" / "assurance" / "verify_release_admission.py"
# l9-ci-core main carrying the l9.deployment-request/v2 producer
# (container-release emits l9.release.requested.v2, the only event l9-deploy accepts).
CORE = "Quantum-L9/l9-ci-core"
CORE_REVISION = "89c9bc4e5ceafab932c92a2fdca2d3739fccf95f"
CONTAINER_RELEASE = f"{CORE}/.github/actions/container-release@{CORE_REVISION}"
ANALYSIS = f"{CORE}/.github/workflows/analyze-semgrep.yml@{CORE_REVISION}"
FULL_SHA = re.compile(r"@[0-9a-f]{40}$")
PUBLISHING = re.compile(r"--push\b|docker\s+(login|push)\b|\bghcr\.io\b|/dispatches\b")


def _workflow(path: Path = RELEASE) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _jobs() -> dict[str, Any]:
    jobs: dict[str, Any] = _workflow()["jobs"]
    return jobs


def _uses(document: Any) -> list[str]:
    if isinstance(document, dict):
        found = [document["uses"]] if isinstance(document.get("uses"), str) else []
        return found + [use for value in document.values() for use in _uses(value)]
    if isinstance(document, list):
        return [use for value in document for use in _uses(value)]
    return []


def _runs(job: dict[str, Any]) -> str:
    return "\n".join(str(step.get("run", "")) for step in job.get("steps", []))


def _step(job: str, name: str) -> dict[str, Any]:
    matches = [s for s in _jobs()[job]["steps"] if s.get("name") == name]
    assert len(matches) == 1, name
    step: dict[str, Any] = matches[0]
    return step


def test_dispatch_is_the_only_trigger() -> None:
    # PyYAML reads the bare `on:` key as boolean True.
    triggers = _workflow()[True]
    assert set(triggers) == {"workflow_dispatch"}
    assert triggers["workflow_dispatch"]["inputs"]["environment"]["options"] == ["production"]


def test_the_core_publisher_is_called_exactly_once_at_the_v2_producer_revision() -> None:
    every_use = [use for path in sorted(WORKFLOWS.glob("*.y*ml")) for use in _uses(_workflow(path))]
    assert [use for use in every_use if "container-release" in use] == [CONTAINER_RELEASE]
    release_uses = _uses(_jobs()["release"])
    assert CONTAINER_RELEASE in release_uses
    assert _jobs()["analysis"]["uses"] == ANALYSIS
    # Every third-party reference in the caller is immutable.
    assert all(FULL_SHA.search(use) for use in _uses(_workflow())), _uses(_workflow())


def test_no_other_workflow_builds_pushes_or_dispatches_an_image() -> None:
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        for name, job in _workflow(path).get("jobs", {}).items():
            assert not PUBLISHING.search(_runs(job)), f"{path.name}:{name} publishes outside Core"


def test_the_release_needs_admission_carrier_proof_and_a_passing_same_run_gate() -> None:
    release = _jobs()["release"]
    assert set(release["needs"]) == {"admission", "carrier-smoke", "analysis"}
    assert "needs.analysis.outputs.gate-status == 'pass'" in release["if"]
    assert "startsWith(github.ref, 'refs/tags/v')" in release["if"]
    assert _jobs()["carrier-smoke"]["needs"] == "admission"
    assert _jobs()["analysis"]["needs"] == "admission"
    # The operator's release authorization is the protected `release` environment.
    assert release["environment"] == "release"
    publish = _step("release", "Publish and request deployment")["with"]
    assert publish["deployment-profile"] == ".l9/deployment.yaml"
    assert publish["image-repository"] == IMAGE
    assert publish["analysis-artifact"] == "${{ needs.analysis.outputs.artifact-name }}"
    assert publish["matrix-id"] == _jobs()["analysis"]["with"]["matrix-id"] == "release-semgrep"
    assert publish["source-revision-build-arg-name"] == "L9_SOURCE_REVISION"
    assert _jobs()["analysis"]["with"]["profile"] == "release"
    assert _jobs()["analysis"]["with"]["event"] == "release"


def test_only_the_release_job_may_write_packages() -> None:
    assert _workflow()["permissions"] == {"contents": "read"}
    for name, job in _jobs().items():
        writes = job.get("permissions", {}).get("packages") == "write"
        assert writes == (name == "release"), name


def test_admission_binds_an_annotated_tag_to_the_admitted_exact_release() -> None:
    guard = _step("admission", "Require a release tag run")["run"]
    assert 'GITHUB_REF_TYPE" != tag' in guard
    assert "^refs/tags/v[0-9]+\\.[0-9]+\\.[0-9]+$" in guard
    annotated = _step("admission", "Require an annotated tag on the run's exact commit")["run"]
    assert 'git cat-file -t "$GITHUB_REF")" = tag' in annotated
    assert '"$GITHUB_REF^{commit}")" = "$GITHUB_SHA"' in annotated
    record = _step("admission", "Check out the release admission record (default branch)")
    assert record["with"]["ref"] == "${{ github.event.repository.default_branch }}"
    verify = _step("admission", "Verify the exact-release admission")["run"]
    assert "tools/assurance/verify_release_admission.py" in verify
    for argument in (
        "--admission-root build/release-admission",
        "--artifact-dir dist",
        '--source-revision "$GITHUB_SHA"',
        '--tag "$GITHUB_REF_NAME"',
    ):
        assert argument in verify
    assert "${{" not in _runs(_jobs()["admission"])
    assert not any(
        step.get("continue-on-error") for job in _jobs().values() for step in job.get("steps", [])
    )


def test_the_carrier_proof_cannot_pass_by_skipping() -> None:
    smoke = _jobs()["carrier-smoke"]
    assert "--push" not in _runs(smoke)
    suite = _step("carrier-smoke", "Run the carrier suite against the image")
    assert suite["env"]["L9_MEMORY_TEST_CARRIER_IMAGE"] == "l9-graphite-memory:carrier-smoke"
    assert "tests/deployment/carrier" in suite["run"]
    assert "^SKIPPED" in _step("carrier-smoke", "Fail if any carrier test skipped")["run"]


@pytest.mark.parametrize(
    ("tag", "source", "expected"),
    [
        ("v3.0.0", "0" * 40, "no release admission receipt"),
        ("v3.0.1", "0" * 40, "release tag 'v3.0.1' is not v3.0.0"),
    ],
    ids=["unadmitted", "tag-mismatched"],
)
def test_the_admission_the_workflow_runs_refuses_an_unadmitted_release(
    tmp_path: Path, tag: str, source: str, expected: str
) -> None:
    import subprocess
    import sys

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "l9_graphite_memory-3.0.0-py3-none-any.whl").write_bytes(b"wheel")
    (dist / "l9_graphite_memory-3.0.0.tar.gz").write_bytes(b"sdist")
    result = subprocess.run(
        [
            sys.executable,
            str(ADMISSION_TOOL),
            "--admission-root",
            str(tmp_path / "default-branch"),
            "--artifact-dir",
            str(dist),
            "--version",
            "3.0.0",
            "--source-revision",
            source,
            "--tag",
            tag,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert expected in result.stdout + result.stderr


def test_the_dockerfile_is_the_profile_carrier() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    # Bases are pinned by digest; the source revision is mandatory and the one
    # the release action passes.
    froms = re.findall(r"^FROM\s+(\S+)", text, flags=re.MULTILINE)
    assert len(froms) == 2 and all("@sha256:" in image for image in froms), froms
    assert "ARG L9_SOURCE_REVISION" in text
    assert "--extra server --extra postgres" in text
    assert re.search(r"^EXPOSE 8200$", text, flags=re.MULTILINE)
    assert re.search(r"^USER 10001:10001$", text, flags=re.MULTILINE)
    assert "L9_MEMORY_STORE_BACKEND=postgres" in text
    # Settings loading mkdirs these; under a read-only root they must pre-exist,
    # and must not be writable by the service.
    assert "install -d -o root -g root -m 0555" in text
    assert "L9_MEMORY_DATA_DIR=/var/lib/l9-memory/data" in text
    assert "L9_MEMORY_STATE_DIR=/var/lib/l9-memory/state" in text
    assert "--host 0.0.0.0 --port 8200" in text
    assert "/readyz" in text
    for refused in (
        "L9_MEMORY_STORE_BACKEND must be postgres",
        "L9_MEMORY_POSTGRES_DSN is required",
        "L9_MEMORY_HTTP_AUTH_REQUIRED must be true",
        "L9_MEMORY_HTTP_AUTH_MODE must be signed-agent",
    ):
        assert refused in text
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "*" in ignore, "the build context is an allow-list"
