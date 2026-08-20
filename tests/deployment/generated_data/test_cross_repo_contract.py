# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/generated_data/test_cross_repo_contract.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEPLOYMENT = ROOT / "deployment" / "generated-data"
VERIFIER = DEPLOYMENT / "verify_cross_repo_contract.py"


def locate_cursor() -> Path | None:
    candidates = [
        os.environ.get("CURSOR_GOVERNANCE_ROOT"),
        ROOT.parent / "Cursor-Governance",
        ROOT.parent / "cursor-governance",
        ROOT.parent.parent / "Cursor-Governance",
        ROOT.parent.parent / "cursor-governance",
    ]

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).resolve()
        if (
            path
            / "environment/agents/generated-data"
            / "adapters"
            / "graphiti_memory.py"
        ).is_file():
            return path
    return None


class CrossRepositoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cursor = locate_cursor()
        if cls.cursor is None:
            raise unittest.SkipTest(
                "Cursor-Governance checkout unavailable"
            )

    def test_actual_producer_contract_is_compatible(
        self,
    ) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(VERIFIER),
                "--cursor-root",
                str(self.cursor),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr or completed.stdout,
        )

        result = json.loads(completed.stdout)
        self.assertTrue(result["compatible"])
        self.assertFalse(result["differences"])
        self.assertNotEqual(
            result["cursor_governance_sha"],
            "unknown",
        )
        self.assertNotEqual(
            result["graphiti_sha"],
            "unknown",
        )

    def test_all_producer_files_are_hashed(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(VERIFIER),
                "--cursor-root",
                str(self.cursor),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        result = json.loads(completed.stdout)

        self.assertEqual(
            set(result["producer_files"]),
            {
                "candidate",
                "query",
                "reuse",
                "invalidation",
            },
        )

        for value in result["producer_files"].values():
            self.assertEqual(
                len(value["sha256"]),
                64,
            )

    def test_fixtures_use_supported_values(self) -> None:
        manifest = __import__("yaml").safe_load(
            (
                DEPLOYMENT / "capability-manifest.yaml"
            ).read_text(encoding="utf-8")
        )
        candidate = json.loads(
            (
                DEPLOYMENT
                / "fixtures"
                / "governed-candidate.json"
            ).read_text(encoding="utf-8")
        )
        reuse = json.loads(
            (
                DEPLOYMENT
                / "fixtures"
                / "reuse-event.json"
            ).read_text(encoding="utf-8")
        )
        invalidation = json.loads(
            (
                DEPLOYMENT
                / "fixtures"
                / "path-invalidation.json"
            ).read_text(encoding="utf-8")
        )

        self.assertIn(
            candidate["knowledge"]["primary_class"],
            manifest["candidate_ingress"][
                "supported_classes"
            ],
        )
        self.assertIn(
            reuse["outcome"],
            manifest["reuse"]["supported_outcomes"],
        )
        self.assertIn(
            invalidation["event_type"],
            manifest["invalidation"][
                "supported_event_types"
            ],
        )

    def test_candidate_preserves_advisory_boundary(
        self,
    ) -> None:
        candidate = json.loads(
            (
                DEPLOYMENT
                / "fixtures"
                / "governed-candidate.json"
            ).read_text(encoding="utf-8")
        )
        governance = candidate["governance"]
        self.assertEqual(
            governance["authority_class"],
            "advisory",
        )
        self.assertEqual(
            governance["route"],
            "memory",
        )
        self.assertEqual(
            governance["promotion_decision"],
            "promote",
        )
        self.assertFalse(
            governance[
                "may_override_repository_state"
            ]
        )
        self.assertFalse(
            governance[
                "may_override_canonical_authority"
            ]
        )


if __name__ == "__main__":
    unittest.main()
