# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_installed_wheel_lifecycle.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-09-06

"""The consumer lifecycle against the *built and installed* wheel (stage M2).

Cursor-Governance binds an installed artifact, never this checkout, so the
proof that matters is the one that runs from a wheel installed into an empty
target directory with nothing else on ``PYTHONPATH``: capabilities, health,
governed continuation admission, tag-selected retrieval, and an idempotent
close, each through the console entry point the consumer actually invokes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "control_plane" / "continuation_candidate.json"


@pytest.fixture(scope="module")
def installed_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the wheel once and install it into an isolated target directory."""

    pytest.importorskip("build")
    root = tmp_path_factory.mktemp("wheel")
    dist = root / "dist"
    build = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist), str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "SOURCE_DATE_EPOCH": "1784592000"},
    )
    assert build.returncode == 0, build.stderr[-2000:]
    wheels = sorted(dist.glob("l9_graphite_memory-*.whl"))
    assert len(wheels) == 1, wheels
    site = root / "site"
    site.mkdir()
    if shutil.which("uv"):
        install = [
            "uv",
            "pip",
            "install",
            "--python",
            sys.executable,
            "--target",
            str(site),
            "--reinstall",
            "--no-deps",
            str(wheels[0]),
        ]
    else:
        install = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--target",
            str(site),
            "--force-reinstall",
            "--no-deps",
            str(wheels[0]),
        ]
    result = subprocess.run(install, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr[-2000:]
    return site


def _env(site: Path, data: Path) -> dict[str, str]:
    """Only the installed wheel is importable; the checkout is not on the path."""

    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "PYTHONPATH",
            "L9_MEMORY_CONFIG",
            "GRAPHITI_GROUP_ID",
            "CURSOR_CONVERSATION_ID",
            "L9_SESSION_ID",
        }
    }
    # pydantic and pyyaml come from the running interpreter's site; the wheel
    # itself is the only l9_graphite_memory on the path.
    env["PYTHONPATH"] = str(site)
    env.update(
        {
            "HOME": str(data / "home"),
            "L9_MEMORY_DATA_DIR": str(data / "data"),
            "L9_MEMORY_STATE_DIR": str(data / "state"),
            "L9_MEMORY_NAMESPACE": "repo-a",
            "L9_MEMORY_PROJECTION_BACKEND": "none",
            "L9_MEMORY_JSON_LOGS": "0",
        }
    )
    return env


def _run(env: dict[str, str], cwd: Path, *argv: str, stdin: str | None = None):
    result = subprocess.run(
        [sys.executable, "-m", "l9_graphite_memory.cli", *argv],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=env,
        input=stdin,
    )
    payload = json.loads(result.stdout) if result.stdout.strip() else None
    return result.returncode, payload, result.stderr


def test_installed_wheel_is_the_module_that_runs(installed_site: Path, tmp_path: Path) -> None:
    env = _env(installed_site, tmp_path)
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import l9_graphite_memory, sys; print(l9_graphite_memory.__file__)",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
        env=env,
    )
    assert probe.stdout.strip().startswith(str(installed_site))


def test_installed_wheel_runs_the_consumer_lifecycle(installed_site: Path, tmp_path: Path) -> None:
    env = _env(installed_site, tmp_path)
    cwd = tmp_path / "workspace"
    cwd.mkdir()

    code, capabilities, _ = _run(env, cwd, "capabilities")
    assert code == 0
    assert capabilities["contract_version"] == "memory-control-plane/v1"
    cli_ops = next(
        item["operations"] for item in capabilities["transports"] if item["transport"] == "cli"
    )
    assert {"close", "hydrate", "ingest_governed_candidate", "capabilities"} <= set(cli_ops)

    code, health, _ = _run(env, cwd, "health")
    assert code == 0 and health["status"] == "complete"
    assert health["projection"]["name"] == "none"
    assert health["package_version"] == capabilities["package_version"]

    candidate = FIXTURE.read_text(encoding="utf-8")
    code, admitted, stderr = _run(env, cwd, "ingest-governed-candidate", stdin=candidate)
    assert code == 0, stderr
    assert admitted["status"] == "admitted" and admitted["record_id"]
    code, replayed, _ = _run(env, cwd, "ingest-governed-candidate", stdin=candidate)
    assert code == 0 and replayed["status"] == "duplicate"
    assert replayed["record_id"] == admitted["record_id"]

    code, hydrated, _ = _run(
        env, cwd, "hydrate", "resume", "--group-id", "repo-a", "--tag", "session_continuation"
    )
    assert code == 0
    record_ids = {rid for section in hydrated["sections"] for rid in section["record_ids"]}
    assert record_ids == {admitted["record_id"]}

    code, found, _ = _run(
        env, cwd, "search", "anything", "--group-id", "repo-a", "--tag", "session_continuation"
    )
    assert code == 0 and len(found["hits"]) == 1
    payload = found["hits"][0]["record"]["metadata"]["structured_payload"]
    assert payload["schema"] == "cursor.continuation/v2"

    close_args = ("close", "--summary", "installed wheel close", "--group-id", "repo-a")
    code, dry, _ = _run(env, cwd, *close_args, "--dry-run")
    assert code == 3 and dry["status"] == "partial"
    code, first, _ = _run(env, cwd, *close_args, "--idempotency-key", "wheel-close-1")
    assert code == 0 and first["status"] == "complete" and first["replayed"] is False
    code, second, _ = _run(env, cwd, *close_args, "--idempotency-key", "wheel-close-1")
    assert code == 0 and second["replayed"] is True
    assert second["record_id"] == first["record_id"]


def test_installed_wheel_cursor_client_lifecycle_proves_installed_entry(
    installed_site: Path, tmp_path: Path
) -> None:
    env = _env(installed_site, tmp_path)
    cwd = tmp_path / "workspace"
    cwd.mkdir()
    config = tmp_path / "home" / ".cursor" / "mcp.json"

    code, installed, _ = _run(env, cwd, "client", "cursor", "install", "--path", str(config))
    assert code == 0 and installed["status"] == "complete"
    written = json.loads(config.read_text(encoding="utf-8"))
    entry = written["mcpServers"]["l9-graphite-memory"]
    assert "env" not in entry and entry["args"][-2:] == ["--transport", "stdio"]

    code, verified, stderr = _run(
        env, cwd, "client", "cursor", "verify", "--path", str(config), "--timeout", "90"
    )
    assert code == 0, stderr
    assert verified["status"] == "complete"
    assert verified["argv_source"] == "installed"
    assert verified["config_path"] == str(config)
    assert list(verified["command_argv"]) == [entry["command"], *entry["args"]]
    assert verified["health_status"] in {"complete", "partial"}
