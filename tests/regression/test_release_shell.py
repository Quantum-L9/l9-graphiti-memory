# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/regression/test_release_shell.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-10-02

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate_release.sh"
PUBLISH = ROOT / ".github" / "workflows" / "publish.yml"


def test_packaged_registry_exists() -> None:
    registry = files("l9_graphite_memory").joinpath("resources/group_registry.yaml")
    assert registry.is_file()
    assert "l9-graphiti-memory" in registry.read_text(encoding="utf-8")


def _dry_run(script: str, tmp_path: Path) -> dict:
    env = os.environ.copy()
    env.update(
        {
            "INFISICAL_CLIENT_SECRET": "never-persist-this-infisical-secret",
            "ZEP_API_KEY": "never-persist-this-zep-secret",
            "GRAPHITI_MCP_TOKEN": "never-persist-this-graphiti-token",
        }
    )
    result = subprocess.run(
        [sys.executable, script, "--dry-run", "--path", str(tmp_path / "mcp.json")],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(result.stdout)


def test_cursor_config_writer_does_not_persist_secrets(tmp_path: Path) -> None:
    payload = _dry_run("scripts/write_cursor_config.py", tmp_path)
    encoded = json.dumps(payload)
    assert "never-persist" not in encoded
    assert "env" not in payload["config"]["mcpServers"]["l9-graphite-memory"]


def test_claude_config_writer_does_not_persist_secrets(tmp_path: Path) -> None:
    payload = _dry_run("scripts/write_claude_config.py", tmp_path)
    encoded = json.dumps(payload)
    assert "never-persist" not in encoded
    assert "env" not in payload["config"]["mcpServers"]["l9-graphite-memory"]


def test_mark_ok_requires_current_fresh_hydration(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_path = state_dir / "hook-test.json"
    state = {
        "schema_version": 3,
        "namespace": "repo",
        "hydrated_at": datetime.now(timezone.utc).isoformat(),
        "hydration_digest": "a" * 64,
        "hydration_status": "complete",
        "task_signature": "task-a",
        "verified_task_signatures": [],
        "ttl_minutes": 30,
        "phase_lock_granted": False,
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    env = os.environ.copy()
    # graphiti_common prefers CURSOR_CONVERSATION_ID over L9_SESSION_ID; clear it
    # so this regression stays hermetic when run under a Cursor agent.
    env.pop("CURSOR_CONVERSATION_ID", None)
    env.update({"L9_MEMORY_STATE_DIR": str(state_dir), "L9_SESSION_ID": "hook-test"})

    subprocess.run(
        ["bash", "hooks/graphiti-mark-ok.sh", "task-a"],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )
    updated = json.loads(state_path.read_text(encoding="utf-8"))
    assert updated["verified_task_signatures"] == ["task-a"]

    wrong = subprocess.run(
        ["bash", "hooks/graphiti-mark-ok.sh", "other-task"],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )
    assert wrong.returncode != 0


def test_release_build_sets_reproducible_epoch() -> None:
    script = Path("scripts/validate_release.sh").read_text(encoding="utf-8")
    assert "SOURCE_DATE_EPOCH" in script
    assert "1784592000" in script


# --- release validation is observational -------------------------------------


def _validator_commands() -> list[list[str]]:
    """Every command line of the validator, split like the shell would.

    Comments are dropped so the assertions below inspect what runs, not what
    the prose says.
    """

    commands: list[list[str]] = []
    for raw in VALIDATOR.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for part in re.split(r"\s*(?:&&|\|\||\|)\s*", line):
            try:
                tokens = shlex.split(part, comments=True)
            except ValueError:
                tokens = part.split()
            if tokens:
                commands.append(tokens)
    return commands


def _tool_invocations(tool: str) -> list[list[str]]:
    return [
        tokens
        for tokens in _validator_commands()
        if any(token.endswith(f"tools/assurance/{tool}") for token in tokens)
    ]


def test_release_validation_never_invokes_metadata_apply_mode() -> None:
    invocations = _tool_invocations("apply_l9_meta.py")
    assert invocations, "validator must still verify inline metadata"
    for tokens in invocations:
        assert "--check" in tokens, tokens


def test_release_validation_never_invokes_manifest_apply_mode() -> None:
    invocations = _tool_invocations("generate_manifest.py")
    assert invocations, "validator must still verify the manifest"
    for tokens in invocations:
        assert "--check" in tokens, tokens


def test_release_validation_evidence_root_is_untracked_build_workspace() -> None:
    script = VALIDATOR.read_text(encoding="utf-8")
    assert 'OUT="${L9_RELEASE_EVIDENCE_DIR:-$ROOT/build/release-validation}"' in script
    assert 'OUT="$ROOT/validation"' not in script
    # The evidence generator is pointed at the workspace, never at its old default.
    evidence = _tool_invocations("generate_validation_evidence.py")
    assert evidence and all("--evidence-dir" in tokens for tokens in evidence), evidence
    # Nothing deletes or rewrites the tracked validation/ tree.
    for tokens in _validator_commands():
        if tokens[0] == "rm":
            assert not any(
                token in {'"$ROOT/validation"', "$ROOT/validation", "validation"}
                or token.startswith("validation/")
                for token in tokens
            ), tokens


def test_release_validation_supports_exact_prebuilt_artifact_consumption() -> None:
    script = VALIDATOR.read_text(encoding="utf-8")
    assert "L9_RELEASE_ARTIFACT_DIR" in script
    # The build happens only in the self-contained branch; publication mode
    # consumes the supplied directory as-is.
    builds = [tokens for tokens in _validator_commands() if "build" in tokens and "-m" in tokens]
    assert len(builds) == 1, builds
    assert '"$ART"' in builds[0] or "$ART" in builds[0], builds[0]
    assert 'ARTIFACT_MODE="publication"' in script
    assert "installed wheel digest matches validated artifact set" in script


def _run_validator(tmp_path: Path, **env_overrides: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("L9_RELEASE_ARTIFACT_DIR", None)
    env.pop("L9_RELEASE_EVIDENCE_DIR", None)
    env.update(env_overrides)
    return subprocess.run(
        ["bash", str(VALIDATOR)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_release_validation_refuses_tracked_validation_tree_as_evidence_root(
    tmp_path: Path,
) -> None:
    tracked = ROOT / "validation"
    before = {p: p.stat().st_mtime_ns for p in tracked.rglob("*") if p.is_file()}
    result = _run_validator(tmp_path, L9_RELEASE_EVIDENCE_DIR=str(tracked))
    assert result.returncode != 0
    assert "not an evidence workspace" in result.stderr
    assert {p: p.stat().st_mtime_ns for p in tracked.rglob("*") if p.is_file()} == before


def test_release_validation_refuses_tracked_overlap_as_evidence_root(tmp_path: Path) -> None:
    result = _run_validator(tmp_path, L9_RELEASE_EVIDENCE_DIR=str(ROOT / "docs" / "adr"))
    assert result.returncode != 0
    assert "overlaps tracked content" in result.stderr


def test_release_validation_refuses_missing_or_empty_artifact_directory(tmp_path: Path) -> None:
    missing = _run_validator(
        tmp_path,
        L9_RELEASE_ARTIFACT_DIR=str(tmp_path / "nowhere"),
        L9_RELEASE_EVIDENCE_DIR=str(tmp_path / "evidence"),
    )
    assert missing.returncode != 0
    assert "not a directory" in missing.stderr
    empty = tmp_path / "dist"
    empty.mkdir()
    result = _run_validator(
        tmp_path,
        L9_RELEASE_ARTIFACT_DIR=str(empty),
        L9_RELEASE_EVIDENCE_DIR=str(tmp_path / "evidence"),
    )
    assert result.returncode != 0
    assert "exactly one release wheel" in result.stderr
    assert not (tmp_path / "evidence").exists()


# --- publication builds once and publishes the validated bytes ---------------


def _publish_steps() -> list[dict]:
    workflow = yaml.safe_load(PUBLISH.read_text(encoding="utf-8"))
    return workflow["jobs"]["validate-and-publish"]["steps"]


def _index(steps: list[dict], predicate: Callable[[dict], bool]) -> int:
    matches = [index for index, step in enumerate(steps) if predicate(step)]
    assert len(matches) == 1, matches
    return matches[0]


def test_publish_builds_release_artifacts_exactly_once_before_validation() -> None:
    steps = _publish_steps()
    builds = [i for i, s in enumerate(steps) if "python -m build" in str(s.get("run", ""))]
    assert len(builds) == 1, builds
    build = builds[0]
    validate = _index(steps, lambda s: "scripts/validate_release.sh" in str(s.get("run", "")))
    publish = _index(
        steps, lambda s: str(s.get("uses", "")).startswith("pypa/gh-action-pypi-publish")
    )
    assert build < validate < publish
    assert "--outdir dist" in steps[build]["run"]
    # Nothing between validation and publication rebuilds.
    for step in steps[validate + 1 :]:
        assert "python -m build" not in str(step.get("run", ""))
        assert "uv build" not in str(step.get("run", ""))


def test_publish_validation_consumes_and_publication_ships_the_same_dist() -> None:
    workflow = yaml.safe_load(PUBLISH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["validate-and-publish"]
    assert job["env"]["L9_RELEASE_ARTIFACT_DIR"] == "dist"
    assert job["env"]["L9_RELEASE_EVIDENCE_DIR"] == "build/release-validation"
    assert job["env"]["SOURCE_DATE_EPOCH"] == "1784592000"
    steps = _publish_steps()
    publish = steps[
        _index(steps, lambda s: str(s.get("uses", "")).startswith("pypa/gh-action-pypi-publish"))
    ]
    assert publish["with"]["packages-dir"].rstrip("/") == "dist"
    proof = steps[
        _index(
            steps,
            lambda s: (
                "build-digests.txt" in str(s.get("run", "")) and "diff" in str(s.get("run", ""))
            ),
        )
    ]
    validate = _index(steps, lambda s: "scripts/validate_release.sh" in str(s.get("run", "")))
    assert steps.index(proof) > validate
    assert "sha256sum dist/*" in proof["run"]
    upload = steps[
        _index(steps, lambda s: str(s.get("uses", "")).startswith("actions/upload-artifact"))
    ]
    uploaded = [line.strip() for line in upload["with"]["path"].splitlines() if line.strip()]
    assert "dist/" in uploaded
    assert "build/release-validation/" in uploaded
    # The tracked validation/ tree is candidate content, not this run's evidence.
    assert "validation/" not in uploaded and "validation" not in uploaded


def test_publish_preserves_release_gates() -> None:
    workflow = yaml.safe_load(PUBLISH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["validate-and-publish"]
    assert job["environment"] == "release"
    assert workflow["permissions"]["id-token"] == "write"
    assert set(job["services"]) == {"postgres", "redis"}
    runs = [str(s.get("run", "")) for s in job["steps"]]
    assert any(r.strip() == "ruff check ." for r in runs)
    assert any(r.strip() == "mypy src/l9_graphite_memory" for r in runs)
    checkout = job["steps"][0]
    assert checkout["uses"].startswith("actions/checkout")
    assert "refs/tags/" in checkout["with"]["ref"]
