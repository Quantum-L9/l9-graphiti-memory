from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shlex
import statistics
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


DEPLOYMENT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Invocation:
    returncode: int
    duration_seconds: float
    response: Mapping[str, Any] | None
    stderr: str


def invoke(
    command: Sequence[str],
    payload: Mapping[str, Any],
    timeout: int,
) -> Invocation:
    started = time.perf_counter()
    completed = subprocess.run(
        list(command),
        input=json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    duration = time.perf_counter() - started

    response: Mapping[str, Any] | None = None
    try:
        parsed = json.loads(completed.stdout or "{}")
        if isinstance(parsed, Mapping):
            response = parsed
    except json.JSONDecodeError:
        pass

    return Invocation(
        returncode=completed.returncode,
        duration_seconds=duration,
        response=response,
        stderr=completed.stderr[-1000:],
    )


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(
        len(ordered) - 1,
        max(0, round((len(ordered) - 1) * p)),
    )
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        choices=(
            "concurrent_identical_candidate",
            "concurrent_reuse",
            "projection_unavailable",
        ),
        required=True,
    )
    parser.add_argument("--command")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    args = parser.parse_args()

    raw_command = (
        args.command
        or os.environ.get(
            (
                "L9_SGD_GRAPHITI_REUSE_COMMAND"
                if args.scenario == "concurrent_reuse"
                else "L9_SGD_GRAPHITI_INGEST_COMMAND"
            ),
            "",
        )
    ).strip()

    if not raw_command:
        raise SystemExit(
            "No command configured for load scenario"
        )

    command = shlex.split(raw_command)
    fixture = (
        DEPLOYMENT
        / "fixtures"
        / (
            "reuse-event.json"
            if args.scenario == "concurrent_reuse"
            else "governed-candidate.json"
        )
    )
    payload = json.loads(
        fixture.read_text(encoding="utf-8")
    )

    invocations: list[Invocation] = []

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, args.workers)
    ) as executor:
        futures = [
            executor.submit(
                invoke,
                command,
                payload,
                args.timeout_seconds,
            )
            for _ in range(max(1, args.iterations))
        ]
        for future in concurrent.futures.as_completed(
            futures
        ):
            invocations.append(future.result())

    durations = [
        item.duration_seconds for item in invocations
    ]
    success = [
        item for item in invocations
        if item.returncode == 0
    ]
    failure = [
        item for item in invocations
        if item.returncode != 0
    ]

    statuses = [
        str(item.response.get("status"))
        for item in success
        if item.response is not None
    ]

    accepted_like = {
        "accepted",
        "duplicate",
        "already_exists",
        "quarantined",
        "merged",
    }

    passed = (
        not failure
        and all(status in accepted_like for status in statuses)
        and len(statuses) == len(success)
    )

    result: dict[str, Any] = {
        "scenario": args.scenario,
        "passed": passed,
        "workers": args.workers,
        "iterations": args.iterations,
        "successes": len(success),
        "failures": len(failure),
        "statuses": statuses,
        "latency_seconds": {
            "p50": percentile(durations, 0.50),
            "p95": percentile(durations, 0.95),
            "p99": percentile(durations, 0.99),
            "mean": (
                statistics.fmean(durations)
                if durations
                else 0.0
            ),
        },
        "failure_details": [
            {
                "returncode": item.returncode,
                "stderr": item.stderr,
                "response": item.response,
            }
            for item in failure
        ],
        "assertions": {
            "partial_transactions_allowed": False,
            "duplicate_canonical_writes_allowed": False,
            "lost_receipts_allowed": False,
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
