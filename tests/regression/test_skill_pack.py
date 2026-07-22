# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/regression/test_skill_pack.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_skill_entrypoint_and_ui_metadata_are_valid() -> None:
    skill = ROOT / "skill" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    assert match is not None
    frontmatter = yaml.safe_load(match.group(1))
    assert set(frontmatter) == {"name", "description"}
    assert re.fullmatch(r"[a-z0-9-]+", frontmatter["name"])
    assert 1 <= len(frontmatter["description"]) <= 1024

    metadata = yaml.safe_load(
        (ROOT / "skill" / "agents" / "openai.yaml").read_text(encoding="utf-8")
    )
    assert metadata["interface"]["display_name"]
    assert metadata["interface"]["short_description"]
