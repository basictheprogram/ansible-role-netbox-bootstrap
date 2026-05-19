#!/usr/bin/env python3
"""Export AWS RDS DB instances to vars/rds_instances.yml.

Queries the RDS API for DB instances in the target region and writes them
in the schema expected by ansible-role-netbox-bootstrap. Defaults to all
engines; use --engines to narrow to specific engine names.

Credentials are resolved via the standard AWS credential chain — ~/.aws,
environment variables, or instance profile. Pass --profile to select a named
profile. No credentials are written to disk by this script.

Configuration is loaded in this order (last wins):
  1. .env in this script's directory
  2. --env-file <path> if provided
  3. Explicit CLI flags

Usage (from the scripts/ directory):
    # All instances in the region
    python export_aws_rds.py --region us-east-1

    # Filter to postgres and mysql only
    python export_aws_rds.py --region us-east-1 --engines postgres,mysql

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
    """Convert an RDS identifier to a NetBox-compatible slug (lowercase, hyphens).

    RDS identifiers are already lowercase and hyphen-separated per AWS rules,
    but dots are replaced defensively for any edge cases.
    Example: my-db-01 -> my-db-01, db.t3.micro -> db-t3-micro
    """
    return name.replace(".", "-").lower()


def _transform(record: dict[str, Any]) -> dict[str, Any]:
    """Transform a raw RDS DBInstance record to an rds_instances entry."""
    identifier = record["DBInstanceIdentifier"]
    engine = record.get("Engine", "")
    engine_version = record.get("EngineVersion", "")
    instance_class = record.get("DBInstanceClass", "")
    az = record.get("AvailabilityZone", "")
    endpoint = record.get("Endpoint") or {}
    tags = {t["Key"]: t["Value"] for t in record.get("TagList", [])}

    return {
        "name": identifier,
        "slug": _slugify(identifier),
        "description": f"{engine} {engine_version}, {instance_class}, {az}",
        "engine": engine,
        "engine_version": engine_version,
        "instance_class": instance_class,
        "status": record.get("DBInstanceStatus", ""),
        "endpoint": endpoint.get("Address", ""),
        "port": endpoint.get("Port", 0),
        "allocated_storage": record.get("AllocatedStorage", 0),
        "storage_type": record.get("StorageType", ""),
        "multi_az": record.get("MultiAZ", False),
        "tags": tags,
        "comments": "",
    }


# ---------------------------------------------------------------------------
# AWS fetch
# ---------------------------------------------------------------------------


def _fetch_db_instances(
    client: Any,  # noqa: ANN401
    *,
    engines: list[str],
    status: str | None,
    verbose: bool,
) -> list[dict[str, Any]]:
    """Fetch RDS DB instances via paginated describe_db_instances.

    Engine filtering is applied server-side via the Filters parameter.
    Status filtering is applied client-side (no server-side status filter
    is available on describe_db_instances).
    Results are sorted by DBInstanceIdentifier for stable YAML output.
    """
    kwargs: dict[str, Any] = {}
    if engines:
        kwargs["Filters"] = [{"Name": "engine", "Values": engines}]
        console.print(f"[dim]Engines: {', '.join(sorted(engines))}[/dim]")

    paginator = client.get_paginator("describe_db_instances")
    raw: list[dict[str, Any]] = []
    for page in paginator.paginate(**kwargs):
        raw.extend(
            record for record in page["DBInstances"] if status is None or record.get("DBInstanceStatus") == status
        )
        if verbose:
            console.print(f"  [dim]fetched page — {len(raw)} matching instances so far[/dim]")

    return sorted(raw, key=lambda r: r["DBInstanceIdentifier"])


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
    "-e",
    "--engines",
    default=None,
    envvar="AWS_EXPORT_RDS_ENGINES",
    help=(
        "Comma-separated DB engine names to include "
        "(e.g. postgres,mysql,aurora-postgresql). Omit to export all engines."
    ),
)
@click.option(
    "-s",
    "--status",
    default=None,
    envvar="AWS_EXPORT_RDS_STATUS",
    help="Filter by DB instance status (e.g. available). Omit to export all statuses.",
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
    engines: str | None,
    status: str | None,
    *,
    dry_run: bool,
    verbose: bool,
) -> None:
    r"""Export AWS RDS DB instances to vars/rds_instances.yml.

    By default all DB instances in the region are exported. Use --engines
    to narrow to specific database engines (e.g. postgres,mysql), and
    --status to filter by instance state (e.g. available).

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
        python export_aws_rds.py --region us-east-1
        python export_aws_rds.py --region us-east-1 --engines postgres,mysql
        python export_aws_rds.py --region us-east-1 --status available
        python export_aws_rds.py --region us-east-1 --dry-run --verbose
    """
    console.rule("[bold blue]AWS RDS DB Instances Export[/bold blue]")

    if dry_run:
        console.print("[yellow]DRY RUN — no files will be written[/yellow]\n")

    engine_list = [e.strip() for e in engines.split(",")] if engines else []

    console.print(f"Region:   [cyan]{region}[/cyan]")
    console.print(f"Profile:  [cyan]{profile or 'default'}[/cyan]")
    console.print(f"Engines:  [cyan]{', '.join(engine_list) if engine_list else 'all'}[/cyan]")
    console.print(f"Status:   [cyan]{status or 'all'}[/cyan]\n")

    try:
        session = boto3.Session(profile_name=profile, region_name=region)
        client = session.client("rds")
        client.describe_db_engine_versions(MaxRecords=1)
        console.print(f"[green]✓[/green] Connected to RDS in [bold]{region}[/bold]\n")
    except (BotoCoreError, ClientError) as exc:
        err_console.print(f"[red]✗[/red] AWS connection failed: {exc}")
        sys.exit(1)

    console.print("[bold cyan]rds_instances[/bold cyan]")
    try:
        raw = _fetch_db_instances(
            client,
            engines=engine_list,
            status=status,
            verbose=verbose,
        )
    except (BotoCoreError, ClientError) as exc:
        err_console.print(f"  [red]✗[/red] Failed to fetch DB instances: {exc}")
        sys.exit(1)

    records: list[dict[str, Any]] = []
    for item in raw:
        try:
            records.append(_transform(item))
        except (KeyError, IndexError) as exc:
            err_console.print(
                f"  [yellow]⚠[/yellow]  Skipping {item.get('DBInstanceIdentifier', '?')} (transform error): {exc}"
            )

    output_path = Path(output_dir)
    dest = output_path / "rds_instances.yml"
    write_yaml(dest, "rds_instances", records, dry_run=dry_run, verbose=verbose)

    console.print()
    console.rule("[green]✓ Export complete[/green]", style="green")


if __name__ == "__main__":
    export()
