"""Verify Python 3 is available on the control-node container."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from testinfra.host import Host


def test_python3_installed(host: Host) -> None:
    """Python 3 must be present — required by Ansible and the export scripts."""
    python = host.package("python3")
    assert python.is_installed


def test_python3_version(host: Host) -> None:
    """Python 3 must be 3.10 or newer."""
    result = host.run("python3 -c 'import sys; print(sys.version_info[:2])'")
    assert result.rc == 0
    # Output looks like "(3, 11)" — extract the minor version integer
    version_str = result.stdout.strip()
    major, minor = (int(x) for x in version_str.strip("()").split(", "))
    assert major == 3
    assert minor >= 10
