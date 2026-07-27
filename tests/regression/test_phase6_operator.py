# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/regression/test_phase6_operator.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-27
"""Regression wiring for the vendored l9-deploy Phase 6 operator pack.

Executes the pack's own validation surfaces from ``tools/phase6`` so the
pack stays functional, not decorative: the exact-state pack validator,
the internal checksum manifest, and the 19-test adversarial hardening
suite all run in every CI push.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "tools" / "phase6"

pytest.importorskip("cryptography")
pytest.importorskip("jsonschema")
pytest.importorskip("jwt")


def test_pack_checksum_manifest_verifies() -> None:
    manifest = PACK / "MANIFEST.sha256"
    assert manifest.is_file()
    checked = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, relative = line.partition("  ")
        target = PACK / relative.strip()
        assert target.is_file(), f"missing pack file: {relative}"
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        assert actual == digest.strip(), f"checksum mismatch: {relative}"
        checked += 1
    assert checked == 72


def test_pack_exact_state_validator_passes() -> None:
    for cache_dir in PACK.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)
    result = subprocess.run(
        [sys.executable, str(PACK / "scripts" / "validate_pack.py"), str(PACK)],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS", payload["errors"]
    assert payload["file_count"] == 73
    assert result.returncode == 0


def test_pack_adversarial_hardening_suite_passes() -> None:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(PACK / "tests" / "test_hardening.py"),
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert "19 passed" in result.stdout
