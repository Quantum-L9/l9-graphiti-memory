# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/generated_data/test_runtime_status_protocol.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from l9_graphite_memory.contracts.generated_data import (
    GovernedMemoryCandidate,
    MemoryCandidateIngestionStatus,
)
from l9_graphite_memory.services.generated_data import GeneratedDataService

ROOT = Path(__file__).resolve().parents[3]


BASE_SHA = "a" * 40


def candidate_payload() -> dict:
    return {
        "schema_version": "1.0.0",
        "kind": "MemoryCandidate",
        "candidate_id": "candidate-001",
        "source": {
            "repository": "Quantum-L9/example",
            "base_sha": BASE_SHA,
            "freshness_sha": BASE_SHA,
            "visibility": "repository_local",
        },
        "knowledge": {
            "primary_class": "repository_fact",
            "statement": "A governed fact.",
            "confidence": 0.99,
            "freshness": {"base_sha": BASE_SHA},
            "scope": {"paths": ["src"]},
            "epistemic_status": "observed",
            "invalidation_conditions": [
                {"condition_type": "relevant_path_changed", "selector": "src"}
            ],
        },
        "governance": {
            "authority_class": "advisory",
            "route": "memory",
            "promotion_decision": "promote",
            "visibility": "repository_local",
            "may_override_repository_state": False,
            "may_override_canonical_authority": False,
        },
        "provenance": {"source_agent_id": "agent-001"},
    }


class FakeMemory:
    def __init__(self, status: str) -> None:
        self.status = status
        self.last_request = None

    def write(self, principal, request):
        self.last_request = request
        return SimpleNamespace(
            status=SimpleNamespace(value=self.status),
            record_id=uuid4() if self.status != "rejected" else None,
            receipt_id=uuid4(),
        )


class RuntimeStatusProtocolTests(unittest.TestCase):
    def test_statuses_preserve_admission_truth(self) -> None:
        cases = {
            "admitted": MemoryCandidateIngestionStatus.ADMITTED,
            "duplicate": MemoryCandidateIngestionStatus.DUPLICATE,
            "quarantined": MemoryCandidateIngestionStatus.QUARANTINED,
            "rejected": MemoryCandidateIngestionStatus.REJECTED,
        }
        principal = SimpleNamespace(agent_id="agent-001")
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                memory = FakeMemory(raw)
                result = GeneratedDataService(memory).ingest_governed_candidate(
                    principal, candidate_payload()
                )
                self.assertEqual(result.status, expected)
                self.assertEqual(result.storage_committed, raw != "rejected")
                if raw == "quarantined":
                    self.assertEqual(result.memory_state, "quarantined")
                if raw == "duplicate":
                    self.assertEqual(result.memory_state, "existing")

    def test_repository_visibility_resolves_exact_namespace(self) -> None:
        candidate = GovernedMemoryCandidate.model_validate(candidate_payload())
        self.assertEqual(candidate.namespace(), "repository/Quantum-L9/example")

    def test_missing_campaign_identifier_is_rejected(self) -> None:
        payload = candidate_payload()
        payload["source"]["visibility"] = "campaign_local"
        payload["governance"]["visibility"] = "campaign_local"
        candidate = GovernedMemoryCandidate.model_validate(payload)
        with self.assertRaises(ValueError):
            candidate.namespace()

    def test_cursor_adapter_accepts_every_downstream_terminal_status(self) -> None:
        cursor_value = os.environ.get("CURSOR_GOVERNANCE_ROOT")
        if not cursor_value:
            self.skipTest("CURSOR_GOVERNANCE_ROOT is not configured")
        cursor = Path(cursor_value).expanduser().resolve()
        adapter_path = cursor / "environment/agents/generated-data/adapters/graphiti_memory.py"
        if not adapter_path.is_file():
            self.fail(f"Cursor adapter missing: {adapter_path}")
        spec = importlib.util.spec_from_file_location("cross_repo_graphiti_adapter", adapter_path)
        if spec is None or spec.loader is None:
            self.fail(f"cannot load {adapter_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["cross_repo_graphiti_adapter"] = module
        spec.loader.exec_module(module)
        downstream = {item.value for item in MemoryCandidateIngestionStatus}
        accepted_by_cursor = set(module.GraphitiMemoryAdapter.TERMINAL_STATUSES) | set(
            module.GraphitiMemoryAdapter.STATUS_ALIASES
        )
        self.assertTrue(
            downstream.issubset(accepted_by_cursor),
            downstream - accepted_by_cursor,
        )
        self.assertEqual(
            module.GraphitiMemoryAdapter.STATUS_ALIASES["admitted"],
            "accepted",
        )
        self.assertEqual(
            module.GraphitiMemoryAdapter.STATUS_ALIASES["duplicate"],
            "deduplicated",
        )

    def test_deployment_commands_match_current_stdin_contract(self) -> None:
        content = (ROOT / "deployment/generated-data/cursor-command-env.example").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("--stdin", content)
        for command in (
            "ingest-governed-candidate",
            "search-context",
            "hydrate-context",
            "record-reuse",
            "invalidate-source",
        ):
            self.assertIn(command, content)


if __name__ == "__main__":
    unittest.main()
