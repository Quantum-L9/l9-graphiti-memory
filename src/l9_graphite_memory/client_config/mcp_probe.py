# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/client_config/mcp_probe.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-27

"""Proof-of-instantiation probe over the generated MCP stdio command.

The probe launches the exact argv that the configurator writes into the
client config, then drives the real JSON-RPC handshake: ``initialize``,
``notifications/initialized``, ``tools/list``, and ``tools/call`` against
``memory.health``. It never imports store or projection layers; the only
evidence channel is the wire protocol of the spawned process, which is the
same channel Cursor itself will use. Captured stderr is redacted against
process-environment secret values before it enters any receipt.
"""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import time
from typing import Any

from .contracts import ClientConfigStatus, ProbeReceipt, ProbeStep
from .cursor import managed_server_entry

REQUIRED_TOOL_NAMES: tuple[str, ...] = (
    "memory.ingest",
    "memory.search",
    "memory.hydrate",
    "memory.get",
    "memory.conflicts",
    "memory.phase_lock",
    "memory.verify_phase_lock",
    "memory.lineage",
    "memory.retention",
    "memory.delete",
    "memory.promote",
    "memory.bootstrap",
    "memory.distill",
    "memory.synthesize_procedures",
    "memory.health",
    "write",
    "search",
)

_STDERR_LIMIT = 2000
_HEALTHY_STATUSES = frozenset({"complete", "partial"})
_SECRET_ENV_MARKERS = ("SECRET", "TOKEN", "KEY", "PASSWORD", "CREDENTIAL")


def _secret_values(env: dict[str, str]) -> tuple[str, ...]:
    values: list[str] = []
    for name, value in env.items():
        upper = name.upper()
        if len(value) >= 6 and any(marker in upper for marker in _SECRET_ENV_MARKERS):
            values.append(value)
    return tuple(sorted(values, key=len, reverse=True))


def redact_stderr(text: str, env: dict[str, str]) -> str:
    """Remove any environment-derived secret material from captured stderr."""
    for value in _secret_values(env):
        if value in text:
            text = text.replace(value, "[REDACTED]")
    return text[:_STDERR_LIMIT]


class _StdioSession:
    """Minimal line-delimited JSON-RPC client over a child process."""

    def __init__(
        self, argv: tuple[str, ...], env: dict[str, str], deadline: float
    ) -> None:
        self.deadline = deadline
        self.process = subprocess.Popen(
            list(argv),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
        self.selector = selectors.DefaultSelector()
        if self.process.stdout is not None:
            self.selector.register(self.process.stdout, selectors.EVENT_READ)

    def send(self, message: dict[str, Any]) -> None:
        if self.process.stdin is None:
            raise BrokenPipeError("child stdin unavailable")
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def receive(self) -> dict[str, Any]:
        while True:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("probe deadline exceeded")
            if not self.selector.select(timeout=min(remaining, 0.5)):
                if self.process.poll() is not None:
                    raise BrokenPipeError("server exited before responding")
                continue
            if self.process.stdout is None:
                raise BrokenPipeError("child stdout unavailable")
            line = self.process.stdout.readline()
            if line == "":
                raise BrokenPipeError("server closed stdout")
            line = line.strip()
            if not line:
                continue
            decoded = json.loads(line)
            if isinstance(decoded, dict):
                return decoded
            raise ValueError("server emitted a non-object JSON-RPC frame")

    def close(self) -> tuple[int | None, str]:
        stderr_text = ""
        try:
            if self.process.stdin is not None:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            if self.process.stderr is not None:
                stderr_text = self.process.stderr.read() or ""
        finally:
            self.selector.close()
            for stream in (self.process.stdout, self.process.stderr):
                if stream is not None:
                    stream.close()
        return self.process.returncode, stderr_text


def probe_generated_server(
    *,
    interpreter: str | None = None,
    env: dict[str, str] | None = None,
    timeout_seconds: float = 30.0,
) -> ProbeReceipt:
    """Run the full proof-of-instantiation handshake and return evidence."""
    entry = managed_server_entry(interpreter)
    argv = (entry.command, *entry.args)
    run_env = dict(os.environ if env is None else env)
    deadline = time.monotonic() + timeout_seconds
    steps: list[ProbeStep] = []
    reasons: list[str] = []
    protocol_version: str | None = None
    server_name: str | None = None
    server_version: str | None = None
    tool_count = 0
    missing: tuple[str, ...] = ()
    required_present = False
    health_status: str | None = None
    timed_out = False
    exit_code: int | None = None
    stderr_text = ""

    session: _StdioSession | None = None
    try:
        session = _StdioSession(argv, run_env, deadline)
        response = _call(
            session, 1, "initialize", {"protocolVersion": "2024-11-05"}
        )
        result = _result_of(response, "initialize", steps)
        info = result.get("serverInfo", {}) if isinstance(result, dict) else {}
        protocol_version = (
            result.get("protocolVersion") if isinstance(result, dict) else None
        )
        if isinstance(info, dict):
            server_name = info.get("name")
            server_version = info.get("version")
        session.send(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        )
        steps.append(
            ProbeStep(method="notifications/initialized", ok=True, detail="sent")
        )
        response = _call(session, 2, "tools/list", {})
        result = _result_of(response, "tools/list", steps)
        tools = result.get("tools", []) if isinstance(result, dict) else []
        names = {
            item.get("name")
            for item in tools
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        tool_count = len(tools)
        missing = tuple(
            sorted(name for name in REQUIRED_TOOL_NAMES if name not in names)
        )
        required_present = not missing
        if missing:
            reasons.append(f"missing required tools: {', '.join(missing)}")
        response = _call(
            session,
            3,
            "tools/call",
            {"name": "memory.health", "arguments": {}},
        )
        result = _result_of(response, "tools/call memory.health", steps)
        health_status = _extract_health_status(result)
        if health_status not in _HEALTHY_STATUSES:
            reasons.append(f"memory.health returned status={health_status!r}")
    except TimeoutError:
        timed_out = True
        reasons.append(f"probe timed out after {timeout_seconds:.0f}s")
        steps.append(ProbeStep(method="timeout", ok=False, detail="deadline exceeded"))
    except (BrokenPipeError, OSError, ValueError, json.JSONDecodeError) as exc:
        reasons.append(f"probe transport failure: {exc}")
        steps.append(
            ProbeStep(method="transport", ok=False, detail=type(exc).__name__)
        )
    finally:
        if session is not None:
            exit_code, stderr_text = session.close()

    succeeded = (
        not timed_out
        and required_present
        and health_status in _HEALTHY_STATUSES
        and all(step.ok for step in steps)
    )
    return ProbeReceipt(
        status=(
            ClientConfigStatus.COMPLETE if succeeded else ClientConfigStatus.FAILED
        ),
        command_argv=argv,
        protocol_version=protocol_version,
        server_name=server_name,
        server_version=server_version,
        tool_count=tool_count,
        required_tools_present=required_present,
        missing_tools=missing,
        health_status=health_status,
        steps=tuple(steps),
        stderr_excerpt=redact_stderr(stderr_text, run_env),
        timed_out=timed_out,
        exit_code=exit_code,
        reasons=tuple(reasons),
    )


def _call(
    session: _StdioSession, request_id: int, method: str, params: dict[str, Any]
) -> dict[str, Any]:
    session.send(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )
    while True:
        response = session.receive()
        if response.get("id") == request_id:
            return response


def _result_of(
    response: dict[str, Any], label: str, steps: list[ProbeStep]
) -> dict[str, Any]:
    error = response.get("error")
    if error is not None:
        detail = str(error.get("message", "")) if isinstance(error, dict) else ""
        steps.append(ProbeStep(method=label, ok=False, detail=detail[:200]))
        raise ValueError(f"{label} failed: {detail}")
    result = response.get("result")
    steps.append(ProbeStep(method=label, ok=True, detail="ok"))
    return result if isinstance(result, dict) else {}


def _extract_health_status(result: dict[str, Any]) -> str | None:
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return None
    first = content[0]
    if not isinstance(first, dict):
        return None
    text = first.get("text")
    if not isinstance(text, str):
        return None
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(decoded, dict):
        status = decoded.get("status")
        return status if isinstance(status, str) else None
    return None
