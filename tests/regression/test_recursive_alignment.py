# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/regression/test_recursive_alignment.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

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
    banned = "Packet" + "Envelope"
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(
            part in {"validation", "dist", "build", "__pycache__"} for part in path.parts
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if banned in text:
            findings.append(path.relative_to(ROOT).as_posix())
    assert findings == []


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
