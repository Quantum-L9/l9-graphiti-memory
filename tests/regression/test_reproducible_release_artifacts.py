"""The release artifact set is byte-reproducible and built by one recipe.

ADR-094 admits a release by the sha256 of its wheel and sdist, recorded before
the tag and compared with what the release workflows build from it. That only
works when every sanctioned build of one commit and SOURCE_DATE_EPOCH yields
the same bytes. setuptools alone does not: its sdist carries checkout mtimes,
umask-dependent modes, pax time records and build-time stamps on generated
members, and its wheel carries umask-dependent modes. The one entry point,
``scripts/build_release_artifacts.sh``, builds and then canonicalizes through
``tools/assurance/reproducible_artifacts.py``. These tests prove the canonical
form (unit), prove the real recipe reproduces across checkout time and umask
(end to end), and pin the workflows to that one recipe (contract).
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ENTRY_POINT = "scripts/build_release_artifacts.sh"
EPOCH = 1784592000
PUBLISH = ROOT / ".github" / "workflows" / "publish.yml"
RELEASE_CONTAINER = ROOT / ".github" / "workflows" / "release-container.yml"
VALIDATOR = ROOT / "scripts" / "validate_release.sh"


def _load_tool() -> ModuleType:
    path = ROOT / "tools" / "assurance" / "reproducible_artifacts.py"
    spec = importlib.util.spec_from_file_location("reproducible_artifacts", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ra = _load_tool()


# --- synthetic archives carrying setuptools' nondeterminism -------------------

_SDIST_MEMBERS = {
    "pkg-1.0/PKG-INFO": (b"Metadata-Version: 2.4\nName: pkg\n", False),
    "pkg-1.0/run.sh": (b"#!/bin/sh\necho hi\n", True),
    "pkg-1.0/src/pkg/__init__.py": (b"VALUE = 1\n", False),
    "pkg-1.0/setup.cfg": (b"[egg_info]\ntag_build = \n", False),
}


def _sdist(*, mtime: float, umask: int, order: list[str], gz_name: str, gz_mtime: int) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        top = tarfile.TarInfo("pkg-1.0")
        top.type = tarfile.DIRTYPE
        top.mode = 0o777 & ~umask
        top.mtime = mtime  # type: ignore[assignment]  # float -> pax mtime record
        top.uname = top.gname = "builder"
        tar.addfile(top)
        for name in order:
            payload, executable = _SDIST_MEMBERS[name]
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = (0o777 if executable else 0o666) & ~umask
            info.mtime = mtime + 0.25  # type: ignore[assignment]
            info.uid = info.gid = 1000
            info.uname = info.gname = "builder"
            tar.addfile(info, io.BytesIO(payload))
    out = io.BytesIO()
    with gzip.GzipFile(
        filename=gz_name, mode="wb", fileobj=out, mtime=gz_mtime, compresslevel=6
    ) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


_WHEEL_ENTRIES = [
    ("pkg/__init__.py", b"VALUE = 1\n", False),
    ("pkg/tool.py", b"#!/usr/bin/env python\n", True),
    ("pkg-1.0.dist-info/RECORD", b"pkg/__init__.py,,\n", False),
]


def _wheel(*, umask: int, date_time: tuple[int, int, int, int, int, int]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, payload, executable in _WHEEL_ENTRIES:
            info = zipfile.ZipInfo(name, date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100000 | ((0o777 if executable else 0o666) & ~umask)) << 16
            zf.writestr(info, payload)
    return out.getvalue()


def _first() -> bytes:
    return _sdist(
        mtime=1_700_000_000.5,
        umask=0o022,
        order=sorted(_SDIST_MEMBERS),
        gz_name="a.tar",
        gz_mtime=111,
    )


def _second() -> bytes:
    return _sdist(
        mtime=1_800_000_000.75,
        umask=0o002,
        order=sorted(_SDIST_MEMBERS, reverse=True),
        gz_name="other.tar",
        gz_mtime=222,
    )


def test_sdists_differing_only_in_build_metadata_canonicalize_identically() -> None:
    a, b = _first(), _second()
    assert a != b
    assert ra.canonical_sdist(a, EPOCH) == ra.canonical_sdist(b, EPOCH)


def test_canonical_sdist_shape_and_content() -> None:
    original = _second()
    canonical = ra.canonical_sdist(original, EPOCH)
    assert canonical[3] & 0x08 == 0, "gzip header names a file"
    assert int.from_bytes(canonical[4:8], "little") == 0, "gzip header carries a time"
    with tarfile.open(fileobj=io.BytesIO(canonical), mode="r:gz") as tar:
        members = tar.getmembers()
        assert not tar.pax_headers
        assert [m.name for m in members] == sorted(m.name for m in members)
        by_name = {m.name: m for m in members}
        for member in members:
            assert member.mtime == EPOCH
            assert (member.uid, member.gid, member.uname, member.gname) == (0, 0, "", "")
            assert not {"mtime", "atime", "ctime"} & set(member.pax_headers)
        assert by_name["pkg-1.0"].mode == 0o755
        assert by_name["pkg-1.0/run.sh"].mode == 0o755
        assert by_name["pkg-1.0/PKG-INFO"].mode == 0o644
        for name, (payload, _) in _SDIST_MEMBERS.items():
            extracted = tar.extractfile(by_name[name])
            assert extracted is not None and extracted.read() == payload
    # Content (member set, types, executable bits, bytes) is exactly the build's.
    assert ra._sdist_content(canonical) == ra._sdist_content(original)
    # The canonical form is a fixed point.
    assert ra.canonical_sdist(canonical, EPOCH) == canonical


def test_wheels_differing_only_in_umask_and_time_canonicalize_identically() -> None:
    a = _wheel(umask=0o022, date_time=(2026, 1, 1, 0, 0, 0))
    b = _wheel(umask=0o002, date_time=(2027, 6, 1, 12, 0, 0))
    assert a != b
    ca, cb = ra.canonical_wheel(a, EPOCH), ra.canonical_wheel(b, EPOCH)
    assert ca == cb
    with zipfile.ZipFile(io.BytesIO(ca)) as zf:
        infos = zf.infolist()
        # Entry order is kept, so RECORD stays last; contents are unchanged.
        assert [i.filename for i in infos] == [name for name, _, _ in _WHEEL_ENTRIES]
        modes = {i.filename: i.external_attr >> 16 for i in infos}
        assert modes["pkg/tool.py"] == 0o100755
        assert modes["pkg/__init__.py"] == 0o100644
        assert all(zf.read(name) == payload for name, payload, _ in _WHEEL_ENTRIES)
        assert zf.testzip() is None
    assert ra.canonical_wheel(ca, EPOCH) == ca


@pytest.mark.parametrize("value", [None, "", "  ", "17.5", "-1", "soon", "100"])
def test_source_date_epoch_fails_closed(value: str | None) -> None:
    with pytest.raises(ra.ReproducibilityError):
        ra.source_date_epoch(value)


def test_check_reports_non_canonical_and_canonicalize_fixes_the_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pkg-1.0.tar.gz").write_bytes(_second())
    (tmp_path / "pkg-1.0-py3-none-any.whl").write_bytes(
        _wheel(umask=0o002, date_time=(2027, 1, 1, 0, 0, 0))
    )
    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(EPOCH))
    assert ra.main(["check", str(tmp_path)]) == 1
    assert ra.main(["canonicalize", str(tmp_path)]) == 0
    assert ra.main(["check", str(tmp_path)]) == 0
    monkeypatch.delenv("SOURCE_DATE_EPOCH")
    assert ra.main(["check", str(tmp_path)]) == 1


def test_canonicalize_refuses_an_unexpected_artifact_set(tmp_path: Path) -> None:
    (tmp_path / "pkg-1.0.tar.gz").write_bytes(_first())
    with pytest.raises(ra.ReproducibilityError, match="exactly one wheel and one sdist"):
        ra.canonicalize(tmp_path, EPOCH)


# --- the real recipe reproduces across checkout time and umask ----------------


def _tracked_files() -> list[str]:
    listed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"], check=True, capture_output=True
    ).stdout
    return [name for name in listed.decode().split("\0") if name and (ROOT / name).is_file()]


def _copy_tree(dest: Path, files: list[str], *, umask: int, mtime: int) -> None:
    """Copy the tracked tree as a fresh checkout under ``umask`` at ``mtime`` would."""
    for name in files:
        source = ROOT / name
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        executable = bool(source.stat().st_mode & 0o111)
        os.chmod(target, (0o777 if executable else 0o666) & ~umask)
        os.utime(target, (mtime, mtime))
    for directory in sorted({p for p in dest.rglob("*") if p.is_dir()}, reverse=True):
        os.chmod(directory, 0o777 & ~umask)
        os.utime(directory, (mtime, mtime))


def _build(tree: Path, out: Path, umask: int) -> dict[str, str]:
    env = {**os.environ, "SOURCE_DATE_EPOCH": str(EPOCH), "PYTHON": sys.executable}
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'umask {umask:03o} && exec bash "$0" "$1"',
            str(tree / ENTRY_POINT),
            str(out),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-4000:]
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir())}


def test_entry_point_builds_identical_bytes_across_checkout_time_and_umask(tmp_path: Path) -> None:
    files = _tracked_files()
    first, second = tmp_path / "first", tmp_path / "second"
    _copy_tree(first, files, umask=0o022, mtime=1_767_225_600)
    _copy_tree(second, files, umask=0o002, mtime=1_798_761_600)
    digests_first = _build(first, tmp_path / "dist-first", 0o022)
    digests_second = _build(second, tmp_path / "dist-second", 0o002)
    assert len(digests_first) == 2
    assert {n for n in digests_first if n.endswith(".whl")} and {
        n for n in digests_first if n.endswith(".tar.gz")
    }
    assert digests_first == digests_second


def test_entry_point_fails_closed_without_a_source_date_epoch(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k != "SOURCE_DATE_EPOCH"}
    for value in (None, "tomorrow"):
        if value is not None:
            env["SOURCE_DATE_EPOCH"] = value
        result = subprocess.run(
            ["bash", str(ROOT / ENTRY_POINT), str(tmp_path / "dist")],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "SOURCE_DATE_EPOCH" in result.stderr
        assert not (tmp_path / "dist").exists()


# --- every build site uses the one recipe -------------------------------------

_DIRECT_BUILD = re.compile(r"-m\s+build\b|\buv\s+build\b|\bpip\s+wheel\b|setup\.py\s+(sdist|bdist)")


def _runs(path: Path) -> list[str]:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        str(step.get("run", ""))
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    ]


def _validator_lines() -> list[str]:
    return [
        line
        for line in VALIDATOR.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


@pytest.mark.parametrize("workflow", [PUBLISH, RELEASE_CONTAINER], ids=lambda p: p.name)
def test_release_workflow_builds_only_through_the_entry_point(workflow: Path) -> None:
    runs = _runs(workflow)
    assert sum(ENTRY_POINT in run for run in runs) == 1
    assert not [run for run in runs if _DIRECT_BUILD.search(run)]


def test_release_validation_builds_only_through_the_entry_point() -> None:
    lines = _validator_lines()
    assert sum(ENTRY_POINT in line for line in lines) == 1
    assert not [line for line in lines if _DIRECT_BUILD.search(line)]


def test_entry_point_is_the_only_direct_build() -> None:
    script = (ROOT / ENTRY_POINT).read_text(encoding="utf-8")
    commands = [
        line for line in script.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]
    assert sum(bool(_DIRECT_BUILD.search(line)) for line in commands) == 1
    assert any('reproducible_artifacts.py" canonicalize' in line for line in commands)
    assert any('reproducible_artifacts.py" check' in line for line in commands)


def _setup_python(path: Path, job: str) -> str:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    versions = {
        str(step["with"]["python-version"])
        for step in workflow["jobs"][job]["steps"]
        if str(step.get("uses", "")).startswith("astral-sh/setup-uv@")
    }
    assert len(versions) == 1, versions
    return versions.pop()


def test_both_release_builds_pin_the_same_python_and_epoch() -> None:
    assert _setup_python(PUBLISH, "validate-and-publish") == _setup_python(
        RELEASE_CONTAINER, "admission"
    )
    publish_env = yaml.safe_load(PUBLISH.read_text(encoding="utf-8"))["jobs"][
        "validate-and-publish"
    ]["env"]
    admission_env = yaml.safe_load(RELEASE_CONTAINER.read_text(encoding="utf-8"))["jobs"][
        "admission"
    ]["env"]
    assert publish_env["SOURCE_DATE_EPOCH"] == admission_env["SOURCE_DATE_EPOCH"] == str(EPOCH)
    assert f'SOURCE_DATE_EPOCH="${{SOURCE_DATE_EPOCH:-{EPOCH}}}"' in VALIDATOR.read_text(
        encoding="utf-8"
    )


def test_build_backend_is_pinned_exactly() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"^requires = \[(.*)\]$", pyproject, flags=re.MULTILINE)
    assert match is not None
    requirements = [r.strip().strip('"') for r in match.group(1).split(",") if r.strip()]
    assert requirements and all(
        re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]*", r) for r in requirements
    )
