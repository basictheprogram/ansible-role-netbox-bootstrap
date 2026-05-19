"""YAML serialization helpers shared by netbox-bootstrap export scripts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import yaml
from rich.console import Console
from rich.syntax import Syntax

_console = Console(highlight=False)


def _yaml_str_representer(dumper: yaml.Dumper, data: str) -> yaml.Node:
    """Use literal block style for multi-line strings."""
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def _build_dumper() -> type[yaml.Dumper]:
    """Build a YAML Dumper with a literal-block string representer."""
    dumper = yaml.Dumper
    dumper.add_representer(str, _yaml_str_representer)
    return dumper


def write_yaml(
    path: Path,
    key: str,
    records: list[dict[str, Any]],
    *,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Serialize records to a YAML file under the given top-level key."""
    data = {key: records}
    content = yaml.dump(
        data,
        Dumper=_build_dumper(),
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    if dry_run:
        _console.print(f"  [dim]~[/dim] would write [bold]{len(records)}[/bold] records → [dim]{path}[/dim]")
        if verbose:
            _console.print(Syntax(content, "yaml", theme="ansi_dark"))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        _console.print(f"  [green]✓[/green] {len(records):>4} records → [dim]{path}[/dim]")
