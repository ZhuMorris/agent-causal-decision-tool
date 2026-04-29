"""CLI for Agent Causal Decision Tool"""

import click
import json
import sys
from pathlib import Path

from ab_test import calculate_ab
from did import calculate_did


@click.group()
@click.version_option(version="0.1.0")
def main():
    """Agent Causal Decision Tool - causal decision and audit for AI agents"""
    pass


@main.command("ab")
@click.option("--control", required=True, help="Control group: conversions/total (e.g., 100/5000)")
@click.option("--variant", required=True, help="Variant group: conversions/total (e.g., 120/5000)")
@click.option("--name", default="variant_1", help="Variant name")
@click.option("--format", "output_format", type=click.Choice(["json", "text"]), default="json")
def ab_test(control, variant, name, output_format):
    """Run A/B test analysis"""
    try:
        c_parts = control.split("/")
        v_parts = variant.split("/")
        
        input_data = {
            "control_conversions": int(c_parts[0]),
            "control_total": int(c_parts[1]),
            "variant_conversions": int(v_parts[0]),
            "variant_total": int(v_parts[1]),
            "variant_name": name
        }
    except (ValueError, IndexError) as e:
        click.echo(f"Error parsing input: {e}", err=True)
        click.echo("Use format: --control 100/5000 --variant 120/5000")
        sys.exit(1)
    
    result = calculate_ab(input_data)
    
    if output_format == "json":
        click.echo(result.model_dump_json(indent=2))
    else:
        _print_ab_text(result)


@main.command("did")
@click.option("--pre-control", required=True, type=float, help="Control group metric before treatment")
@click.option("--post-control", required=True, type=float, help="Control group metric after treatment")
@click.option("--pre-treated", required=True, type=float, help="Treated group metric before treatment")
@click.option("--post-treated", required=True, type=float, help="Treated group metric after treatment")
@click.option("--format", "output_format", type=click.Choice(["json", "text"]), default="json")
def did_analysis(pre_control, post_control, pre_treated, post_treated, output_format):
    """Run Difference-in-Differences analysis"""
    input_data = {
        "pre_control": pre_control,
        "post_control": post_control,
        "pre_treated": pre_treated,
        "post_treated": post_treated
    }
    
    result = calculate_did(input_data)
    
    if output_format == "json":
        click.echo(result.model_dump_json(indent=2))
    else:
        _print_did_text(result)


@main.command("audit")
@click.argument("input_file", type=click.Path(exists=True))
def audit(input_file):
    """Reconstruct and audit a previous decision"""
    with open(input_file, "r") as f:
        data = json.load(f)
    
    # Re-run based on mode
    if data.get("mode") == "ab_test":
        result = calculate_ab(data.get("inputs", {}))
        click.echo("=== A/B Test Audit ===")
    elif data.get("mode") == "did":
        result = calculate_did(data.get("inputs", {}))
        click.echo("=== DiD Audit ===")
    else:
        click.echo(f"Unknown mode: {data.get('mode')}", err=True)
        sys.exit(1)
    
    click.echo(result.model_dump_json(indent=2))


@main.command("version")
def version():
    """Show version info"""
    click.echo("agent-causal-decision-tool v0.1.0")


def _print_ab_text(result):
    """Print A/B test in human-readable format"""
    rec = result.recommendation
    stats = result.statistics
    traffic = result.traffic_stats
    
    click.echo("=" * 50)
    click.echo("A/B TEST RESULTS")
    click.echo("=" * 50)
    click.echo(f"Decision: {rec.decision.upper()} ({rec.confidence} confidence)")
    click.echo(f"Summary: {rec.summary}")
    click.echo()
    click.echo("Traffic:")
    click.echo(f"  Control:  {traffic.control_size:,}")
    click.echo(f"  Variant:  {traffic.variant_size:,}")
    click.echo(f"  Total:    {traffic.total_size:,}")
    click.echo()
    click.echo("Statistics:")
    click.echo(f"  Control rate:  {stats['control_rate']:.4f}")
    click.echo(f"  Variant rate:  {stats['variant_rate']:.4f}")
    click.echo(f"  Relative lift: {stats['relative_lift_pct']:.2f}%")
    click.echo(f"  P-value:       {stats['p_value']:.6f}")
    click.echo(f"  95% CI:        [{stats['confidence_interval_95'][0]:.4f}, {stats['confidence_interval_95'][1]:.4f}]")
    
    if result.warnings:
        click.echo()
        click.echo("Warnings:")
        for w in result.warnings:
            click.echo(f"  [{w.severity.upper()}] {w.code}: {w.message}")
    
    click.echo()
    click.echo("Next steps:")
    for step in result.next_steps:
        click.echo(f"  -> {step}")


def _print_did_text(result):
    """Print DiD in human-readable format"""
    rec = result.recommendation
    stats = result.statistics
    
    click.echo("=" * 50)
    click.echo("DIFFERENCE-IN-DIFFERENCES RESULTS")
    click.echo("=" * 50)
    click.echo(f"Decision: {rec.decision.upper()} ({rec.confidence} confidence)")
    click.echo(f"Summary: {rec.summary}")
    click.echo()
    click.echo("DiD Estimate:")
    click.echo(f"  Absolute:  {stats['did_estimate']:.4f}")
    click.echo(f"  Relative:  {stats['relative_did_pct']:.2f}%")
    click.echo()
    click.echo("Changes:")
    click.echo(f"  Control group:    {stats['control_change']:.4f}")
    click.echo(f"  Treatment group:  {stats['treatment_change']:.4f}")
    
    if result.warnings:
        click.echo()
        click.echo("Warnings:")
        for w in result.warnings:
            click.echo(f"  [{w.severity.upper()}] {w.code}: {w.message}")
    
    click.echo()
    click.echo("Assumptions:")
    for a in result.assumptions:
        click.echo(f"  - {a}")


if __name__ == "__main__":
    main()