# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: deployment/generated-data/verify_cross_repo_contract.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from collections.abc import Iterable
from pathlib import Path

try:
    import yaml
except ImportError as exc:
    raise SystemExit("PyYAML is required") from exc


DEPLOYMENT = Path(__file__).resolve().parent
GENERATED_DATA_AGENT_DIR = Path("environment/agents/generated-data")
CAPABILITY_MANIFEST = "capability-manifest.yaml"


def locate_cursor_root(explicit: str | None) -> Path:
    candidates = [
        explicit,
        os.environ.get("CURSOR_GOVERNANCE_ROOT"),
        "../Cursor-Governance",
        "../cursor-governance",
        "../../Cursor-Governance",
        "../../cursor-governance",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        root = Path(candidate).expanduser().resolve()
        if (
            root.is_dir()
            and (
                root
                / GENERATED_DATA_AGENT_DIR
                / "adapters"
                / "graphiti_memory.py"
            ).is_file()
        ):
            return root
    raise FileNotFoundError(
        "Cursor-Governance checkout not found"
    )


def strings_in_python(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
    }


def extract_known_values(
    strings: Iterable[str],
    expected: set[str],
) -> set[str]:
    return expected & set(strings)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cursor-root")
    args = parser.parse_args()

    cursor = locate_cursor_root(args.cursor_root)

    producer_files = {
        "candidate": (
            cursor
            / GENERATED_DATA_AGENT_DIR
            / "adapters"
            / "graphiti_memory.py"
        ),
        "query": (
            cursor
            / GENERATED_DATA_AGENT_DIR
            / "retrieval"
            / "context_query.py"
        ),
        "reuse": (
            cursor
            / GENERATED_DATA_AGENT_DIR
            / "retrieval"
            / "reuse_recorder.py"
        ),
        "invalidation": (
            cursor
            / GENERATED_DATA_AGENT_DIR
            / "invalidation"
            / "repository_event_bridge.py"
        ),
    }

    manifest = yaml.safe_load(
        (
            DEPLOYMENT / CAPABILITY_MANIFEST
        ).read_text(encoding="utf-8")
    )

    supported_classes = set(
        manifest["candidate_ingress"]["supported_classes"]
    )
    reuse_outcomes = set(
        manifest["reuse"]["supported_outcomes"]
    )
    invalidation_events = set(
        manifest["invalidation"][
            "supported_event_types"
        ]
    )

    classifier = (
        cursor
        / GENERATED_DATA_AGENT_DIR
        / "runtime"
        / "classifier.py"
    )
    unit_schema = (
        cursor
        / GENERATED_DATA_AGENT_DIR
        / "schemas"
        / "generated-data-unit.schema.json"
    )
    extra_class_strings: set[str] = set()
    if classifier.is_file():
        extra_class_strings |= strings_in_python(classifier)
    if unit_schema.is_file():
        extra_class_strings |= set(
            json.loads(unit_schema.read_text(encoding="utf-8"))
            .get("properties", {})
            .get("primary_class", {})
            .get("enum", [])
        )
    candidate_strings = strings_in_python(
        producer_files["candidate"]
    ) | extra_class_strings
    reuse_strings = strings_in_python(
        producer_files["reuse"]
    )
    invalidation_strings = strings_in_python(
        producer_files["invalidation"]
    )

    producer_supported = extract_known_values(
        candidate_strings,
        supported_classes
        | set(
            manifest["candidate_ingress"][
                "rejected_classes"
            ]
        ),
    )
    producer_reuse = extract_known_values(
        reuse_strings,
        reuse_outcomes,
    )
    producer_invalidation = extract_known_values(
        invalidation_strings,
        invalidation_events,
    )

    differences: list[str] = []

    missing_supported = supported_classes - producer_supported
    if missing_supported:
        differences.append(
            "Producer adapter does not expose expected classes: "
            + ", ".join(sorted(missing_supported))
        )

    missing_reuse = reuse_outcomes - producer_reuse
    if missing_reuse:
        differences.append(
            "Producer reuse recorder does not expose outcomes: "
            + ", ".join(sorted(missing_reuse))
        )

    # The producer may generate only a subset directly. It must at least support
    # repository path changes for this activation pack.
    if "repository_path_changed" not in invalidation_strings:
        differences.append(
            "Producer invalidation bridge lacks "
            "repository_path_changed"
        )

    fixture_candidate = json.loads(
        (
            DEPLOYMENT / "fixtures" / "governed-candidate.json"
        ).read_text(encoding="utf-8")
    )
    fixture_reuse = json.loads(
        (
            DEPLOYMENT / "fixtures" / "reuse-event.json"
        ).read_text(encoding="utf-8")
    )
    fixture_invalidation = json.loads(
        (
            DEPLOYMENT
            / "fixtures"
            / "path-invalidation.json"
        ).read_text(encoding="utf-8")
    )

    if fixture_candidate["knowledge"]["primary_class"] not in supported_classes:
        differences.append(
            "Candidate fixture class is not supported"
        )
    if fixture_reuse["outcome"] not in reuse_outcomes:
        differences.append(
            "Reuse fixture outcome is not supported"
        )
    if (
        fixture_invalidation["event_type"]
        not in invalidation_events
    ):
        differences.append(
            "Invalidation fixture event is not supported"
        )

    result = {
        "graphiti_sha": _git_sha(Path.cwd()),
        "cursor_governance_sha": _git_sha(cursor),
        "producer_files": {
            key: {
                "path": str(path),
                "sha256": sha256(path),
            }
            for key, path in producer_files.items()
        },
        "consumer_files": {
            "manifest": {
                "path": str(
                    DEPLOYMENT / CAPABILITY_MANIFEST
                ),
                "sha256": sha256(
                    DEPLOYMENT / CAPABILITY_MANIFEST
                ),
            }
        },
        "observed": {
            "producer_supported_classes": sorted(
                producer_supported
            ),
            "producer_reuse_outcomes": sorted(
                producer_reuse
            ),
            "producer_invalidation_events": sorted(
                producer_invalidation
            ),
        },
        "compatible": not differences,
        "differences": differences,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not differences else 1


def _git_sha(root: Path) -> str:
    import subprocess

    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return (
        completed.stdout.strip()
        if completed.returncode == 0
        else "unknown"
    )


if __name__ == "__main__":
    raise SystemExit(main())
