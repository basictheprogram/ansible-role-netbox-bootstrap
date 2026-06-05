"""Verify Ansible meets the minimum version required by the role."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from testinfra.host import Host

_MIN_ANSIBLE_VERSION = (2, 20)


def test_ansible_installed(host: Host) -> None:
    """Ansible must be installed on the control-node container."""
    result = host.run("ansible --version")
    assert result.rc == 0


def test_ansible_version(host: Host) -> None:
    """Ansible must be >= 2.20 as required by meta/main.yml."""
    result = host.run(
        "python3 -c \"import ansible; v=tuple(int(x) for x in ansible.__version__.split('.')[:2]);print(v)\""
    )
    assert result.rc == 0
    version_str = result.stdout.strip()
    major, minor = (int(x) for x in version_str.strip("()").split(", "))
    assert (major, minor) >= _MIN_ANSIBLE_VERSION
