"""Click CLI helpers shared by netbox-bootstrap export scripts."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from environs import Env

if TYPE_CHECKING:
    import click


def load_script_env(script_file: str | Path) -> None:
    """Load .env from the directory containing script_file.

    Call at module level in each script, passing __file__:

        load_script_env(__file__)

    Uses load_dotenv with override=False so existing environment variables
    are never clobbered.
    """
    load_dotenv(Path(script_file).resolve().parent / ".env", override=False)


def env_file_callback(
    _ctx: click.Context,
    _param: click.Parameter,
    value: str | None,
) -> str | None:
    """Eager Click callback: load an alternate .env and override os.environ.

    Fires before Click resolves envvar= defaults on the remaining options,
    so values in the alternate file win over the script-dir .env.
    """
    if value:
        env = Env()
        env.read_env(value, recurse=False, override=True)
    return value
