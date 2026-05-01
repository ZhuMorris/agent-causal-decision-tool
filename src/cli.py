"""CLI for Agent Causal Decision Tool"""

import click
import json
import sys
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError

from ab_test import calculate_ab
from did import calculate_did
from planning import calculate_plan
from bayes import calculate_bayes_ab
from audit import format_audit_text, check_experiment_maturity
from cohort import cohort_breakdown
import store


def _get_version():
    try:
        return version("agent_causal_decision_tool")
    except PackageNotFoundError:
        return "unknown"

_VERSION = _get_version()

@click.group()
@click.version_option(version=_VERSION)
def main():
    """"Agent Causal Decision Tool - causal decision and audit for AI agents"""
    pass


@main.command("bayes")
@click.option("--control", required=True, help="Control group: conversions/total (e.g., 100/5000)")
@click.option("--variant", required=True, help="Variant group: conversions/total (e.g., 120/5000)")
@click.option("--name", default="variant_1", help="Variant name")
@click.option("--format", "output_format", type=click.Choice(["json", "text"]), default="json")
@click.option("--save", "auto_save", is_flag=True, help="Save result to experiment history")
@click.option("--samples", default=20000, type=int, help="Monte Carlo samples (default: 20000)")
def bayes_ab(control, variant, name, output_format, auto_save, samples):
    """Run Bayesian A/B test using Beta-Binomial conjugate model"""
    if samples < 1:
        raise click.BadParameter("n_samples must be >= 1")
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
    
    result = calculate_bayes_ab(input_data, n_samples=samples)
    result_json = json.dumps(result, indent=2)
    
    if auto_save:
        row_id = store.save_experiment(result_json, "bayesian_ab", json.dumps(input_data))
        click.echo(f"[Saved to history as experiment #{row_id}]", err=True)
    
    if output_format == "json":
        click.echo(result_json)
    else:
        _print_bayes_text(result)


@main.command("ab")
@click.option("--control", required=True, help="Control group: conversions/total (e.g., 100/5000)")
@click.option("--variant", required=True, help="Variant group: conversions/total (e.g., 120/5000)")
@click.option("--name", default="variant_1", help="Variant name")
@click.option("--format", "output_format", type=click.Choice(["json", "text"]), default="json")
@click.option("--save", "auto_save", is_flag=True, help="Save result to experiment history")
# Sequential early stopping options
@click.option("--sequential/--no-sequential", "sequential_enabled", default=False, help="Enable sequential early stopping")
@click.option("--experiment-start", "experiment_start_time", default=None, help="Experiment start ISO 8601 timestamp")
@click.option("--experiment-end", "experiment_end_time", default=None, help="Experiment end ISO 8601 timestamp")
@click.option("--min-runtime-days", "min_runtime_days", default=7, type=int, help="Minimum days before early stop (default: 7)")
@click.option("--min-sample-per-arm", "min_sample_per_arm", default=2000, type=int, help="Minimum sample per arm before early stop (default: 2000)")
@click.option("--early-stop-p", "early_stop_p_threshold", default=0.01, type=float, help="p-value threshold for early stop (default: 0.01)")
@click.option("--max-runtime-days", "max_runtime_days", default=None, type=int, help="Hard cap on runtime in days; escalate if exceeded")
def ab_test(control, variant, name, output_format, auto_save, sequential_enabled, experiment_start_time, experiment_end_time, min_runtime_days, min_sample_per_arm, early_stop_p_threshold, max_runtime_days):
    """Run A/B test analysis with optional sequential early stopping"""
    try:
        c_parts = control.split("/")
        v_parts = variant.split("/")

        
        input_data = {
            "control_conversions": int(c_parts[0]),
            "control_total": int(c_parts[1]),
            "variant_conversions": int(v_parts[0]),
            "variant_total": int(v_parts[1]),
            "variant_name": name,
            "sequential_enabled": sequential_enabled,
            "experiment_start_time": experiment_start_time,
            "experiment_end_time": experiment_end_time,
            "min_runtime_days": min_runtime_days,
            "min_sample_per_arm": min_sample_per_arm,
            "early_stop_p_threshold": early_stop_p_threshold,
            "max_runtime_days": max_runtime_days,
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


@main.command("cohort-breakdown")
@click.option("--file", "input_file", type=click.Path(exists=True), help="Path to segment JSON or CSV file")
@click.option("--json", "json_input", help="JSON input string (alternative to --file)")
@click.option("--format", "output_format", type=click.Choice(["json", "text"]), default="json")
@click.option("--save", "auto_save", is_flag=True, help="Save result to experiment history")
def cohort_breakdown_cmd(input_file, json_input, output_format, auto_save):
    """Run segment-level experiment analysis.

    Accepts pre-computed segment data with conversion counts per arm.
    Use --file for JSON or CSV input. Use --json to pass JSON directly.

    Example JSON input:
    {
      "experiment_id": "checkout-v3",
      "metric": "conversion_rate",
      "prior_result_id": "dec_20260501_001",
      "prior_decision": "wait",
      "segments": [
        {"segment_name": "new_users", "segment_definition_note": "...",
         "control_conversions": 21, "control_total": 1000,
         "variant_conversions": 67, "variant_total": 1000}
      ]
    }
    """
    try:
        if input_file:
            suffix = Path(input_file).suffix.lower()
            if suffix == ".csv":
                data = _parse_cohort_csv(input_file)
            else:
                with open(input_file) as f:
                    data = json.load(f)
        elif json_input:
            data = json.loads(json_input)
        else:
            data = json.load(sys.stdin)

        result = cohort_breakdown(data)
        result_json = json.dumps(result, indent=2)

        if auto_save:
            row_id = store.save_experiment(result_json, "cohort_breakdown", json.dumps(data))
            click.echo(f"[Saved to history as experiment #{row_id}]", err=True)

        if output_format == "json":
            click.echo(result_json)
        else:
            _print_cohort_text(result)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _parse_cohort_csv(path):
    """Parse CSV segment data into cohort_breakdown input format."""
    import csv
    segments = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["segment_name"]
            if name not in segments:
                segments[name] = {
                    "segment_name": name,
                    "segment_definition_note": row.get("segment_definition_note", ""),
                    "control_conversions": 0,
                    "control_total": 0,
                    "variant_conversions": 0,
                    "variant_total": 0,
                }
            arm = row["arm"].lower()
            conv = int(row["conversions"])
            total = int(row["total"])
            if arm == "control":
                segments[name]["control_conversions"] += conv
                segments[name]["control_total"] += total
            elif arm == "variant":
                segments[name]["variant_conversions"] += conv
                segments[name]["variant_total"] += total

    return {"segments": list(segments.values())}


def _print_cohort_text(result):
    """Print cohort breakdown in human-readable format."""
    click.echo("=" * 50)
    click.echo("COHORT BREAKDOWN RESULTS")
    click.echo("=" * 50)
    click.echo(f"Method: {result['method']}")
    click.echo(f"Experiment: {result.get('experiment_id', 'unknown')}")
    click.echo(f"Metric: {result.get('metric', 'unknown')}")
    if result.get('prior_result_id'):
        click.echo(f"Prior result: {result['prior_result_id']} ({result.get('prior_decision', 'unknown')})")
    click.echo()
    click.echo(f"Override: {result.get('cohort_decision_override')}")
    if result.get('cohort_override_reason'):
        click.echo(f"  {result['cohort_override_reason']}")
    click.echo(f"Interaction flag: {result.get('interaction_flag', False)}")
    click.echo()
    click.echo("Segments:")
    click.echo(f"  {'Segment':<20} {'Ctrl Rate':>10} {'Var Rate':>10} {'Lift':>8} {'Raw-p':>8} {'Adj-p':>8} {'Decision':<18}")
    click.echo("  " + "-" * 90)
    for seg in result.get('segments', []):
        click.echo(
            f"  {seg['segment_name']:<20} "
            f"{seg['control_rate']:>10.4f} {seg['variant_rate']:>10.4f} "
            f"{seg['relative_lift_pct']:>7.1f}% {seg['p_value_raw']:>8.4f} "
            f"{seg['p_value_adjusted']:>8.4f} {seg['decision']:<18}"
        )
    click.echo()
    click.echo("Priority Ranking:")
    for r in result.get('priority_ranking', []):
        click.echo(f"  {r['rank']}. {r['segment']}: {r['rationale']}")
    click.echo()
    click.echo(f"Summary: {result.get('summary', '')}")
    click.echo(f"Recommended action: {result.get('recommended_next_action', 'unknown')}")
    if result.get('warnings'):
        click.echo()
        click.echo("Warnings:")
        for w in result['warnings']:
            click.echo(f"  [{w.split(':')[0]}] {w}")


@main.command("validate-input")
@click.option("--file", "input_file", type=click.Path(exists=True), help="Path to input file")
@click.option("--json", "json_input", help="JSON input string")
def validate_input_cmd(input_file, json_input):
    """Validate input data schema and quality before running analysis.

    Supports: ab_test, did, cohort_breakdown, planning.
    Pass --file or --json with a 'mode' field to specify validation mode.
    """
    try:
        if input_file:
            with open(input_file) as f:
                data = json.load(f)
        elif json_input:
            data = json.loads(json_input)
        else:
            data = json.load(sys.stdin)

        mode = data.pop("mode", "ab_test") if isinstance(data, dict) else "ab_test"
        result = _validate_input(data, mode)
        click.echo(json.dumps(result, indent=2))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _validate_input(data: dict, mode: str) -> dict:
    """Validate input for given mode."""
    errors = []
    warnings = []

    if mode == "cohort_breakdown":
        segments = data.get("segments", [])
        if not segments:
            errors.append("No segments provided")
        for seg in segments:
            for f in ["segment_name", "control_conversions", "control_total",
                      "variant_conversions", "variant_total"]:
                if f not in seg:
                    errors.append(f"Missing '{f}' in segment '{seg.get('segment_name', '?')}'")
            if seg.get("control_total", 0) <= 0 or seg.get("variant_total", 0) <= 0:
                errors.append(f"Invalid totals in segment '{seg.get('segment_name', '?')}'")
        return {
            "valid": len(errors) == 0,
            "mode": mode,
            "errors": errors,
            "warnings": warnings,
            "segment_count": len(segments),
        }
    else:
        return {"valid": True, "mode": mode, "errors": [], "warnings": [], "note": "Basic validation passed"}


@main.command("did")
@click.option("--pre-control", required=True, type=float, help="Control group metric before treatment")
@click.option("--post-control", required=True, type=float, help="Control group metric after treatment")
@click.option("--pre-treated", required=True, type=float, help="Treated group metric before treatment")
@click.option("--post-treated", required=True, type=float, help="Treated group metric after treatment")
@click.option("--format", "output_format", type=click.Choice(["json", "text"]), default="json")
@click.option("--save", "auto_save", is_flag=True, help="Save result to experiment history")
@click.option("--pre-periods", "pre_periods", default=None, type=int, help="Number of pre-period observations (e.g. days/weeks)")
@click.option("--post-periods", "post_periods", default=None, type=int, help="Number of post-period observations")
@click.option("--treatment-obs", "treatment_observation_count", default=None, type=int, help="Total underlying observations for treatment group")
@click.option("--control-obs", "control_observation_count", default=None, type=int, help="Total underlying observations for control group")
def did_analysis(pre_control, post_control, pre_treated, post_treated, output_format, auto_save, pre_periods, post_periods, treatment_observation_count, control_observation_count):
    """Run Difference-in-Differences analysis with robustness diagnostics"""
    input_data = {
        "pre_control": pre_control,
        "post_control": post_control,
        "pre_treated": pre_treated,
        "post_treated": post_treated,
        "pre_periods": pre_periods,
        "post_periods": post_periods,
        "treatment_observation_count": treatment_observation_count,
        "control_observation_count": control_observation_count,
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
    inputs_dict = data.get("inputs", {})
    if name:
        inputs_dict["experiment_name"] = name
    inputs_json = json.dumps(inputs_dict)
    
    row_id = store.save_experiment(json.dumps(data), detected_mode, inputs_json)
    click.echo(f"Saved as experiment #{row_id}")


@main.command("history")
@click.option("--mode", default=None, type=click.Choice(["ab_test", "did", "planning", "bayesian_ab"]), help="Filter by experiment mode")
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
@click.option("--maturity", is_flag=True, help="Include experiment maturity assessment")
def audit(input_file, output_format, maturity):
    """Reconstruct and audit a previous decision with detailed decision path"""
    with open(input_file, "r") as f:
        data = json.load(f)
    
    mode = data.get("mode", "ab_test")
    
    if output_format == "json":
        # Show full audit object with decision path
        audit_obj = data.get("audit", {})
        audit_obj["mode"] = mode
        audit_obj["inputs"] = data.get("inputs", {})
        
        if maturity:
            maturity_result = check_experiment_maturity(audit_obj, data)
            audit_obj["maturity_assessment"] = maturity_result
        
        click.echo(json.dumps(audit_obj, indent=2))
    else:
        # Show human-readable decision path
        audit_obj = data.get("audit", {})
        audit_obj["mode"] = mode
        audit_obj["inputs"] = data.get("inputs", {})
        
        text = format_audit_text({
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
        })
        
        if maturity:
            maturity_result = check_experiment_maturity(audit_obj, data)
            text += "\n\n" + _format_maturity_text(maturity_result)
        
        click.echo(text)


def _format_maturity_text(maturity: dict) -> str:
    """Format maturity assessment as human-readable text."""
    label = maturity["maturity_label"].upper()
    score = maturity["maturity_score"]
    desc = maturity["description"]
    
    lines = [
        "=" * 50,
        "EXPERIMENT MATURITY ASSESSMENT",
        "=" * 50,
        f"Score: {score}/100  [{label}]",
        f"{desc}",
        ""
    ]
    
    if maturity.get("issues"):
        lines.append("ISSUES:")
        for issue in maturity["issues"]:
            lines.append(f"  ✗ {issue}")
        lines.append("")
    
    if maturity.get("warnings"):
        lines.append("WARNINGS:")
        for w in maturity["warnings"]:
            lines.append(f"  ⚠ {w}")
        lines.append("")
    
    lines.append("CHECKS:")
    checks = maturity.get("checks", {})
    for check, passed in checks.items():
        status = "✓" if passed else "✗"
        lines.append(f"  [{status}] {check}")
    
    return "\n".join(lines)


@main.command("version")
def version():
    """"Show version info"""
    click.echo(f"agent-causal-decision-tool {_VERSION}")


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
    
    if result.sequential_reviewed and result.sequential_summary:
        click.echo()
        click.echo("Sequential Early Stopping:")
        ss = result.sequential_summary
        click.echo(f"  Reviewed:            {result.sequential_reviewed}")
        click.echo(f"  Early stop applied:  {result.early_stop_applied}")
        click.echo(f"  Reason:             {ss.reason}")
        if ss.observed_runtime_days is not None:
            click.echo(f"  Runtime:             {ss.observed_runtime_days:.1f}d / {ss.min_runtime_days}d min")
        click.echo(f"  Sample per arm:      {ss.observed_sample_per_arm} / {ss.min_sample_per_arm} min")
        click.echo(f"  p threshold:         {ss.early_stop_p_threshold}")
    
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
    
    if result.did_diagnostics:
        click.echo()
        click.echo("DiD Diagnostics:")
        diag = result.did_diagnostics
        click.echo(f"  Pre periods:              {diag.pre_periods}")
        click.echo(f"  Post periods:            {diag.post_periods}")
        click.echo(f"  Treatment obs count:     {diag.treatment_observation_count}")
        click.echo(f"  Control obs count:       {diag.control_observation_count}")
        click.echo(f"  Parallel trends evidence: {diag.parallel_trends_evidence}")
        click.echo(f"  Caution level:            {diag.recommended_caution_level}")
        if diag.fragility_flags:
            click.echo(f"  Fragility flags:          {', '.join(diag.fragility_flags)}")
    
    if result.explanation:
        click.echo()
        click.echo(f"Explanation: {result.explanation}")
    
    click.echo()
    click.echo("Assumptions:")
    for a in result.assumptions:
        click.echo(f"  - {a}")


def _print_bayes_text(result):
    """Print Bayesian A/B test in human-readable format"""
    rec = result["recommendation"]
    stats = result["statistics"]
    traffic = result["traffic_stats"]
    
    click.echo("=" * 50)
    click.echo("BAYESIAN A/B TEST RESULTS")
    click.echo("=" * 50)
    click.echo(f"Decision: {rec['decision'].upper()} ({rec['confidence']} confidence)")
    click.echo(f"Summary: {rec['summary']}")
    click.echo()
    click.echo("Traffic:")
    click.echo(f"  Control:  {traffic['control_size']:,}")
    click.echo(f"  Variant:  {traffic['variant_size']:,}")
    click.echo(f"  Total:    {traffic['total_size']:,}")
    click.echo()
    click.echo("Posterior (after data):")
    pc = stats["posterior_control"]
    pv = stats["posterior_variant"]
    click.echo(f"  Control:  Beta(α={pc['alpha']}, β={pc['beta']}) mean={pc['mean']:.4f}")
    click.echo(f"  Variant:  Beta(α={pv['alpha']}, β={pv['beta']}) mean={pv['mean']:.4f}")
    click.echo()
    n_samples = stats["monte_carlo_samples"]
    click.echo(f"Monte Carlo Results ({n_samples:,} samples):")
    click.echo(f"  P(Variant wins):  {stats['p_variant_wins']:.4f}")
    click.echo(f"  P(Control wins):  {stats['p_control_wins']:.4f}")
    click.echo(f"  P(Tie):           {stats['p_tie']:.4f}")
    click.echo()
    click.echo("Lift Distribution:")
    click.echo(f"  Median lift:  {stats['lift_median_pct']:.2f}%")
    click.echo(f"  95% CI:       [{stats['lift_95ci_pct'][0]:.2f}%, {stats['lift_95ci_pct'][1]:.2f}%]")
    click.echo()
    click.echo("Observed Rates:")
    click.echo(f"  Control rate:  {stats['control_rate_observed']:.4f}")
    click.echo(f"  Variant rate:  {stats['variant_rate_observed']:.4f}")
    click.echo(f"  Relative lift: {stats['relative_lift_pct']:.2f}%")
    
    warnings = result.get("warnings", [])
    if warnings:
        click.echo()
        click.echo("Warnings:")
        for w in warnings:
            click.echo(f"  [{w['severity'].upper()}] {w['code']}: {w['message']}")
    
    click.echo()
    click.echo("Next steps:")
    for step in result.get("next_steps", []):
        click.echo(f"  -> {step}")


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