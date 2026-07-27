#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: release-work/l9-deploy-phase6-operator/scripts/run_adversarial_tests.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: isolated_adversarial_test_runner
# tags: [validation, adversarial-tests, timeout, machine-readable]
# owner: igor_beylin
# status: active
# version: 1.1.0
# updated: 2026-07-26
# Purpose: discover and execute each adversarial test in an isolated process with bounded timeout and parallel sharding.
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_MODULE = "tests.test_hardening.Phase6HardeningTests"


def discover_tests() -> list[str]:
    sys.path.insert(0, str(ROOT))
    from tests.test_hardening import Phase6HardeningTests  # type: ignore
    return [f"{TEST_MODULE}.{name}" for name in unittest.defaultTestLoader.getTestCaseNames(Phase6HardeningTests)]


def execute(test_name: str, timeout_seconds: int, env: dict[str, str]) -> dict[str, object]:
    started = time.monotonic()
    command = [sys.executable, "-m", "unittest", "-v", test_name]
    try:
        process = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        status = "PASS" if process.returncode == 0 else "FAIL"
        returncode: int | None = process.returncode
        stdout = process.stdout
        stderr = process.stderr
    except subprocess.TimeoutExpired as exc:
        status = "TIMEOUT"
        returncode = None
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
    return {
        "test": test_name,
        "status": status,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.timeout_seconds < 5:
        parser.error("--timeout-seconds must be at least 5")
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")

    tests = discover_tests()
    if not tests:
        print("FAIL: unittest discovery found zero tests", file=sys.stderr)
        return 2

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    started = time.monotonic()
    print(f"Discovered {len(tests)} adversarial tests; workers={args.workers}; timeout={args.timeout_seconds}s", flush=True)
    records: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_map = {pool.submit(execute, test, args.timeout_seconds, env): test for test in tests}
        for completed, future in enumerate(concurrent.futures.as_completed(future_map), 1):
            record = future.result()
            records.append(record)
            print(
                f"[{completed:02d}/{len(tests):02d}] {record['status']:7s} "
                f"{record['elapsed_seconds']:8.3f}s {record['test']}",
                flush=True,
            )
            if record["status"] != "PASS":
                if record["stdout"]:
                    print(record["stdout"], file=sys.stderr)
                if record["stderr"]:
                    print(record["stderr"], file=sys.stderr)

    records.sort(key=lambda item: str(item["test"]))
    failed = sum(1 for item in records if item["status"] != "PASS")
    clean_records = [{key: value for key, value in item.items() if key not in {"stdout", "stderr"}} for item in records]
    report = {
        "schema": "l9.deploy.phase6-adversarial-test-report/v1",
        "status": "PASS" if failed == 0 else "FAIL",
        "discovered": len(tests),
        "passed": len(tests) - failed,
        "failed": failed,
        "workers": args.workers,
        "timeout_seconds": args.timeout_seconds,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "tests": clean_records,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "discovered", "passed", "failed", "elapsed_seconds")}, sort_keys=True), flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
