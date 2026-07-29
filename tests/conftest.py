"""Root pytest configuration for the active-memory test additions.

This file exists so `pytest-asyncio` auto mode and the `tests.conformance`/
`tests.external_runtime` packages resolve correctly when this overlay is
merged into the target repository's existing `tests/` tree. If the
target repository already defines a root `tests/conftest.py`, merge the
`asyncio_mode` setting into it instead of overwriting.
"""

from __future__ import annotations

import pytest

pytest_plugins: list[str] = []


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "asyncio: mark test as asyncio-based (provided by pytest-asyncio)"
    )
