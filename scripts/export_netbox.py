#!/usr/bin/env python3
"""Export NetBox configuration to YAML variable files for ansible-role-netbox-bootstrap.

Configuration is loaded in this order (last wins):
  1. .env in this script's directory
  2. --env-file <path> if provided
  3. Explicit CLI flags

Usage (from the scripts/ directory):
    # Minimal — values come from .env
    python export_netbox.py

    # Override specific values at runtime
    python export_netbox.py --url https://netbox.example.com --sections users,groups

See --help for all options.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click
import pynetbox
import urllib3
import yaml
from environs import Env

# ---------------------------------------------------------------------------
# Load .env from the script's own directory (not cwd).
# This populates os.environ so that Click's envvar= picks up the values.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).parent
_env = Env()
_env.read_env(_SCRIPT_DIR / ".env", recurse=False)


# ---------------------------------------------------------------------------
# Data cleaners
# ---------------------------------------------------------------------------


def _clean_common(record: dict[str, Any]) -> dict[str, Any]:
    """Remove auto-generated / instance-specific fields from any record."""
    drop = {"id", "url", "display", "created", "last_updated", "object_id"}
    return {k: v for k, v in record.items() if k not in drop}


def _resolve_nested(value: Any) -> Any:  # noqa: ANN401
    """Collapse nested related-object dicts to their slug or name.

    Lists of nested objects become lists of slugs/names.
    Recursively handles nested structures.
    """
    if isinstance(value, dict):
        if "slug" in value:
            return value["slug"]
        if "name" in value:
            return value["name"]
        if "label" in value:
            return value["label"]
        return {k: _resolve_nested(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_nested(item) for item in value]
    return value


def _clean_record(
    record: dict[str, Any],
    keep_nested: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Clean a record: drop auto-fields and resolve nested objects.

    keep_nested: field names to leave as-is (e.g. permission content_types).
    """
    cleaned = _clean_common(record)
    result: dict[str, Any] = {}
    for k, v in cleaned.items():
        result[k] = v if k in keep_nested else _resolve_nested(v)
    return {k: v for k, v in result.items() if v not in (None, "", [], {})}


def clean_user(record: dict[str, Any]) -> dict[str, Any]:
    """Clean a user record: drop password hash and session key."""
    drop = {"password", "session_key"}
    r = {k: v for k, v in record.items() if k not in drop}
    return _clean_record(r)


def clean_permission(record: dict[str, Any]) -> dict[str, Any]:
    """Clean a permission record.

    Keep object_types as app_label.model strings, groups as names, actions as list.
    """
    r = _clean_common(record)
    result: dict[str, Any] = {}
    for k, v in r.items():
        if k == "object_types":
            result[k] = [item.get("display", "") for item in (v or [])]
        elif k == "groups":
            result[k] = [item.get("name", "") for item in (v or [])]
        elif k == "users":
            result[k] = [item.get("username", "") for item in (v or [])]
        elif k in ("actions", "constraints"):
            result[k] = v
        else:
            result[k] = _resolve_nested(v)
    return {k: v for k, v in result.items() if v not in (None, "", [], {})}


def clean_custom_field(record: dict[str, Any]) -> dict[str, Any]:
    """Clean a custom field record: keep object_types as display strings."""
    r = _clean_common(record)
    result: dict[str, Any] = {}
    for k, v in r.items():
        if k == "object_types":
            result[k] = [item.get("display", "") for item in (v or [])]
        elif k in ("choices", "filter_logic", "ui_visibility"):
            result[k] = v
        else:
            result[k] = _resolve_nested(v)
    return {k: v for k, v in result.items() if v not in (None, "", [], {})}


def clean_webhook(record: dict[str, Any]) -> dict[str, Any]:
    """Clean a webhook record: keep content_types as-is."""
    r = _clean_common(record)
    result: dict[str, Any] = {}
    for k, v in r.items():
        if k == "content_types":
            result[k] = v if isinstance(v, list) else []
        else:
            result[k] = _resolve_nested(v)
    return {k: v for k, v in result.items() if v not in (None, "", [], {})}


def clean_export_template(record: dict[str, Any]) -> dict[str, Any]:
    """Clean an export template record: keep content_types and template_code as-is."""
    r = _clean_common(record)
    result: dict[str, Any] = {}
    for k, v in r.items():
        if k in ("content_types", "template_code"):
            result[k] = v
        else:
            result[k] = _resolve_nested(v)
    return {k: v for k, v in result.items() if v not in (None, "", [], {})}


def clean_custom_link(record: dict[str, Any]) -> dict[str, Any]:
    """Clean a custom link record: keep content_types and link_url as-is."""
    r = _clean_common(record)
    result: dict[str, Any] = {}
    for k, v in r.items():
        if k == "content_types":
            result[k] = v
        else:
            result[k] = _resolve_nested(v)
    return {k: v for k, v in result.items() if v not in (None, "", [], {})}


def clean_default(record: dict[str, Any]) -> dict[str, Any]:
    """Clean a record using default field stripping and nested object resolution."""
    return _clean_record(record)


# ---------------------------------------------------------------------------
# Section registry
# Each entry is a 5-tuple: section_key, pynetbox_app, pynetbox_endpoint,
# cleaner_fn, yaml_key.
# yaml_key is the top-level key written in the output YAML file. It may
# differ from section_key to avoid Ansible reserved words — e.g. the
# 'tags' section writes 'netbox_tags' because 'tags' is reserved in Ansible.
# ---------------------------------------------------------------------------

CleanerFn = Callable[[dict[str, Any]], dict[str, Any]]
SectionSpec = tuple[str, str, str, CleanerFn, str]

SECTIONS: list[SectionSpec] = [
    # Tier 1 — Users & Access
    ("groups", "users", "groups", clean_default, "groups"),
    ("users", "users", "users", clean_user, "users"),
    ("permissions", "users", "permissions", clean_permission, "permissions"),
    # Tier 2 — Extras
    ("tags", "extras", "tags", clean_default, "netbox_tags"),
    ("custom_fields", "extras", "custom_fields", clean_custom_field, "custom_fields"),
    ("custom_links", "extras", "custom_links", clean_custom_link, "custom_links"),
    ("webhooks", "extras", "webhooks", clean_webhook, "webhooks"),
    (
        "export_templates",
        "extras",
        "export_templates",
        clean_export_template,
        "export_templates",
    ),
    # Tier 3 — Tenancy
    ("tenant_groups", "tenancy", "tenant_groups", clean_default, "tenant_groups"),
    ("tenants", "tenancy", "tenants", clean_default, "tenants"),
    # Tier 4 — DCIM structure
    ("regions", "dcim", "regions", clean_default, "regions"),
    ("site_groups", "dcim", "site_groups", clean_default, "site_groups"),
    ("sites", "dcim", "sites", clean_default, "sites"),
    ("locations", "dcim", "locations", clean_default, "locations"),
    ("rack_roles", "dcim", "rack_roles", clean_default, "rack_roles"),
    ("device_roles", "dcim", "device_roles", clean_default, "device_roles"),
    ("platforms", "dcim", "platforms", clean_default, "platforms"),
    # Tier 5 — IPAM structure
    ("rirs", "ipam", "rirs", clean_default, "rirs"),
    ("aggregates", "ipam", "aggregates", clean_default, "aggregates"),
    ("vrfs", "ipam", "vrfs", clean_default, "vrfs"),
    ("route_targets", "ipam", "route_targets", clean_default, "route_targets"),
    ("vlan_groups", "ipam", "vlan_groups", clean_default, "vlan_groups"),
]

SECTION_KEYS: list[str] = [s[0] for s in SECTIONS]


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------


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
        click.echo(f"  [dry-run] would write {len(records)} records → {path}")
        if verbose:
            click.echo(content)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        click.echo(f"  ✓ {len(records):>4} records → {path}")


# ---------------------------------------------------------------------------
# Export loop (extracted to keep the Click command under complexity threshold)
# ---------------------------------------------------------------------------


def _export_sections(
    nb: pynetbox.api,
    selected: list[str],
    output_path: Path,
    *,
    dry_run: bool,
    verbose: bool,
) -> list[str]:
    """Fetch and write each requested section; return keys that failed."""
    errors: list[str] = []
    for key, app_name, endpoint_name, cleaner, yaml_key in SECTIONS:
        if key not in selected:
            continue
        click.echo(f"\n[{key}]")
        try:
            app = getattr(nb, app_name)
            endpoint = getattr(app, endpoint_name)
            raw_records = list(endpoint.all())
        except Exception as exc:  # noqa: BLE001
            click.echo(f"  ✗ Failed to fetch: {exc}", err=True)
            errors.append(key)
            continue

        cleaned: list[dict[str, Any]] = []
        for record in raw_records:
            try:
                record_dict = dict(record)
                cleaned.append(cleaner(record_dict))
            except Exception as exc:  # noqa: BLE001
                click.echo(f"  ⚠  Skipping record (clean error): {exc}", err=True)

        dest = output_path / f"{key}.yml"
        write_yaml(dest, yaml_key, cleaned, dry_run=dry_run, verbose=verbose)
    return errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _env_file_callback(
    _ctx: click.Context,
    _param: click.Parameter,
    value: str | None,
) -> str | None:
    """Eager callback: load an alternate .env and override os.environ.

    Fires before Click resolves envvar= defaults on the remaining options,
    so values in the alternate file win over the script-dir .env.
    """
    if value:
        override_env = Env()
        override_env.read_env(value, recurse=False, override=True)
    return value


@click.command()
@click.option(
    "--env-file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    is_eager=True,
    expose_value=False,
    callback=_env_file_callback,
    help="Path to an alternate .env file. Overrides script-directory .env values.",
)
@click.option("-u", "--url", required=True, envvar="NETBOX_URL", help="NetBox base URL.")
@click.option(
    "-t",
    "--token",
    required=True,
    envvar="NETBOX_TOKEN",
    help="API token including any prefix.",
)
@click.option(
    "-o",
    "--output-dir",
    default="../vars",
    show_default=True,
    envvar="NETBOX_OUTPUT_DIR",
    type=click.Path(file_okay=False),
    help="Directory to write YAML var files into.",
)
@click.option(
    "-s",
    "--sections",
    default=None,
    envvar="NETBOX_SECTIONS",
    help=f"Comma-separated sections to export. Valid: {', '.join(SECTION_KEYS)}. Omit for all.",
)
@click.option(
    "--insecure",
    is_flag=True,
    default=False,
    envvar="NETBOX_INSECURE",
    help="Disable TLS verification.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print what would be exported without writing files.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Verbose output (print YAML in dry-run mode).",
)
def export(  # noqa: PLR0913
    url: str,
    token: str,
    output_dir: str,
    sections: str | None,
    *,
    insecure: bool,
    dry_run: bool,
    verbose: bool,
) -> None:
    r"""Export NetBox configuration to YAML variable files.

    Configuration precedence (last wins):
      1. .env in the scripts/ directory
      2. --env-file <path>
      3. Explicit CLI flags

    \b
    Example — values from .env, override sections at runtime:
        python export_netbox.py --sections users,groups,permissions
    """
    if sections:
        requested = [s.strip() for s in sections.split(",")]
        invalid = [s for s in requested if s not in SECTION_KEYS]
        if invalid:
            msg = f"Unknown sections: {', '.join(invalid)}. Valid: {', '.join(SECTION_KEYS)}"
            raise click.BadParameter(msg)
        selected = requested
    else:
        selected = SECTION_KEYS

    if insecure:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        click.echo("⚠️  TLS verification disabled.", err=True)

    click.echo(f"Connecting to {url} ...")
    try:
        nb = pynetbox.api(url, token=token)
        nb.http_session.verify = not insecure
        nb.status()
    except Exception as exc:  # noqa: BLE001
        click.echo(f"✗ Failed to connect to NetBox: {exc}", err=True)
        sys.exit(1)

    output_path = Path(output_dir)
    click.echo(f"Exporting {len(selected)} section(s) → {output_path}" + (" [DRY RUN]" if dry_run else ""))

    errors = _export_sections(nb, selected, output_path, dry_run=dry_run, verbose=verbose)

    click.echo()
    if errors:
        click.echo(f"⚠️  Completed with errors in: {', '.join(errors)}", err=True)
        sys.exit(1)
    else:
        click.echo("✓ Export complete.")


if __name__ == "__main__":
    export()
