# ADR-070: Secret-File Credential Resolution for Active-Memory Redis

- Status: Accepted
- Date: 2026-07-28
- Related: ADR-016 (secret and credential boundaries), ADR-069

## Context

The original active-memory build plan assumed Redis credentials were
supplied via a single environment variable containing a full connection
URL (`url_env`). This is incompatible with container orchestration
patterns that mount credentials as files (e.g. Docker Compose secrets,
Kubernetes Secret volumes), where processes should read credentials
from a file rather than the process environment, reducing exposure via
`/proc/<pid>/environ`, child-process inheritance, and process-listing
tools.

## Decision

Add `RedisCredentialSettings` supporting four mutually exclusive
credential sources, in strict precedence order:

1. `url_file` — a mounted file containing a complete `redis://` or
   `rediss://` URL.
2. `host` + `password_file` (+ optional `username`, `port`, `database`,
   `tls`) — structured connection parameters with the password read
   from a mounted file.
3. `secret_provider_reference` — an opaque string resolved via a
   caller-supplied `secret_provider` callback (e.g. Vault, a cloud
   secret manager). This package defines only the resolution contract,
   not any specific provider integration.
4. `url_env` — an environment variable containing a full URL. Lowest
   precedence; documented as development-oriented only.

Configuring more than one source raises
`AmbiguousCredentialSourceError` rather than silently picking one.
Configuring zero sources raises `CredentialResolutionError`.

Secret-file reads enforce:

- Absolute path required.
- Symlinks rejected.
- Regular file required.
- Maximum size 16 KiB.
- No embedded NUL bytes.
- Exactly one trailing newline stripped; contents otherwise passed
  through unmodified.
- Non-empty after trimming.

All resolved credentials expose only a `redacted_summary()` method for
diagnostics; the raw `redis_url` field is never included in any log
statement produced by code in this change.

## Consequences

- Positive: consumer applications using Docker/Kubernetes secret
  mounts have a first-class, tested resolution path.
- Positive: ambiguous configuration fails fast at startup instead of
  silently picking an unintended credential source.
- Negative: this package does not implement any concrete
  `secret_provider` (e.g. no bundled Vault client); consumers must
  supply their own callback if they use option 3.
- Negative: credential rotation requires an explicit, consumer-invoked
  reload path (not yet implemented in this change — see MANIFEST.md
  "Unknowns/Deferred").

## Alternatives Considered

- **Single supported source (env var only).** Rejected: does not meet
  container secret-mount deployment patterns used by consumer
  applications.
- **Automatic file-watching credential reload.** Deferred: adds
  filesystem-watching complexity; explicit reload is sufficient for the
  stated rotation test scenario and avoids surprising background I/O.
