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
DEPLOYMENT = ROOT / "deployment" / "generated-data"
TOOLS = DEPLOYMENT / "verify_generated_data_tools.py"
LIVE = DEPLOYMENT / "live_end_to_end_proof.py"


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


def run(
    command: list[str],
    *,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=dict(env or os.environ),
        check=False,
        timeout=30,
    )


class CommandProtocolTests(unittest.TestCase):
    def test_static_tool_verifier_emits_json_only(
        self,
    ) -> None:
        completed = run(
            [
                sys.executable,
                str(TOOLS),
                "--mode",
                "static",
            ]
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        parsed = json.loads(completed.stdout)
        self.assertIsInstance(parsed, dict)
        self.assertTrue(parsed["ready"])

    def test_invalid_json_stdout_fails_live_proof(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)

            invalid = write_command(
                directory,
                "invalid-json",
                """
                print("not-json")
                """,
            )

            env = dict(os.environ)
            for name in (
                "L9_SGD_GRAPHITI_CAPABILITIES_COMMAND",
                "L9_SGD_GRAPHITI_INGEST_COMMAND",
                "L9_SGD_GRAPHITI_SEARCH_COMMAND",
                "L9_SGD_GRAPHITI_HYDRATE_COMMAND",
                "L9_SGD_GRAPHITI_REUSE_COMMAND",
                "L9_SGD_GRAPHITI_INVALIDATE_COMMAND",
            ):
                env[name] = str(invalid)

            completed = run(
                [
                    sys.executable,
                    str(LIVE),
                    "--mode",
                    "commands",
                ],
                env=env,
            )

        self.assertNotEqual(
            completed.returncode,
            0,
        )
        result = json.loads(completed.stdout)
        self.assertFalse(
            result["full_loop_proven"]
        )
        self.assertTrue(result["failures"])

    def test_nonzero_exit_is_reported_as_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            failing = write_command(
                directory,
                "failing",
                """
                import json
                import sys
                print(
                    json.dumps(
                        {"status": "error"}
                    )
                )
                print(
                    "synthetic diagnostic",
                    file=sys.stderr,
                )
                raise SystemExit(5)
                """,
            )

            env = dict(os.environ)
            env[
                "L9_SGD_GRAPHITI_CAPABILITIES_COMMAND"
            ] = str(failing)
            for name in (
                "L9_SGD_GRAPHITI_INGEST_COMMAND",
                "L9_SGD_GRAPHITI_SEARCH_COMMAND",
                "L9_SGD_GRAPHITI_HYDRATE_COMMAND",
                "L9_SGD_GRAPHITI_REUSE_COMMAND",
                "L9_SGD_GRAPHITI_INVALIDATE_COMMAND",
            ):
                env[name] = str(failing)

            completed = run(
                [
                    sys.executable,
                    str(LIVE),
                    "--mode",
                    "commands",
                ],
                env=env,
            )

        self.assertNotEqual(
            completed.returncode,
            0,
        )
        result = json.loads(completed.stdout)
        self.assertTrue(
            any(
                "synthetic diagnostic" in failure
                for failure in result["failures"]
            )
        )

    def test_example_environment_has_no_secret_values(
        self,
    ) -> None:
        content = (
            DEPLOYMENT
            / "cursor-command-env.example"
        ).read_text(encoding="utf-8")

        lowered = content.lower()
        self.assertNotIn(
            "bearer ",
            lowered,
        )
        self.assertNotIn(
            "api_key=",
            lowered,
        )
        self.assertNotIn(
            "password=",
            lowered,
        )
        self.assertNotIn(
            "token=",
            lowered,
        )

    def test_all_expected_commands_are_declared(
        self,
    ) -> None:
        content = (
            DEPLOYMENT
            / "cursor-command-env.example"
        ).read_text(encoding="utf-8")

        expected = {
            "L9_SGD_GRAPHITI_INGEST_COMMAND",
            "L9_SGD_GRAPHITI_SEARCH_COMMAND",
            "L9_SGD_GRAPHITI_HYDRATE_COMMAND",
            "L9_SGD_GRAPHITI_REUSE_COMMAND",
            "L9_SGD_GRAPHITI_INVALIDATE_COMMAND",
            "L9_SGD_GRAPHITI_CAPABILITIES_COMMAND",
        }

        declared = {
            line.split("=", 1)[0]
            for line in content.splitlines()
            if line.startswith("L9_SGD_")
        }

        self.assertEqual(declared, expected)


if __name__ == "__main__":
    unittest.main()
