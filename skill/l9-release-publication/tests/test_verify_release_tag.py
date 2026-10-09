# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: skill/l9-release-publication/tests/test_verify_release_tag.py
#   layer: skill
#   owner: memory-control-plane
#   status: active
#   version: 2.6.0
#   updated: 2026-07-22

"""Identity checks for an annotated release tag."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_release_tag.py"


def _git(repo: Path, *args: str) -> str:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Release Test",
            "GIT_AUTHOR_EMAIL": "release-test@example.com",
            "GIT_COMMITTER_NAME": "Release Test",
            "GIT_COMMITTER_EMAIL": "release-test@example.com",
        }
    )
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout.strip()


def _repo(tmp: Path) -> tuple[Path, str, str]:
    repo = tmp / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "README").write_text("admitted\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "admit")
    commit = _git(repo, "rev-parse", "HEAD")
    _git(repo, "tag", "-a", "v1.2.3", "-m", "admitted tag")
    tag_object = _git(repo, "rev-parse", "v1.2.3")
    return repo, tag_object, commit


def _run(repo: Path, *extra: str, gh_bin: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if gh_bin is not None:
        env["PATH"] = str(gh_bin) + os.pathsep + env.get("PATH", "")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-dir", str(repo), "--tag", "v1.2.3", *extra],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_local_match(tmp_path: Path) -> None:
    repo, tag_object, commit = _repo(tmp_path)
    result = _run(repo, "--tag-object", tag_object, "--peeled-commit", commit)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "MATCH"
    assert payload["local_kind"] == "tag"


def test_local_mismatch_does_not_accept_a_different_peel(tmp_path: Path) -> None:
    repo, tag_object, _commit = _repo(tmp_path)
    result = _run(repo, "--tag-object", tag_object, "--peeled-commit", "0" * 40)
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "MISMATCH"


def test_lightweight_tag_is_not_annotated(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "README").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "admit")
    commit = _git(repo, "rev-parse", "HEAD")
    _git(repo, "tag", "v1.2.3")
    result = _run(repo, "--tag-object", commit, "--peeled-commit", commit)
    assert result.returncode == 1
    assert json.loads(result.stdout)["local_kind"] == "commit"


def test_remote_absent(tmp_path: Path) -> None:
    repo, tag_object, commit = _repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "gh"
    fake.write_text(
        "#!/bin/sh\necho 'gh: Not Found (HTTP 404)' >&2\nexit 1\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    result = _run(
        repo,
        "--tag-object",
        tag_object,
        "--peeled-commit",
        commit,
        "--remote",
        "example/repo",
        gh_bin=bin_dir,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "REMOTE_ABSENT"


def test_require_remote_rejects_absence(tmp_path: Path) -> None:
    repo, tag_object, commit = _repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "gh"
    fake.write_text(
        "#!/bin/sh\necho 'gh: Not Found (HTTP 404)' >&2\nexit 1\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    result = _run(
        repo,
        "--tag-object",
        tag_object,
        "--peeled-commit",
        commit,
        "--remote",
        "example/repo",
        "--require-remote",
        gh_bin=bin_dir,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "MISMATCH"


def test_remote_match(tmp_path: Path) -> None:
    repo, tag_object, commit = _repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "gh"
    fake.write_text(
        f"""#!/usr/bin/env python3
import sys
path = sys.argv[-1]
if path.endswith("/git/ref/tags/v1.2.3"):
    print('{{"object":{{"sha":"{tag_object}","type":"tag"}}}}')
elif path.endswith("/git/tags/{tag_object}"):
    print('{{"object":{{"sha":"{commit}","type":"commit"}}}}')
else:
    sys.stderr.write("unexpected path\\n")
    raise SystemExit(1)
""",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    result = _run(
        repo,
        "--tag-object",
        tag_object,
        "--peeled-commit",
        commit,
        "--remote",
        "example/repo",
        "--require-remote",
        gh_bin=bin_dir,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "MATCH"
    assert payload["remote_tag_object"] == tag_object
    assert payload["remote_peeled"] == commit
