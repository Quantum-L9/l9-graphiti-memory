# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/generated_data/test_load_harness.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import json
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HARNESS = (
    ROOT
    / "deployment"
    / "generated-data"
    / "load_test_generated_data.py"
)


def make_command(
    directory: Path,
    body: str,
) -> Path:
    path = directory / "synthetic-command"
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


class LoadHarnessTests(unittest.TestCase):
    def test_concurrent_identical_candidate_accepts_duplicates(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            command = make_command(
                directory,
                """
                import json
                import sys

                json.load(sys.stdin)
                print(
                    json.dumps(
                        {
                            "status": "duplicate",
                            "storage_committed": False
                        }
                    )
                )
                """,
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(HARNESS),
                    "--scenario",
                    "concurrent_identical_candidate",
                    "--command",
                    str(command),
                    "--workers",
                    "4",
                    "--iterations",
                    "8",
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
        self.assertTrue(result["passed"])
        self.assertEqual(result["failures"], 0)
        self.assertEqual(result["successes"], 8)

    def test_invalid_status_fails_harness(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            command = make_command(
                directory,
                """
                import json
                import sys

                json.load(sys.stdin)
                print(
                    json.dumps(
                        {"status": "mystery"}
                    )
                )
                """,
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(HARNESS),
                    "--scenario",
                    "concurrent_identical_candidate",
                    "--command",
                    str(command),
                    "--workers",
                    "2",
                    "--iterations",
                    "2",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )

        self.assertNotEqual(
            completed.returncode,
            0,
        )
        result = json.loads(completed.stdout)
        self.assertFalse(result["passed"])

    def test_nonzero_subprocess_is_counted_as_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            command = make_command(
                directory,
                """
                import sys
                print("failed", file=sys.stderr)
                raise SystemExit(5)
                """,
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(HARNESS),
                    "--scenario",
                    "concurrent_reuse",
                    "--command",
                    str(command),
                    "--workers",
                    "2",
                    "--iterations",
                    "4",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )

        self.assertNotEqual(
            completed.returncode,
            0,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["failures"], 4)
        self.assertTrue(
            result["failure_details"]
        )

    def test_harness_is_bounded(self) -> None:
        content = HARNESS.read_text(encoding="utf-8")
        self.assertIn(
            "--iterations",
            content,
        )
        self.assertIn(
            "--workers",
            content,
        )
        self.assertNotIn(
            "while True",
            content,
        )


if __name__ == "__main__":
    unittest.main()
