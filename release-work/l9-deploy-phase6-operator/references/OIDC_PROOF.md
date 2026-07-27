<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/l9-deploy-phase6-operator/references/OIDC_PROOF.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

<!--
skill_schema: 1
parent: l9-deploy-phase6-operator
layer: reference
role: oidc_proof_protocol
tags: [oidc, infisical, github, jwks, negative-test]
owner: igor_beylin
status: active
version: 3.0.0
updated: 2026-07-26
-->
# OIDC Proof Protocol

## Cryptographic verifier

Use `verify_oidc_claims.py`. In live mode it accepts only the official GitHub issuer JWKS endpoint. Local JWKS files require the hidden test flag and are forbidden in live operation.

The verifier requires and checks:

- RS256 and a matching JWKS key ID;
- issuer `https://token.actions.githubusercontent.com`;
- expected audience;
- `exp`, `iat`, `nbf`, `jti`, repository, environment, subject, run ID, and workflow identity;
- subject equality to the repository/environment claims;
- canonical repository/workflow ownership for the positive case;
- non-canonical authorization class for the negative case;
- strict Infisical exchange receipt identity, environment, HTTP status, request ID, and response digest.

The raw JWT is deleted in `finally`, including failure paths. The proof retains only redacted claims, claim digest, JTI digest, JWKS digest, key ID, workflow identity, and exchange metadata.

## Positive proof

The approved deployment job must produce an authorized token for `Quantum-L9/l9-deploy` in `staging`; the Infisical exchange must return ALLOWED with a success status. Capture the matching audit event.

## Negative proof

Use `assets/oidc-negative-probe.yml` only in a designated external probe repository. The same Infisical identity exchange must return DENIED with HTTP 401 or 403. Never add the probe workflow to `l9-deploy`.

An unauthorized exchange returning ALLOWED is an immediate terminal NO-GO even if all ordinary assertions otherwise pass.

Both verifier outputs must be independently attested before import. Caller-authored booleans are not accepted as authority.
