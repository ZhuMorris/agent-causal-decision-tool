"""CLI for Agent Causal Decision Tool"""

import click
import json
import sys
from pathlib import Path

from ab_test import calculate_ab
from did import calculate_did
from planning import calculate_plan
from audit import format_audit_text


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


@main.command("plan")
@click.option("--baseline", required=True, type=float, help="Baseline conversion rate (e.g., 0.02 for 2%)")
@click.option("--mde", "mde_pct", required=True, type=float, help="Minimum detectable effect as relative %% lift (e.g., 5 for 5% lift)")
@click.option("--traffic", "daily_traffic", required=True, type=int, help="Daily traffic per arm")
@click.option("--confidence", default=0.95, type=float, help="Confidence level (default: 0.95)")
@click.option("--power", default=0.8, type=float, help="Statistical power (default: 0.8)")
@click.option("--allocation", default="equal", type=click.Choice(["equal", "custom"]), help="Traffic allocation")
@click.option("--allocation-ratio", default=None, help="Custom allocation ratio (e.g., 0.3/0.7)")
@click.option("--format", "output_format", type=click.Choice(["json", "text"]), default="json")
def plan(baseline, mde_pct, daily_traffic, confidence, power, allocation, allocation_ratio, output_format):
    """Plan an A/B test: compute sample size, duration, and feasibility"""
    try:
        input_data = {
            "baseline_conversion_rate": baseline,
            "mde_pct": mde_pct,
            "daily_traffic": daily_traffic,
            "confidence_level": confidence,
            "power": power,
            "allocation": allocation,
            "allocation_ratio": allocation_ratio
        }
    except Exception as e:
        click.echo(f"Error parsing input: {e}", err=True)
        sys.exit(1)
    
    result = calculate_plan(input_data)
    
    if output_format == "json":
        click.echo(result.model_dump_json(indent=2))
    else:
        _print_plan_text(result)


@main.command("audit")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def audit(input_file, output_format):
    """Reconstruct and audit a previous decision with detailed decision path"""
    with open(input_file, "r") as f:
        data = json.load(f)
    
    mode = data.get("mode", "ab_test")
    
    if output_format == "json":
        # Show full audit object with decision path
        audit_obj = data.get("audit", {})
        audit_obj["mode"] = mode
        audit_obj["inputs"] = data.get("inputs", {})
        click.echo(json.dumps(audit_obj, indent=2))
    else:
        # Show human-readable decision path
        click.echo(format_audit_text({
            "mode": mode,
            "generated_at": data.get("timestamp", "unknown"),
            "inputs": data.get("inputs", {}),
            "decision_path": data.get("audit", {}).get("decision_path", []),
            "warnings_triggered": data.get("warnings", []),
            "limitations": data.get("audit", {}).get("limitations", []),
            "final_decision": {
                "decision": data.get("recommendation", {}).get("decision", "unknown"),
                "confidence": data.get("recommendation", {}).get("confidence", "unknown"),
                "summary": data.get("recommendation", {}).get("summary", "")
            }
        }))


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


def _print_plan_text(result):
    """Print planning output in human-readable format"""
    rec = result.recommendation
    plan = result.planning
    
    click.echo("=" * 50)
    click.echo("EXPERIMENT PLANNING RESULTS")
    click.echo("=" * 50)
    click.echo(f"Feasibility: {plan['feasibility'].upper()}")
    click.echo(f"Decision: {rec.decision.upper()} ({rec.confidence} confidence)")
    click.echo(f"Summary: {rec.summary}")
    click.echo()
    click.echo("Planning:")
    click.echo(f"  Required per arm:  {plan['required_sample_per_arm']:,}")
    click.echo(f"  Total required:     {plan['total_required']:,}")
    click.echo(f"  Daily per arm:      {plan['daily_per_arm']:,}")
    click.echo(f"  Estimated days:     {plan['estimated_days']:.1f}")
    click.echo(f"  MDE (absolute):     {plan['mde_absolute']:.4f}")
    alloc = plan['allocation_used']
    click.echo(f"  Allocation:          control={alloc['control']}, variant={alloc['variant']}")
    
    if result.warnings:
        click.echo()
        click.echo("Warnings:")
        for w in result.warnings:
            click.echo(f"  [{w.severity.upper()}] {w.code}: {w.message}")


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