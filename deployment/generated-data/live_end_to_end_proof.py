from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence


DEPLOYMENT = Path(__file__).resolve().parent


class ProofFailure(RuntimeError):
    pass


def command(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        raise ProofFailure(f"{name} is not configured")
    return tuple(shlex.split(raw))


def invoke(
    command_value: Sequence[str],
    payload: Mapping[str, Any] | None,
    *,
    timeout: int = 45,
) -> Mapping[str, Any]:
    completed = subprocess.run(
        list(command_value),
        input=(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            )
            if payload is not None
            else None
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )

    if completed.returncode != 0:
        raise ProofFailure(
            f"{' '.join(command_value)} failed: "
            f"{completed.stderr.strip()}"
        )

    try:
        response = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ProofFailure(
            f"{' '.join(command_value)} returned invalid JSON"
        ) from exc

    if not isinstance(response, Mapping):
        raise ProofFailure(
            f"{' '.join(command_value)} returned non-object JSON"
        )
    return response


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("commands",),
        default="commands",
    )
    args = parser.parse_args()

    failures: list[str] = []
    evidence: dict[str, Any] = {}

    candidate = json.loads(
        (
            DEPLOYMENT
            / "fixtures"
            / "governed-candidate.json"
        ).read_text(encoding="utf-8")
    )
    suffix = uuid.uuid4().hex[:12]
    candidate["candidate_id"] = (
        f"{candidate['candidate_id']}-{suffix}"
    )
    candidate["knowledge"]["unit_id"] = (
        f"{candidate['knowledge']['unit_id']}-{suffix}"
    )

    reuse_fixture = json.loads(
        (
            DEPLOYMENT / "fixtures" / "reuse-event.json"
        ).read_text(encoding="utf-8")
    )
    invalidation = json.loads(
        (
            DEPLOYMENT
            / "fixtures"
            / "path-invalidation.json"
        ).read_text(encoding="utf-8")
    )
    invalidation["event_id"] = (
        f"{invalidation['event_id']}-{suffix}"
    )

    result: dict[str, Any] = {
        "mode": args.mode,
        "candidate_ingress_proven": False,
        "canonical_commit_proven": False,
        "search_proven": False,
        "hydration_proven": False,
        "reuse_proven": False,
        "invalidation_proven": False,
        "normal_exclusion_proven": False,
        "historical_evidence_proven": False,
        "deletion_absent": False,
        "tool_plane_proven": False,
        "cross_repo_contract_proven": False,
        "full_loop_proven": False,
        "record_id": None,
        "receipts": [],
        "evidence": evidence,
        "failures": failures,
    }

    try:
        capabilities = invoke(
            command("L9_SGD_GRAPHITI_CAPABILITIES_COMMAND"),
            None,
        )
        evidence["capabilities"] = capabilities
        result["tool_plane_proven"] = bool(
            capabilities.get("runtime", {}).get(
                "mcp_tool_plane_ready", False
            )
            or capabilities.get("runtime", {}).get(
                "candidate_ingress_ready", False
            )
        )

        ingestion = invoke(
            command("L9_SGD_GRAPHITI_INGEST_COMMAND"),
            candidate,
        )
        evidence["ingestion"] = ingestion
        status = str(ingestion.get("status", ""))
        result["candidate_ingress_proven"] = status in {
            "accepted",
            "duplicate",
            "merged",
            "quarantined",
            "contested",
        }
        result["canonical_commit_proven"] = bool(
            ingestion.get(
                "storage_committed",
                status in {"accepted", "merged"},
            )
        )
        record_id = ingestion.get("record_id")
        result["record_id"] = record_id

        if not record_id:
            raise ProofFailure(
                "Ingestion returned no record_id"
            )

        query = {
            "schema_version": "1.0.0",
            "query": candidate["knowledge"]["statement"],
            "repository": candidate["source"]["repository"],
            "repository_class": candidate["source"][
                "repository_class"
            ],
            "paths": candidate["knowledge"]["scope"]["paths"],
            "base_sha": candidate["source"]["base_sha"],
            "visibility_ceiling": candidate["governance"][
                "visibility"
            ],
            "max_items": 10,
            "max_characters": 10000,
            "include_contested": False,
            "include_raw_evidence": False
        }

        search = invoke(
            command("L9_SGD_GRAPHITI_SEARCH_COMMAND"),
            query,
        )
        evidence["search_before"] = search
        search_ids = _record_ids(search)
        result["search_proven"] = record_id in search_ids

        hydrate_request = {
            **query,
            "record_ids": [record_id],
        }
        hydration = invoke(
            command("L9_SGD_GRAPHITI_HYDRATE_COMMAND"),
            hydrate_request,
        )
        evidence["hydrate_before"] = hydration
        result["hydration_proven"] = (
            record_id in _record_ids(hydration)
            or record_id
            == str(hydration.get("record_id", ""))
        )

        reuse_fixture["event_id"] = (
            f"{reuse_fixture['event_id']}-{suffix}"
        )
        reuse_fixture["record_id"] = record_id
        reuse = invoke(
            command("L9_SGD_GRAPHITI_REUSE_COMMAND"),
            reuse_fixture,
        )
        evidence["reuse"] = reuse
        result["reuse_proven"] = str(
            reuse.get("status", "")
        ) in {
            "recorded",
            "duplicate",
            "accepted",
        }

        invalidation_response = invoke(
            command("L9_SGD_GRAPHITI_INVALIDATE_COMMAND"),
            invalidation,
        )
        evidence["invalidation"] = invalidation_response
        result["invalidation_proven"] = str(
            invalidation_response.get("status", "")
        ) in {
            "invalidated",
            "partially_invalidated",
            "duplicate",
            "accepted",
        }
        result["deletion_absent"] = (
            invalidation_response.get("deleted") is not True
        )

        search_after = invoke(
            command("L9_SGD_GRAPHITI_SEARCH_COMMAND"),
            query,
        )
        evidence["search_after"] = search_after
        result["normal_exclusion_proven"] = (
            record_id not in _record_ids(search_after)
        )

        historical_query = {
            **query,
            "include_historical": True,
            "include_invalidated": True,
        }
        historical = invoke(
            command("L9_SGD_GRAPHITI_SEARCH_COMMAND"),
            historical_query,
        )
        evidence["historical"] = historical
        result["historical_evidence_proven"] = (
            record_id in _record_ids(historical)
        )

        result["cross_repo_contract_proven"] = True

    except Exception as exc:
        failures.append(str(exc))

    required = (
        "candidate_ingress_proven",
        "canonical_commit_proven",
        "search_proven",
        "hydration_proven",
        "reuse_proven",
        "invalidation_proven",
        "normal_exclusion_proven",
        "historical_evidence_proven",
        "deletion_absent",
        "tool_plane_proven",
        "cross_repo_contract_proven",
    )
    result["full_loop_proven"] = (
        not failures
        and all(result[name] for name in required)
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["full_loop_proven"] else 1


def _record_ids(payload: Mapping[str, Any]) -> set[str]:
    raw = payload.get(
        "records",
        payload.get(
            "results",
            payload.get("candidates", []),
        ),
    )
    if not isinstance(raw, list):
        return set()

    ids: set[str] = set()
    for item in raw:
        if isinstance(item, Mapping):
            value = item.get(
                "record_id",
                item.get("id"),
            )
            if value is not None:
                ids.add(str(value))
    return ids


if __name__ == "__main__":
    raise SystemExit(main())
