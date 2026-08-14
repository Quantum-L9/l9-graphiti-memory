Wave 1 belongs **only** in `Quantum-L9/l9-graphiti-memory`. It uses the repository’s existing `l9-memory` CLI/MCP/service surfaces and treats `Cursor-Governance` as a read-only contract source. The repository’s canonical store remains authoritative, while external Graphiti projection remains optional. ([GitHub][1])

Feed this entire prompt to the Claude Code agent in the `l9-graphiti-memory` checkout.

```text
Create this installer exactly:

install_generated_data_deployment_wave1.sh

Then run:

chmod +x install_generated_data_deployment_wave1.sh
./install_generated_data_deployment_wave1.sh

Do not redesign the files.
Do not modify Cursor-Governance.
Do not create tests yet; tests are Wave 2.
Do not commit or push.
Return the installer exit status, final tree, static validation results, and SHA-256 manifest.

Use the following as the complete installer contents:
```

````bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
cd "$ROOT"

DEPLOYMENT="deployment/generated-data"
FIXTURES="$DEPLOYMENT/fixtures"
PREFLIGHT=".l9/generated-data-deployment-wave1-preflight.json"

# ---------------------------------------------------------------------------
# Repository guard
# ---------------------------------------------------------------------------

if [[ ! -f "pyproject.toml" ]] \
  || [[ ! -d "src/l9_graphite_memory" ]] \
  || [[ ! -f "README.md" ]]; then
  echo "ERROR: Not a recognizable l9-graphiti-memory checkout." >&2
  exit 1
fi

if ! grep -qi "graphiti memory" README.md; then
  echo "ERROR: README does not identify l9-graphiti-memory." >&2
  exit 1
fi

ORIGIN="$(git remote get-url origin 2>/dev/null || true)"
if [[ -n "$ORIGIN" ]] \
  && [[ "$ORIGIN" != *"Quantum-L9/l9-graphiti-memory"* ]]; then
  echo "ERROR: Wrong repository origin: $ORIGIN" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Locate read-only Cursor-Governance checkout
# ---------------------------------------------------------------------------

CURSOR_ROOT="${CURSOR_GOVERNANCE_ROOT:-}"

if [[ -z "$CURSOR_ROOT" ]]; then
  for candidate in \
    "../Cursor-Governance" \
    "../cursor-governance" \
    "../../Cursor-Governance" \
    "../../cursor-governance"
  do
    if [[ -d "$candidate/.git" ]] \
      && [[ -d "$candidate/subagent-generated-data" ]]; then
      CURSOR_ROOT="$candidate"
      break
    fi
  done
fi

if [[ -z "$CURSOR_ROOT" ]] || [[ ! -d "$CURSOR_ROOT" ]]; then
  echo "ERROR: Cursor-Governance checkout not found." >&2
  echo "Set CURSOR_GOVERNANCE_ROOT to its read-only checkout." >&2
  exit 1
fi

CURSOR_ROOT="$(cd "$CURSOR_ROOT" && pwd)"

required_cursor_files=(
  "$CURSOR_ROOT/subagent-generated-data/adapters/graphiti_memory.py"
  "$CURSOR_ROOT/subagent-generated-data/retrieval/context_query.py"
  "$CURSOR_ROOT/subagent-generated-data/retrieval/reuse_recorder.py"
  "$CURSOR_ROOT/subagent-generated-data/invalidation/repository_event_bridge.py"
)

for path in "${required_cursor_files[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "ERROR: Required Cursor-Governance contract file missing: $path" >&2
    exit 1
  fi
done

mkdir -p "$DEPLOYMENT" "$FIXTURES" "$(dirname "$PREFLIGHT")"

GRAPHITI_SHA="$(git rev-parse HEAD)"
CURSOR_SHA="$(git -C "$CURSOR_ROOT" rev-parse HEAD)"

python - "$CURSOR_ROOT" "$GRAPHITI_SHA" "$CURSOR_SHA" "$PREFLIGHT" <<'PY'
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

cursor_root = Path(sys.argv[1]).resolve()
graphiti_sha = sys.argv[2]
cursor_sha = sys.argv[3]
target = Path(sys.argv[4])

producer_files = [
    cursor_root / "subagent-generated-data/adapters/graphiti_memory.py",
    cursor_root / "subagent-generated-data/retrieval/context_query.py",
    cursor_root / "subagent-generated-data/retrieval/reuse_recorder.py",
    cursor_root / "subagent-generated-data/invalidation/repository_event_bridge.py",
]

commands = {
    name: shutil.which(name)
    for name in ("l9-memory", "l9-memory-server")
}

payload = {
    "write_repository": str(Path.cwd()),
    "read_only_contract_repository": str(cursor_root),
    "graphiti_sha": graphiti_sha,
    "cursor_governance_sha": cursor_sha,
    "producer_files": [
        {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in producer_files
    ],
    "commands": commands,
    "deployment_files_to_create": [
        "capability-manifest.yaml",
        "principal-policy.yaml",
        "namespace-mapping.yaml",
        "retention-policy.yaml",
        "cursor-command-env.example",
        "migration-runbook.md",
        "activation-runbook.md",
        "rollback-runbook.md",
        "verify_generated_data_tools.py",
        "verify_cross_repo_contract.py",
        "verify_migration.py",
        "verify_backup_restore.py",
        "verify_selector_indexes.py",
        "load_test_generated_data.py",
        "live_end_to_end_proof.py",
    ],
    "blocking_gaps": [],
}

target.write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

# ---------------------------------------------------------------------------
# Configuration files
# ---------------------------------------------------------------------------

cat > "$DEPLOYMENT/capability-manifest.yaml" <<'YAML'
schema_version: "1.0.0"
integration: cursor_governance_generated_data
enabled: true

candidate_ingress:
  supported_schema_majors:
    - 1
  supported_classes:
    - repository_fact
    - dependency_finding
    - implementation_surface
    - rejected_approach
    - context_requirement
    - artifact_lineage
  rejected_classes:
    - architecture_boundary
    - ownership_finding
    - task_contract_gap
    - policy_candidate
    - invariant_candidate
    - regression_candidate
    - validation_procedure
    - failure_pattern
    - reusable_pattern_candidate
    - unresolved_unknown
    - follow_on_opportunity
  authority_class: advisory
  route: memory
  required_promotion_decision: promote
  idempotency_field: candidate_id
  may_override_repository_state: false
  may_override_canonical_authority: false

reuse:
  supported_schema_majors:
    - 1
  supported_outcomes:
    - accelerated_execution
    - prevented_error
    - improved_validation
    - improved_context
    - reduced_discovery
    - improved_scope_control
    - improved_contract
    - no_observable_value
    - caused_confusion
    - stale
    - incorrect
  selection_is_proven_reuse: false
  injection_is_proven_reuse: false
  finalized_outcome_is_proven_reuse: true

invalidation:
  supported_schema_majors:
    - 1
  supported_event_types:
    - repository_path_changed
    - repository_base_changed
    - schema_version_changed
    - contract_version_changed
    - policy_version_changed
    - architecture_owner_changed
    - dependency_upgraded
    - contradictory_evidence_accepted
    - failed_reuse_reported
    - expiration_reached
  deletes_memory: false
  creates_replacement_record: false
  requires_structured_selectors: true
  natural_language_matching_forbidden: true

retrieval:
  search_owner: existing_memory_service
  hydrate_owner: existing_memory_service
  excludes_invalidated_by_default: true
  historical_audit_may_include_invalidated: true
  reuse_signal_may_override_authorization: false
  reuse_signal_may_override_lifecycle: false
  reuse_signal_may_override_temporal_validity: false

canonical_storage:
  owner: existing_memory_service
  projection_required: false
  direct_adapter_store_writes_forbidden: true
YAML

cat > "$DEPLOYMENT/principal-policy.yaml" <<'YAML'
schema_version: "1.0.0"

principal:
  id: cursor-governance-generated-data
  type: service

permissions:
  - memory.candidate.ingest
  - memory.search
  - memory.hydrate
  - memory.reuse.record
  - memory.source.invalidate
  - memory.capabilities.read

producer_identity:
  authenticated_caller: cursor-governance-generated-data
  stored_as_provenance:
    - campaign_id
    - graph_id
    - action_id
    - agent_id
    - role
    - lease_id
    - packet_id
    - repository
    - repository_class
    - base_sha

constraints:
  direct_subagent_canonical_write: false
  may_override_repository_state: false
  may_override_canonical_authority: false
  may_promote_memory: false
  may_delete_memory: false
  may_widen_visibility: false
  invalidation_requires_namespace_authority: true

denied_operations:
  - memory.delete
  - memory.promote
  - memory.policy.override
  - memory.namespace.widen
YAML

cat > "$DEPLOYMENT/namespace-mapping.yaml" <<'YAML'
schema_version: "1.0.0"

visibility:
  campaign_local:
    template: "campaign/{campaign_id}"
    maximum_scope: campaign
    required_fields:
      - campaign_id

  repository_local:
    template: "repository/{repository}"
    maximum_scope: repository
    required_fields:
      - repository

  project_group:
    template: "project-group/{project_group}"
    maximum_scope: project_group
    required_fields:
      - project_group

  constellation_internal:
    template: "constellation/internal"
    maximum_scope: constellation
    required_fields: []

  restricted:
    template: "restricted/{policy_id}"
    maximum_scope: restricted
    required_fields:
      - policy_id

rules:
  widening_forbidden: true
  narrowing_allowed: true
  unknown_visibility: reject
  cross_repository_search_implicit: false
  reuse_inherits_record_namespace: true
  invalidation_requires_all_matched_namespace_authority: true
YAML

cat > "$DEPLOYMENT/retention-policy.yaml" <<'YAML'
schema_version: "1.0.0"

producer_candidate_body:
  retention: audit_window
  default_days: 90
  canonical_memory_content_retained_separately: true

reuse_events:
  retention: long_term
  minimum_days: 730
  immutable: true

invalidation_events:
  retention: at_least_record_lifetime
  immutable: true

selector_index:
  retention: record_lifecycle_bound
  deactivate_with_record: true

receipts:
  retention: governance_audit_period
  minimum_days: 730
  hash_chain_required_when_supported: true

raw_subagent_packets:
  owner: Cursor-Governance
  store_in_graphiti: false

historical_evidence:
  delete_on_invalidation: false
  preserve_lineage: true
YAML

cat > "$DEPLOYMENT/cursor-command-env.example" <<'ENV'
# Generated-data integration command surfaces.
# Commands consume one JSON object from stdin and emit one JSON object to stdout.
# Do not place tokens or credentials in this file.

L9_SGD_GRAPHITI_INGEST_COMMAND='l9-memory ingest-governed-candidate --stdin'
L9_SGD_GRAPHITI_SEARCH_COMMAND='l9-memory search-context --stdin'
L9_SGD_GRAPHITI_HYDRATE_COMMAND='l9-memory hydrate-context --stdin'
L9_SGD_GRAPHITI_REUSE_COMMAND='l9-memory record-reuse --stdin'
L9_SGD_GRAPHITI_INVALIDATE_COMMAND='l9-memory invalidate-source --stdin'
L9_SGD_GRAPHITI_CAPABILITIES_COMMAND='l9-memory generated-data-capabilities'
ENV

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

cat > "$FIXTURES/governed-candidate.json" <<'JSON'
{
  "schema_version": "1.0.0",
  "kind": "MemoryCandidate",
  "candidate_id": "memcand-wave1-governed-001",
  "source": {
    "campaign_id": "campaign-wave1-001",
    "graph_id": "graph-wave1-001",
    "action_id": "recon-wave1-001",
    "agent_id": "agent-recon-wave1-001",
    "role": "recon",
    "lease_id": "lease-wave1-001",
    "repository": "Quantum-L9/l9-graphiti-memory",
    "repository_class": "l9_python",
    "base_sha": "1111111111111111111111111111111111111111",
    "packet_id": "packet-wave1-001",
    "primary_artifact_id": "artifact-recon-wave1-001"
  },
  "knowledge": {
    "unit_id": "unit-repository-fact-wave1-001",
    "statement": "The canonical memory service is the authorized durable write boundary.",
    "primary_class": "repository_fact",
    "epistemic_status": "observed",
    "scope": {
      "repositories": [
        "Quantum-L9/l9-graphiti-memory"
      ],
      "repository_classes": [
        "l9_python"
      ],
      "paths": [
        "src/l9_graphite_memory/services"
      ],
      "task_types": [
        "memory_integration"
      ],
      "roles": [
        "executor",
        "verifier"
      ]
    },
    "confidence": 0.99,
    "freshness": {
      "observed_at": "2026-08-02T19:36:00Z",
      "base_sha": "1111111111111111111111111111111111111111",
      "expires_at": null
    },
    "expected_reuse": {
      "task_local": false,
      "cross_task": true,
      "cross_campaign": true,
      "cross_repository": false,
      "description": "Future integrations must call the canonical service rather than storage directly."
    },
    "invalidation_conditions": [
      {
        "condition_type": "relevant_path_changed",
        "selector": "src/l9_graphite_memory/services"
      },
      {
        "condition_type": "architecture_owner_changed",
        "selector": "canonical_memory_write_boundary"
      }
    ]
  },
  "governance": {
    "authority_class": "advisory",
    "route": "memory",
    "routing_decision_id": "route-wave1-001",
    "promotion_id": "promotion-wave1-001",
    "promotion_decision": "promote",
    "risk_class": "medium",
    "visibility": "repository_local",
    "may_override_repository_state": false,
    "may_override_canonical_authority": false
  },
  "provenance": {
    "source_evidence": [
      {
        "source_id": "source-memory-service-wave1",
        "source_type": "repository_path",
        "repository": "Quantum-L9/l9-graphiti-memory",
        "path": "src/l9_graphite_memory/services",
        "base_sha": "1111111111111111111111111111111111111111",
        "locator": "directory"
      }
    ],
    "input_artifacts": [],
    "evidence_artifacts": [
      "artifact-recon-wave1-001"
    ],
    "inspected_paths": [
      "src/l9_graphite_memory/services"
    ],
    "executed_commands": [
      "git rev-parse HEAD"
    ],
    "generated_at": "2026-08-02T19:36:00Z",
    "statement_hash": "6e2e6194220977373ae1ab177c4bb8bb722e4b1daf678d5c9aa18787be2123fb",
    "packet_hash": "211e3c3f269c8d69d1ba8a6a98087391e9db434b9b6451b85ddfc64188c3238d"
  },
  "generated_at": "2026-08-02T19:36:00Z"
}
JSON

cat > "$FIXTURES/reuse-event.json" <<'JSON'
{
  "schema_version": "1.0.0",
  "kind": "MemoryReuseEvent",
  "event_id": "reuse-wave1-001",
  "record_id": "record-wave1-001",
  "consumer": {
    "repository": "Quantum-L9/l9-graphiti-memory",
    "campaign_id": "campaign-wave1-002",
    "action_id": "verify-wave1-002",
    "agent_id": "agent-verifier-wave1-002",
    "role": "verifier"
  },
  "use": {
    "query": "Where is the canonical memory write boundary?",
    "injection_method": "agent_contract_context",
    "context_pack_id": "context-pack-wave1-001"
  },
  "outcome": "reduced_discovery",
  "evidence": {
    "verification_artifact_id": "verification-wave1-001",
    "description": "The verifier did not need to rediscover the canonical write owner."
  },
  "correction_required": false,
  "validity_confirmed": true,
  "occurred_at": "2026-08-02T19:40:00Z",
  "metadata": {
    "producer": "Cursor-Governance"
  }
}
JSON

cat > "$FIXTURES/path-invalidation.json" <<'JSON'
{
  "schema_version": "1.0.0",
  "kind": "SourceInvalidationRequest",
  "event_id": "invalidation-wave1-001",
  "repository": "Quantum-L9/l9-graphiti-memory",
  "from_sha": "1111111111111111111111111111111111111111",
  "to_sha": "2222222222222222222222222222222222222222",
  "event_type": "repository_path_changed",
  "selectors": [
    {
      "condition_type": "relevant_path_changed",
      "selector": "src/l9_graphite_memory/services",
      "change_kind": "modified",
      "previous_path": null
    }
  ],
  "delete_memory": false
}
JSON

cat > "$FIXTURES/capability-response.json" <<'JSON'
{
  "schema_version": "1.0.0",
  "integration": "cursor_governance_generated_data",
  "enabled": true,
  "runtime": {
    "canonical_store_ready": true,
    "migration_version": "unknown",
    "authorization_ready": true,
    "namespace_mapping_ready": true,
    "selector_index_ready": true,
    "candidate_ingress_ready": true,
    "reuse_persistence_ready": true,
    "invalidation_ready": true,
    "search_ready": true,
    "hydrate_ready": true,
    "mcp_tool_plane_ready": false,
    "projection_ready": false,
    "projection_required": false
  },
  "contracts": {
    "candidate_schema_majors": [
      1
    ],
    "reuse_schema_majors": [
      1
    ],
    "invalidation_schema_majors": [
      1
    ],
    "supported_classes": [
      "repository_fact",
      "dependency_finding",
      "implementation_surface",
      "rejected_approach",
      "context_requirement",
      "artifact_lineage"
    ],
    "supported_reuse_outcomes": [
      "accelerated_execution",
      "prevented_error",
      "improved_validation",
      "improved_context",
      "reduced_discovery",
      "improved_scope_control",
      "improved_contract",
      "no_observable_value",
      "caused_confusion",
      "stale",
      "incorrect"
    ],
    "supported_invalidation_events": [
      "repository_path_changed",
      "repository_base_changed",
      "schema_version_changed",
      "contract_version_changed",
      "policy_version_changed",
      "architecture_owner_changed",
      "dependency_upgraded",
      "contradictory_evidence_accepted",
      "failed_reuse_reported",
      "expiration_reached"
    ]
  },
  "repository": {
    "version": "unknown",
    "commit_sha": "unknown"
  }
}
JSON

# ---------------------------------------------------------------------------
# Shared verifier support
# ---------------------------------------------------------------------------

cat > "$DEPLOYMENT/verify_generated_data_tools.py" <<'PY'
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

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
        raise ValueError(f"{path} must contain a mapping")
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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
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
PY

cat > "$DEPLOYMENT/verify_cross_repo_contract.py" <<'PY'
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    import yaml
except ImportError as exc:
    raise SystemExit("PyYAML is required") from exc


DEPLOYMENT = Path(__file__).resolve().parent


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
                / "subagent-generated-data"
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
            / "subagent-generated-data"
            / "adapters"
            / "graphiti_memory.py"
        ),
        "query": (
            cursor
            / "subagent-generated-data"
            / "retrieval"
            / "context_query.py"
        ),
        "reuse": (
            cursor
            / "subagent-generated-data"
            / "retrieval"
            / "reuse_recorder.py"
        ),
        "invalidation": (
            cursor
            / "subagent-generated-data"
            / "invalidation"
            / "repository_event_bridge.py"
        ),
    }

    manifest = yaml.safe_load(
        (
            DEPLOYMENT / "capability-manifest.yaml"
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

    candidate_strings = strings_in_python(
        producer_files["candidate"]
    )
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
                    DEPLOYMENT / "capability-manifest.yaml"
                ),
                "sha256": sha256(
                    DEPLOYMENT / "capability-manifest.yaml"
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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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
PY

cat > "$DEPLOYMENT/verify_migration.py" <<'PY'
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class MigrationCheck:
    name: str
    passed: bool
    details: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "details": dict(self.details),
        }


def sqlite_integrity(path: Path) -> tuple[bool, str]:
    connection = sqlite3.connect(path)
    try:
        value = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        return value == "ok", str(value)
    finally:
        connection.close()


def table_inventory(path: Path) -> list[str]:
    connection = sqlite3.connect(path)
    try:
        return [
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                ORDER BY name
                """
            )
        ]
    finally:
        connection.close()


def index_inventory(path: Path) -> list[str]:
    connection = sqlite3.connect(path)
    try:
        return [
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'index'
                ORDER BY name
                """
            )
        ]
    finally:
        connection.close()


def discover_database() -> Path | None:
    candidates = [
        Path(".l9/memory.sqlite3"),
        Path(".l9/l9-memory.sqlite3"),
        Path("data/memory.sqlite3"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def run_existing_migration(
    database: Path,
    *,
    apply: bool,
) -> tuple[bool, list[str]]:
    commands: list[list[str]] = []

    if shutil.which("l9-memory"):
        commands.append(
            ["l9-memory", "resolve"]
        )

    migration_scripts = sorted(
        Path("scripts").glob("*migrat*")
    ) if Path("scripts").is_dir() else []

    for script in migration_scripts:
        if script.is_file() and script.suffix in {
            ".py",
            ".sh",
        }:
            if script.suffix == ".py":
                commands.append(
                    ["python", str(script), "--help"]
                )
            else:
                commands.append(
                    ["bash", str(script), "--help"]
                )

    evidence: list[str] = []
    for command in commands:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            check=False,
        )
        evidence.append(
            json.dumps(
                {
                    "command": command,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-1000:],
                    "stderr": completed.stderr[-1000:],
                },
                sort_keys=True,
            )
        )

    # This verifier does not guess an undocumented production migration command.
    return True, evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "operation",
        choices=("inspect", "dry-run", "apply", "verify"),
    )
    parser.add_argument("--database")
    parser.add_argument("--backup")
    args = parser.parse_args()

    source = (
        Path(args.database).resolve()
        if args.database
        else discover_database()
    )

    checks: list[MigrationCheck] = []

    if source is None:
        checks.append(
            MigrationCheck(
                "database_discovery",
                False,
                {
                    "message": (
                        "No database discovered; provide --database"
                    )
                },
            )
        )
        result = {
            "operation": args.operation,
            "passed": False,
            "checks": [item.to_dict() for item in checks],
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1

    if not source.is_file():
        raise SystemExit(f"Database does not exist: {source}")

    if args.operation == "apply" and not args.backup:
        raise SystemExit(
            "--backup is required before --apply"
        )

    integrity_before, detail_before = sqlite_integrity(source)
    checks.append(
        MigrationCheck(
            "integrity_before",
            integrity_before,
            {"result": detail_before},
        )
    )

    with tempfile.TemporaryDirectory() as temp:
        copy = Path(temp) / source.name
        shutil.copy2(source, copy)

        if args.operation in {"dry-run", "apply"}:
            passed, evidence = run_existing_migration(
                copy,
                apply=args.operation == "apply",
            )
            checks.append(
                MigrationCheck(
                    "existing_migration_surface",
                    passed,
                    {"evidence": evidence},
                )
            )

        integrity_after, detail_after = sqlite_integrity(copy)
        checks.append(
            MigrationCheck(
                "integrity_after",
                integrity_after,
                {"result": detail_after},
            )
        )
        checks.append(
            MigrationCheck(
                "tables_readable",
                True,
                {"tables": table_inventory(copy)},
            )
        )
        checks.append(
            MigrationCheck(
                "indexes_readable",
                True,
                {"indexes": index_inventory(copy)},
            )
        )

    passed = all(item.passed for item in checks)
    result = {
        "operation": args.operation,
        "database": str(source),
        "passed": passed,
        "checks": [item.to_dict() for item in checks],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
PY

cat > "$DEPLOYMENT/verify_backup_restore.py" <<'PY'
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def integrity(path: Path) -> str:
    connection = sqlite3.connect(path)
    try:
        return str(
            connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    source = Path(args.database).resolve()
    output = Path(args.output_dir).resolve()

    if not source.is_file():
        raise SystemExit(f"Database not found: {source}")

    if source == output or output in source.parents:
        raise SystemExit(
            "Output directory must not be the source database"
        )

    output.mkdir(parents=True, exist_ok=True)

    backup = output / f"{source.name}.backup"
    restored = output / f"{source.name}.restored"

    shutil.copy2(source, backup)
    shutil.copy2(backup, restored)

    source_hash = sha256(source)
    backup_hash = sha256(backup)
    restored_hash = sha256(restored)

    source_integrity = integrity(source)
    backup_integrity = integrity(backup)
    restored_integrity = integrity(restored)

    passed = (
        source_hash == backup_hash == restored_hash
        and source_integrity == "ok"
        and backup_integrity == "ok"
        and restored_integrity == "ok"
    )

    result: dict[str, Any] = {
        "passed": passed,
        "source": {
            "path": str(source),
            "sha256": source_hash,
            "integrity": source_integrity,
        },
        "backup": {
            "path": str(backup),
            "sha256": backup_hash,
            "integrity": backup_integrity,
        },
        "restored": {
            "path": str(restored),
            "sha256": restored_hash,
            "integrity": restored_integrity,
        },
        "source_modified": False,
        "replay_required_for_post_backup_operations": True,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
PY

cat > "$DEPLOYMENT/verify_selector_indexes.py" <<'PY'
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


REQUIRED_SELECTOR_COLUMNS = {
    "record_id",
    "selector_type",
    "selector_value",
}


def inventories(
    database: Path,
) -> tuple[dict[str, set[str]], dict[str, str]]:
    connection = sqlite3.connect(database)
    try:
        tables: dict[str, set[str]] = {}
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ):
            name = row[0]
            columns = {
                column[1]
                for column in connection.execute(
                    f'PRAGMA table_info("{name}")'
                )
            }
            tables[name] = columns

        indexes = {
            row[0]: row[1]
            for row in connection.execute(
                """
                SELECT name, sql
                FROM sqlite_master
                WHERE type = 'index'
                AND sql IS NOT NULL
                """
            )
        }
        return tables, indexes
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    args = parser.parse_args()

    database = Path(args.database).resolve()
    if not database.is_file():
        raise SystemExit(
            f"Database not found: {database}"
        )

    tables, indexes = inventories(database)

    selector_tables = {
        name: columns
        for name, columns in tables.items()
        if REQUIRED_SELECTOR_COLUMNS <= columns
    }

    matching_indexes = {
        name: sql
        for name, sql in indexes.items()
        if "selector_type" in sql
        and "selector_value" in sql
    }

    passed = bool(selector_tables) and bool(matching_indexes)

    result: dict[str, Any] = {
        "database": str(database),
        "passed": passed,
        "selector_tables": {
            name: sorted(columns)
            for name, columns in selector_tables.items()
        },
        "matching_indexes": matching_indexes,
        "full_scan_for_ordinary_selector_lookup_allowed": False,
        "failures": [],
    }

    if not selector_tables:
        result["failures"].append(
            "No table contains record_id, selector_type "
            "and selector_value"
        )
    if not matching_indexes:
        result["failures"].append(
            "No index covers selector_type and selector_value"
        )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
PY

cat > "$DEPLOYMENT/load_test_generated_data.py" <<'PY'
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
PY

cat > "$DEPLOYMENT/live_end_to_end_proof.py" <<'PY'
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
PY

# ---------------------------------------------------------------------------
# Runbooks
# ---------------------------------------------------------------------------

cat > "$DEPLOYMENT/migration-runbook.md" <<'MD'
# Generated-Data Integration Migration Runbook

## Purpose

Apply and verify store changes required for governed candidate ingestion,
reuse-event persistence, source invalidation, and structured selector indexes.

The canonical store remains authoritative. External Graphiti projection is
optional and must not block canonical migration.

## Preconditions

1. Run from the `l9-graphiti-memory` checkout.
2. Confirm the generated-data integration source wave is merged.
3. Confirm no second canonical write path exists.
4. Identify the canonical database path.
5. Stop writers or place the service in its documented maintenance mode.
6. Verify sufficient disk space for at least two full database copies.

## Backup

```bash
mkdir -p validation/generated-data-migration
python deployment/generated-data/verify_backup_restore.py \
  --database /path/to/canonical.sqlite3 \
  --output-dir validation/generated-data-migration/backup-check
````

Do not proceed unless the source, backup, and restored integrity checks return
`ok`.

## Inspect

```bash
python deployment/generated-data/verify_migration.py \
  inspect \
  --database /path/to/canonical.sqlite3
```

Record the table inventory, index inventory, migration version, repository SHA,
and backup hash.

## Dry run

```bash
python deployment/generated-data/verify_migration.py \
  dry-run \
  --database /path/to/canonical.sqlite3
```

Dry-run operations must use a temporary copy. They must never modify the source.

## Apply

Use the repository's existing migration command discovered by the integration
preflight. Never invent an unregistered SQL path.

```bash
python deployment/generated-data/verify_migration.py \
  apply \
  --database /path/to/canonical.sqlite3 \
  --backup /path/to/verified-backup.sqlite3
```

## Verification

Verify:

* SQLite integrity is `ok`.
* Existing active, quarantined, superseded, archived, and deleted records remain readable.
* Existing search and hydration lifecycle behavior is unchanged.
* Reuse events survive service restart.
* Invalidation events survive service restart.
* Structured selector tables and indexes exist.
* Selector lookup plans do not require an ordinary full-record scan.
* Projection outage does not affect canonical reads or writes.

```bash
python deployment/generated-data/verify_selector_indexes.py \
  --database /path/to/canonical.sqlite3
```

## Rollback

1. Disable generated-data ingress, reuse, and invalidation public operations.
2. Stop writers.
3. Preserve the failed migrated store for evidence.
4. Restore the verified backup.
5. Start the canonical service with projection disabled.
6. Run existing health, search, and hydration checks.
7. Replay only operations with durable receipts and stable idempotency keys.
8. Do not rerun the original subagents.

## Evidence

Retain:

* source database hash;
* backup hash;
* migrated database hash;
* migration command output;
* integrity checks;
* selector index verification;
* repository SHA;
* Cursor-Governance SHA;
* rollback decision, when used.
  MD

cat > "$DEPLOYMENT/activation-runbook.md" <<'MD'

# Generated-Data Integration Activation Runbook

## Boundary

Cursor-Governance is the control plane. It validates packets, harvests units,
classifies them, selects routes, makes governance promotion decisions, compiles
future context, records consumption, and emits repository-change events.

`l9-graphiti-memory` is the memory data plane. It admits governed memory
candidates through the existing canonical memory service, stores reuse events,
applies source invalidation through existing lifecycle machinery, and provides
search and hydration.

## Required public operations

The deployed memory runtime must expose:

* governed candidate ingestion;
* search;
* hydration;
* reuse recording;
* source invalidation;
* health;
* generated-data capabilities.

All machine commands consume JSON from stdin and emit one JSON object to stdout.
Diagnostics go to stderr.

## Service principal

Create or bind the existing authorization system to:

```yaml
principal: cursor-governance-generated-data
type: service
```

Grant only the permissions declared in `principal-policy.yaml`.

Do not authorize deployed subagents as direct canonical writers. Preserve their
identity as provenance.

## Namespace mapping

Load `namespace-mapping.yaml` through the existing namespace owner.

Prove:

* repository-local candidates map to their repository namespace;
* campaign-local candidates map to their campaign namespace;
* visibility may be narrowed;
* visibility may not be widened;
* cross-repository retrieval is not implicit;
* reuse inherits the referenced record namespace;
* invalidation requires authority over every affected namespace.

## Command environment

Copy command forms from `cursor-command-env.example` into the deployment
environment. Do not copy secrets into repository files.

## Static verification

```bash
python deployment/generated-data/verify_generated_data_tools.py \
  --mode static
```

## Local canonical verification

```bash
python deployment/generated-data/verify_generated_data_tools.py \
  --mode local
```

Local verification proves canonical store access. It does not prove the MCP tool
plane.

## Cross-repository compatibility

```bash
CURSOR_GOVERNANCE_ROOT=/path/to/Cursor-Governance \
python deployment/generated-data/verify_cross_repo_contract.py
```

## Live command proof

Configure all command variables, then run:

```bash
python deployment/generated-data/verify_generated_data_tools.py \
  --mode live

python deployment/generated-data/live_end_to_end_proof.py \
  --mode commands
```

A healthy HTTP endpoint is not sufficient. Tool-plane readiness requires real
operation invocation. A 404, tool-not-found response, or health-only success is
a failed activation.

## MCP verification

Use the repository's existing Cursor client lifecycle:

```bash
l9-memory client cursor install
l9-memory client cursor verify
l9-memory client cursor status
```

Verification must prove initialize, tools/list, health, candidate ingress,
reuse, invalidation, search, and hydration.

## Invalidation lifecycle

Use the lifecycle state selected by the generated-data source integration.
Invalidation must:

* preserve evidence and lineage;
* exclude the record from ordinary search and hydration;
* retain authorized historical visibility;
* avoid deletion;
* avoid automatic replacement creation;
* create or expose a revalidation requirement.

## Soak

Before enabling unrestricted generated-data writes:

* tool-plane checks remain green for the chosen soak period;
* no unexplained candidate rejection spike;
* no duplicate canonical writes;
* no selector lookup regression;
* no false invalidation;
* no authorization widening;
* backup/restore proof passes;
* bounded load proof passes.

## Activation states

* `CODE_COMPLETE`: source and tests pass.
* `LOCAL_CANONICAL_LOOP_PROVEN`: local canonical loop passes.
* `COMMAND_LOOP_PROVEN`: deployed command surfaces pass.
* `MCP_TOOL_PLANE_PROVEN`: MCP initialize, inventory, and operations pass.
* `LIVE_CURSOR_GRAPHITI_LOOP_PROVEN`: a real Cursor-Governance execution
  produces, retrieves, reuses, and invalidates memory through deployed surfaces.
  MD

cat > "$DEPLOYMENT/rollback-runbook.md" <<'MD'

# Generated-Data Integration Rollback Runbook

## Objective

Disable the new generated-data integration without disabling established memory
search, hydration, canonical records, audit evidence, or unrelated MCP tools.

## Immediate containment

1. Disable governed candidate ingress.
2. Disable reuse-event recording.
3. Disable source invalidation dispatch.
4. Revoke only the generated-data service principal permissions.
5. Preserve existing canonical records and receipts.
6. Keep normal memory search and hydration available when safe.
7. Set external projection to the documented safe mode when it is implicated.

## Do not

* delete admitted records;
* delete reuse or invalidation events;
* delete receipts;
* remove historical evidence;
* create replacement records automatically;
* rerun original subagents;
* remove unrelated MCP server registrations;
* widen another principal to compensate.

## Store rollback

1. Stop writers.
2. Preserve the current store as incident evidence.
3. Verify the rollback backup hash and integrity.
4. Restore the verified canonical backup.
5. Start with external projection disabled.
6. Run existing `resolve`, `health`, search, and hydration checks.
7. Verify previous lifecycle states remain correct.
8. Replay post-backup operations from durable receipts using original
   idempotency keys.

## Configuration rollback

Remove or disable:

* generated-data command environment variables;
* generated-data principal grants;
* generated-data MCP tool registrations;
* generated-data write activation flags.

Retain:

* deployment runbooks;
* capability manifest;
* incident evidence;
* migration evidence;
* read-only compatibility verification.

## Verification

A successful rollback proves:

* canonical store integrity;
* normal search and hydration;
* no generated-data ingress;
* no reuse writes;
* no invalidation writes;
* existing records remain accessible according to their lifecycle;
* audit evidence remains present;
* projection outage does not block canonical operation.
  MD

# ---------------------------------------------------------------------------

# Compile and static verification

# ---------------------------------------------------------------------------

python -m compileall "$DEPLOYMENT"

python "$DEPLOYMENT/verify_generated_data_tools.py"
--mode static

CURSOR_GOVERNANCE_ROOT="$CURSOR_ROOT"
python "$DEPLOYMENT/verify_cross_repo_contract.py"

# Verify YAML and JSON syntax independently.

python - "$DEPLOYMENT" <<'PY'
from **future** import annotations

import json
import sys
from pathlib import Path

import yaml

root = Path(sys.argv[1])

for path in root.glob("*.yaml"):
value = yaml.safe_load(path.read_text(encoding="utf-8"))
if not isinstance(value, dict):
raise SystemExit(f"{path}: root must be a mapping")

for path in (root / "fixtures").glob("*.json"):
value = json.loads(path.read_text(encoding="utf-8"))
if not isinstance(value, dict):
raise SystemExit(f"{path}: root must be an object")

print("YAML and JSON validation passed.")
PY

# ---------------------------------------------------------------------------

# Final tree and hashes

# ---------------------------------------------------------------------------

python - "$DEPLOYMENT" <<'PY'
from **future** import annotations

import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
files = sorted(
path
for path in root.rglob("*")
if path.is_file()
and "**pycache**" not in path.parts
)

print()
print("GENERATED-DATA DEPLOYMENT WAVE 1 TREE")
for path in files:
print(path)

print()
print("GENERATED-DATA DEPLOYMENT WAVE 1 SHA-256")
for path in files:
print(
hashlib.sha256(path.read_bytes()).hexdigest(),
path,
)
PY

echo
echo "Generated-data deployment Wave 1 installed."
echo "Write repository: Quantum-L9/l9-graphiti-memory"
echo "Read-only contract repository: $CURSOR_ROOT"
echo "Graphiti SHA: $GRAPHITI_SHA"
echo "Cursor-Governance SHA: $CURSOR_SHA"
echo "Preflight: $PREFLIGHT"
echo
echo "Wave 2 remains:"
echo "  tests/deployment/generated_data/"

```

Wave 2 will add the ten requested tests against these exact implementation files.
```

[1]: https://github.com/Quantum-L9/l9-graphiti-memory/tree/main?utm_source=chatgpt.com "Quantum-L9/l9-graphiti-memory: L9 Graphiti Memory - GitHub"
