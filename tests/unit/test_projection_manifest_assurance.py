# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_projection_manifest_assurance.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-26
from __future__ import annotations

import json
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_projection_schema_is_packaged_as_a_resource() -> None:
    schema = (
        files("l9_graphite_memory")
        .joinpath("resources")
        .joinpath("projections")
        .joinpath("schema.json")
    )
    assert schema.is_file()
    value = json.loads(schema.read_text(encoding="utf-8"))
    assert value["title"] == "L9 Projection Manifest"
    assert value["properties"]["api_version"]["const"] == ("memory.quantum-l9.dev/v1")


def test_projection_manifest_assurance_command_passes() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "tools/assurance/validate_projection_manifests.py",
            "config/projections/facts-v8.yaml",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["results"][0]["deterministic"] is True
