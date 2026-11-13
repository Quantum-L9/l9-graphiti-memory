# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/release_dispatch/test_release_dispatch_workflow.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 3.0.1
#   updated: 2026-11-13

"""release-dispatch.yml starts the container release as the repository bot.

l9-deploy requires the approver of its `production` environment to differ from
the requester, and the requester is the actor of the release-container.yml run.
The dispatcher makes that actor the GitHub App behind GITHUB_TOKEN instead of
the human approver. These tests pin what that requires statically: a manual
trigger, the narrowest token, inputs that never reach shell text, fail-closed
tag checks, and exactly one dispatch target. They cannot prove the dispatched
run's actor; that is observable only on the first real run.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
DISPATCHER = WORKFLOWS / "release-dispatch.yml"
RELEASE = WORKFLOWS / "release-container.yml"
FULL_SHA = re.compile(r"@[0-9a-f]{40}$")
DISPATCHING = re.compile(r"\bgh\s+workflow\s+run\b|/dispatches\b")


def _workflow(path: Path = DISPATCHER) -> dict[Any, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _job() -> dict[str, Any]:
    jobs: dict[str, Any] = _workflow()["jobs"]
    assert set(jobs) == {"dispatch"}
    job: dict[str, Any] = jobs["dispatch"]
    return job


def _steps() -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = _job()["steps"]
    return steps


def _step(name: str) -> dict[str, Any]:
    matches = [step for step in _steps() if step.get("name") == name]
    assert len(matches) == 1, name
    return matches[0]


def _uses(document: Any) -> list[str]:
    if isinstance(document, dict):
        found = [document["uses"]] if isinstance(document.get("uses"), str) else []
        return found + [use for value in document.values() for use in _uses(value)]
    if isinstance(document, list):
        return [use for value in document for use in _uses(value)]
    return []


def test_manual_dispatch_is_the_only_trigger_with_the_release_inputs() -> None:
    # PyYAML reads the bare `on:` key as boolean True.
    triggers = _workflow()[True]
    assert set(triggers) == {"workflow_dispatch"}
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"tag", "environment"}
    assert inputs["tag"]["required"] is True
    assert inputs["tag"]["type"] == "string"
    assert inputs["environment"]["required"] is True
    assert inputs["environment"]["type"] == "choice"
    release_options = _workflow(RELEASE)[True]["workflow_dispatch"]["inputs"]["environment"]
    assert inputs["environment"]["options"] == release_options["options"]


def test_the_token_is_scoped_to_the_dispatch_job_only() -> None:
    assert _workflow()["permissions"] == {}
    assert _job()["permissions"] == {"actions": "write", "contents": "read"}
    env = _job()["env"]
    assert env["GH_TOKEN"] == "${{ github.token }}"
    # No secret other than the built-in token is referenced anywhere.
    assert "secrets." not in DISPATCHER.read_text(encoding="utf-8")


def test_one_dispatch_per_tag_at_a_time() -> None:
    concurrency = _workflow()["concurrency"]
    assert concurrency["group"] == "release-dispatch-${{ inputs.tag }}"
    assert concurrency["cancel-in-progress"] is False


def test_inputs_reach_the_shell_only_through_env() -> None:
    env = _job()["env"]
    assert env["RELEASE_TAG"] == "${{ inputs.tag }}"
    assert env["RELEASE_ENVIRONMENT"] == "${{ inputs.environment }}"
    for step in _steps():
        run = str(step.get("run", ""))
        assert "${{" not in run, step.get("name")
        assert step.get("shell") == "bash", step.get("name")
        assert "set -euo pipefail" in run, step.get("name")
        assert not step.get("continue-on-error"), step.get("name")


def test_no_third_party_action_and_any_reference_is_pinned() -> None:
    uses = _uses(_workflow())
    assert uses == []
    assert all(FULL_SHA.search(use) for use in uses)


def test_checks_fail_closed_before_the_dispatch() -> None:
    names = [step["name"] for step in _steps()]
    assert names == [
        "Require this dispatcher to run from the default branch",
        "Require a release tag name",
        "Require an existing annotated tag",
        "Require the release workflow at the tag",
        "Require that no branch shares the tag's name",
        "Dispatch the release as the repository bot",
    ]
    branch = _step("Require this dispatcher to run from the default branch")["run"]
    assert '"$GITHUB_REF" != "refs/heads/$DEFAULT_BRANCH"' in branch
    assert _job()["env"]["DEFAULT_BRANCH"] == "${{ github.event.repository.default_branch }}"
    name = _step("Require a release tag name")["run"]
    assert '"$RELEASE_TAG" =~ ^v[0-9]+\\.[0-9]+\\.[0-9]+$' in name
    annotated = _step("Require an existing annotated tag")["run"]
    assert "repos/$GH_REPO/git/ref/tags/$RELEASE_TAG" in annotated
    assert "--jq '.object.type'" in annotated
    assert '"$ref_type" != tag' in annotated
    present = _step("Require the release workflow at the tag")["run"]
    assert "contents/.github/workflows/$TARGET_WORKFLOW?ref=refs/tags/$RELEASE_TAG" in present


def test_the_only_dispatch_is_release_container_on_the_tag() -> None:
    assert _job()["env"]["TARGET_WORKFLOW"] == RELEASE.name
    dispatch = _step("Dispatch the release as the repository bot")["run"]
    assert (
        'gh workflow run "$TARGET_WORKFLOW" --ref "$RELEASE_TAG" '
        '-f environment="$RELEASE_ENVIRONMENT"'
    ) in dispatch
    # The dispatch API takes a branch or tag name, never a qualified ref, so a
    # branch sharing the tag's name must be refused before the dispatch.
    assert '--ref "refs/' not in dispatch
    unambiguous = _step("Require that no branch shares the tag's name")["run"]
    assert "repos/$GH_REPO/git/ref/heads/$RELEASE_TAG" in unambiguous
    assert "exit 1" in unambiguous
    names = [s["name"] for s in _steps()]
    assert names.index("Require that no branch shares the tag's name") < names.index(
        "Dispatch the release as the repository bot"
    )
    dispatching_steps = [s["name"] for s in _steps() if DISPATCHING.search(str(s.get("run", "")))]
    assert dispatching_steps == ["Dispatch the release as the repository bot"]
    # No other workflow dispatches a workflow run.
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        if path == DISPATCHER:
            continue
        for job_name, job in (_workflow(path).get("jobs") or {}).items():
            for step in job.get("steps") or []:
                assert not DISPATCHING.search(str(step.get("run", ""))), f"{path.name}:{job_name}"


def test_the_dispatcher_does_not_duplicate_or_replace_release_gates() -> None:
    # Parsed content only: the header comment names these gates on purpose.
    runs = "\n".join(str(step.get("run", "")) for step in _steps())
    assert "verify_release_admission" not in runs
    assert "container-release" not in runs
    assert "environment" not in _job()
    release_job = _workflow(RELEASE)["jobs"]["release"]
    assert release_job["environment"] == "release"
    assert set(release_job["needs"]) == {"admission", "carrier-smoke", "analysis"}
