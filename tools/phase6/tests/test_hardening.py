#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/phase6/tests/test_hardening.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: test
# role: adversarial_authority_regression_suite
# tags: [phase6, security, provenance, tamper-resistance]
# owner: igor_beylin
# status: active
# version: 1.1.0
# updated: 2026-07-26
# Purpose: prove that forged, replayed, mutated, unbound, or weak Phase 6 evidence cannot authorize GO.
from __future__ import annotations

import base64
import copy
import datetime as dt
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from pathlib import Path

import jwt
import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import phase6ctl  # noqa: E402

from phase6_integrity import (  # noqa: E402
    canonical,
    private_key_pem,
    public_key_pem,
    sha256_bytes,
    sha256_file,
    sign_record,
)

CTL = SCRIPTS / "phase6ctl.py"
OIDC = SCRIPTS / "verify_oidc_claims.py"
POLICY = yaml.safe_load((ROOT / "references/GO_NO_GO_POLICY.yaml").read_text(encoding="utf-8"))


def run_script(script: Path, *args: object, ok: bool = True) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(script), *map(str, args)]
    try:
        process = subprocess.run(command, text=True, capture_output=True, check=False, timeout=45)
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(f"subprocess timed out: {command!r}\nstdout={exc.stdout!r}\nstderr={exc.stderr!r}") from exc
    if ok and process.returncode:
        raise AssertionError(process.stderr + process.stdout)
    return process


def ctl(*args: object, ok: bool = True) -> SimpleNamespace:
    stdout = io.StringIO()
    stderr = io.StringIO()
    old_argv = sys.argv
    try:
        sys.argv = [str(CTL), *map(str, args)]
        with redirect_stdout(stdout), redirect_stderr(stderr):
            returncode = int(phase6ctl.main())
    finally:
        sys.argv = old_argv
    result = SimpleNamespace(args=[str(CTL), *map(str, args)], returncode=returncode, stdout=stdout.getvalue(), stderr=stderr.getvalue())
    if ok and returncode:
        raise AssertionError(result.stderr + result.stdout)
    return result


def create_keypair(base: Path, prefix: str) -> tuple[Path, Path, Ed25519PrivateKey]:
    base.mkdir(parents=True, exist_ok=True)
    seed = hashlib.sha256(f"{base.resolve()}::{prefix}".encode("utf-8")).digest()
    private = Ed25519PrivateKey.from_private_bytes(seed)
    private_path = base / f"{prefix}-private.pem"
    public_path = base / f"{prefix}-public.pem"
    private_path.write_bytes(private_key_pem(private))
    public_path.write_bytes(public_key_pem(private.public_key()))
    return private_path, public_path, private


def write_config(path: Path, mode: str = "synthetic_test") -> Path:
    config = json.loads((ROOT / "config/phase6-inputs.example.json").read_text(encoding="utf-8"))
    config["schema"] = "l9.deploy.phase6-input/v2"
    config["authorization"] = {
        "execution_authorized": True,
        "change_ticket": "TEST-CHANGE",
        "operator": "test-operator",
        "independent_approver": "test-reviewer",
        "approved_at": "2026-07-26T12:00:00Z",
    }
    config["repository"].update(
        checkout_path="/tmp/l9-deploy",
        expected_ref="refs/heads/main",
        expected_commit_sha="b" * 40,
    )
    config["evidence"].update(run_root="/tmp/phase6", mode=mode)
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def details_for(evidence_class: str, check_id: str) -> dict[str, object]:
    digest = "sha256:" + "a" * 64
    values: dict[str, dict[str, object]] = {
        "repository": {
            "repository": "Quantum-L9/l9-deploy",
            "commit_sha": "b" * 40,
            "worktree_clean": True,
            "phase5_status": "PASS",
            "phase5_command_exit_code": 0,
            "production_contact": False,
        },
        "github": {
            "environment": "staging",
            "protected": True,
            "runner_labels": ["self-hosted", "l9-deployment", "hetzner-private"],
            "approval_count": 1,
            "repository": "Quantum-L9/l9-deploy",
            "production_contact": False,
        },
        "oidc": {
            "repository_claim": "Quantum-L9/l9-deploy",
            "environment_claim": "staging",
            "exchange_result": "ALLOWED",
            "policy_match": True,
            "token_signature_verified_by_issuer": True,
            "issuer": "https://token.actions.githubusercontent.com",
            "audience": "https://github.com/Quantum-L9",
            "subject": "repo:Quantum-L9/l9-deploy:environment:staging",
            "run_id": 123,
            "job_workflow_ref": "Quantum-L9/l9-deploy/.github/workflows/deploy.yml@refs/heads/main",
            "key_id": "test-kid",
            "algorithm": "RS256",
            "claims_sha256": "c" * 64,
            "authorization_class": "AUTHORIZED",
            "jti_sha256": "d" * 64,
            "issued_at": 1,
            "expires_at": 2,
            "jwks_source": "local-test-jwks",
            "jwks_sha256": "e" * 64,
            "exchange_request_id": "req-1",
            "exchange_http_status": 200,
            "identity_id": "identity-test",
            "production_contact": False,
        },
        "infisical": {
            "project_id": "project-test",
            "environment": "staging",
            "audit_review_clean": True,
            "unauthorized_access_count": 0,
            "event_count": 1,
            "redaction_verified": True,
            "audit_export_sha256": "f" * 64,
            "production_contact": False,
        },
        "deployment": {
            "image_digest": digest,
            "config_identity": "cfg-2",
            "health": "GREEN",
            "promotion_state": "ACTIVE",
            "attestation_verified": True,
            "active_state_unchanged": True,
            "candidate_rejected": True,
            "previous_image_digest": digest,
            "previous_config_identity": "cfg-1",
            "production_contact": False,
            "run_id": 123,
            "artifact_id": 456,
        },
        "rollback": {
            "prior_image_digest": digest,
            "restored_image_digest": digest,
            "prior_config_identity": "cfg-1",
            "restored_config_identity": "cfg-1",
            "health": "GREEN",
            "state_pointer_restored": True,
            "production_contact": False,
            "run_id": 123,
            "artifact_id": 456,
        },
        "leakage": {"finding_count": 0, "files_scanned": 5, "unauthorized_access_count": 0, "production_contact": False},
        "receipts": {"receipt_count": 3, "ledger_chain_valid": True, "all_digests_valid": True, "bundle_sha256": "e" * 64, "production_contact": False},
        "final": {
            "environment": "staging",
            "health": "GREEN",
            "worktree_clean": True,
            "terminal_release": "final-healthy-candidate",
            "production_contact": False,
            "active_image_digest": digest,
            "active_config_identity": "cfg-2",
        },
    }
    result = copy.deepcopy(values[evidence_class])
    if check_id == "oidc_negative_exchange_denied":
        result.update(repository_claim="Quantum-L9/unauthorized-probe", exchange_result="DENIED", policy_match=False, authorization_class="UNAUTHORIZED", subject="repo:Quantum-L9/unauthorized-probe:environment:staging", exchange_http_status=403)
    if check_id == "invalid_secret_containment_passed":
        result["promotion_state"] = "REJECTED"
    return result


def create_synthetic_record(stage: Path, run_dir: Path, check_id: str, private: Ed25519PrivateKey, overrides: dict[str, object] | None = None, wrong_key: Ed25519PrivateKey | None = None) -> Path:
    spec = POLICY["checks"][check_id]
    evidence_class = spec["evidence_class"]
    artifacts = []
    for index, role in enumerate(spec["artifact_requirements"]["required_roles"]):
        relative = f"evidence/artifacts/{check_id}/{role}-{index}.json"
        artifact_path = stage / relative
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps({"check_id": check_id, "role": role}) + "\n", encoding="utf-8")
        artifacts.append({
            "path": relative,
            "sha256": sha256_file(artifact_path),
            "size_bytes": artifact_path.stat().st_size,
            "media_type": "application/json",
            "role": role,
        })
    record = {
        "schema": "l9.deploy.phase6-evidence-record/v3",
        "run_binding": json.loads((run_dir / "integrity/run-binding.json").read_text(encoding="utf-8")),
        "evidence_class": evidence_class,
        "check_id": check_id,
        "scenario_id": spec["scenario"],
        "captured_at": "2026-07-26T12:00:00Z",
        "source": {
            "kind": "synthetic_test",
            "locator": f"synthetic://{check_id}",
            "producer": {
                "id": "synthetic_fixture",
                "version": "1.0.0",
                "executable_sha256": sha256_file(Path(__file__)),
            },
        },
        "status": "PASS",
        "subject": check_id,
        "assertions": copy.deepcopy(spec.get("assertions", {})),
        "artifacts": artifacts,
        "details": details_for(evidence_class, check_id),
    }
    if overrides:
        for dotted, value in overrides.items():
            target: dict[str, object] = record
            parts = dotted.split(".")
            for part in parts[:-1]:
                target = target[part]  # type: ignore[assignment,index]
            target[parts[-1]] = value
    signed = sign_record(record, wrong_key or private)
    output = stage / f"{check_id}.json"
    output.write_text(json.dumps(signed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


_EMPTY_RUN_CACHE: dict[str, tuple[Path, Path, Path, Path, Ed25519PrivateKey, Path]] = {}


def _init_run_fresh(base: Path, mode: str) -> tuple[Path, Path, Path, Ed25519PrivateKey, Path]:
    ledger_private_path, ledger_public_path, _ = create_keypair(base / "keys", "ledger")
    _, evidence_public_path, evidence_private = create_keypair(base / "keys", "evidence")
    config = write_config(base / "config.json", mode)
    process = ctl(
        "init",
        "--config", config,
        "--run-root", base / "runs",
        "--ledger-signing-key", ledger_private_path,
        "--trusted-evidence-public-key", evidence_public_path,
    )
    return Path(process.stdout.strip()), ledger_private_path, ledger_public_path, evidence_private, evidence_public_path


def init_run(base: Path, mode: str = "synthetic_test") -> tuple[Path, Path, Path, Ed25519PrivateKey, Path]:
    if mode not in _EMPTY_RUN_CACHE:
        cache_root = Path(tempfile.mkdtemp(prefix=f"phase6h2-empty-{mode}-"))
        run_dir, ledger_private, ledger_public, evidence_private, evidence_public = _init_run_fresh(cache_root, mode)
        _EMPTY_RUN_CACHE[mode] = (cache_root, run_dir, ledger_private, ledger_public, evidence_private, evidence_public)
    cache_root, cached_run, cached_ledger_private, cached_ledger_public, evidence_private, cached_evidence_public = _EMPTY_RUN_CACHE[mode]
    shutil.copytree(cache_root, base, dirs_exist_ok=True)
    return (
        base / cached_run.relative_to(cache_root),
        base / cached_ledger_private.relative_to(cache_root),
        base / cached_ledger_public.relative_to(cache_root),
        evidence_private,
        base / cached_evidence_public.relative_to(cache_root),
    )


_BUNDLE_CACHE: tuple[Path, Path, Path, Path, Path, Ed25519PrivateKey, Path] | None = None


def _build_bundle_fresh(base: Path, mutate: dict[str, dict[str, object]] | None = None) -> tuple[Path, Path, Path, Path, Ed25519PrivateKey, Path]:
    run_dir, ledger_private_path, ledger_public_path, evidence_private, evidence_public_path = init_run(base)
    stage = base / "stage"
    stage.mkdir()
    for check_id, spec in POLICY["checks"].items():
        if "evidence_class" not in spec:
            continue
        create_synthetic_record(stage, run_dir, check_id, evidence_private, (mutate or {}).get(check_id))
    ctl(
        "add-evidence-batch",
        "--run-dir", run_dir,
        "--directory", stage,
        "--artifact-root", stage,
        "--ledger-signing-key", ledger_private_path,
    )
    return run_dir, ledger_private_path, ledger_public_path, evidence_public_path, evidence_private, stage


def build_bundle(base: Path, mutate: dict[str, dict[str, object]] | None = None) -> tuple[Path, Path, Path, Path, Ed25519PrivateKey, Path]:
    global _BUNDLE_CACHE
    if mutate:
        return _build_bundle_fresh(base, mutate)
    if _BUNDLE_CACHE is None:
        cache_root = Path(tempfile.mkdtemp(prefix="phase6h2-bundle-cache-"))
        run_dir, ledger_private, ledger_public, evidence_public, evidence_private, stage = _build_bundle_fresh(cache_root)
        _BUNDLE_CACHE = (cache_root, run_dir, ledger_private, ledger_public, evidence_public, evidence_private, stage)
    cache_root, cached_run, cached_ledger_private, cached_ledger_public, cached_evidence_public, evidence_private, cached_stage = _BUNDLE_CACHE
    shutil.copytree(cache_root, base, dirs_exist_ok=True)
    return (
        base / cached_run.relative_to(cache_root),
        base / cached_ledger_private.relative_to(cache_root),
        base / cached_ledger_public.relative_to(cache_root),
        base / cached_evidence_public.relative_to(cache_root),
        evidence_private,
        base / cached_stage.relative_to(cache_root),
    )


class Phase6HardeningTests(unittest.TestCase):
    def test_synthetic_format_positive_control(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, private_path, public_path, evidence_public_path, _, _ = build_bundle(Path(directory))
            ctl("generate-report", "--run-dir", run_dir, "--ledger-signing-key", private_path)
            result = ctl("validate-evidence", "--run-dir", run_dir, "--trusted-ledger-public-key", public_path, "--trusted-evidence-public-key", evidence_public_path, "--allow-synthetic")
            self.assertIn('"status": "PASS"', result.stdout)

    def test_arbitrary_evidence_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run_dir, private_path, _, _, _ = init_run(base)
            fake = base / "fake.json"
            fake.write_text('{"status":"PASS"}', encoding="utf-8")
            result = ctl("add-evidence", "--run-dir", run_dir, "--file", fake, "--artifact-root", base, "--ledger-signing-key", private_path, ok=False)
            self.assertNotEqual(result.returncode, 0)

    def test_post_ingestion_record_mutation_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, private_path, public_path, evidence_public_path, _, _ = build_bundle(Path(directory))
            record = run_dir / "evidence/records/oidc_negative_exchange_denied.json"
            value = json.loads(record.read_text(encoding="utf-8"))
            value["details"]["exchange_result"] = "ALLOWED"
            value["assertions"]["unauthorized_exchange_allowed"] = True
            record.write_text(json.dumps(value), encoding="utf-8")
            ctl("generate-report", "--run-dir", run_dir, "--ledger-signing-key", private_path, ok=False)
            result = ctl("validate-evidence", "--run-dir", run_dir, "--trusted-ledger-public-key", public_path, "--trusted-evidence-public-key", evidence_public_path, "--allow-synthetic", ok=False)
            self.assertIn("evidence record digest mismatch", result.stdout)

    def test_rehashed_ledger_with_forged_record_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, private_path, public_path, evidence_public_path, _, _ = build_bundle(Path(directory))
            record = run_dir / "evidence/records/oidc_negative_exchange_denied.json"
            value = json.loads(record.read_text(encoding="utf-8"))
            value["details"]["exchange_result"] = "ALLOWED"
            record.write_text(json.dumps(value), encoding="utf-8")
            lines = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            previous = "0" * 64
            for event in lines:
                event["previous_hash"] = previous
                if event["event_type"] == "evidence_recorded" and event["payload"].get("check_id") == "oidc_negative_exchange_denied":
                    event["payload"]["record_sha256"] = sha256_file(record)
                unsigned = {key: item for key, item in event.items() if key not in {"event_hash", "signature"}}
                event["event_hash"] = sha256_bytes(canonical(unsigned))
                previous = event["event_hash"]
            (run_dir / "events.jsonl").write_text("\n".join(json.dumps(item, sort_keys=True) for item in lines) + "\n", encoding="utf-8")
            ctl("generate-report", "--run-dir", run_dir, "--ledger-signing-key", private_path, ok=False)
            decision = json.loads((run_dir / "derived-decision.json").read_text(encoding="utf-8"))
            self.assertTrue(any("signature invalid" in item for item in decision["integrity_errors"]))
            result = ctl("validate-evidence", "--run-dir", run_dir, "--trusted-ledger-public-key", public_path, "--trusted-evidence-public-key", evidence_public_path, "--allow-synthetic", ok=False)
            self.assertIn("signature invalid", result.stdout)

    def test_synthetic_all_true_record_rejected_in_live_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run_dir, private_path, _, private, _ = init_run(base, mode="live")
            stage = base / "stage"
            stage.mkdir()
            record = create_synthetic_record(stage, run_dir, "phase5_validation_passed", private)
            result = ctl("add-evidence", "--run-dir", run_dir, "--file", record, "--artifact-root", stage, "--ledger-signing-key", private_path, ok=False)
            self.assertIn("not allowed", result.stdout)

    def test_immediate_no_go_for_unauthorized_oidc_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            overrides = {
                "oidc_negative_exchange_denied": {
                    "details.exchange_result": "ALLOWED",
                    "assertions.exchange_denied": False,
                    "assertions.unauthorized_exchange_allowed": True,
                    "status": "FAIL",
                }
            }
            run_dir, private_path, _, _, _, _ = build_bundle(Path(directory), overrides)
            result = ctl("generate-report", "--run-dir", run_dir, "--ledger-signing-key", private_path, ok=False)
            decision = json.loads((run_dir / "derived-decision.json").read_text(encoding="utf-8"))
            self.assertEqual(decision["decision"], "NO_GO")
            self.assertIn("unauthorized_oidc_success", {item["rule_id"] for item in decision["immediate_no_go"]})
            self.assertNotEqual(result.returncode, 0)

    def test_fake_github_locator_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run_dir, private_path, _, private, _ = init_run(base, mode="live")
            stage = base / "stage"
            stage.mkdir()
            check_id = "protected_environment_enforced"
            spec = POLICY["checks"][check_id]
            relative = f"evidence/artifacts/{check_id}/github.json"
            artifact = stage / relative
            artifact.parent.mkdir(parents=True)
            artifact.write_text("{}\n", encoding="utf-8")
            record = {
                "schema": "l9.deploy.phase6-evidence-record/v3",
                "evidence_class": "github",
                "check_id": check_id,
                "scenario_id": "S00",
                "captured_at": "2026-07-26T12:00:00Z",
                "source": {"kind": "github_api_collector", "locator": "github-api://fake/run/not-a-number", "producer": {"id": spec["producer_id"], "version": "2.0.0", "executable_sha256": sha256_file(ROOT / spec["producer_script"])}},
                "status": "PASS",
                "subject": "fake",
                "assertions": copy.deepcopy(spec["assertions"]),
                "artifacts": [{"path": relative, "sha256": sha256_file(artifact), "size_bytes": artifact.stat().st_size, "media_type": "application/json", "role": "github_environment_export"}],
                "details": details_for("github", check_id),
            }
            path = stage / "record.json"
            path.write_text(json.dumps(sign_record(record, private)), encoding="utf-8")
            result = ctl("add-evidence", "--run-dir", run_dir, "--file", path, "--artifact-root", stage, "--ledger-signing-key", private_path, ok=False)
            self.assertIn("locator", result.stdout)

    def test_artifact_digest_mismatch_and_path_traversal_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run_dir, private_path, _, private, _ = init_run(base)
            stage = base / "stage"
            stage.mkdir()
            path = create_synthetic_record(stage, run_dir, "phase5_validation_passed", private)
            value = json.loads(path.read_text(encoding="utf-8"))
            value["artifacts"][0]["sha256"] = "f" * 64
            path.write_text(json.dumps(sign_record({key: item for key, item in value.items() if key != "attestation"}, private)), encoding="utf-8")
            result = ctl("add-evidence", "--run-dir", run_dir, "--file", path, "--artifact-root", stage, "--ledger-signing-key", private_path, ok=False)
            self.assertIn("digest mismatch", result.stderr + result.stdout)

            run_dir2, private_path2, _, private2, _ = init_run(base / "second")
            stage2 = base / "second-stage"
            stage2.mkdir()
            path2 = create_synthetic_record(stage2, run_dir2, "phase5_validation_passed", private2)
            value2 = json.loads(path2.read_text(encoding="utf-8"))
            value2["artifacts"][0]["path"] = "evidence/artifacts/phase5_validation_passed/../escape.json"
            path2.write_text(json.dumps(sign_record({key: item for key, item in value2.items() if key != "attestation"}, private2)), encoding="utf-8")
            result2 = ctl("add-evidence", "--run-dir", run_dir2, "--file", path2, "--artifact-root", stage2, "--ledger-signing-key", private_path2, ok=False)
            self.assertIn("normalized", result2.stdout)

    def test_wrong_key_verifier_envelope_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run_dir, private_path, _, private, _ = init_run(base)
            stage = base / "stage"
            stage.mkdir()
            wrong = Ed25519PrivateKey.from_private_bytes(b"\x99" * 32)
            path = create_synthetic_record(stage, run_dir, "oidc_positive_exchange_passed", private, wrong_key=wrong)
            result = ctl("add-evidence", "--run-dir", run_dir, "--file", path, "--artifact-root", stage, "--ledger-signing-key", private_path, ok=False)
            self.assertIn("attestation", result.stdout)

    def test_unledgered_record_and_artifact_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, private_path, public_path, evidence_public_path, _, _ = build_bundle(Path(directory))
            (run_dir / "evidence/records/unledgered.json").write_text("{}\n", encoding="utf-8")
            extra = run_dir / "evidence/artifacts/unledgered/extra.json"
            extra.parent.mkdir(parents=True)
            extra.write_text("{}\n", encoding="utf-8")
            ctl("generate-report", "--run-dir", run_dir, "--ledger-signing-key", private_path, ok=False)
            result = ctl("validate-evidence", "--run-dir", run_dir, "--trusted-ledger-public-key", public_path, "--trusted-evidence-public-key", evidence_public_path, "--allow-synthetic", ok=False)
            self.assertIn("unledgered evidence record", result.stdout)
            self.assertIn("unledgered proof artifact", result.stdout)

    def test_manual_go_report_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, private_path, public_path, evidence_public_path, _, _ = build_bundle(Path(directory))
            ctl("generate-report", "--run-dir", run_dir, "--ledger-signing-key", private_path)
            (run_dir / "GO_NO_GO_REPORT.md").write_text("# forged\n\n**Decision:** GO\n", encoding="utf-8")
            result = ctl("validate-evidence", "--run-dir", run_dir, "--trusted-ledger-public-key", public_path, "--trusted-evidence-public-key", evidence_public_path, "--allow-synthetic", ok=False)
            self.assertIn("not the generated report", result.stdout)


    def test_ledger_and_evidence_keys_must_be_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            private_path, public_path, _ = create_keypair(base / "keys", "shared")
            config = write_config(base / "config.json")
            result = ctl(
                "init",
                "--config", config,
                "--run-root", base / "runs",
                "--ledger-signing-key", private_path,
                "--trusted-evidence-public-key", public_path,
                ok=False,
            )
            self.assertIn("must be distinct", result.stderr + result.stdout)

    def test_cross_run_record_replay_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            _, _, _, evidence_public_path, _, stage = build_bundle(base / "run-a")
            ledger_private_b, _, _ = create_keypair(base / "run-b/keys", "ledger")
            config_b = write_config(base / "run-b/config.json")
            init_b = ctl(
                "init",
                "--config", config_b,
                "--run-root", base / "run-b/runs",
                "--ledger-signing-key", ledger_private_b,
                "--trusted-evidence-public-key", evidence_public_path,
            )
            run_b = Path(init_b.stdout.strip())
            replay = stage / "phase5_validation_passed.json"
            result = ctl(
                "add-evidence",
                "--run-dir", run_b,
                "--file", replay,
                "--artifact-root", stage,
                "--ledger-signing-key", ledger_private_b,
                ok=False,
            )
            self.assertIn("run binding", result.stdout)

    def test_local_jwks_is_forbidden_outside_test_mode_and_token_is_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            token_file = base / "token.jwt"
            token_file.write_text("not-a-token", encoding="utf-8")
            jwks = base / "jwks.json"
            jwks.write_text('{"keys": []}', encoding="utf-8")
            exchange = base / "exchange.json"
            exchange.write_text("{}", encoding="utf-8")
            result = run_script(
                OIDC,
                "--token-file", token_file,
                "--jwks-file", jwks,
                "--expected-audience", "https://github.com/Quantum-L9",
                "--expected-token-repository", "Quantum-L9/l9-deploy",
                "--mode", "positive",
                "--exchange-proof", exchange,
                "--output-root", base / "out",
                ok=False,
            )
            self.assertIn("forbidden", result.stderr + result.stdout)
            self.assertFalse(token_file.exists())

    def test_oidc_verifier_checks_real_signature_and_deletes_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            rsa_private = generate_private_key(public_exponent=65537, key_size=2048)
            jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(rsa_private.public_key()))
            jwk["kid"] = "kid-1"
            jwks = base / "jwks.json"
            jwks.write_text(json.dumps({"keys": [jwk]}), encoding="utf-8")
            current = int(dt.datetime.now(dt.timezone.utc).timestamp())
            claims = {
                "iss": "https://token.actions.githubusercontent.com",
                "aud": "https://github.com/Quantum-L9",
                "sub": "repo:Quantum-L9/l9-deploy:environment:staging",
                "jti": "jti-1",
                "repository": "Quantum-L9/l9-deploy",
                "environment": "staging",
                "run_id": "123",
                "job_workflow_ref": "Quantum-L9/l9-deploy/.github/workflows/deploy.yml@refs/heads/main",
                "iat": current,
                "nbf": current - 1,
                "exp": current + 300,
            }
            token = jwt.encode(claims, rsa_private, algorithm="RS256", headers={"kid": "kid-1"})
            token_file = base / "token.jwt"
            token_file.write_text(token, encoding="utf-8")
            exchange = base / "exchange.json"
            exchange.write_text(json.dumps({"schema": "l9.deploy.infisical-exchange/v2", "provider": "infisical", "result": "ALLOWED", "request_id": "req-1", "captured_at": "2026-07-26T12:00:00Z", "http_status": 200, "identity_id": "identity-test", "environment": "staging", "response_sha256": "f" * 64}), encoding="utf-8")
            result = run_script(OIDC, "--token-file", token_file, "--jwks-file", jwks, "--test-mode", "--expected-audience", "https://github.com/Quantum-L9", "--expected-token-repository", "Quantum-L9/l9-deploy", "--mode", "positive", "--exchange-proof", exchange, "--output-root", base / "out")
            self.assertIn('"signature_verified": true', result.stdout)
            self.assertFalse(token_file.exists())
            self.assertTrue((base / "out/evidence/artifacts/oidc_positive_exchange_passed/oidc-verification.json").is_file())

            header_part, payload_part, signature_part = token.split(".")
            signature = bytearray(base64.urlsafe_b64decode(signature_part + "=" * (-len(signature_part) % 4)))
            signature[0] ^= 0x01
            bad_signature = base64.urlsafe_b64encode(bytes(signature)).decode("ascii").rstrip("=")
            bad_token = ".".join([header_part, payload_part, bad_signature])
            bad_file = base / "bad.jwt"
            bad_file.write_text(bad_token, encoding="utf-8")
            result_bad = run_script(OIDC, "--token-file", bad_file, "--jwks-file", jwks, "--test-mode", "--expected-audience", "https://github.com/Quantum-L9", "--expected-token-repository", "Quantum-L9/l9-deploy", "--mode", "positive", "--exchange-proof", exchange, "--output-root", base / "bad-out", ok=False)
            self.assertNotEqual(result_bad.returncode, 0)
            self.assertFalse(bad_file.exists())

    def test_live_collector_to_attestor_to_ledger_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            ledger_private, _, _ = create_keypair(base / "keys", "ledger-live")
            evidence_private, evidence_public, _ = create_keypair(base / "keys", "evidence-live")
            config_path = write_config(base / "config.json", mode="live")
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["source_release"]["workflow_run_id"] = 123
            config["target"]["base_url"] = "https://staging.example.invalid"
            config["target"]["health_path"] = "/health"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            initialized = ctl(
                "init", "--config", config_path, "--run-root", base / "runs",
                "--ledger-signing-key", ledger_private,
                "--trusted-evidence-public-key", evidence_public,
            )
            run_dir = Path(initialized.stdout.strip())
            snapshot = {
                "schema": "l9.deploy.phase6-host-health/v1",
                "repository": "Quantum-L9/l9-deploy",
                "commit_sha": "b" * 40,
                "environment": "staging",
                "workflow_run_id": 123,
                "artifact_id": 456,
                "health": "GREEN",
                "active_image_digest": "sha256:" + "a" * 64,
                "active_config_identity": "cfg-final",
                "base_url": "https://staging.example.invalid",
                "health_path": "/health",
                "http_status": 200,
                "checked_at": "2026-07-26T12:00:00Z",
                "production_contact": False,
            }
            snapshot_path = base / "host-health.json"
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            stage = base / "stage"
            run_script(
                SCRIPTS / "collect_final_convergence.py",
                "--config", config_path, "--health-snapshot", snapshot_path,
                "--convergence-id", "live-pipeline-test", "--output-root", stage,
            )
            record = base / "final-record.json"
            run_script(
                SCRIPTS / "build_evidence_record.py",
                "--run-dir", run_dir, "--check-id", "final_staging_health_green",
                "--proof-file", stage / "evidence/artifacts/final_staging_health_green/final-convergence-proof.json",
                "--artifact-root", stage, "--evidence-signing-key", evidence_private,
                "--output", record,
            )
            imported = ctl(
                "add-evidence", "--run-dir", run_dir, "--file", record,
                "--artifact-root", stage, "--ledger-signing-key", ledger_private,
            )
            self.assertEqual(imported.returncode, 0)
            stored = json.loads((run_dir / "evidence/records/final_staging_health_green.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["status"], "PASS")
            self.assertEqual({item["role"] for item in stored["artifacts"]}, {"final_convergence_proof", "host_health_snapshot"})

    def test_final_health_snapshot_is_strictly_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config = json.loads((ROOT / "config/phase6-inputs.example.json").read_text(encoding="utf-8"))
            config["repository"]["expected_commit_sha"] = "b" * 40
            config["source_release"]["workflow_run_id"] = 123
            config["target"]["base_url"] = "https://staging.example.invalid"
            config["target"]["health_path"] = "/health"
            config_path = base / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            snapshot = {
                "schema": "l9.deploy.phase6-host-health/v1",
                "repository": "Quantum-L9/l9-deploy",
                "commit_sha": "b" * 40,
                "environment": "staging",
                "workflow_run_id": 123,
                "artifact_id": 456,
                "health": "GREEN",
                "active_image_digest": "sha256:" + "a" * 64,
                "active_config_identity": "cfg-final",
                "base_url": "https://staging.example.invalid",
                "health_path": "/health",
                "http_status": 200,
                "checked_at": "2026-07-26T12:00:00Z",
                "production_contact": False,
            }
            snapshot_path = base / "health.json"
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            collector = SCRIPTS / "collect_final_convergence.py"
            passed = run_script(collector, "--config", config_path, "--health-snapshot", snapshot_path, "--convergence-id", "test", "--output-root", base / "out")
            self.assertEqual(passed.returncode, 0)
            snapshot["commit_sha"] = "c" * 40
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            rejected = run_script(collector, "--config", config_path, "--health-snapshot", snapshot_path, "--convergence-id", "test-2", "--output-root", base / "bad", ok=False)
            self.assertIn("commit does not match", rejected.stderr + rejected.stdout)

    def test_workflow_receipt_rejects_extra_and_unbound_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config = write_config(base / "config.json")
            run_json = base / "run.json"
            run_json.write_text(json.dumps({"id": 123, "head_sha": "b" * 40, "repository": {"full_name": "Quantum-L9/l9-deploy"}}), encoding="utf-8")
            details = {
                "image_digest": "sha256:" + "a" * 64,
                "config_identity": "cfg-2",
                "health": "GREEN",
                "promotion_state": "ACTIVE",
                "run_id": 123,
                "artifact_id": 456,
                "production_contact": False,
            }
            receipt = {
                "schema": "l9.deploy.phase6-live-receipt/v1",
                "check_id": "healthy_candidate_deploy_passed",
                "repository": "Quantum-L9/l9-deploy",
                "run_id": 123,
                "artifact_id": 456,
                "captured_at": "2026-07-26T12:00:00Z",
                "details": details,
            }
            receipt_path = base / "receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            collector = SCRIPTS / "collect_workflow_evidence.py"
            passed = run_script(collector, "--config", config, "--check-id", "healthy_candidate_deploy_passed", "--run-json", run_json, "--artifact-id", 456, "--receipt", receipt_path, "--output-root", base / "out")
            self.assertEqual(passed.returncode, 0)
            receipt["operator_note"] = "untrusted"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            extra = run_script(collector, "--config", config, "--check-id", "healthy_candidate_deploy_passed", "--run-json", run_json, "--artifact-id", 456, "--receipt", receipt_path, "--output-root", base / "bad", ok=False)
            self.assertIn("fields mismatch", extra.stderr + extra.stdout)
            receipt.pop("operator_note")
            receipt["details"]["artifact_id"] = 999
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            unbound = run_script(collector, "--config", config, "--check-id", "healthy_candidate_deploy_passed", "--run-json", run_json, "--artifact-id", 456, "--receipt", receipt_path, "--output-root", base / "bad2", ok=False)
            self.assertIn("not bound", unbound.stderr + unbound.stdout)

    def test_infisical_audit_requires_nonempty_redacted_staging_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            collector = SCRIPTS / "collect_infisical_audit.py"
            audit = base / "audit.json"
            audit.write_text(json.dumps({"project_id": "project-1", "environment": "staging", "audit_id": "audit-1", "events": [{"authorized": True, "environment": "staging", "access_token": "secret-token-value"}]}), encoding="utf-8")
            leaked = run_script(collector, "--audit-export", audit, "--project-id", "project-1", "--audit-id", "audit-1", "--output-root", base / "leaked", ok=False)
            self.assertIn("redaction verification", leaked.stderr + leaked.stdout)
            audit.write_text(json.dumps({"project_id": "project-1", "environment": "staging", "audit_id": "audit-1", "events": [{"authorized": True, "environment": "staging", "access_token": "[REDACTED]"}]}), encoding="utf-8")
            passed = run_script(collector, "--audit-export", audit, "--project-id", "project-1", "--audit-id", "audit-1", "--output-root", base / "clean")
            self.assertEqual(passed.returncode, 0)
            audit.write_text(json.dumps({"events": []}), encoding="utf-8")
            empty = run_script(collector, "--audit-export", audit, "--project-id", "project-1", "--audit-id", "audit-1", "--output-root", base / "empty", ok=False)
            self.assertIn("non-empty", empty.stderr + empty.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
