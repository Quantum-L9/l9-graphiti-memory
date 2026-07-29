# ADR-066: Secret-File Credential Resolution for Active-Memory Redis

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-066-secret-file-credential-resolution.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

## Status

Accepted (2026-07-28)

Related: ADR-016 (secret and credential boundaries), ADR-065

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

## Rejected Alternatives

Supporting only an environment-variable URL was rejected because it is
fundamentally incompatible with the file-mounted secret patterns used
by the container orchestrators active-memory consumers actually run
on. Automatic file-watching reload was deferred (not rejected outright)
because it introduces background filesystem I/O and failure modes
(partial reads mid-rotation, watch-descriptor exhaustion) that are
unjustified until a consumer demonstrates a concrete rotation-latency
requirement that explicit reload cannot satisfy.

## Invariants

Exactly one credential source is configured at any time; construction
raises `AmbiguousCredentialSourceError` for more than one and
`CredentialResolutionError` for zero. Secret-file reads always enforce:
absolute path, no symlinks, regular file only, max 16 KiB, no embedded
NUL bytes, exactly one trailing newline stripped, non-empty after
trimming. `redacted_summary()` never exposes the raw `redis_url` or
password; no code path in this change logs the raw value.

## Security Impact

This ADR exists specifically to reduce credential exposure surface:
file-mounted secrets avoid `/proc/<pid>/environ` and child-process
environment inheritance exposure that `url_env` carries. Symlink
rejection prevents a mounted secret path from being redirected to an
unintended file at read time (TOCTOU-style substitution). The 16 KiB
size cap and NUL-byte rejection bound the blast radius of a
misconfigured or malicious mount. `redacted_summary()` is the only
credential-derived value permitted in logs or error messages.

## Migration Impact

No stored data or schema changes. Existing consumers using `url_env`
continue to work unchanged (lowest-precedence, still-supported source).
Consumers migrating to file-mounted secrets adopt `url_file` or
`host`/`password_file` at their own pace; there is no forced cutover
date and no wire-format change.

## Validation Requirements

Unit tests must cover: precedence ordering across all four sources,
`AmbiguousCredentialSourceError` for multi-source configuration,
`CredentialResolutionError` for zero-source configuration, every
secret-file validation rule (absolute path, symlink rejection, regular
file, size cap, NUL rejection, trailing-newline stripping, non-empty
trimming), and that `redacted_summary()` never contains the raw
`redis_url` or password substring.

## Rollback Conditions

Revert to environment-variable-only credential resolution only if the
four-source precedence model is shown to cause consumer
misconfiguration incidents that outweigh its container-secret-mount
benefits. Rollback is backward compatible for existing `url_env`
consumers but is a breaking change for any consumer that has already
adopted `url_file`, `host`/`password_file`, or
`secret_provider_reference`.

## Supersedes / Superseded By

Supersedes no prior ADR. Not superseded.
