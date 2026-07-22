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
    module = _load(
        "layer_boundary_check", ROOT / "tools/assurance/check_layer_boundaries.py"
    )
    assert module.scan(ROOT) == ()


def test_deprecated_inter_node_envelope_name_is_absent() -> None:
    banned = "Packet" + "Envelope"
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(
            part in {"validation", "dist", "build", "__pycache__"}
            for part in path.parts
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if banned in text:
            findings.append(path.relative_to(ROOT).as_posix())
    assert findings == []
