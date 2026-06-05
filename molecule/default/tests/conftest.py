"""Pytest configuration and shared fixtures for molecule tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from testinfra.host import Host


@pytest.fixture(scope="session")
def host(host: Host) -> Host:
    """Return the testinfra host under test."""
    return host
