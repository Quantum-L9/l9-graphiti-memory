"""ADR-100: hosted Memory stdio and signed-agent provisions are superseded.

The decision record points at the five predecessors, and each predecessor
points back. This test does not claim the old doors are unreachable.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADR = ROOT / "docs" / "adr"
SUCCESSOR = ADR / "ADR-100-native-oauth-mcp-full-cutover.md"
PREDECESSORS = (
    "ADR-038-sdk-mcp-cli-and-http-surface.md",
    "ADR-064-cursor-client-instantiation-and-proof-boundary.md",
    "ADR-082-consumer-control-plane-transport-parity.md",
    "ADR-083-server-side-local-authorization-and-one-class-vocabulary.md",
    "ADR-098-remote-mcp-transport-and-signed-agent-http-identity.md",
)


def _supersession_section(text: str) -> str:
    marker = "## Supersedes / Superseded By"
    start = text.index(marker)
    rest = text[start + len(marker) :]
    nxt = rest.find("\n## ")
    return rest if nxt < 0 else rest[:nxt]


def test_successor_names_each_predecessor_and_keeps_agents_invariants() -> None:
    text = SUCCESSOR.read_text(encoding="utf-8")
    assert text.startswith("# ADR-100:")
    section = _supersession_section(text)
    for name in PREDECESSORS:
        assert name[:7] in section
    assert "AGENTS.md" in text
    assert "invariants 1 through 10 are unchanged" in text
    assert "does not contain that receipt" in text
    assert "Quantum-L9/.github" in text


def test_predecessors_point_at_adr_100_without_losing_original_status() -> None:
    for name in PREDECESSORS:
        text = (ADR / name).read_text(encoding="utf-8")
        assert "ADR-100 (2026-10-27)" in _supersession_section(text)
        status = text.split("## Context", 1)[0]
        assert "Accepted" in status
        assert "ADR-100" in status


def test_index_lists_adr_100() -> None:
    index = (ADR / "README.md").read_text(encoding="utf-8")
    assert "ADR-100-native-oauth-mcp-full-cutover.md" in index
    assert "ADR-001 through ADR-100" in index


def test_adr_ledger_validates_through_100() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "assurance" / "validate_adrs.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "PASS: 100 ADRs complete and indexed" in completed.stdout
