"""Connector CLI commands for Agent Causal Decision Tool.

Usage:
  agent-causal connect posthog --experiment-id <id>
  agent-causal connect posthog --experiment-id <id> --decide
  agent-causal connect posthog --dry-run
"""

from __future__ import annotations

import json
import sys
from typing import Optional

import click

from ..actions import run_action
from .posthog import PostHogConnector, _load_posthog_config
from . import ConnectorError, InsufficientDataError, ConnectorAuthError


def _echo_json(data: dict):
    """Print data as JSON to stdout."""
    print(json.dumps(data, indent=2))


@click.group("connect")
def connect_group():
    """Connect to external experiment data sources."""
    pass


@connect_group.command("posthog")
@click.option(
    "--experiment-id",
    type=str,
    default=None,
    help="PostHog experiment ID to fetch",
)
@click.option(
    "--decide",
    is_flag=True,
    default=False,
    help="Run the fetched experiment data through the decision workflow",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Validate connector configuration (don't fetch any data)",
)
@click.option(
    "--api-key",
    type=str,
    default=None,
    help="PostHog API key (or set POSTHOG_API_KEY env var)",
)
@click.option(
    "--project-id",
    type=str,
    default=None,
    help="PostHog project ID (or set POSTHOG_PROJECT_ID env var)",
)
@click.option(
    "--instance-url",
    type=str,
    default=None,
    help="PostHog instance URL (default: https://app.posthog.com)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "text"]),
    default="json",
    help="Output format",
)
def posthog(
    experiment_id: Optional[str],
    decide: bool,
    dry_run: bool,
    api_key: Optional[str],
    project_id: Optional[str],
    instance_url: Optional[str],
    output_format: str,
):
    """Fetch experiment data from PostHog and optionally run a decision."""
    try:
        connector = PostHogConnector(
            api_key=api_key,
            project_id=project_id,
            instance_url=instance_url,
        )

        if dry_run:
            if connector.health_check():
                click.echo("PostHog connector: configured ✓")
                # Show what's loaded
                click.echo(f"  API key : {connector.masked_api_key}")
                click.echo(f"  Project : {connector._project_id}")
                click.echo(f"  Instance: {connector._instance_url}")
            else:
                click.echo("PostHog connector: not configured ✗", err=True)
                click.echo("  Set POSTHOG_API_KEY and POSTHOG_PROJECT_ID env vars,", err=True)
                click.echo("  or add them to ~/.posthogrc", err=True)
                sys.exit(1)
            return

        if not experiment_id:
            click.echo("Error: --experiment-id is required (unless --dry-run)", err=True)
            sys.exit(1)

        result = connector.fetch_experiment(experiment_id)

        if decide:
            # Run the fetched data through the decision workflow
            decision = run_action("decide", result.data)
            if output_format == "text":
                _print_decision_text(decision)
            else:
                _echo_json(decision)
        else:
            if output_format == "text":
                _print_experiment_text(result.data)
            else:
                _echo_json(result.to_dict())

    except ConnectorAuthError as exc:
        click.echo(f"Auth error: {exc}", err=True)
        sys.exit(1)
    except InsufficientDataError as exc:
        click.echo(f"Insufficient data: {exc}", err=True)
        _echo_json(exc.to_dict())
        sys.exit(1)
    except ConnectorError as exc:
        click.echo(f"Connector error: {exc}", err=True)
        sys.exit(1)


def _print_experiment_text(data: dict):
    """Print normalized experiment data in human-readable text format."""
    click.echo(f"Experiment: {data.get('experiment_name', 'unknown')}")
    click.echo(f"Feature flag: {data.get('feature_flag_key', 'N/A')}")
    click.echo(f"Variant: {data.get('variant_name', 'test')}")
    click.echo(f"Period: {data.get('start_date', '?')} → {data.get('end_date', '?')}")
    click.echo(f"Control conversions: {data.get('control_conversions')} / {data.get('control_total')}")
    click.echo(f"Variant conversions: {data.get('variant_conversions')} / {data.get('variant_total')}")


def _print_decision_text(decision: dict):
    """Print decision result in human-readable text format."""
    result = decision.get("result", {})
    sel = result.get("selected_method", "unknown")
    decision_val = result.get("decision", "unknown")
    reason = result.get("selection_reason", "")
    click.echo(f"Decision: {decision_val} (via {sel})")
    click.echo(f"Reason: {reason}")
    stats = result.get("statistics", {})
    if stats:
        click.echo(f"Statistics: {json.dumps(stats, indent=2)}")


# Register connect subcommand with the main CLI
connect_group.add_command(posthog)