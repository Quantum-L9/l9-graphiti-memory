#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: release-work/l9-deploy-phase6-operator/scripts/verify_oidc_claims.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: oidc_cryptographic_verifier
# tags: [oidc, jwt, jwks, claims, redaction, evidence]
# owner: igor_beylin
# status: active
# version: 2.0.0
# updated: 2026-07-26
# Purpose: cryptographically verify GitHub OIDC JWTs and emit redacted proof without retaining the raw token.
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

import jwt

from phase6_integrity import canonical, sha256_bytes, sha256_file

ISSUER = "https://token.actions.githubusercontent.com"
OFFICIAL_JWKS_URL = f"{ISSUER}/.well-known/jwks"
CANONICAL_REPOSITORY = "Quantum-L9/l9-deploy"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_jwks(file_path: Path | None, url: str) -> dict[str, Any]:
    if file_path:
        value = json.loads(file_path.read_text(encoding="utf-8"))
    else:
        with urllib.request.urlopen(url, timeout=15) as response:
            value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("keys"), list):
        raise ValueError("JWKS must contain a keys array")
    return value


def load_exchange_proof(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema", "provider", "result", "request_id", "captured_at",
        "http_status", "identity_id", "environment", "response_sha256",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("exchange proof does not match the strict Infisical exchange contract")
    if value["schema"] != "l9.deploy.infisical-exchange/v2" or value["provider"] != "infisical":
        raise ValueError("invalid Infisical exchange proof identity")
    if value["result"] not in {"ALLOWED", "DENIED"} or value["environment"] != "staging":
        raise ValueError("invalid Infisical exchange result or environment")
    if value["result"] == "ALLOWED" and value["http_status"] not in {200, 201}:
        raise ValueError("allowed exchange must carry a successful HTTP status")
    if value["result"] == "DENIED" and value["http_status"] not in {401, 403}:
        raise ValueError("denied exchange must carry an authorization failure status")
    if not isinstance(value["response_sha256"], str) or len(value["response_sha256"]) != 64:
        raise ValueError("exchange response digest is invalid")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token-file", required=True, type=Path)
    parser.add_argument("--jwks-file", type=Path)
    parser.add_argument("--jwks-url", default=OFFICIAL_JWKS_URL)
    parser.add_argument("--test-mode", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--expected-audience", required=True)
    parser.add_argument("--expected-token-repository", required=True)
    parser.add_argument("--expected-environment", default="staging")
    parser.add_argument("--mode", required=True, choices=["positive", "negative"])
    parser.add_argument("--exchange-proof", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()

    token = args.token_file.read_text(encoding="utf-8").strip()
    try:
        if args.jwks_file and not args.test_mode:
            raise ValueError("local JWKS files are forbidden outside explicit test mode")
        if not args.jwks_file and args.jwks_url != OFFICIAL_JWKS_URL:
            raise ValueError("live OIDC verification must use the official GitHub issuer JWKS endpoint")
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            raise ValueError("GitHub OIDC token must use RS256 and include kid")
        jwks = load_jwks(args.jwks_file, args.jwks_url)
        jwks_source = "local-test-jwks" if args.jwks_file else OFFICIAL_JWKS_URL
        jwks_sha256 = sha256_bytes(canonical(jwks))
        matching = [item for item in jwks["keys"] if isinstance(item, dict) and item.get("kid") == header["kid"]]
        if len(matching) != 1:
            raise ValueError("JWKS did not contain exactly one matching key")
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(matching[0]))
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=ISSUER,
            audience=args.expected_audience,
            leeway=30,
            options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub", "jti", "repository", "environment", "run_id"]},
        )
        if claims.get("repository") != args.expected_token_repository:
            raise ValueError("repository claim mismatch")
        if claims.get("environment") != args.expected_environment:
            raise ValueError("environment claim mismatch")
        run_id = int(claims["run_id"])
        exchange = load_exchange_proof(args.exchange_proof)
        authorization_class = "AUTHORIZED" if claims.get("repository") == CANONICAL_REPOSITORY and claims.get("environment") == "staging" else "UNAUTHORIZED"
        expected_subject = f"repo:{claims['repository']}:environment:{claims['environment']}"
        if claims.get("sub") != expected_subject:
            raise ValueError("OIDC subject is not bound to the repository and environment claims")
        workflow_ref = claims.get("job_workflow_ref")
        if not isinstance(workflow_ref, str) or not workflow_ref:
            raise ValueError("job_workflow_ref claim is required")
        if args.mode == "positive":
            if authorization_class != "AUTHORIZED":
                raise ValueError("positive proof does not contain the authorized repository and environment")
            if not workflow_ref.startswith(f"{CANONICAL_REPOSITORY}/.github/workflows/"):
                raise ValueError("positive proof workflow identity is not owned by the canonical repository")
        if args.mode == "negative" and authorization_class != "UNAUTHORIZED":
            raise ValueError("negative proof does not contain an unauthorized repository claim")
        safe_claims = {
            key: claims.get(key)
            for key in ["iss", "aud", "sub", "repository", "repository_id", "ref", "environment", "workflow", "job_workflow_ref", "actor", "run_id", "iat", "nbf", "exp"]
            if key in claims
        }
        details = {
            "repository_claim": claims["repository"],
            "environment_claim": claims["environment"],
            "exchange_result": exchange["result"],
            "policy_match": authorization_class == "AUTHORIZED",
            "token_signature_verified_by_issuer": True,
            "issuer": claims["iss"],
            "audience": claims["aud"],
            "subject": claims["sub"],
            "run_id": run_id,
            "job_workflow_ref": workflow_ref,
            "key_id": header["kid"],
            "algorithm": header["alg"],
            "claims_sha256": sha256_bytes(canonical(safe_claims)),
            "authorization_class": authorization_class,
            "jti_sha256": sha256_bytes(str(claims["jti"]).encode("utf-8")),
            "issued_at": int(claims["iat"]),
            "expires_at": int(claims["exp"]),
            "jwks_source": jwks_source,
            "jwks_sha256": jwks_sha256,
            "exchange_request_id": exchange["request_id"],
            "exchange_http_status": exchange["http_status"],
            "identity_id": exchange["identity_id"],
            "production_contact": False,
        }
        check_id = "oidc_positive_exchange_passed" if args.mode == "positive" else "oidc_negative_exchange_denied"
        directory = args.output_root / f"evidence/artifacts/{check_id}"
        directory.mkdir(parents=True, exist_ok=True)
        exchange_copy = directory / "infisical-exchange.json"
        exchange_copy.write_bytes(args.exchange_proof.read_bytes())
        jwks_copy = directory / "github-oidc-jwks.json"
        jwks_copy.write_text(json.dumps(jwks, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        proof_path = directory / "oidc-verification.json"
        proof = {
            "schema": "l9.deploy.phase6-proof/v1",
            "producer_id": "verify_oidc_claims",
            "producer_version": "2.0.0",
            "producer_executable_sha256": sha256_file(Path(__file__)),
            "captured_at": now(),
            "subject": f"GitHub OIDC {args.mode} cryptographic verification",
            "source_kind": "oidc_verifier",
            "source_locator": f"github-oidc://{claims['repository']}/runs/{run_id}/{args.mode}",
            "artifact_role": "oidc_verification",
            "media_type": "application/json",
            "details": details,
            "related_artifacts": [
                {"path": exchange_copy.relative_to(args.output_root).as_posix(), "role": "infisical_exchange_receipt", "media_type": "application/json"},
                {"path": jwks_copy.relative_to(args.output_root).as_posix(), "role": "github_oidc_jwks", "media_type": "application/json"},
            ],
        }
        proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        expected_exchange = "ALLOWED" if args.mode == "positive" else "DENIED"
        status = "PASS" if exchange["result"] == expected_exchange else "FAIL"
        print(json.dumps({"status": status, "proof": str(proof_path), "signature_verified": True}, indent=2))
        return 0 if status == "PASS" else 3
    finally:
        args.token_file.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, json.JSONDecodeError, jwt.PyJWTError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
