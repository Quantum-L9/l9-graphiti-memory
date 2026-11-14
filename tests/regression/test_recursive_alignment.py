# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/regression/test_recursive_alignment.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-11-13

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_recursive_alignment_has_no_violations() -> None:
    module = _load(
        "recursive_alignment_check",
        ROOT / "tools/assurance/check_recursive_alignment.py",
    )
    assert module.scan(ROOT) == ()


def test_layer_boundaries_have_no_violations() -> None:
    module = _load("layer_boundary_check", ROOT / "tools/assurance/check_layer_boundaries.py")
    assert module.scan(ROOT) == ()


def test_deprecated_inter_node_envelope_name_is_absent() -> None:
    """Independent of ``scan``: no repository file carries the banned name.

    The candidate set is the checker's own enumeration of this repository's
    files (``_repository_files``), not every byte under the checkout: a CI
    runner materializes tooling that is not this repository's -- Core injects
    its SDK source under ``.l9/runtime`` -- and judging it was a false
    failure, not coverage.
    """

    module = _load(
        "recursive_alignment_check_files",
        ROOT / "tools/assurance/check_recursive_alignment.py",
    )
    banned = "Packet" + "Envelope"
    findings: list[str] = []
    for path in module._repository_files(ROOT):
        if not path.is_file() or any(
            part in {"validation", "dist", "build", "__pycache__"}
            for part in path.relative_to(ROOT).parts
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if banned in text:
            findings.append(path.relative_to(ROOT).as_posix())
    assert findings == []


def _transport_paths(module, root: Path) -> list[str]:
    return sorted(
        item.path
        for item in module.scan(root)
        if item.rule == "transport" and item.evidence == "deprecated inter-node envelope reference"
    )


def _git(root: Path, *args: str) -> None:
    import subprocess

    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


_BANNED_LINE = "name = '" + "Packet" + "Envelope" + "'\n"


def test_injected_core_runtime_is_not_judged_in_a_work_tree(tmp_path: Path) -> None:
    """Regression (#120): Core's injected ``.l9/runtime`` SDK source failed the scan.

    On the Core runner the l9-ci SDK source is materialized under
    ``.l9/runtime/sdk/source`` and no ignore rule names it. It is not this
    repository's content and produces no finding, while the same text in a
    tracked file, an untracked new file, or a file the repository itself
    tracks under ``.l9/runtime`` still does.
    """

    module = _load(
        "check_recursive_alignment_runtime",
        ROOT / "tools" / "assurance" / "check_recursive_alignment.py",
    )
    _git(tmp_path, "init", "-q")
    injected = tmp_path / ".l9" / "runtime" / "sdk" / "source" / "l9_ci" / "baseline"
    injected.mkdir(parents=True)
    (injected / "packet_envelope.py").write_text(_BANNED_LINE, encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "tracked.py").write_text(_BANNED_LINE, encoding="utf-8")
    (tmp_path / "src" / "untracked.py").write_text(_BANNED_LINE, encoding="utf-8")
    owned = tmp_path / ".l9" / "runtime" / "owned.json"
    owned.write_text(_BANNED_LINE, encoding="utf-8")
    _git(tmp_path, "add", "src/tracked.py", ".l9/runtime/owned.json")

    assert _transport_paths(module, tmp_path) == [
        ".l9/runtime/owned.json",
        "src/tracked.py",
        "src/untracked.py",
    ]


def test_injected_core_runtime_is_not_judged_without_a_work_tree(tmp_path: Path) -> None:
    """The release-tarball case: no index, so the tree is walked, still
    pruning the injected ``.l9/runtime`` directory and nothing else."""

    module = _load(
        "check_recursive_alignment_runtime_walk",
        ROOT / "tools" / "assurance" / "check_recursive_alignment.py",
    )
    injected = tmp_path / ".l9" / "runtime" / "sdk" / "source"
    injected.mkdir(parents=True)
    (injected / "baseline.py").write_text(_BANNED_LINE, encoding="utf-8")
    (tmp_path / ".l9" / "repo-workflow.json").write_text(_BANNED_LINE, encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "module.py").write_text(_BANNED_LINE, encoding="utf-8")

    assert module._is_work_tree_root(tmp_path) is False
    assert _transport_paths(module, tmp_path) == [".l9/repo-workflow.json", "src/module.py"]


def test_text_file_walk_never_enters_an_excluded_directory(tmp_path: Path, monkeypatch) -> None:
    """Regression: the scan walked into ``.git`` and raced git's own gc.

    A merge can detach ``git gc --auto``, which removes ``.git/objects/<xx>``
    while the scan walks; Python 3.10's ``rglob`` then raised
    ``FileNotFoundError`` (test_manifest_retirement on #100). Here inspecting
    a path inside one object directory removes its sibling, as gc would. The
    reliable detector is the last assertion: a walk that enters an excluded
    directory inspects paths there (the old ``rglob`` walk did, on every
    Python), while a pruning walk inspects none and so cannot race.
    """

    import shutil

    module = _load(
        "check_recursive_alignment_walk",
        ROOT / "tools" / "assurance" / "check_recursive_alignment.py",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "kept.py").write_text("VALUE = 1\n", encoding="utf-8")
    objects = tmp_path / ".git" / "objects"
    for name in ("e0", "e1"):
        (objects / name).mkdir(parents=True)
        (objects / name / "loose").write_text("x\n", encoding="utf-8")
    for excluded in ("build/lib", "pkg.egg-info"):
        (tmp_path / excluded).mkdir(parents=True)
        (tmp_path / excluded / "inside.txt").write_text("x\n", encoding="utf-8")

    real_is_file = Path.is_file
    inspected: list[str] = []

    def is_file(self: Path) -> bool:
        inspected.append(self.as_posix())
        for mine, sibling in (("e0", "e1"), ("e1", "e0")):
            if f"/.git/objects/{mine}" in self.as_posix():
                shutil.rmtree(objects / sibling, ignore_errors=True)
        return real_is_file(self)

    monkeypatch.setattr(Path, "is_file", is_file)
    files = module._text_files(tmp_path)

    assert [path.relative_to(tmp_path).as_posix() for path in files] == ["src/kept.py"]
    assert not [path for path in inspected if "/.git/" in path or "/build/" in path]
