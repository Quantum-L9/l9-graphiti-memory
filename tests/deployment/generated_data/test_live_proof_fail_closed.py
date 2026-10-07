# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/generated_data/test_live_proof_fail_closed.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-10-02

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[3]
LIVE = ROOT / "deployment" / "generated-data" / "live_end_to_end_proof.py"


REQUIRED_ENV = (
    "L9_SGD_GRAPHITI_CAPABILITIES_COMMAND",
    "L9_SGD_GRAPHITI_INGEST_COMMAND",
    "L9_SGD_GRAPHITI_SEARCH_COMMAND",
    "L9_SGD_GRAPHITI_HYDRATE_COMMAND",
    "L9_SGD_GRAPHITI_REUSE_COMMAND",
    "L9_SGD_GRAPHITI_INVALIDATE_COMMAND",
)


def write_command(
    directory: Path,
    name: str,
    body: str,
) -> Path:
    path = directory / name
    path.write_text(
        "#!/usr/bin/env python3\n" + textwrap.dedent(body),
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def execute(
    env_overrides: Mapping[str, str],
) -> tuple[int, dict]:
    env = dict(os.environ)
    for name in REQUIRED_ENV:
        env.pop(name, None)
    env.update(env_overrides)

    completed = subprocess.run(
        [
            sys.executable,
            str(LIVE),
            "--mode",
            "commands",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )
    return completed.returncode, json.loads(completed.stdout)


class LiveProofFailClosedTests(unittest.TestCase):
    def test_missing_commands_fail(self) -> None:
        returncode, result = execute({})
        self.assertNotEqual(returncode, 0)
        self.assertFalse(result["full_loop_proven"])
        self.assertTrue(result["failures"])

    def test_health_only_does_not_prove_tool_plane(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)

            capabilities = write_command(
                directory,
                "capabilities",
                """
                import json
                print(
                    json.dumps(
                        {
                            "runtime": {
                                "canonical_store_ready": True,
                                "candidate_ingress_ready": False,
                                "mcp_tool_plane_ready": False
                            }
                        }
                    )
                )
                """,
            )

            fail = write_command(
                directory,
                "fail",
                """
                import json
                import sys
                print(
                    json.dumps(
                        {"status": "not_found"}
                    )
                )
                print("404 tool route", file=sys.stderr)
                raise SystemExit(5)
                """,
            )

            env = {name: str(fail) for name in REQUIRED_ENV}
            env["L9_SGD_GRAPHITI_CAPABILITIES_COMMAND"] = str(capabilities)

            returncode, result = execute(env)

        self.assertNotEqual(returncode, 0)
        self.assertFalse(result["tool_plane_proven"])
        self.assertFalse(result["full_loop_proven"])

    def test_mcp_404_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            not_found = write_command(
                directory,
                "not-found",
                """
                import json
                import sys

                print(
                    json.dumps(
                        {
                            "status": "not_found",
                            "http_status": 404
                        }
                    )
                )
                print("HTTP 404", file=sys.stderr)
                raise SystemExit(5)
                """,
            )
            env = {name: str(not_found) for name in REQUIRED_ENV}

            returncode, result = execute(env)

        self.assertNotEqual(returncode, 0)
        self.assertFalse(result["full_loop_proven"])
        self.assertTrue(any("404" in failure for failure in result["failures"]))

    def test_missing_reuse_prevents_full_loop(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)

            command = write_command(
                directory,
                "router",
                """
                import json
                import os
                import sys

                name = os.path.basename(sys.argv[0])
                payload = {}
                try:
                    payload = json.load(sys.stdin)
                except Exception:
                    pass

                print(
                    json.dumps(
                        {
                            "status": "accepted",
                            "record_id": "record-1",
                            "storage_committed": True,
                            "runtime": {
                                "candidate_ingress_ready": True,
                                "mcp_tool_plane_ready": True
                            },
                            "records": [
                                {"record_id": "record-1"}
                            ]
                        }
                    )
                )
                """,
            )

            reuse_fail = write_command(
                directory,
                "reuse-fail",
                """
                import json
                import sys
                print(
                    json.dumps(
                        {"status": "rejected"}
                    )
                )
                raise SystemExit(7)
                """,
            )

            env = {name: str(command) for name in REQUIRED_ENV}
            env["L9_SGD_GRAPHITI_REUSE_COMMAND"] = str(reuse_fail)

            returncode, result = execute(env)

        self.assertNotEqual(returncode, 0)
        self.assertFalse(result["reuse_proven"])
        self.assertFalse(result["full_loop_proven"])

    def test_invalidation_deletion_claim_fails_proof(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)

            generic = write_command(
                directory,
                "generic",
                """
                import json
                import sys

                try:
                    json.load(sys.stdin)
                except Exception:
                    pass

                print(
                    json.dumps(
                        {
                            "status": "accepted",
                            "record_id": "record-1",
                            "storage_committed": True,
                            "runtime": {
                                "candidate_ingress_ready": True,
                                "mcp_tool_plane_ready": True
                            },
                            "records": [
                                {"record_id": "record-1"}
                            ]
                        }
                    )
                )
                """,
            )

            deleting = write_command(
                directory,
                "deleting",
                """
                import json
                import sys

                json.load(sys.stdin)
                print(
                    json.dumps(
                        {
                            "status": "invalidated",
                            "deleted": True
                        }
                    )
                )
                """,
            )

            env = {name: str(generic) for name in REQUIRED_ENV}
            env["L9_SGD_GRAPHITI_INVALIDATE_COMMAND"] = str(deleting)

            returncode, result = execute(env)

        self.assertNotEqual(returncode, 0)
        self.assertFalse(result["deletion_absent"])
        self.assertFalse(result["full_loop_proven"])


# A stateful stand-in for the six deployed commands. Each copy dispatches on
# its own file name; ingest, invalidate, and search share one state file, so
# search reflects the invalidation outcome the stub was told to report.
STATEFUL_ROUTER = """
import json
import os
import sys

name = os.path.basename(sys.argv[0])
state_path = os.environ["PROOF_STATE"]
invalidation = json.loads(os.environ["PROOF_INVALIDATION"])
try:
    payload = json.load(sys.stdin)
except Exception:
    payload = {}
try:
    with open(state_path, encoding="utf-8") as handle:
        state = json.load(handle)
except FileNotFoundError:
    state = {"archived": False}
record = {"record_id": "record-1"}
if name == "capabilities":
    response = {"runtime": {"candidate_ingress_ready": True, "mcp_tool_plane_ready": True}}
elif name == "ingest":
    response = {"status": "admitted", "record_id": "record-1", "storage_committed": True}
elif name == "hydrate":
    response = {"records": [record]}
elif name == "reuse":
    response = {"status": "recorded"}
elif name == "invalidate":
    response = dict(invalidation)
    if response.get("transitioned") and os.environ.get("PROOF_ARCHIVE", "1") == "1":
        state["archived"] = True
elif name == "search":
    historical = bool(payload.get("include_invalidated"))
    visible = historical or not state["archived"]
    response = {"candidates": [record] if visible else []}
else:
    raise SystemExit(f"unknown command {name}")
with open(state_path, "w", encoding="utf-8") as handle:
    json.dump(state, handle)
print(json.dumps(response))
"""

COMMAND_NAMES = {
    "L9_SGD_GRAPHITI_CAPABILITIES_COMMAND": "capabilities",
    "L9_SGD_GRAPHITI_INGEST_COMMAND": "ingest",
    "L9_SGD_GRAPHITI_SEARCH_COMMAND": "search",
    "L9_SGD_GRAPHITI_HYDRATE_COMMAND": "hydrate",
    "L9_SGD_GRAPHITI_REUSE_COMMAND": "reuse",
    "L9_SGD_GRAPHITI_INVALIDATE_COMMAND": "invalidate",
}


def run_stateful(invalidation: Mapping[str, object], *, archive: bool = True) -> tuple[int, dict]:
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        env = {
            variable: str(write_command(directory, name, STATEFUL_ROUTER))
            for variable, name in COMMAND_NAMES.items()
        }
        env["PROOF_STATE"] = str(directory / "state.json")
        env["PROOF_INVALIDATION"] = json.dumps(invalidation)
        env["PROOF_ARCHIVE"] = "1" if archive else "0"
        return execute(env)


class InvalidationProofTests(unittest.TestCase):
    """ADR-095: only a real, retrieval-visible lifecycle transition is proof."""

    APPLIED: ClassVar[dict[str, object]] = {
        "status": "applied",
        "matched": 1,
        "transitioned": 1,
        "deleted": False,
    }

    def test_applied_transition_with_exclusion_and_history_proves(self) -> None:
        returncode, result = run_stateful(self.APPLIED)
        self.assertEqual(returncode, 0, result["failures"])
        self.assertTrue(result["invalidation_proven"])
        self.assertTrue(result["full_loop_proven"])

    def test_applied_alone_does_not_prove(self) -> None:
        for override in (
            {"matched": 0, "transitioned": 0},
            {"matched": 1, "transitioned": 0},
            {"matched": True, "transitioned": True},
        ):
            with self.subTest(override=override):
                returncode, result = run_stateful({"status": "applied", **override})
                self.assertNotEqual(returncode, 0)
                self.assertFalse(result["invalidation_proven"])
                self.assertFalse(result["full_loop_proven"])

    def test_status_other_than_applied_does_not_prove(self) -> None:
        for status in ("invalidated", "accepted", "duplicate", "rejected"):
            with self.subTest(status=status):
                returncode, result = run_stateful({**self.APPLIED, "status": status})
                self.assertNotEqual(returncode, 0)
                self.assertFalse(result["invalidation_proven"])

    def test_deletion_claim_does_not_prove(self) -> None:
        returncode, result = run_stateful({**self.APPLIED, "deleted": True})
        self.assertNotEqual(returncode, 0)
        self.assertFalse(result["deletion_absent"])
        self.assertFalse(result["invalidation_proven"])

    def test_transition_without_retrieval_exclusion_does_not_prove(self) -> None:
        # The receipt claims a transition, but ordinary search still returns
        # the record: the claim is not proof.
        returncode, result = run_stateful(self.APPLIED, archive=False)
        self.assertNotEqual(returncode, 0)
        self.assertFalse(result["normal_exclusion_proven"])
        self.assertFalse(result["invalidation_proven"])


if __name__ == "__main__":
    unittest.main()
