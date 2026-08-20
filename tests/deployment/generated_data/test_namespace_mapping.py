# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/generated_data/test_namespace_mapping.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
PATH = (
    ROOT
    / "deployment"
    / "generated-data"
    / "namespace-mapping.yaml"
)


def load_mapping() -> Mapping[str, Any]:
    value = yaml.safe_load(
        PATH.read_text(encoding="utf-8")
    )
    if not isinstance(value, Mapping):
        raise TypeError(
            "namespace-mapping root must be a mapping"
        )
    return value


def render_namespace(
    mapping: Mapping[str, Any],
    visibility: str,
    values: Mapping[str, str],
) -> str:
    visibility_map = mapping["visibility"]

    if visibility not in visibility_map:
        raise ValueError(
            f"Unknown visibility: {visibility}"
        )

    entry = visibility_map[visibility]
    for field in entry["required_fields"]:
        if not values.get(field):
            raise ValueError(
                f"Missing required field: {field}"
            )

    return str(entry["template"]).format(**values)


class NamespaceMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mapping = load_mapping()

    def test_campaign_mapping_is_deterministic(self) -> None:
        values = {"campaign_id": "campaign-001"}
        first = render_namespace(
            self.mapping,
            "campaign_local",
            values,
        )
        second = render_namespace(
            self.mapping,
            "campaign_local",
            values,
        )
        self.assertEqual(
            first,
            "campaign/campaign-001",
        )
        self.assertEqual(first, second)

    def test_repository_mapping_is_deterministic(
        self,
    ) -> None:
        result = render_namespace(
            self.mapping,
            "repository_local",
            {
                "repository": (
                    "Quantum-L9/l9-graphiti-memory"
                )
            },
        )
        self.assertEqual(
            result,
            (
                "repository/"
                "Quantum-L9/l9-graphiti-memory"
            ),
        )

    def test_required_fields_are_enforced(self) -> None:
        with self.assertRaises(ValueError):
            render_namespace(
                self.mapping,
                "repository_local",
                {},
            )

        with self.assertRaises(ValueError):
            render_namespace(
                self.mapping,
                "restricted",
                {},
            )

    def test_unknown_visibility_is_rejected(self) -> None:
        self.assertEqual(
            self.mapping["rules"][
                "unknown_visibility"
            ],
            "reject",
        )
        with self.assertRaises(ValueError):
            render_namespace(
                self.mapping,
                "public_internet",
                {},
            )

    def test_widening_is_forbidden(self) -> None:
        rules = self.mapping["rules"]
        self.assertTrue(
            rules["widening_forbidden"]
        )
        self.assertTrue(
            rules["narrowing_allowed"]
        )

    def test_cross_repository_search_not_implicit(
        self,
    ) -> None:
        self.assertFalse(
            self.mapping["rules"][
                "cross_repository_search_implicit"
            ]
        )

    def test_reuse_inherits_record_namespace(self) -> None:
        self.assertTrue(
            self.mapping["rules"][
                "reuse_inherits_record_namespace"
            ]
        )

    def test_invalidation_requires_all_authority(
        self,
    ) -> None:
        self.assertTrue(
            self.mapping["rules"][
                "invalidation_requires_all_"
                "matched_namespace_authority"
            ]
        )


if __name__ == "__main__":
    unittest.main()
