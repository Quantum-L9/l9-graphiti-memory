# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/generated_data/test_live_proof_fail_closed.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

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

ROOT = Path(__file__).resolve().parents[3]
LIVE = (
    ROOT
    / "deployment"
    / "generated-data"
    / "live_end_to_end_proof.py"
)


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
        "#!/usr/bin/env python3\n"
        + textwrap.dedent(body),
        encoding="utf-8",
    )
    path.chmod(
        path.stat().st_mode
        | stat.S_IXUSR
    )
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
    return completed.returncode, json.loads(
        completed.stdout
    )


class LiveProofFailClosedTests(unittest.TestCase):
    def test_missing_commands_fail(self) -> None:
        returncode, result = execute({})
        self.assertNotEqual(returncode, 0)
        self.assertFalse(
            result["full_loop_proven"]
        )
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

            env = {
                name: str(fail)
                for name in REQUIRED_ENV
            }
            env[
                "L9_SGD_GRAPHITI_CAPABILITIES_COMMAND"
            ] = str(capabilities)

            returncode, result = execute(env)

        self.assertNotEqual(returncode, 0)
        self.assertFalse(
            result["tool_plane_proven"]
        )
        self.assertFalse(
            result["full_loop_proven"]
        )

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
            env = {
                name: str(not_found)
                for name in REQUIRED_ENV
            }

            returncode, result = execute(env)

        self.assertNotEqual(returncode, 0)
        self.assertFalse(
            result["full_loop_proven"]
        )
        self.assertTrue(
            any(
                "404" in failure
                for failure in result["failures"]
            )
        )

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

            env = {
                name: str(command)
                for name in REQUIRED_ENV
            }
            env[
                "L9_SGD_GRAPHITI_REUSE_COMMAND"
            ] = str(reuse_fail)

            returncode, result = execute(env)

        self.assertNotEqual(returncode, 0)
        self.assertFalse(
            result["reuse_proven"]
        )
        self.assertFalse(
            result["full_loop_proven"]
        )

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

            env = {
                name: str(generic)
                for name in REQUIRED_ENV
            }
            env[
                "L9_SGD_GRAPHITI_INVALIDATE_COMMAND"
            ] = str(deleting)

            returncode, result = execute(env)

        self.assertNotEqual(returncode, 0)
        self.assertFalse(
            result["deletion_absent"]
        )
        self.assertFalse(
            result["full_loop_proven"]
        )


if __name__ == "__main__":
    unittest.main()
