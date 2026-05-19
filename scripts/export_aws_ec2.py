#!/usr/bin/env python3
"""Export AWS EC2 instance types to vars/virtual_machine_types.yml.

Queries the EC2 API for a targeted set of instance families and writes them
in the schema expected by ansible-role-netbox-bootstrap. Defaults to the
general-purpose t and m families; extend with --families for other needs.

Credentials are resolved via the standard AWS credential chain — ~/.aws,
environment variables, or instance profile. Pass --profile to select a named
profile. No credentials are written to disk by this script.

Configuration is loaded in this order (last wins):
  1. .env in this script's directory
  2. --env-file <path> if provided
  3. Explicit CLI flags

Usage (from the scripts/ directory):
    # Minimal — region from .env
    python export_aws_ec2.py

    # Override at runtime
    python export_aws_ec2.py --region us-east-1 --profile staging

See --help for all options.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import boto3
import click
from botocore.exceptions import BotoCoreError, ClientError
from export_utils import env_file_callback, load_script_env, write_yaml
from rich.console import Console

# ---------------------------------------------------------------------------
# Load .env from the script's own directory (not cwd).
# ---------------------------------------------------------------------------
load_script_env(__file__)

console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Convert an EC2 instance type name to a NetBox-compatible slug.

    Dots are replaced with hyphens; the result is lowercased.
    Examples: t3.micro -> t3-micro, m5.xlarge -> m5-xlarge
    """
    return name.replace(".", "-").lower()


def _build_description(
    vcpus: float,
    memory_mib: int,
    architecture: str,
    *,
    current_gen: bool,
) -> str:
    """Build a human-readable description from EC2 instance type fields."""
    generation = "current generation" if current_gen else "previous generation"
    return f"{vcpus} vCPUs, {memory_mib} MB, {architecture}, {generation}"


def _transform(record: dict[str, Any]) -> dict[str, Any]:
    """Transform a raw EC2 InstanceType record to a virtual_machine_types entry."""
    name = record["InstanceType"]
    vcpus = float(record["VCpuInfo"]["DefaultVCpus"])
    memory_mib = int(record["MemoryInfo"]["SizeInMiB"])
    architecture = record["ProcessorInfo"]["SupportedArchitectures"][0]
    current_gen = record.get("CurrentGeneration", False)

    return {
        "name": name,
        "slug": _slugify(name),
        "description": _build_description(
            vcpus,
            memory_mib,
            architecture,
            current_gen=current_gen,
        ),
        "vcpus": vcpus,
        "memory": memory_mib,
        "default_platform": "",
        "tags": [],
        "owner_group": "",
        "owner": "",
        "comments": "",
    }


# ---------------------------------------------------------------------------
# AWS fetch
# ---------------------------------------------------------------------------


def _family(instance_type: str) -> str:
    """Return the generation string of an instance type (e.g. 't3' from 't3.micro')."""
    return instance_type.split(".", maxsplit=1)[0]


def _fetch_instance_types(
    client: Any,  # noqa: ANN401
    *,
    families: list[str],
    current_gen_only: bool,
    verbose: bool,
) -> list[dict[str, Any]]:
    """Fetch EC2 instance types via paginated describe_instance_types.

    Results are filtered to the requested families client-side and sorted
    by InstanceType name for stable YAML output.
    """
    filters = []
    if current_gen_only:
        filters.append({"Name": "current-generation", "Values": ["true"]})
        console.print("[dim]Filtering to current-generation instances only[/dim]")

    family_set = set(families)
    console.print(f"[dim]Families: {', '.join(sorted(family_set))}[/dim]")

    paginator = client.get_paginator("describe_instance_types")
    raw: list[dict[str, Any]] = []
    for page in paginator.paginate(Filters=filters):
        raw.extend(
            record
            for record in page["InstanceTypes"]
            if any(_family(record["InstanceType"]).startswith(f) for f in family_set)
        )
        if verbose:
            console.print(f"  [dim]fetched page — {len(raw)} matching instance types so far[/dim]")

    return sorted(raw, key=lambda r: r["InstanceType"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--env-file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    is_eager=True,
    expose_value=False,
    callback=env_file_callback,
    help="Path to an alternate .env file. Overrides script-directory .env values.",
)
@click.option(
    "-r",
    "--region",
    required=True,
    envvar="AWS_EXPORT_REGION",
    help="AWS region to query (e.g. us-east-1).",
)
@click.option(
    "-p",
    "--profile",
    default=None,
    envvar="AWS_EXPORT_PROFILE",
    help="AWS CLI profile name. Uses default credential chain if omitted.",
)
@click.option(
    "-o",
    "--output-dir",
    default="../vars",
    show_default=True,
    envvar="AWS_EXPORT_OUTPUT_DIR",
    type=click.Path(file_okay=False),
    help="Directory to write YAML var files into.",
)
@click.option(
    "-f",
    "--families",
    default="t,m",
    show_default=True,
    envvar="AWS_EXPORT_FAMILIES",
    help="Comma-separated list of instance family prefixes to include (e.g. t,m,c).",
)
@click.option(
    "--current-gen-only",
    is_flag=True,
    default=False,
    envvar="AWS_EXPORT_CURRENT_GEN_ONLY",
    help="Export current-generation instance types only.",
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
    region: str,
    profile: str | None,
    output_dir: str,
    families: str,
    *,
    current_gen_only: bool,
    dry_run: bool,
    verbose: bool,
) -> None:
    r"""Export AWS EC2 instance types to vars/virtual_machine_types.yml.

    Only the instance families specified by --families are exported.
    The default (t,m) covers burstable and general-purpose types — enough
    for most NetBox VM type bootstraps without pulling in GPU, HPC, or
    bare-metal records.

    Credentials are resolved via the standard AWS credential chain
    (~/.aws, environment variables, instance profile). Pass --profile
    to select a named profile.

    \b
    Configuration precedence (last wins):
      1. .env in the scripts/ directory
      2. --env-file <path>
      3. Explicit CLI flags

    \b
    Examples:
        python export_aws_ec2.py --region us-east-1
        python export_aws_ec2.py --region eu-west-1 --profile staging
        python export_aws_ec2.py --region us-east-1 --families t,m,c --current-gen-only
        python export_aws_ec2.py --region us-east-1 --dry-run --verbose
    """
    console.rule("[bold blue]AWS EC2 Instance Types Export[/bold blue]")

    if dry_run:
        console.print("[yellow]DRY RUN — no files will be written[/yellow]\n")

    family_list = [f.strip() for f in families.split(",") if f.strip()]

    console.print(f"Region:   [cyan]{region}[/cyan]")
    console.print(f"Profile:  [cyan]{profile or 'default'}[/cyan]")
    console.print(f"Families: [cyan]{', '.join(family_list)}[/cyan]\n")

    try:
        session = boto3.Session(profile_name=profile, region_name=region)
        client = session.client("ec2")
        client.describe_account_attributes()
        console.print(f"[green]✓[/green] Connected to EC2 in [bold]{region}[/bold]\n")
    except (BotoCoreError, ClientError) as exc:
        err_console.print(f"[red]✗[/red] AWS connection failed: {exc}")
        sys.exit(1)

    console.print("[bold cyan]virtual_machine_types[/bold cyan]")
    try:
        raw = _fetch_instance_types(
            client,
            families=family_list,
            current_gen_only=current_gen_only,
            verbose=verbose,
        )
    except (BotoCoreError, ClientError) as exc:
        err_console.print(f"  [red]✗[/red] Failed to fetch instance types: {exc}")
        sys.exit(1)

    records: list[dict[str, Any]] = []
    for item in raw:
        try:
            records.append(_transform(item))
        except (KeyError, IndexError) as exc:
            err_console.print(
                f"  [yellow]⚠[/yellow]  Skipping {item.get('InstanceType', '?')} (transform error): {exc}"
            )

    output_path = Path(output_dir)
    dest = output_path / "virtual_machine_types.yml"
    write_yaml(dest, "virtual_machine_types", records, dry_run=dry_run, verbose=verbose)

    console.print()
    console.rule("[green]✓ Export complete[/green]", style="green")


if __name__ == "__main__":
    export()
