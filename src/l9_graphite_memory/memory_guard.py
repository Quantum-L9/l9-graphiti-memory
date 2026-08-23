# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/memory_guard.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Network-free receipt guard for optional editor hooks.

This guard is not the constellation Gate. It owns no routing and no workflow.
It only verifies short-lived hydration and phase-lock evidence produced by the
canonical memory service.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

_READ_ONLY_TOOLS = frozenset({"Read", "Grep", "Glob", "SemanticSearch", "ListDir", "TaskExplore"})
_READ_ONLY_SHELL = re.compile(
    r"^\s*(?:"
    r"pwd|whoami|id|uname(?:\s+-[a-z]+)?|"
    r"ls(?:\s+[^;&|><]*)?|"
    r"(?:cat|head|tail|wc|grep|rg)\s+[^;&|><]+|"
    r"git\s+(?:status|diff|log|show|rev-parse|branch\s+--show-current|remote\s+get-url)(?:\s+[^;&|><]*)?|"
    r"find\s+(?!.*(?:-delete|-exec(?:dir)?|-ok(?:dir)?))[^;&|><]+"
    r")\s*$",
    re.IGNORECASE,
)
_GOVERNED_CHANGE = re.compile(r"\b(?:GMP|phase\s*[0-9]+|modification\s+lock)\b", re.IGNORECASE)


class GuardEvidence(BaseModel):
    """Ephemeral verification cache. It is evidence, not workflow state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 3
    namespace: str | None = None
    hydrated_at: datetime | None = None
    hydration_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    hydration_status: str | None = None
    task_signature: str | None = None
    verified_task_signatures: tuple[str, ...] = ()
    ttl_minutes: int = Field(default=30, ge=1, le=1_440)
    phase_lock_granted: bool = False
    phase_lock_task_signature: str | None = None
    phase_lock_expires_at: datetime | None = None


class HookRequest(BaseModel):
    """Normalized editor-hook input using canonical snake_case fields."""

    model_config = ConfigDict(extra="ignore")

    tool_name: str = ""
    conversation_id: str = "default"
    command: str = ""
    full_command: str = ""
    input: str = ""


class GuardDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    permission: str
    user_message: str | None = None

    def hook_payload(self) -> dict[str, str]:
        return {
            key: value
            for key, value in self.model_dump(exclude_none=True).items()
            if isinstance(value, str)
        }


def evidence_dir() -> Path:
    configured = os.environ.get("L9_MEMORY_STATE_DIR")
    return (
        Path(configured).expanduser()
        if configured
        else Path("~/.local/state/l9-memory").expanduser()
    )


def evidence_path(conversation_id: str) -> Path:
    return evidence_dir() / f"{conversation_id or 'default'}.json"


def load_evidence(conversation_id: str) -> GuardEvidence | None:
    path = evidence_path(conversation_id)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return GuardEvidence.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError):
        return None


def guard_enabled() -> bool:
    return os.environ.get("L9_MEMORY_WRITE_GATES", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def hydration_fresh(evidence: GuardEvidence) -> bool:
    if evidence.hydrated_at is None or not evidence.hydration_digest:
        return False
    if evidence.hydration_status not in {"complete", "partial"}:
        return False
    hydrated_at = evidence.hydrated_at
    if hydrated_at.tzinfo is None:
        hydrated_at = hydrated_at.replace(tzinfo=timezone.utc)
    age_minutes = (
        datetime.now(timezone.utc) - hydrated_at.astimezone(timezone.utc)
    ).total_seconds() / 60
    return 0 <= age_minutes <= evidence.ttl_minutes


def memory_ok(evidence: GuardEvidence | None, task_signature: str | None = None) -> bool:
    if evidence is None or not hydration_fresh(evidence):
        return False
    if task_signature is None:
        return True
    return task_signature in evidence.verified_task_signatures


def phase_lock_ok(evidence: GuardEvidence | None) -> bool:
    if evidence is None or not evidence.phase_lock_granted:
        return False
    if evidence.task_signature and evidence.phase_lock_task_signature != evidence.task_signature:
        return False
    expiry = evidence.phase_lock_expires_at
    if expiry is None:
        return False
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) <= expiry.astimezone(timezone.utc)


def shell_is_read_only(command: str) -> bool:
    return bool(command and _READ_ONLY_SHELL.fullmatch(command))


def _allow() -> dict[str, str]:
    return GuardDecision(permission="allow").hook_payload()


def _deny(message: str) -> dict[str, str]:
    return GuardDecision(permission="deny", user_message=message).hook_payload()


def _request(payload: str) -> HookRequest:
    raw = json.loads(payload) if payload.strip() else {}
    return HookRequest.model_validate(raw)


def pre_tool_use(payload: str) -> dict[str, str]:
    if not guard_enabled():
        return _allow()
    try:
        request = _request(payload)
    except (json.JSONDecodeError, ValidationError):
        return _deny("L9 memory guard: invalid hook payload")
    if request.tool_name in _READ_ONLY_TOOLS or request.tool_name.startswith("mcp_"):
        return _allow()
    if request.tool_name.lower() in {"shell", "bash", "terminal"}:
        command = request.command or request.full_command or request.input
        if shell_is_read_only(command):
            return _allow()
    evidence = load_evidence(request.conversation_id)
    if _GOVERNED_CHANGE.search(payload) and not phase_lock_ok(evidence):
        return _deny(
            "L9 memory guard: governed modification requires a current conflict-free phase-lock receipt"
        )
    if memory_ok(evidence):
        return _allow()
    return _deny("L9 memory guard: mutation blocked until current hydration evidence exists")


def shell_guard(payload: str) -> dict[str, str]:
    if not guard_enabled():
        return _allow()
    try:
        request = _request(payload)
    except (json.JSONDecodeError, ValidationError):
        return _deny("L9 memory guard: invalid shell payload")
    command = request.command or request.full_command
    if shell_is_read_only(command):
        return _allow()
    return (
        _allow()
        if memory_ok(load_evidence(request.conversation_id))
        else _deny("L9 memory guard: mutating shell command blocked until memory is hydrated")
    )


def subagent_guard(payload: str) -> dict[str, str]:
    if not guard_enabled():
        return _allow()
    try:
        request = _request(payload)
    except (json.JSONDecodeError, ValidationError):
        return _deny("L9 memory guard: invalid subagent payload")
    return (
        _allow()
        if memory_ok(load_evidence(request.conversation_id))
        else _deny("L9 memory guard: subagent blocked until parent memory is hydrated")
    )


def main(argv: list[str] | None = None) -> int:
    values = argv or sys.argv[1:]
    if len(values) != 1 or values[0] not in {"pre_tool_use", "shell", "subagent"}:
        sys.stdout.write(json.dumps(_deny("L9 memory guard: invalid mode")) + "\n")
        return 2
    payload = sys.stdin.read()
    handlers = {
        "pre_tool_use": pre_tool_use,
        "shell": shell_guard,
        "subagent": subagent_guard,
    }
    try:
        result = handlers[values[0]](payload)
    except Exception as exc:  # noqa: BLE001
        result = (
            _deny(f"L9 memory guard error: {type(exc).__name__}") if guard_enabled() else _allow()
        )
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
