from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any, Mapping

import yaml


ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = (
    ROOT
    / "deployment"
    / "generated-data"
    / "principal-policy.yaml"
)


def load_policy() -> Mapping[str, Any]:
    value = yaml.safe_load(
        POLICY_PATH.read_text(encoding="utf-8")
    )
    if not isinstance(value, Mapping):
        raise AssertionError(
            "principal-policy root must be a mapping"
        )
    return value


class PrincipalPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy()

    def test_dedicated_service_principal(self) -> None:
        principal = self.policy["principal"]
        self.assertEqual(
            principal["id"],
            "cursor-governance-generated-data",
        )
        self.assertEqual(
            principal["type"],
            "service",
        )

    def test_minimum_required_permissions(self) -> None:
        permissions = set(self.policy["permissions"])
        self.assertEqual(
            permissions,
            {
                "memory.candidate.ingest",
                "memory.search",
                "memory.hydrate",
                "memory.reuse.record",
                "memory.source.invalidate",
                "memory.capabilities.read",
            },
        )

    def test_subagents_are_provenance_not_callers(
        self,
    ) -> None:
        producer = self.policy["producer_identity"]
        self.assertEqual(
            producer["authenticated_caller"],
            "cursor-governance-generated-data",
        )
        fields = set(
            producer["stored_as_provenance"]
        )
        self.assertTrue(
            {
                "campaign_id",
                "graph_id",
                "action_id",
                "agent_id",
                "role",
                "lease_id",
                "packet_id",
            }
            <= fields
        )

    def test_dangerous_authority_is_denied(self) -> None:
        constraints = self.policy["constraints"]
        self.assertFalse(
            constraints[
                "direct_subagent_canonical_write"
            ]
        )
        self.assertFalse(
            constraints[
                "may_override_repository_state"
            ]
        )
        self.assertFalse(
            constraints[
                "may_override_canonical_authority"
            ]
        )
        self.assertFalse(
            constraints["may_promote_memory"]
        )
        self.assertFalse(
            constraints["may_delete_memory"]
        )
        self.assertFalse(
            constraints["may_widen_visibility"]
        )

    def test_denied_operations_are_explicit(self) -> None:
        denied = set(self.policy["denied_operations"])
        self.assertEqual(
            denied,
            {
                "memory.delete",
                "memory.promote",
                "memory.policy.override",
                "memory.namespace.widen",
            },
        )

    def test_invalidation_requires_namespace_authority(
        self,
    ) -> None:
        self.assertTrue(
            self.policy["constraints"][
                "invalidation_requires_namespace_authority"
            ]
        )


if __name__ == "__main__":
    unittest.main()
