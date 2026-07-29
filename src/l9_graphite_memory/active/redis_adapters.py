# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/active/redis_adapters.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Redis 7.2+ adapters for active-memory ports.

The optional `redis` dependency is imported lazily, keeping the base
package importable without Redis support installed.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from l9_graphite_memory.active.deployment import (
    ActiveDeployment,
    derive_deployment_hash,
)
from l9_graphite_memory.active.errors import (
    ActiveMemoryUnavailableError,
    ContextVersionConflictError,
    LeaseExpiredError,
)
from l9_graphite_memory.active.models import (
    ActiveContext,
    ActiveContextDraft,
    ActiveObservation,
    AgentEvent,
    AgentEventType,
    AgentIdentity,
    AgentLease,
    AgentPresence,
    AgentScope,
    AgentStatus,
    AgentSubscription,
)

Clock = Callable[[], datetime]


def _redis_modules() -> tuple[Any, type[Exception], type[Exception]]:
    try:
        import redis.asyncio as redis
        from redis.exceptions import NoScriptError, RedisError

        return redis, NoScriptError, RedisError
    except ImportError as exc:
        raise ActiveMemoryUnavailableError(
            "Redis adapter requires optional dependency redis>=5,<7"
        ) from exc


def _default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, frozenset)):
        return list(value)
    raise TypeError(type(value).__name__)


def _dump(value: Any) -> str:
    return json.dumps(
        asdict(value), default=_default, separators=(",", ":"), sort_keys=True
    )


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _identity(data: Mapping[str, Any]) -> AgentIdentity:
    return AgentIdentity(
        agent_id=data["agent_id"],
        instance_id=data["instance_id"],
        role=data["role"],
        principal_id=data["principal_id"],
        capabilities=frozenset(data.get("capabilities", [])),
        session_id=data.get("session_id"),
        memory_group_ids=tuple(data.get("memory_group_ids", [])),
        metadata=data.get("metadata", {}),
    )


def _presence(data: Mapping[str, Any]) -> AgentPresence:
    return AgentPresence(
        identity=_identity(data["identity"]),
        status=AgentStatus(data["status"]),
        deployment_id=data["deployment_id"],
        started_at=_dt(data["started_at"]),
        heartbeat_at=_dt(data["heartbeat_at"]),
        expires_at=_dt(data["expires_at"]),
        presence_version=data["presence_version"],
    )


def _observation(data: Mapping[str, Any]) -> ActiveObservation:
    return ActiveObservation(
        observation_id=data["observation_id"],
        kind=data["kind"],
        summary=data["summary"],
        created_at=_dt(data["created_at"]),
        confidence=data.get("confidence"),
        relevance=data.get("relevance"),
        source_reference=data.get("source_reference"),
        promotable=data.get("promotable", False),
    )


def _draft(data: Mapping[str, Any]) -> ActiveContextDraft:
    return ActiveContextDraft(
        objective=data.get("objective"),
        status=AgentStatus(data["status"]),
        working_on=tuple(data.get("working_on", [])),
        blockers=tuple(data.get("blockers", [])),
        observations=tuple(
            _observation(o) for o in data.get("observations", [])
        ),
        graph_references=tuple(data.get("graph_references", [])),
    )


def _context(data: Mapping[str, Any]) -> ActiveContext:
    return ActiveContext(
        agent_id=data["agent_id"],
        instance_id=data["instance_id"],
        role=data["role"],
        deployment_id=data["deployment_id"],
        group_id=data["group_id"],
        draft=_draft(data["draft"]),
        version=data["version"],
        updated_at=_dt(data["updated_at"]),
        expires_at=_dt(data["expires_at"]),
        schema_version=data.get("schema_version", 1),
    )


@dataclass(slots=True)
class RedisHealth:
    backend: str = "redis"
    connectivity: str = "healthy"
    authentication: str = "authenticated"


@dataclass(slots=True)
class RedisPage:
    items: tuple[AgentPresence, ...]
    next_cursor: str | None


class RedisActiveStore:
    """Redis ActiveStore using bounded keys, TTLs, indexes, and Lua CAS."""

    _CAS = """local p=redis.call('GET',KEYS[1]); if not p then return {-2} end; local c=redis.call('GET',KEYS[2]); local v=0; if c then v=cjson.decode(c).version end; if ARGV[1]~='' and tonumber(ARGV[1])~=v then return {-1,v} end; local d=cjson.decode(ARGV[2]); d.version=v+1; local out=cjson.encode(d); redis.call('SET',KEYS[2],out,'EX',ARGV[3]); return {v+1,out}"""

    def __init__(
        self,
        url: str,
        deployment: ActiveDeployment,
        *,
        key_prefix: str = "l9gm:active",
        context_ttl_seconds: int = 60,
        presence_ttl_seconds: int = 30,
        client: Any | None = None,
        clock: Clock | None = None,
    ) -> None:
        redis, _, _ = _redis_modules()
        self._r = client or redis.from_url(url, decode_responses=True)
        self._d = deployment
        self._prefix = f"{key_prefix}:v1:{derive_deployment_hash(deployment)}"
        self._ct = context_ttl_seconds
        self._pt = presence_ttl_seconds
        self._sha: str | None = None
        self._clock: Clock = clock or (lambda: datetime.now(timezone.utc))

    def _presence_key(self, a: str, i: str) -> str:
        return f"{self._prefix}:agent:{a}:{i}:presence"

    def _context_key(self, a: str, i: str) -> str:
        return f"{self._prefix}:agent:{a}:{i}:context"

    def _index_key(self) -> str:
        return f"{self._prefix}:agent:index"

    async def _call(self, method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            return await method(*args, **kwargs)
        except Exception as exc:
            _, _, redis_error_cls = _redis_modules()
            if isinstance(exc, redis_error_cls):
                raise ActiveMemoryUnavailableError(str(exc)) from exc
            raise

    async def register(
        self, identity: AgentIdentity, _lease: AgentLease
    ) -> AgentPresence:
        # Redis has no separate lease record: the presence key's own TTL
        # (`ex=self._pt`) is the sole source of lease-expiry truth here.
        now = self._clock()
        presence = AgentPresence(
            identity=identity,
            status=AgentStatus.STARTING,
            deployment_id=self._d.deployment_id,
            started_at=now,
            heartbeat_at=now,
            expires_at=now + timedelta(seconds=self._pt),
            presence_version=1,
        )
        await self._call(
            self._r.set,
            self._presence_key(identity.agent_id, identity.instance_id),
            _dump(presence),
            ex=self._pt,
        )
        await self._call(
            self._r.zadd,
            self._index_key(),
            {
                f"{identity.agent_id}|{identity.instance_id}": presence.expires_at.timestamp()
            },
        )
        return presence

    async def renew(self, lease: AgentLease) -> AgentPresence:
        raw = await self._call(
            self._r.get, self._presence_key(lease.agent_id, lease.instance_id)
        )
        if not raw:
            raise LeaseExpiredError(lease.agent_id, lease.instance_id)
        old = _presence(json.loads(raw))
        now = self._clock()
        presence = AgentPresence(
            identity=old.identity,
            status=old.status,
            deployment_id=old.deployment_id,
            started_at=old.started_at,
            heartbeat_at=now,
            expires_at=now + timedelta(seconds=self._pt),
            presence_version=old.presence_version + 1,
        )
        await self._call(
            self._r.set,
            self._presence_key(lease.agent_id, lease.instance_id),
            _dump(presence),
            ex=self._pt,
        )
        await self._call(
            self._r.zadd,
            self._index_key(),
            {f"{lease.agent_id}|{lease.instance_id}": presence.expires_at.timestamp()},
        )
        return presence

    async def unregister(self, lease: AgentLease) -> None:
        await self._call(
            self._r.unlink,
            self._presence_key(lease.agent_id, lease.instance_id),
            self._context_key(lease.agent_id, lease.instance_id),
        )
        await self._call(
            self._r.zrem, self._index_key(), f"{lease.agent_id}|{lease.instance_id}"
        )

    async def put_context(
        self,
        lease: AgentLease,
        expected_version: int | None,
        draft: ActiveContextDraft,
    ) -> ActiveContext:
        presence = await self.get_presence(lease.agent_id, lease.instance_id)
        if presence is None:
            raise LeaseExpiredError(lease.agent_id, lease.instance_id)
        now = self._clock()
        group_id = (
            presence.identity.memory_group_ids[0]
            if presence.identity.memory_group_ids
            else "default"
        )
        data = {
            "agent_id": lease.agent_id,
            "instance_id": lease.instance_id,
            "role": presence.identity.role,
            "deployment_id": self._d.deployment_id,
            "group_id": group_id,
            "version": 0,
            "draft": json.loads(_dump(draft)),
            "updated_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=self._ct)).isoformat(),
            "schema_version": 1,
        }
        keys = [
            self._presence_key(lease.agent_id, lease.instance_id),
            self._context_key(lease.agent_id, lease.instance_id),
        ]
        args = [
            "" if expected_version is None else str(expected_version),
            json.dumps(data, separators=(",", ":")),
            str(self._ct),
        ]
        if not self._sha:
            self._sha = await self._call(self._r.script_load, self._CAS)
        try:
            result = await self._r.evalsha(self._sha, len(keys), *keys, *args)
        except Exception as exc:
            _, no_script_error_cls, redis_error_cls = _redis_modules()
            if isinstance(exc, no_script_error_cls):
                self._sha = await self._call(self._r.script_load, self._CAS)
                result = await self._call(
                    self._r.evalsha, self._sha, len(keys), *keys, *args
                )
            elif isinstance(exc, redis_error_cls):
                raise ActiveMemoryUnavailableError(str(exc)) from exc
            else:
                raise
        if int(result[0]) == -2:
            raise LeaseExpiredError(lease.agent_id, lease.instance_id)
        if int(result[0]) == -1:
            raise ContextVersionConflictError(expected_version, int(result[1]))
        return _context(json.loads(result[1]))

    async def get_context(
        self, agent_id: str, instance_id: str | None = None
    ) -> ActiveContext | None:
        if instance_id is None:
            return None
        raw = await self._call(self._r.get, self._context_key(agent_id, instance_id))
        return _context(json.loads(raw)) if raw else None

    async def get_presence(
        self, agent_id: str, instance_id: str | None = None
    ) -> AgentPresence | None:
        if instance_id is None:
            return None
        raw = await self._call(self._r.get, self._presence_key(agent_id, instance_id))
        return _presence(json.loads(raw)) if raw else None

    async def list_active(
        self, scope: AgentScope, cursor: str | None, limit: int
    ) -> RedisPage:
        start = int(cursor or 0)
        members = await self._call(
            self._r.zrange, self._index_key(), start, start + limit - 1
        )
        items = []
        for member in members:
            agent_id, instance_id = member.split("|", 1)
            presence = await self.get_presence(agent_id, instance_id)
            if (
                presence
                and (
                    scope.group_id is None
                    or scope.group_id in presence.identity.memory_group_ids
                )
                and (scope.role is None or scope.role == presence.identity.role)
            ):
                items.append(presence)
        return RedisPage(
            tuple(items), str(start + limit) if len(members) == limit else None
        )

    async def health(self) -> RedisHealth:
        await self._call(self._r.ping)
        return RedisHealth()

    async def close(self) -> None:
        await self._r.aclose()


class RedisAwarenessBus:
    """Redis Pub/Sub AwarenessBus using exact SUBSCRIBE channels only."""

    def __init__(
        self,
        url: str,
        deployment: ActiveDeployment,
        *,
        channel_prefix: str = "l9gm:active",
        client: Any | None = None,
    ) -> None:
        redis, _, _ = _redis_modules()
        self._r = client or redis.from_url(url, decode_responses=True)
        self._base = f"{channel_prefix}.v1.{derive_deployment_hash(deployment)}"

    def _channel(self, group_id: str | None) -> str:
        return f"{self._base}.group.{group_id}" if group_id else f"{self._base}.global"

    async def publish(self, event: AgentEvent) -> None:
        try:
            await self._r.publish(self._channel(event.group_id), _dump(event))
        except Exception as exc:
            raise ActiveMemoryUnavailableError(str(exc)) from exc

    async def subscribe(
        self, subscription: AgentSubscription
    ) -> AsyncIterator[AgentEvent]:
        channel = self._channel(subscription.scope.group_id)
        pubsub = self._r.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = json.loads(message["data"])
                yield AgentEvent(
                    event_id=data["event_id"],
                    event_type=AgentEventType(data["event_type"]),
                    agent_id=data["agent_id"],
                    instance_id=data["instance_id"],
                    role=data["role"],
                    deployment_id=data["deployment_id"],
                    occurred_at=_dt(data["occurred_at"]),
                    schema_version=data.get("schema_version", 1),
                    group_id=data.get("group_id"),
                    state_version=data.get("state_version"),
                    trace_id=data.get("trace_id"),
                )
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    async def health(self) -> RedisHealth:
        await self._r.ping()
        return RedisHealth()

    async def close(self) -> None:
        await self._r.aclose()
