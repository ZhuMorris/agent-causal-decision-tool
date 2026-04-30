"""CLI for Agent Causal Decision Tool"""

import click
import json
import sys
from pathlib import Path

from ab_test import calculate_ab
from did import calculate_did
from planning import calculate_plan
from audit import format_audit_text
import store


@click.group()
@click.version_option(version="0.2.0")
def main():
    """Agent Causal Decision Tool - causal decision and audit for AI agents"""
    pass


@main.command("ab")
@click.option("--control", required=True, help="Control group: conversions/total (e.g., 100/5000)")
@click.option("--variant", required=True, help="Variant group: conversions/total (e.g., 120/5000)")
@click.option("--name", default="variant_1", help="Variant name")
@click.option("--format", "output_format", type=click.Choice(["json", "text"]), default="json")
@click.option("--save", "auto_save", is_flag=True, help="Save result to experiment history")
def ab_test(control, variant, name, output_format, auto_save):
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
    result_json = result.model_dump_json(indent=2)
    
    if auto_save:
        row_id = store.save_experiment(result_json, "ab_test", json.dumps(input_data))
        click.echo(f"[Saved to history as experiment #{row_id}]", err=True)
    
    if output_format == "json":
        click.echo(result_json)
    else:
        _print_ab_text(result)


@main.command("did")
@click.option("--pre-control", required=True, type=float, help="Control group metric before treatment")
@click.option("--post-control", required=True, type=float, help="Control group metric after treatment")
@click.option("--pre-treated", required=True, type=float, help="Treated group metric before treatment")
@click.option("--post-treated", required=True, type=float, help="Treated group metric after treatment")
@click.option("--format", "output_format", type=click.Choice(["json", "text"]), default="json")
@click.option("--save", "auto_save", is_flag=True, help="Save result to experiment history")
def did_analysis(pre_control, post_control, pre_treated, post_treated, output_format, auto_save):
    """Run Difference-in-Differences analysis"""
    input_data = {
        "pre_control": pre_control,
        "post_control": post_control,
        "pre_treated": pre_treated,
        "post_treated": post_treated
    }
    
    result = calculate_did(input_data)
    result_json = result.model_dump_json(indent=2)
    
    if auto_save:
        row_id = store.save_experiment(result_json, "did", json.dumps(input_data))
        click.echo(f"[Saved to history as experiment #{row_id}]", err=True)
    
    if output_format == "json":
        click.echo(result_json)
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
@click.option("--save", "auto_save", is_flag=True, help="Save result to experiment history")
def plan(baseline, mde_pct, daily_traffic, confidence, power, allocation, allocation_ratio, output_format, auto_save):
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
    result_json = result.model_dump_json(indent=2)
    
    if auto_save:
        row_id = store.save_experiment(result_json, "planning", json.dumps(input_data))
        click.echo(f"[Saved to history as experiment #{row_id}]", err=True)
    
    if output_format == "json":
        click.echo(result_json)
    else:
        _print_plan_text(result)


@main.command("save")
@click.argument("result_file", type=click.Path(exists=True))
@click.option("--name", default=None, help="Optional experiment name for labeling")
@click.option("--mode", default=None, help="Override mode (auto-detected from JSON if omitted)")
def save_experiment(result_file, name, mode):
    """Save a prior experiment result JSON to the persistent history"""
    with open(result_file, "r") as f:
        data = json.load(f)
    
    detected_mode = mode or data.get("mode", "unknown")
    inputs_json = json.dumps(data.get("inputs", {}))
    if name:
        data["inputs"]["experiment_name"] = name
    
    row_id = store.save_experiment(json.dumps(data), detected_mode, inputs_json)
    click.echo(f"Saved as experiment #{row_id}")


@main.command("history")
@click.option("--mode", default=None, type=click.Choice(["ab_test", "did", "planning"]), help="Filter by experiment mode")
@click.option("--limit", default=20, type=int, help="Number of results to show (default: 20)")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def history(mode, limit, output_format):
    """List past experiments from history"""
    experiments = store.list_experiments(mode=mode, limit=limit)
    
    if not experiments:
        click.echo("No experiments in history.")
        return
    
    if output_format == "json":
        # Return lightweight records (not full raw JSON blobs)
        lightweight = []
        for e in experiments:
            lightweight.append({
                "id": e["id"],
                "mode": e["mode"],
                "decision": e["decision"],
                "confidence": e["confidence"],
                "summary": e["summary"],
                "primary_lift": e["primary_lift"],
                "p_value": e["p_value"],
                "created_at": e["created_at"],
                "experiment_name": e["experiment_name"]
            })
        click.echo(json.dumps(lightweight, indent=2))
    else:
        click.echo(f"{'ID':<5} {'Date':<10} {'Mode':<10} {'Decision':<12} {'Lift':<8} {'P-value':<8} {'Summary'}")
        click.echo("-" * 90)
        for e in experiments:
            lift_str = f"{e['primary_lift']:.2f}" if e['primary_lift'] is not None else "-"
            p_str = f"{e['p_value']:.4f}" if e['p_value'] is not None else "-"
            date = e['created_at'][:10]
            mode_str = e['mode'][:10]
            decision_str = e['decision'][:12]
            name_str = e['experiment_name'] or ""
            summary = e['summary'][:40] if e['summary'] else ""
            click.echo(f"{e['id']:<5} {date:<10} {mode_str:<10} {decision_str:<12} {lift_str:<8} {p_str:<8} {summary} {name_str}")


@main.command("compare")
@click.argument("experiment_ids", nargs=-1, type=int, required=True)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def compare(experiment_ids, output_format):
    """Compare multiple experiments by their IDs. Usage: compare 1 3 5"""
    ids = list(experiment_ids)
    comparison = store.compare_experiments(ids)
    
    if "error" in comparison:
        click.echo(f"Error: {comparison['error']}", err=True)
        sys.exit(1)
    
    if output_format == "json":
        click.echo(json.dumps(comparison, indent=2))
    else:
        _print_compare_text(comparison)


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
    click.echo("agent-causal-decision-tool v0.2.0")


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


def _print_compare_text(comparison):
    """Print experiment comparison in human-readable format"""
    click.echo("=" * 50)
    click.echo("EXPERIMENT COMPARISON")
    click.echo("=" * 50)
    click.echo(f"Experiments compared: {comparison['count']}")
    click.echo()
    
    click.echo("Summary by decision:")
    for decision, exps in comparison['by_decision'].items():
        click.echo(f"  {decision.upper()}: {len(exps)} experiment(s)")
    click.echo()
    
    click.echo("Summary by mode:")
    for mode, ids in comparison['by_mode'].items():
        click.echo(f"  {mode}: {len(ids)} experiment(s)")
    click.echo()
    
    if comparison.get('lift_summary'):
        ls = comparison['lift_summary']
        click.echo(f"Lift summary: max={ls['max']:.2f}%, min={ls['min']:.2f}%, avg={ls['avg']:.2f}% ({ls['count']} experiments)")
        click.echo()
    
    click.echo("Individual experiments:")
    click.echo(f"  {'ID':<5} {'Mode':<10} {'Decision':<12} {'Lift':<8} {'P-value':<8} {'Created'}")
    click.echo("  " + "-" * 55)
    for exp in comparison['experiments']:
        lift_str = f"{exp['primary_lift']:.2f}" if exp['primary_lift'] is not None else "-"
        p_str = f"{exp['p_value']:.4f}" if exp['p_value'] is not None else "-"
        date = exp['created_at'][:10]
        click.echo(f"  {exp['id']:<5} {exp['mode']:<10} {exp['decision']:<12} {lift_str:<8} {p_str:<8} {date}")
    
    attention = comparison.get("attention", {})
    if attention.get("suggestion"):
        click.echo()
        click.echo(f"Attention needed: {attention['suggestion']}")


if __name__ == "__main__":
    main()