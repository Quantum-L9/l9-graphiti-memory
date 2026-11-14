# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/redaction.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 3.0.0
#   updated: 2026-11-14

"""The one redaction path for connection strings and connection errors.

A database driver's error text routinely quotes the connection string it was
handed, or the host, port, user and database it tried. None of that may reach
a log line, a raised message, a health body or startup stderr. Every store or
connection exception that is logged or surfaced passes through
:func:`redact_connection_error` first; a DSN that must be named is passed
through :func:`redact_dsn`.

Redaction is two-layered. The generic layer strips every credential shape a
connection string can carry, whatever produced the text: ``password=...`` in
keyword form (quoted or bare), the userinfo of a URI (``user:pass@``), and the
value of any query parameter whose name says it is secret. The specific layer,
when the DSN is known, also replaces each of its own component values (the
whole DSN, password, user, host, port, database), so a driver message such as
``could not translate host name "db.internal"`` loses the host as well.
"""

from __future__ import annotations

import re
from urllib.parse import unquote

REDACTED = "***"

# Stable machine reason codes a probe may publish in place of exception text.
STORE_UNAVAILABLE = "store_unavailable"
PROBE_FAILED = "probe_failed"

# Keyword form: ``key=value`` or ``key = 'quoted value'`` (libpq rules: a
# quoted value may contain escaped quotes and spaces).
_KEYWORD_PAIR = re.compile(r"(\b[A-Za-z_][A-Za-z0-9_]*)\s*=\s*('(?:[^'\\]|\\.)*'?|[^\s'&]+)")
# URI userinfo: ``scheme://user:pass@`` or ``scheme://user@``. The password
# may itself contain ``@`` or ``:``; the last ``@`` before the host ends it.
_URI_USERINFO = re.compile(r"(\b[A-Za-z][A-Za-z0-9+.-]*://)[^\s/?#\"']*@")
_URI = re.compile(
    r"^\s*[A-Za-z][A-Za-z0-9+.-]*://"
    r"(?:(?P<userinfo>[^/?#]*)@)?"
    r"(?P<host>\[[^\]/?#]*\]?|[^:/?#]*)"
    r"(?::(?P<port>[^/?#]*))?"
    r"(?:/(?P<path>[^?#]*))?"
    r"(?:\?(?P<query>[^#]*))?"
)
_SECRET_NAME = re.compile(r"pass|secret|token|key|cred|auth", re.IGNORECASE)
# Components whose values identify where the store is or who connects to it.
_IDENTIFYING = ("password", "user", "host", "hostaddr", "port", "dbname", "sslpassword")
# Values this short are too likely to collide with unrelated text to replace
# by substring; the generic layer still strips them where they are labelled.
_MIN_COMPONENT_LENGTH = 3


def _unquote_keyword_value(value: str) -> str:
    if value.startswith("'"):
        value = value[1:-1] if value.endswith("'") and len(value) > 1 else value[1:]
        value = re.sub(r"\\(.)", r"\1", value)
    return value


def dsn_components(dsn: str) -> tuple[str, ...]:
    """Every identifying value a DSN carries, parsed leniently.

    A DSN that the driver itself rejects still yields what it can: the point
    is to know what to scrub, never to validate.
    """

    values: list[str] = []
    match = _URI.match(dsn)
    if match is not None:
        userinfo = match.group("userinfo") or ""
        user, _, password = userinfo.partition(":")
        values.extend([user, password, unquote(user), unquote(password)])
        host = (match.group("host") or "").strip("[]")
        port = match.group("port") or ""
        path = match.group("path") or ""
        # libpq percent-decodes every URI component before it uses or reports
        # it, so the decoded form is what a driver message carries.
        values.extend([host, port, path, unquote(host), unquote(port), unquote(path)])
        for pair in (match.group("query") or "").split("&"):
            name, _, value = pair.partition("=")
            if name in _IDENTIFYING or _SECRET_NAME.search(name):
                values.extend([value, unquote(value)])
    else:
        for name, raw in _KEYWORD_PAIR.findall(dsn):
            if name in _IDENTIFYING or _SECRET_NAME.search(name):
                values.extend([raw, _unquote_keyword_value(raw)])
    return tuple(
        value for value in dict.fromkeys(values) if len(value.strip()) >= _MIN_COMPONENT_LENGTH
    )


def _generic(text: str) -> str:
    text = _URI_USERINFO.sub(lambda m: f"{m.group(1)}{REDACTED}@", text)

    def keyword(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in _IDENTIFYING or _SECRET_NAME.search(name):
            return f"{name}={REDACTED}"
        return match.group(0)

    return _KEYWORD_PAIR.sub(keyword, text)


def redact_connection_error(text: str, dsn: str | None = None) -> str:
    """Return ``text`` with every credential and store coordinate removed."""

    if dsn:
        stripped = dsn.strip()
        if stripped:
            text = text.replace(stripped, REDACTED)
        # Longest first, so a password containing the user name is removed whole.
        for value in sorted(dsn_components(dsn), key=len, reverse=True):
            text = text.replace(value, REDACTED)
    return _generic(text)


def redact_dsn(dsn: str) -> str:
    """A DSN with every identifying component replaced; safe to print."""

    return redact_connection_error(dsn, dsn)
