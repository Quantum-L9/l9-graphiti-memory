# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/curation/quarantine.py
#   layer: curation
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-09-04

"""Automated quarantine review: evidence-bound provider verdicts (ADR-080).

The model binding is injected, as it is for provider-backed extraction: this
package owns the payload a reviewer sees, the validation its answer must pass,
and the fail-closed defaults when it cannot answer. It does not own a model
client. A deployment names its provider with
``L9_MEMORY_QUARANTINE_REVIEW_PROVIDER`` (``package.module:factory``), and the
factory returns an object with ``review(payload) -> dict``.
"""

from __future__ import annotations

import importlib
import logging
from datetime import datetime, timezone
from typing import Any, Protocol, cast

from l9_graphite_memory.contracts import (
    QUARANTINE_REVIEW_POLICY_VERSION,
    MemoryRecord,
    QuarantineReviewPolicy,
    QuarantineReviewVerdict,
    QuarantineVerdict,
)

log = logging.getLogger("l9.memory.quarantine_review")

#: Upper bound on content handed to a provider; quarantined records are
#: reviewed whole, but a reviewer that needs more than this has a different
#: problem than quarantine.
MAX_REVIEW_CONTENT_CHARS = 16_000


class StructuredReviewProvider(Protocol):
    """Provider returns a JSON-compatible verdict for a review payload.

    Expected keys: ``verdict`` (``release`` | ``hold`` | ``escalate``),
    ``confidence`` (0..1), ``reasons`` (non-empty list of strings). Optional:
    ``blockers`` (list of strings), ``model`` (string).
    """

    def review(self, payload: dict[str, Any]) -> dict[str, Any]: ...


def review_payload(record: MemoryRecord) -> dict[str, Any]:
    """Everything a reviewer is given, and nothing it is not.

    Content is passed as admitted (already PII-redacted by normalization);
    the admission signals that caused quarantine travel alongside so the
    reviewer judges the record for what it was held for.
    """

    metadata = record.metadata
    return {
        "record_id": str(record.record_id),
        "namespace": record.namespace,
        "memory_class": record.memory_class.value,
        "content": record.content[:MAX_REVIEW_CONTENT_CHARS],
        "assertion": record.assertion.model_dump(mode="json") if record.assertion else None,
        "tags": list(record.tags),
        "safety_signals": list(metadata.get("safety_signals", [])),
        "pii_redacted": bool(metadata.get("pii_redacted", False)),
        "evidence": [
            {"kind": item.kind.value, "description": item.description} for item in record.evidence
        ],
        "provenance": {
            "source": record.provenance.source,
            "tool": record.provenance.tool,
            "extraction_method": record.provenance.extraction_method,
        },
        "valid_from": record.temporal.valid_from.isoformat(),
        "recorded_at": record.temporal.recorded_at.isoformat(),
    }


def _text_items(value: Any, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field} must be a list of strings")
    items = tuple(str(item).strip() for item in value)
    if any(not item for item in items):
        raise ValueError(f"{field} contains empty text")
    return items


class EvidenceBoundProviderReviewer:
    """Validate a provider's verdict and fail closed on anything else.

    A malformed answer is never read as a release. It becomes an ESCALATE
    carrying the validation error, so a person sees that the reviewer is
    misbehaving. A provider that raises is read as HOLD: an outage is not a
    finding about the record, and the record is simply reviewed next run.
    """

    name = "evidence-bound-review/v1"

    def __init__(
        self,
        provider: StructuredReviewProvider,
        *,
        policy: QuarantineReviewPolicy | None = None,
    ) -> None:
        self.provider = provider
        self.policy = policy or QuarantineReviewPolicy()
        self.policy_version = self.policy.policy_version

    def review(self, record: MemoryRecord) -> QuarantineReviewVerdict:
        payload = review_payload(record)
        reviewed_at = datetime.now(timezone.utc)
        try:
            raw = self.provider.review(payload)
        except Exception as exc:  # noqa: BLE001 - provider failures are held, not raised
            log.warning(
                "quarantine_review_provider_failed",
                extra={"record_id": str(record.record_id), "error": str(exc)},
            )
            return QuarantineReviewVerdict(
                record_id=record.record_id,
                verdict=QuarantineVerdict.HOLD,
                confidence=0.0,
                reasons=(f"review provider failed: {exc}",),
                reviewer=self.name,
                policy_version=self.policy_version,
                reviewed_at=reviewed_at,
            )
        try:
            if not isinstance(raw, dict):
                raise TypeError("provider returned a non-object verdict")
            verdict = QuarantineVerdict(str(raw.get("verdict", "")).strip().lower())
            confidence = float(raw.get("confidence", 0.0))
            reasons = _text_items(raw.get("reasons"), field="reasons")
            if not reasons:
                raise ValueError("provider gave no reasons")
            blockers = _text_items(raw.get("blockers"), field="blockers")
            model_value = raw.get("model")
            model = str(model_value)[:200] if model_value else None
            return QuarantineReviewVerdict(
                record_id=record.record_id,
                verdict=verdict,
                confidence=confidence,
                reasons=reasons,
                blockers=blockers,
                reviewer=self.name,
                model=model,
                policy_version=self.policy_version,
                reviewed_at=reviewed_at,
            )
        except (ValueError, TypeError) as exc:
            return QuarantineReviewVerdict(
                record_id=record.record_id,
                verdict=QuarantineVerdict.ESCALATE,
                confidence=0.0,
                reasons=(f"provider output invalid: {exc}",),
                blockers=("review provider returned an unusable verdict",),
                reviewer=self.name,
                policy_version=self.policy_version,
                reviewed_at=reviewed_at,
            )


class NullQuarantineReviewer:
    """No reviewer is configured: every record is held and reported as unreviewed."""

    name = "none"
    policy_version = QUARANTINE_REVIEW_POLICY_VERSION

    def review(self, record: MemoryRecord) -> QuarantineReviewVerdict:
        return QuarantineReviewVerdict(
            record_id=record.record_id,
            verdict=QuarantineVerdict.HOLD,
            confidence=0.0,
            reasons=("no quarantine review provider is configured",),
            reviewer=self.name,
            policy_version=self.policy_version,
        )


def apply_policy(
    verdict: QuarantineReviewVerdict,
    record: MemoryRecord,
    policy: QuarantineReviewPolicy,
) -> QuarantineReviewVerdict:
    """Turn a reviewer's opinion into what the policy allows.

    - a credential-bearing record, or an exfiltration signal, escalates
      whatever the reviewer said;
    - a RELEASE below the confidence floor becomes a HOLD;
    - everything else stands.
    """

    metadata = record.metadata
    blockers = list(verdict.blockers)
    # Records admitted before ``pii_types`` was recorded carry only the
    # ``pii_redacted`` boolean; for those the reviewer's own blockers are the
    # only credential signal available.
    for pii_type in metadata.get("pii_types", []):
        if pii_type in policy.blocker_pii_types:
            blockers.append(f"record carried a credential-shaped value ({pii_type})")
    for signal in metadata.get("safety_signals", []):
        if signal in policy.blocker_safety_signals:
            blockers.append(f"admission flagged {signal}")
    if blockers:
        return verdict.model_copy(
            update={
                "verdict": QuarantineVerdict.ESCALATE,
                "blockers": tuple(dict.fromkeys(blockers)),
            }
        )
    if (
        verdict.verdict is QuarantineVerdict.RELEASE
        and verdict.confidence < policy.release_min_confidence
    ):
        return verdict.model_copy(
            update={
                "verdict": QuarantineVerdict.HOLD,
                "reasons": (
                    *verdict.reasons,
                    (
                        f"release confidence {verdict.confidence:.2f} is below the policy "
                        f"floor {policy.release_min_confidence:.2f}"
                    ),
                ),
            }
        )
    return verdict


def load_review_provider(spec: str) -> StructuredReviewProvider:
    """Resolve ``package.module:factory`` to a provider instance.

    The factory is called with no arguments and must return an object with a
    ``review`` method. Resolution errors are raised as ``ValueError`` so the
    CLI reports a configuration mistake rather than a traceback.
    """

    module_name, _, attribute = spec.strip().partition(":")
    if not module_name or not attribute:
        raise ValueError(
            f"quarantine review provider must be 'package.module:factory', got {spec!r}"
        )
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ValueError(f"quarantine review provider module not importable: {exc}") from exc
    factory = getattr(module, attribute, None)
    if factory is None:
        raise ValueError(f"quarantine review provider {spec!r} has no attribute {attribute!r}")
    provider = factory() if callable(factory) else factory
    if not callable(getattr(provider, "review", None)):
        raise TypeError(f"quarantine review provider {spec!r} does not expose review()")
    return cast(StructuredReviewProvider, provider)
