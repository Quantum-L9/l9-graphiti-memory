from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise SystemExit("PyYAML is required") from exc


ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    required: bool
    details: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "required": self.required,
            "details": dict(self.details),
        }


def load_yaml(path: Path) -> Mapping[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise TypeError(f"{path} must contain a mapping")
    return value


def run_json_command(
    command: Sequence[str],
    *,
    payload: Mapping[str, Any] | None = None,
    timeout: int = 30,
) -> tuple[bool, Mapping[str, Any], str]:
    completed = subprocess.run(
        list(command),
        input=(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            )
            if payload is not None
            else None
        ),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

    if completed.returncode != 0:
        return (
            False,
            {},
            completed.stderr.strip()
            or f"exit={completed.returncode}",
        )

    try:
        response = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return False, {}, "stdout was not valid JSON"

    if not isinstance(response, Mapping):
        return False, {}, "stdout JSON was not an object"

    return True, response, completed.stderr.strip()


def command_from_env(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name, "").strip()
    return tuple(shlex.split(raw)) if raw else ()


def static_checks() -> list[Check]:
    manifest = load_yaml(DEPLOYMENT / "capability-manifest.yaml")
    principal = load_yaml(DEPLOYMENT / "principal-policy.yaml")
    namespace = load_yaml(DEPLOYMENT / "namespace-mapping.yaml")
    retention = load_yaml(DEPLOYMENT / "retention-policy.yaml")

    required_classes = {
        "repository_fact",
        "dependency_finding",
        "implementation_surface",
        "rejected_approach",
        "context_requirement",
        "artifact_lineage",
    }
    supported = set(
        manifest["candidate_ingress"]["supported_classes"]
    )

    checks = [
        Check(
            name="manifest_enabled",
            passed=manifest.get("enabled") is True,
            required=True,
            details={},
        ),
        Check(
            name="supported_classes_exact",
            passed=supported == required_classes,
            required=True,
            details={
                "supported": sorted(supported),
                "expected": sorted(required_classes),
            },
        ),
        Check(
            name="service_principal",
            passed=(
                principal.get("principal", {}).get("type")
                == "service"
            ),
            required=True,
            details={
                "principal": principal.get("principal", {})
            },
        ),
        Check(
            name="delete_denied",
            passed=(
                principal.get("constraints", {}).get(
                    "may_delete_memory"
                )
                is False
            ),
            required=True,
            details={},
        ),
        Check(
            name="visibility_widening_forbidden",
            passed=(
                namespace.get("rules", {}).get(
                    "widening_forbidden"
                )
                is True
            ),
            required=True,
            details={},
        ),
        Check(
            name="raw_packets_owned_by_governance",
            passed=(
                retention.get("raw_subagent_packets", {}).get(
                    "owner"
                )
                == "Cursor-Governance"
                and retention.get(
                    "raw_subagent_packets", {}
                ).get("store_in_graphiti")
                is False
            ),
            required=True,
            details={},
        ),
    ]

    fixture_names = (
        "governed-candidate.json",
        "reuse-event.json",
        "path-invalidation.json",
        "capability-response.json",
    )
    for name in fixture_names:
        path = DEPLOYMENT / "fixtures" / name
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            passed = isinstance(value, Mapping)
        except (OSError, json.JSONDecodeError):
            passed = False
        checks.append(
            Check(
                name=f"fixture:{name}",
                passed=passed,
                required=True,
                details={"path": str(path)},
            )
        )

    return checks


def local_checks() -> list[Check]:
    checks = static_checks()

    cli = shutil.which("l9-memory")
    checks.append(
        Check(
            name="l9_memory_cli",
            passed=cli is not None,
            required=True,
            details={"path": cli},
        )
    )

    if cli:
        for command in (
            ("l9-memory", "resolve"),
            ("l9-memory", "health"),
        ):
            completed = subprocess.run(
                list(command),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            checks.append(
                Check(
                    name="command:" + " ".join(command),
                    passed=completed.returncode == 0,
                    required=True,
                    details={
                        "returncode": completed.returncode,
                        "stdout": completed.stdout[-2000:],
                        "stderr": completed.stderr[-2000:],
                    },
                )
            )

    return checks


def live_checks() -> list[Check]:
    checks = local_checks()

    commands = {
        "capabilities": command_from_env(
            "L9_SGD_GRAPHITI_CAPABILITIES_COMMAND"
        ),
        "ingest": command_from_env(
            "L9_SGD_GRAPHITI_INGEST_COMMAND"
        ),
        "search": command_from_env(
            "L9_SGD_GRAPHITI_SEARCH_COMMAND"
        ),
        "hydrate": command_from_env(
            "L9_SGD_GRAPHITI_HYDRATE_COMMAND"
        ),
        "reuse": command_from_env(
            "L9_SGD_GRAPHITI_REUSE_COMMAND"
        ),
        "invalidate": command_from_env(
            "L9_SGD_GRAPHITI_INVALIDATE_COMMAND"
        ),
    }

    for name, command in commands.items():
        checks.append(
            Check(
                name=f"configured:{name}",
                passed=bool(command),
                required=True,
                details={"command": list(command)},
            )
        )

    capability_command = commands["capabilities"]
    if capability_command:
        passed, response, error = run_json_command(
            capability_command
        )
        tool_plane_ready = bool(
            response.get("runtime", {}).get(
                "mcp_tool_plane_ready", False
            )
        )
        checks.append(
            Check(
                name="live_capability_response",
                passed=passed,
                required=True,
                details={
                    "response": response,
                    "error": error,
                },
            )
        )
        checks.append(
            Check(
                name="tool_plane_not_liveness_only",
                passed=passed and tool_plane_ready,
                required=True,
                details={
                    "mcp_tool_plane_ready": tool_plane_ready
                },
            )
        )

    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("static", "local", "live"),
        required=True,
    )
    args = parser.parse_args()

    checks = {
        "static": static_checks,
        "local": local_checks,
        "live": live_checks,
    }[args.mode]()

    ready = all(
        item.passed for item in checks if item.required
    )
    result = {
        "mode": args.mode,
        "ready": ready,
        "checks": [item.to_dict() for item in checks],
        "failures": [
            item.to_dict()
            for item in checks
            if item.required and not item.passed
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
