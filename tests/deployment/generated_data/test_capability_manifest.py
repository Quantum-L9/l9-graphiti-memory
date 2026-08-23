# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/generated_data/test_capability_manifest.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import json
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
DEPLOYMENT = ROOT / "deployment" / "generated-data"


def load_yaml(name: str) -> Mapping[str, Any]:
    value = yaml.safe_load((DEPLOYMENT / name).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} root must be a mapping")
    return value


class CapabilityManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = load_yaml("capability-manifest.yaml")

    def test_manifest_identity_and_version(self) -> None:
        self.assertEqual(
            self.manifest["schema_version"],
            "1.0.0",
        )
        self.assertEqual(
            self.manifest["integration"],
            "cursor_governance_generated_data",
        )
        self.assertIs(
            self.manifest["enabled"],
            True,
        )

    def test_supported_classes_are_exact(self) -> None:
        expected = {
            "repository_fact",
            "dependency_finding",
            "implementation_surface",
            "rejected_approach",
            "context_requirement",
            "artifact_lineage",
        }
        actual = set(self.manifest["candidate_ingress"]["supported_classes"])
        self.assertEqual(actual, expected)

    def test_supported_and_rejected_classes_do_not_overlap(
        self,
    ) -> None:
        ingress = self.manifest["candidate_ingress"]
        supported = set(ingress["supported_classes"])
        rejected = set(ingress["rejected_classes"])
        self.assertFalse(
            supported & rejected,
            supported & rejected,
        )

    def test_governance_boundary_is_fail_closed(self) -> None:
        ingress = self.manifest["candidate_ingress"]
        self.assertEqual(
            ingress["authority_class"],
            "advisory",
        )
        self.assertEqual(
            ingress["route"],
            "memory",
        )
        self.assertEqual(
            ingress["required_promotion_decision"],
            "promote",
        )
        self.assertFalse(ingress["may_override_repository_state"])
        self.assertFalse(ingress["may_override_canonical_authority"])

    def test_invalidation_never_deletes(self) -> None:
        invalidation = self.manifest["invalidation"]
        self.assertFalse(invalidation["deletes_memory"])
        self.assertFalse(invalidation["creates_replacement_record"])
        self.assertTrue(invalidation["requires_structured_selectors"])
        self.assertTrue(invalidation["natural_language_matching_forbidden"])

    def test_reuse_requires_finalized_outcome(self) -> None:
        reuse = self.manifest["reuse"]
        self.assertFalse(reuse["selection_is_proven_reuse"])
        self.assertFalse(reuse["injection_is_proven_reuse"])
        self.assertTrue(reuse["finalized_outcome_is_proven_reuse"])

    def test_projection_is_not_canonical_requirement(self) -> None:
        storage = self.manifest["canonical_storage"]
        self.assertFalse(storage["projection_required"])
        self.assertTrue(storage["direct_adapter_store_writes_forbidden"])

    def test_fixture_capability_response_agrees(
        self,
    ) -> None:
        response = json.loads(
            (DEPLOYMENT / "fixtures" / "capability-response.json").read_text(encoding="utf-8")
        )

        contracts = response["contracts"]
        manifest = self.manifest

        self.assertEqual(
            set(contracts["supported_classes"]),
            set(manifest["candidate_ingress"]["supported_classes"]),
        )
        self.assertEqual(
            set(contracts["supported_reuse_outcomes"]),
            set(manifest["reuse"]["supported_outcomes"]),
        )
        self.assertEqual(
            set(contracts["supported_invalidation_events"]),
            set(manifest["invalidation"]["supported_event_types"]),
        )

    def test_runtime_fixture_does_not_claim_mcp_readiness(
        self,
    ) -> None:
        response = json.loads(
            (DEPLOYMENT / "fixtures" / "capability-response.json").read_text(encoding="utf-8")
        )
        self.assertFalse(response["runtime"]["mcp_tool_plane_ready"])


if __name__ == "__main__":
    unittest.main()
