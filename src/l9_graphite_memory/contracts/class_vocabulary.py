# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/class_vocabulary.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-09-19

"""The one memory-class vocabulary, shared by every transport.

Before this module the CLI and the MCP agent door each carried their own alias
table. They disagreed: ``lesson`` resolved to :attr:`MemoryClass.PROCEDURAL`
through ``l9-memory write`` and to :attr:`MemoryClass.INSIGHT` through
``memory.write_agent``. Nothing errored, so a caller filtering
``memory_classes=["insight"]`` silently missed every lesson the other lane had
written, and the two lanes could not produce a comparable corpus.

One table now answers "what class is this spelling?" for the CLI's ``--kind``,
for the MCP ``memory_class`` argument, and for the tool description an agent
reads before calling. ``lesson`` resolves to ``procedural`` everywhere: that is
the established meaning, carried by the CLI since the legacy kind map was
introduced and by the corpus already written through it.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from .enums import MemoryClass

#: Accepted non-canonical spellings and the class each resolves to.
#:
#: A canonical ``MemoryClass`` value is always accepted and is deliberately
#: absent here — :func:`resolve_memory_class` tries the enum first, so this
#: table holds only the spellings that would otherwise be rejected.
CLASS_ALIASES: Mapping[str, MemoryClass] = MappingProxyType(
    {
        "lesson": MemoryClass.PROCEDURAL,
        "note": MemoryClass.OBSERVATION,
        "fact": MemoryClass.SEMANTIC,
        "manifest": MemoryClass.META,
        # A pickup/continuation record is what a session resumes from, which is
        # episodic. The consumer has resolved `pickup_context` that way for as
        # long as it has had a kind table, and its continuation capsule is
        # written as an episodic record; the agent door's own table said `meta`,
        # which is the same divergence this module exists to remove. The
        # established meaning wins.
        "pickup": MemoryClass.EPISODIC,
        "pickup_context": MemoryClass.EPISODIC,
        "session": MemoryClass.EPISODIC,
        "session_summary": MemoryClass.EPISODIC,
    }
)

#: Classes an agent may assert on the ungated agent lane (``memory.write_agent``).
#:
#: Every class except :attr:`MemoryClass.IDENTITY`. An identity record asserts
#: who a subject *is*; that claim is not something an agent may make for itself
#: on a lane that takes no phase-lock and no human review, so it stays on the
#: governed and operator paths.
AGENT_WRITABLE_CLASSES: frozenset[MemoryClass] = frozenset(
    member for member in MemoryClass if member is not MemoryClass.IDENTITY
)


def known_class_spellings() -> tuple[str, ...]:
    """Every spelling :func:`resolve_memory_class` accepts, sorted."""

    canonical = {member.value for member in MemoryClass}
    return tuple(sorted(canonical | set(CLASS_ALIASES)))


def resolve_memory_class(value: str) -> MemoryClass:
    """Resolve a caller-supplied spelling to its canonical class.

    Resolution is a single pass: a canonical value wins, otherwise the alias
    table answers once. An alias never points at another alias, which
    :mod:`tests.unit.test_class_vocabulary` asserts, so there is no chain to
    follow and no order in which two tables can disagree.

    Raises:
        ValueError: the spelling is neither a class nor a known alias.
    """

    text = str(value)
    try:
        return MemoryClass(text)
    except ValueError:
        pass
    resolved = CLASS_ALIASES.get(text)
    if resolved is None:
        raise ValueError(
            f"unknown memory class {text!r}; choose from {', '.join(known_class_spellings())}"
        )
    return resolved


def agent_writable_class(value: str) -> MemoryClass:
    """Resolve a spelling and require it be writable on the agent lane.

    Raises:
        ValueError: the spelling is unknown, or names a class the agent lane
            does not accept.
    """

    resolved = resolve_memory_class(value)
    if resolved not in AGENT_WRITABLE_CLASSES:
        allowed = ", ".join(sorted(member.value for member in AGENT_WRITABLE_CLASSES))
        raise ValueError(
            f"the agent write lane does not accept memory_class={value!r} "
            f"(resolves to {resolved.value}). Allowed: {allowed}"
        )
    return resolved


def alias_summary() -> str:
    """The alias table rendered for a tool description or a help string.

    Generated rather than hand-maintained: a fourth copy of the vocabulary is
    how the first three drifted apart.
    """

    return ", ".join(
        f"{spelling}→{member.value}" for spelling, member in sorted(CLASS_ALIASES.items())
    )


def agent_writable_summary() -> str:
    """The agent-lane allowlist rendered for a tool description."""

    return ", ".join(sorted(member.value for member in AGENT_WRITABLE_CLASSES))


__all__ = [
    "AGENT_WRITABLE_CLASSES",
    "CLASS_ALIASES",
    "agent_writable_class",
    "agent_writable_summary",
    "alias_summary",
    "known_class_spellings",
    "resolve_memory_class",
]
