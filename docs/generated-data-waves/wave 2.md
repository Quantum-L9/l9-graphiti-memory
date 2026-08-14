Wave 2 installs only the requested test suite in **`Quantum-L9/l9-graphiti-memory`**. It treats the Wave 1 deployment files as the implementation under test and `Cursor-Governance` as the read-only producer-contract source. The repository’s documented local interface remains `l9-memory`, including canonical health, search, hydrate, and MCP server commands. ([GitHub][1])

Feed this entire prompt to the Claude Code agent in the `l9-graphiti-memory` checkout.

Install **Generated-Data Deployment Wave 2** in:

`Quantum-L9/l9-graphiti-memory`

Wave 1 must already exist under:

```text
deployment/generated-data/
```

This wave creates:

```text
tests/deployment/generated_data/
├── __init__.py
├── test_capability_manifest.py
├── test_principal_policy.py
├── test_namespace_mapping.py
├── test_command_protocols.py
├── test_cross_repo_contract.py
├── test_migration_verifier.py
├── test_backup_restore.py
├── test_selector_indexes.py
├── test_load_harness.py
└── test_live_proof_fail_closed.py
```

Create one installer:

```text
install_generated_data_deployment_wave2.sh
```

Use the complete installer below exactly.

Do not redesign the tests.
Do not modify Wave 1 files.
Do not modify Cursor-Governance.
Do not weaken assertions to obtain a pass.
Do not make network calls.
Do not require live credentials.
Do not commit or push.

After creating it, run:

```bash
chmod +x install_generated_data_deployment_wave2.sh
./install_generated_data_deployment_wave2.sh
```

Return only:

* repository guard result;
* installer exit status;
* static validation result;
* focused test result;
* Wave 1 regression verification result;
* cross-repository contract result;
* final test tree;
* SHA-256 manifest;
* genuine failures.

Use this installer:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
cd "$ROOT"

DEPLOYMENT="deployment/generated-data"
TESTS="tests/deployment/generated_data"

# ---------------------------------------------------------------------------
# Repository and Wave 1 guards
# ---------------------------------------------------------------------------

if [[ ! -f "pyproject.toml" ]] \
  || [[ ! -d "src/l9_graphite_memory" ]] \
  || [[ ! -f "README.md" ]]; then
  echo "ERROR: Not a recognizable l9-graphiti-memory checkout." >&2
  exit 1
fi

ORIGIN="$(git remote get-url origin 2>/dev/null || true)"
if [[ -n "$ORIGIN" ]] \
  && [[ "$ORIGIN" != *"Quantum-L9/l9-graphiti-memory"* ]]; then
  echo "ERROR: Wrong repository origin: $ORIGIN" >&2
  exit 1
fi

required_wave1_files=(
  "$DEPLOYMENT/capability-manifest.yaml"
  "$DEPLOYMENT/principal-policy.yaml"
  "$DEPLOYMENT/namespace-mapping.yaml"
  "$DEPLOYMENT/retention-policy.yaml"
  "$DEPLOYMENT/cursor-command-env.example"
  "$DEPLOYMENT/migration-runbook.md"
  "$DEPLOYMENT/activation-runbook.md"
  "$DEPLOYMENT/rollback-runbook.md"
  "$DEPLOYMENT/verify_generated_data_tools.py"
  "$DEPLOYMENT/verify_cross_repo_contract.py"
  "$DEPLOYMENT/verify_migration.py"
  "$DEPLOYMENT/verify_backup_restore.py"
  "$DEPLOYMENT/verify_selector_indexes.py"
  "$DEPLOYMENT/load_test_generated_data.py"
  "$DEPLOYMENT/live_end_to_end_proof.py"
  "$DEPLOYMENT/fixtures/governed-candidate.json"
  "$DEPLOYMENT/fixtures/reuse-event.json"
  "$DEPLOYMENT/fixtures/path-invalidation.json"
  "$DEPLOYMENT/fixtures/capability-response.json"
)

for required in "${required_wave1_files[@]}"; do
  if [[ ! -f "$required" ]]; then
    echo "ERROR: Required Wave 1 file missing: $required" >&2
    exit 1
  fi
done

CURSOR_ROOT="${CURSOR_GOVERNANCE_ROOT:-}"

if [[ -z "$CURSOR_ROOT" ]]; then
  for candidate in \
    "../Cursor-Governance" \
    "../cursor-governance" \
    "../../Cursor-Governance" \
    "../../cursor-governance"
  do
    if [[ -d "$candidate/subagent-generated-data" ]]; then
      CURSOR_ROOT="$candidate"
      break
    fi
  done
fi

if [[ -z "$CURSOR_ROOT" ]] || [[ ! -d "$CURSOR_ROOT" ]]; then
  echo "ERROR: Cursor-Governance checkout not found." >&2
  echo "Set CURSOR_GOVERNANCE_ROOT." >&2
  exit 1
fi

CURSOR_ROOT="$(cd "$CURSOR_ROOT" && pwd)"

mkdir -p "$TESTS"

cat > "$TESTS/__init__.py" <<'PY'
"""Deployment verification tests for Cursor-Governance generated data."""
PY

cat > "$TESTS/test_capability_manifest.py" <<'PY'
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, Mapping

import yaml


ROOT = Path(__file__).resolve().parents[3]
DEPLOYMENT = ROOT / "deployment" / "generated-data"


def load_yaml(name: str) -> Mapping[str, Any]:
    value = yaml.safe_load(
        (DEPLOYMENT / name).read_text(encoding="utf-8")
    )
    if not isinstance(value, Mapping):
        raise AssertionError(f"{name} root must be a mapping")
    return value


class CapabilityManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = load_yaml("capability-manifest.yaml")

    def test_manifest_identity_and_version(self) -> None:
        self.assertEqual(
            self.manifest["schema_version"],
            "1.0.0",
        )
        self.assertEqual(
            self.manifest["integration"],
            "cursor_governance_generated_data",
        )
        self.assertIs(
            self.manifest["enabled"],
            True,
        )

    def test_supported_classes_are_exact(self) -> None:
        expected = {
            "repository_fact",
            "dependency_finding",
            "implementation_surface",
            "rejected_approach",
            "context_requirement",
            "artifact_lineage",
        }
        actual = set(
            self.manifest["candidate_ingress"][
                "supported_classes"
            ]
        )
        self.assertEqual(actual, expected)

    def test_supported_and_rejected_classes_do_not_overlap(
        self,
    ) -> None:
        ingress = self.manifest["candidate_ingress"]
        supported = set(ingress["supported_classes"])
        rejected = set(ingress["rejected_classes"])
        self.assertFalse(
            supported & rejected,
            supported & rejected,
        )

    def test_governance_boundary_is_fail_closed(self) -> None:
        ingress = self.manifest["candidate_ingress"]
        self.assertEqual(
            ingress["authority_class"],
            "advisory",
        )
        self.assertEqual(
            ingress["route"],
            "memory",
        )
        self.assertEqual(
            ingress["required_promotion_decision"],
            "promote",
        )
        self.assertFalse(
            ingress[
                "may_override_repository_state"
            ]
        )
        self.assertFalse(
            ingress[
                "may_override_canonical_authority"
            ]
        )

    def test_invalidation_never_deletes(self) -> None:
        invalidation = self.manifest["invalidation"]
        self.assertFalse(
            invalidation["deletes_memory"]
        )
        self.assertFalse(
            invalidation[
                "creates_replacement_record"
            ]
        )
        self.assertTrue(
            invalidation[
                "requires_structured_selectors"
            ]
        )
        self.assertTrue(
            invalidation[
                "natural_language_matching_forbidden"
            ]
        )

    def test_reuse_requires_finalized_outcome(self) -> None:
        reuse = self.manifest["reuse"]
        self.assertFalse(
            reuse["selection_is_proven_reuse"]
        )
        self.assertFalse(
            reuse["injection_is_proven_reuse"]
        )
        self.assertTrue(
            reuse[
                "finalized_outcome_is_proven_reuse"
            ]
        )

    def test_projection_is_not_canonical_requirement(self) -> None:
        storage = self.manifest["canonical_storage"]
        self.assertFalse(
            storage["projection_required"]
        )
        self.assertTrue(
            storage[
                "direct_adapter_store_writes_forbidden"
            ]
        )

    def test_fixture_capability_response_agrees(
        self,
    ) -> None:
        response = json.loads(
            (
                DEPLOYMENT
                / "fixtures"
                / "capability-response.json"
            ).read_text(encoding="utf-8")
        )

        contracts = response["contracts"]
        manifest = self.manifest

        self.assertEqual(
            set(contracts["supported_classes"]),
            set(
                manifest["candidate_ingress"][
                    "supported_classes"
                ]
            ),
        )
        self.assertEqual(
            set(
                contracts[
                    "supported_reuse_outcomes"
                ]
            ),
            set(
                manifest["reuse"][
                    "supported_outcomes"
                ]
            ),
        )
        self.assertEqual(
            set(
                contracts[
                    "supported_invalidation_events"
                ]
            ),
            set(
                manifest["invalidation"][
                    "supported_event_types"
                ]
            ),
        )

    def test_runtime_fixture_does_not_claim_mcp_readiness(
        self,
    ) -> None:
        response = json.loads(
            (
                DEPLOYMENT
                / "fixtures"
                / "capability-response.json"
            ).read_text(encoding="utf-8")
        )
        self.assertFalse(
            response["runtime"][
                "mcp_tool_plane_ready"
            ]
        )


if __name__ == "__main__":
    unittest.main()
PY

cat > "$TESTS/test_principal_policy.py" <<'PY'
from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any, Mapping

import yaml


ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = (
    ROOT
    / "deployment"
    / "generated-data"
    / "principal-policy.yaml"
)


def load_policy() -> Mapping[str, Any]:
    value = yaml.safe_load(
        POLICY_PATH.read_text(encoding="utf-8")
    )
    if not isinstance(value, Mapping):
        raise AssertionError(
            "principal-policy root must be a mapping"
        )
    return value


class PrincipalPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy()

    def test_dedicated_service_principal(self) -> None:
        principal = self.policy["principal"]
        self.assertEqual(
            principal["id"],
            "cursor-governance-generated-data",
        )
        self.assertEqual(
            principal["type"],
            "service",
        )

    def test_minimum_required_permissions(self) -> None:
        permissions = set(self.policy["permissions"])
        self.assertEqual(
            permissions,
            {
                "memory.candidate.ingest",
                "memory.search",
                "memory.hydrate",
                "memory.reuse.record",
                "memory.source.invalidate",
                "memory.capabilities.read",
            },
        )

    def test_subagents_are_provenance_not_callers(
        self,
    ) -> None:
        producer = self.policy["producer_identity"]
        self.assertEqual(
            producer["authenticated_caller"],
            "cursor-governance-generated-data",
        )
        fields = set(
            producer["stored_as_provenance"]
        )
        self.assertTrue(
            {
                "campaign_id",
                "graph_id",
                "action_id",
                "agent_id",
                "role",
                "lease_id",
                "packet_id",
            }
            <= fields
        )

    def test_dangerous_authority_is_denied(self) -> None:
        constraints = self.policy["constraints"]
        self.assertFalse(
            constraints[
                "direct_subagent_canonical_write"
            ]
        )
        self.assertFalse(
            constraints[
                "may_override_repository_state"
            ]
        )
        self.assertFalse(
            constraints[
                "may_override_canonical_authority"
            ]
        )
        self.assertFalse(
            constraints["may_promote_memory"]
        )
        self.assertFalse(
            constraints["may_delete_memory"]
        )
        self.assertFalse(
            constraints["may_widen_visibility"]
        )

    def test_denied_operations_are_explicit(self) -> None:
        denied = set(self.policy["denied_operations"])
        self.assertEqual(
            denied,
            {
                "memory.delete",
                "memory.promote",
                "memory.policy.override",
                "memory.namespace.widen",
            },
        )

    def test_invalidation_requires_namespace_authority(
        self,
    ) -> None:
        self.assertTrue(
            self.policy["constraints"][
                "invalidation_requires_namespace_authority"
            ]
        )


if __name__ == "__main__":
    unittest.main()
PY

cat > "$TESTS/test_namespace_mapping.py" <<'PY'
from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any, Mapping

import yaml


ROOT = Path(__file__).resolve().parents[3]
PATH = (
    ROOT
    / "deployment"
    / "generated-data"
    / "namespace-mapping.yaml"
)


def load_mapping() -> Mapping[str, Any]:
    value = yaml.safe_load(
        PATH.read_text(encoding="utf-8")
    )
    if not isinstance(value, Mapping):
        raise AssertionError(
            "namespace-mapping root must be a mapping"
        )
    return value


def render_namespace(
    mapping: Mapping[str, Any],
    visibility: str,
    values: Mapping[str, str],
) -> str:
    visibility_map = mapping["visibility"]

    if visibility not in visibility_map:
        raise ValueError(
            f"Unknown visibility: {visibility}"
        )

    entry = visibility_map[visibility]
    for field in entry["required_fields"]:
        if not values.get(field):
            raise ValueError(
                f"Missing required field: {field}"
            )

    return str(entry["template"]).format(**values)


class NamespaceMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mapping = load_mapping()

    def test_campaign_mapping_is_deterministic(self) -> None:
        values = {"campaign_id": "campaign-001"}
        first = render_namespace(
            self.mapping,
            "campaign_local",
            values,
        )
        second = render_namespace(
            self.mapping,
            "campaign_local",
            values,
        )
        self.assertEqual(
            first,
            "campaign/campaign-001",
        )
        self.assertEqual(first, second)

    def test_repository_mapping_is_deterministic(
        self,
    ) -> None:
        result = render_namespace(
            self.mapping,
            "repository_local",
            {
                "repository": (
                    "Quantum-L9/l9-graphiti-memory"
                )
            },
        )
        self.assertEqual(
            result,
            (
                "repository/"
                "Quantum-L9/l9-graphiti-memory"
            ),
        )

    def test_required_fields_are_enforced(self) -> None:
        with self.assertRaises(ValueError):
            render_namespace(
                self.mapping,
                "repository_local",
                {},
            )

        with self.assertRaises(ValueError):
            render_namespace(
                self.mapping,
                "restricted",
                {},
            )

    def test_unknown_visibility_is_rejected(self) -> None:
        self.assertEqual(
            self.mapping["rules"][
                "unknown_visibility"
            ],
            "reject",
        )
        with self.assertRaises(ValueError):
            render_namespace(
                self.mapping,
                "public_internet",
                {},
            )

    def test_widening_is_forbidden(self) -> None:
        rules = self.mapping["rules"]
        self.assertTrue(
            rules["widening_forbidden"]
        )
        self.assertTrue(
            rules["narrowing_allowed"]
        )

    def test_cross_repository_search_not_implicit(
        self,
    ) -> None:
        self.assertFalse(
            self.mapping["rules"][
                "cross_repository_search_implicit"
            ]
        )

    def test_reuse_inherits_record_namespace(self) -> None:
        self.assertTrue(
            self.mapping["rules"][
                "reuse_inherits_record_namespace"
            ]
        )

    def test_invalidation_requires_all_authority(
        self,
    ) -> None:
        self.assertTrue(
            self.mapping["rules"][
                "invalidation_requires_all_"
                "matched_namespace_authority"
            ]
        )


if __name__ == "__main__":
    unittest.main()
PY

cat > "$TESTS/test_command_protocols.py" <<'PY'
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Any, Mapping


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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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
PY

cat > "$TESTS/test_cross_repo_contract.py" <<'PY'
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[3]
DEPLOYMENT = ROOT / "deployment" / "generated-data"
VERIFIER = DEPLOYMENT / "verify_cross_repo_contract.py"


def locate_cursor() -> Path | None:
    candidates = [
        os.environ.get("CURSOR_GOVERNANCE_ROOT"),
        ROOT.parent / "Cursor-Governance",
        ROOT.parent / "cursor-governance",
        ROOT.parent.parent / "Cursor-Governance",
        ROOT.parent.parent / "cursor-governance",
    ]

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).resolve()
        if (
            path
            / "subagent-generated-data"
            / "adapters"
            / "graphiti_memory.py"
        ).is_file():
            return path
    return None


class CrossRepositoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cursor = locate_cursor()
        if cls.cursor is None:
            raise unittest.SkipTest(
                "Cursor-Governance checkout unavailable"
            )

    def test_actual_producer_contract_is_compatible(
        self,
    ) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(VERIFIER),
                "--cursor-root",
                str(self.cursor),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=30,
        )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr or completed.stdout,
        )

        result = json.loads(completed.stdout)
        self.assertTrue(result["compatible"])
        self.assertFalse(result["differences"])
        self.assertNotEqual(
            result["cursor_governance_sha"],
            "unknown",
        )
        self.assertNotEqual(
            result["graphiti_sha"],
            "unknown",
        )

    def test_all_producer_files_are_hashed(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(VERIFIER),
                "--cursor-root",
                str(self.cursor),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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

        self.assertEqual(
            set(result["producer_files"]),
            {
                "candidate",
                "query",
                "reuse",
                "invalidation",
            },
        )

        for value in result["producer_files"].values():
            self.assertEqual(
                len(value["sha256"]),
                64,
            )

    def test_fixtures_use_supported_values(self) -> None:
        manifest = __import__("yaml").safe_load(
            (
                DEPLOYMENT / "capability-manifest.yaml"
            ).read_text(encoding="utf-8")
        )
        candidate = json.loads(
            (
                DEPLOYMENT
                / "fixtures"
                / "governed-candidate.json"
            ).read_text(encoding="utf-8")
        )
        reuse = json.loads(
            (
                DEPLOYMENT
                / "fixtures"
                / "reuse-event.json"
            ).read_text(encoding="utf-8")
        )
        invalidation = json.loads(
            (
                DEPLOYMENT
                / "fixtures"
                / "path-invalidation.json"
            ).read_text(encoding="utf-8")
        )

        self.assertIn(
            candidate["knowledge"]["primary_class"],
            manifest["candidate_ingress"][
                "supported_classes"
            ],
        )
        self.assertIn(
            reuse["outcome"],
            manifest["reuse"]["supported_outcomes"],
        )
        self.assertIn(
            invalidation["event_type"],
            manifest["invalidation"][
                "supported_event_types"
            ],
        )

    def test_candidate_preserves_advisory_boundary(
        self,
    ) -> None:
        candidate = json.loads(
            (
                DEPLOYMENT
                / "fixtures"
                / "governed-candidate.json"
            ).read_text(encoding="utf-8")
        )
        governance = candidate["governance"]
        self.assertEqual(
            governance["authority_class"],
            "advisory",
        )
        self.assertEqual(
            governance["route"],
            "memory",
        )
        self.assertEqual(
            governance["promotion_decision"],
            "promote",
        )
        self.assertFalse(
            governance[
                "may_override_repository_state"
            ]
        )
        self.assertFalse(
            governance[
                "may_override_canonical_authority"
            ]
        )


if __name__ == "__main__":
    unittest.main()
PY

cat > "$TESTS/test_migration_verifier.py" <<'PY'
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VERIFIER = (
    ROOT
    / "deployment"
    / "generated-data"
    / "verify_migration.py"
)


def create_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE memory_records (
                record_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                body TEXT NOT NULL
            );

            INSERT INTO memory_records (
                record_id,
                state,
                body
            ) VALUES
                ('active-1', 'active', 'a'),
                ('quarantine-1', 'quarantined', 'b'),
                ('archive-1', 'archived', 'c'),
                ('deleted-1', 'deleted', 'd');

            CREATE TABLE schema_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT INTO schema_metadata (
                key,
                value
            ) VALUES ('version', 'previous');
            """
        )
        connection.commit()
    finally:
        connection.close()


def invoke(
    operation: str,
    database: Path,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            operation,
            "--database",
            str(database),
            *extra,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=60,
    )


class MigrationVerifierTests(unittest.TestCase):
    def test_inspect_preserves_source_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "memory.sqlite3"
            create_database(database)
            before = database.read_bytes()

            completed = invoke(
                "inspect",
                database,
            )

            after = database.read_bytes()

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        self.assertEqual(before, after)
        result = json.loads(completed.stdout)
        self.assertTrue(result["passed"])

    def test_dry_run_uses_copy_and_preserves_source(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "memory.sqlite3"
            create_database(database)
            before = database.read_bytes()

            completed = invoke(
                "dry-run",
                database,
            )

            after = database.read_bytes()

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        self.assertEqual(before, after)

    def test_apply_requires_backup_argument(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "memory.sqlite3"
            create_database(database)

            completed = invoke(
                "apply",
                database,
            )

        self.assertNotEqual(
            completed.returncode,
            0,
        )
        self.assertIn(
            "--backup is required",
            completed.stderr,
        )

    def test_mixed_lifecycle_rows_remain_readable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "memory.sqlite3"
            create_database(database)

            completed = invoke(
                "verify",
                database,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr,
            )

            connection = sqlite3.connect(database)
            try:
                states = {
                    row[0]
                    for row in connection.execute(
                        "SELECT state FROM memory_records"
                    )
                }
            finally:
                connection.close()

        self.assertEqual(
            states,
            {
                "active",
                "quarantined",
                "archived",
                "deleted",
            },
        )

    def test_missing_database_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "missing.sqlite3"

            completed = invoke(
                "inspect",
                database,
            )

        self.assertNotEqual(
            completed.returncode,
            0,
        )
        self.assertIn(
            "Database does not exist",
            completed.stderr,
        )


if __name__ == "__main__":
    unittest.main()
PY

cat > "$TESTS/test_backup_restore.py" <<'PY'
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VERIFIER = (
    ROOT
    / "deployment"
    / "generated-data"
    / "verify_backup_restore.py"
)


def create_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE records (
                id TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT INTO records VALUES (
                'record-1',
                'canonical'
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


def sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


class BackupRestoreTests(unittest.TestCase):
    def test_backup_restore_is_byte_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = root / "source.sqlite3"
            output = root / "output"
            create_database(database)

            before = sha256(database)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(VERIFIER),
                    "--database",
                    str(database),
                    "--output-dir",
                    str(output),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=30,
            )

            after = sha256(database)

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr,
        )
        self.assertEqual(before, after)

        result = json.loads(completed.stdout)
        self.assertTrue(result["passed"])
        self.assertEqual(
            result["source"]["sha256"],
            result["backup"]["sha256"],
        )
        self.assertEqual(
            result["backup"]["sha256"],
            result["restored"]["sha256"],
        )
        self.assertFalse(
            result["source_modified"]
        )

    def test_source_database_is_not_modified(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = root / "source.sqlite3"
            output = root / "output"
            create_database(database)
            before = database.read_bytes()

            subprocess.run(
                [
                    sys.executable,
                    str(VERIFIER),
                    "--database",
                    str(database),
                    "--output-dir",
                    str(output),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                timeout=30,
            )

            after = database.read_bytes()

        self.assertEqual(before, after)

    def test_missing_database_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(VERIFIER),
                    "--database",
                    str(root / "missing.sqlite3"),
                    "--output-dir",
                    str(root / "output"),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=30,
            )

        self.assertNotEqual(
            completed.returncode,
            0,
        )
        self.assertIn(
            "Database not found",
            completed.stderr,
        )


if __name__ == "__main__":
    unittest.main()
PY

cat > "$TESTS/test_selector_indexes.py" <<'PY'
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VERIFIER = (
    ROOT
    / "deployment"
    / "generated-data"
    / "verify_selector_indexes.py"
)


def create_indexed_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE memory_source_selectors (
                selector_id TEXT PRIMARY KEY,
                record_id TEXT NOT NULL,
                repository TEXT NOT NULL,
                selector_type TEXT NOT NULL,
                selector_value TEXT NOT NULL,
                active INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                deactivated_at TEXT
            );

            CREATE INDEX
                idx_selector_repository_value
            ON memory_source_selectors (
                repository,
                selector_type,
                selector_value,
                active
            );

            CREATE INDEX
                idx_selector_record_active
            ON memory_source_selectors (
                record_id,
                active
            );

            INSERT INTO memory_source_selectors VALUES (
                'selector-1',
                'record-1',
                'Quantum-L9/example',
                'relevant_path_changed',
                'src/a.py',
                1,
                '2026-08-02T00:00:00Z',
                NULL
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


class SelectorIndexTests(unittest.TestCase):
    def test_indexed_schema_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "indexed.sqlite3"
            create_indexed_database(database)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(VERIFIER),
                    "--database",
                    str(database),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
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
        self.assertTrue(result["selector_tables"])
        self.assertTrue(result["matching_indexes"])

    def test_unindexed_schema_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "unindexed.sqlite3"
            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    """
                    CREATE TABLE records (
                        record_id TEXT PRIMARY KEY,
                        body TEXT
                    )
                    """
                )
                connection.commit()
            finally:
                connection.close()

            completed = subprocess.run(
                [
                    sys.executable,
                    str(VERIFIER),
                    "--database",
                    str(database),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
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
        self.assertTrue(result["failures"])

    def test_query_plan_uses_selector_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "indexed.sqlite3"
            create_indexed_database(database)

            connection = sqlite3.connect(database)
            try:
                plan = list(
                    connection.execute(
                        """
                        EXPLAIN QUERY PLAN
                        SELECT record_id
                        FROM memory_source_selectors
                        WHERE
                            repository = ?
                            AND selector_type = ?
                            AND selector_value = ?
                            AND active = 1
                        """,
                        (
                            "Quantum-L9/example",
                            "relevant_path_changed",
                            "src/a.py",
                        ),
                    )
                )
            finally:
                connection.close()

        details = " ".join(str(row) for row in plan)
        self.assertIn(
            "INDEX",
            details.upper(),
        )

    def test_unrelated_selector_is_not_matched(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "indexed.sqlite3"
            create_indexed_database(database)

            connection = sqlite3.connect(database)
            try:
                rows = list(
                    connection.execute(
                        """
                        SELECT record_id
                        FROM memory_source_selectors
                        WHERE
                            repository = ?
                            AND selector_type = ?
                            AND selector_value = ?
                            AND active = 1
                        """,
                        (
                            "Quantum-L9/example",
                            "relevant_path_changed",
                            "src/unrelated.py",
                        ),
                    )
                )
            finally:
                connection.close()

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
PY

cat > "$TESTS/test_load_harness.py" <<'PY'
from __future__ import annotations

import json
import os
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
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
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
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
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
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
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
PY

cat > "$TESTS/test_live_proof_fail_closed.py" <<'PY'
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Mapping


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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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

            state = directory / "state.json"

            command = write_command(
                directory,
                "router",
                f"""
                import json
                import os
                import sys

                name = os.path.basename(sys.argv[0])
                payload = {{}}
                try:
                    payload = json.load(sys.stdin)
                except Exception:
                    pass

                print(
                    json.dumps(
                        {{
                            "status": "accepted",
                            "record_id": "record-1",
                            "storage_committed": True,
                            "runtime": {{
                                "candidate_ingress_ready": True,
                                "mcp_tool_plane_ready": True
                            }},
                            "records": [
                                {{"record_id": "record-1"}}
                            ]
                        }}
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
PY

# ---------------------------------------------------------------------------
# Static validation
# ---------------------------------------------------------------------------

python - <<'PY'
from __future__ import annotations

import ast
from pathlib import Path

root = Path("tests/deployment/generated_data")
errors: list[str] = []

for path in sorted(root.glob("*.py")):
    try:
        ast.parse(
            path.read_text(encoding="utf-8")
        )
    except SyntaxError as exc:
        errors.append(f"{path}: {exc}")

if errors:
    print(
        "GENERATED-DATA DEPLOYMENT WAVE 2 "
        "STATIC VALIDATION FAILED"
    )
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)

print(
    "GENERATED-DATA DEPLOYMENT WAVE 2 "
    "STATIC VALIDATION PASSED"
)
PY

python -m compileall "$TESTS"

# ---------------------------------------------------------------------------
# Wave 1 regression verification
# ---------------------------------------------------------------------------

python "$DEPLOYMENT/verify_generated_data_tools.py" \
  --mode static

CURSOR_GOVERNANCE_ROOT="$CURSOR_ROOT" \
python "$DEPLOYMENT/verify_cross_repo_contract.py"

# ---------------------------------------------------------------------------
# Focused Wave 2 tests
# ---------------------------------------------------------------------------

CURSOR_GOVERNANCE_ROOT="$CURSOR_ROOT" \
python -m unittest discover \
  -s "$TESTS" \
  -p 'test_*.py' \
  -v

# Run through pytest when available, without requiring pytest installation.
if command -v uv >/dev/null 2>&1 \
  && uv run python -c 'import pytest' >/dev/null 2>&1
then
  CURSOR_GOVERNANCE_ROOT="$CURSOR_ROOT" \
  uv run pytest -q "$TESTS"
elif python -c 'import pytest' >/dev/null 2>&1
then
  CURSOR_GOVERNANCE_ROOT="$CURSOR_ROOT" \
  python -m pytest -q "$TESTS"
fi

# ---------------------------------------------------------------------------
# Final tree and hashes
# ---------------------------------------------------------------------------

python - <<'PY'
from __future__ import annotations

import hashlib
from pathlib import Path

root = Path("tests/deployment/generated_data")
files = sorted(
    path
    for path in root.rglob("*")
    if path.is_file()
    and "__pycache__" not in path.parts
)

print()
print("GENERATED-DATA DEPLOYMENT WAVE 2 TREE")
for path in files:
    print(path)

print()
print("GENERATED-DATA DEPLOYMENT WAVE 2 SHA-256")
for path in files:
    digest = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
    print(f"{digest}  {path}")
PY

echo
echo "Generated-data deployment Wave 2 installed."
echo "Write repository: Quantum-L9/l9-graphiti-memory"
echo "Read-only producer repository: $CURSOR_ROOT"
echo "Tests installed: $TESTS"
```

The Wave 2 fail-closed tests explicitly cover the currently documented risk where an endpoint may appear healthy while the MCP tool route is unavailable; health-only success and HTTP 404 tool behavior cannot produce a live activation result. ([GitHub][2])

[1]: https://github.com/Quantum-L9/l9-graphiti-memory/tree/main?utm_source=chatgpt.com "Quantum-L9/l9-graphiti-memory: L9 Graphiti Memory - GitHub"
[2]: https://github.com/Quantum-L9/Cursor-Governance/blob/main/reports/GRAPHITI%20GAPS%20TO%20FILL.md?utm_source=chatgpt.com "GRAPHITI GAPS TO FILL.md - GitHub"
