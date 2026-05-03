"""Experiment planning module for Agent Causal Decision Tool"""

import json
from math import ceil
from typing import Optional
from schema import PlanningInput, PlanningOutput, Recommendation, WarningDetail, WarningCode


def calculate_plan(input_data: dict) -> PlanningOutput:
    """
    Run experiment planning and return structured output.
    
    Computes required sample size, duration estimate, and feasibility
    for an A/B test given baseline conversion, MDE, and daily traffic.
    """
    planning_input = PlanningInput(**input_data)
    
    # Extract parameters
    p = planning_input.baseline_conversion_rate  # baseline rate
    mde_pct = planning_input.mde_pct              # MDE in percent (e.g., 5 for 5% lift)
    daily_traffic = planning_input.daily_traffic
    confidence = planning_input.confidence_level
    power = planning_input.power
    allocation = planning_input.allocation
    allocation_ratio = planning_input.allocation_ratio
    
    # Convert percentages to fractions
    mde_fraction = mde_pct / 100.0  # e.g., 5 -> 0.05
    
    # Z-scores
    alpha = 1 - confidence
    z_alpha = 1.96 if confidence == 0.95 else _z_from_alpha(alpha)
    z_beta = 0.84 if power == 0.8 else _z_from_power(power)
    
    # Effective MDE in absolute terms
    absolute_mde = p * mde_fraction  # e.g., 0.02 * 0.05 = 0.001 (0.1%)
    
    # Parse allocation
    if allocation == "custom":
        if not allocation_ratio:
            raise ValueError("allocation_ratio required when allocation=custom")
        parts = allocation_ratio.split("/")
        r_control = float(parts[0])
        r_variant = float(parts[1])
        if abs(r_control + r_variant - 1.0) > 0.001:
            raise ValueError("allocation_ratio must sum to 1 (e.g., 0.3/0.7)")
    else:
        r_control = 0.5
        r_variant = 0.5
    
    # Sample size formula
    # Base formula for equal allocation: n = 2 * (Z_a + Z_b)^2 * p * (1-p) / (mde * p)^2
    # Adjusted for custom allocation: multiply by (1/r + 1/(1-r))
    if absolute_mde <= 0:
        raise ValueError("MDE results in zero effect. Increase MDE or baseline.")
    
    ratio_factor = (1.0 / r_control) + (1.0 / r_variant)  # = 4 for equal, different for custom
    
    n = ratio_factor * (z_alpha + z_beta) ** 2 * p * (1 - p) / (absolute_mde ** 2)
    required_per_arm = ceil(n)
    # total_required: sum of per-arm requirements across all arms
    # = required_per_arm/r_control + required_per_arm/r_variant (weighted sum)
    total_required = ceil(required_per_arm / r_control + required_per_arm / r_variant)
    
    # Duration
    daily_per_arm = daily_traffic
    estimated_days = required_per_arm / daily_per_arm if daily_per_arm > 0 else float('inf')
    
    # Feasibility
    if estimated_days <= 14:
        feasibility = "feasible"
        confidence_level = "high"
        summary = f"Experiment is feasible. Need {required_per_arm:,} users per arm, ~{estimated_days:.1f} days."
    elif estimated_days <= 60:
        feasibility = "slow"
        confidence_level = "medium"
        summary = f"Experiment will take ~{estimated_days:.1f} days. Consider if timeline is acceptable."
    else:
        feasibility = "not_recommended"
        confidence_level = "low"
        summary = f"Experiment requires ~{estimated_days:.0f} days. Not recommended at current traffic."
    
    # Warnings
    warnings = []

    # BASELINE_VERY_LOW: baseline rate < 0.005 → warning
    if p < 0.005:
        warnings.append(WarningDetail(
            code=WarningCode.BASELINE_VERY_LOW,
            message=f"Baseline rate {p:.4f} is very low (<0.005). Estimations may be unreliable.",
            severity="warning"
        ))

    # BASELINE_NEAR_ZERO: baseline rate < 0.001 → critical
    if p < 0.001:
        warnings.append(WarningDetail(
            code=WarningCode.BASELINE_NEAR_ZERO,
            message=f"Baseline rate {p:.6f} is near zero (<0.001). Do not run experiment without careful review.",
            severity="critical"
        ))

    if daily_traffic < 100:
        warnings.append(WarningDetail(
            code=WarningCode.LOW_TRAFFIC,
            message=f"Daily traffic per arm ({daily_traffic}) is below recommended minimum of 100. Results may be unreliable.",
            severity="warning"
        ))

    if estimated_days > 30:
        warnings.append(WarningDetail(
            code=WarningCode.SLOW_EXPERIMENT,
            message=f"Estimated duration ({estimated_days:.1f} days) exceeds 30 days. Season effects may confound results.",
            severity="warning"
        ))

    if feasibility == "not_recommended":
        warnings.append(WarningDetail(
            code=WarningCode.INFEASIBLE_EXPERIMENT,
            message="Consider using DiD (Difference-in-Differences) if you cannot wait for enough traffic.",
            severity="warning"
        ))

    if mde_fraction < 0.01:
        warnings.append(WarningDetail(
            code=WarningCode.SMALL_MDE,
            message=f"MDE of {mde_pct}% is very small. May require impossibly large sample. Check feasibility.",
            severity="info"
        ))
    
    # Recommendation
    if feasibility == "feasible":
        decision = "ship"  # ready to run
    elif feasibility == "slow":
        decision = "keep_running"  # can proceed with caution
    else:
        decision = "escalate"  # needs review
    
    recommendation = Recommendation(
        decision=decision,
        confidence=confidence_level,
        summary=summary,
        primary_metricLift=round(mde_pct, 4),
        p_value=None,
        warning=warnings[0].message if warnings else None
    )
    
    # Planning output dict
    planning_dict = {
        "required_sample_per_arm": required_per_arm,
        "total_required": total_required,
        "daily_per_arm": daily_per_arm,
        "estimated_days": round(estimated_days, 2),
        "feasibility": feasibility,
        "mde_absolute": round(absolute_mde, 6),
        "mde_ci_95": _compute_mde_ci(p, daily_traffic, mde_fraction, confidence),
        "allocation_used": {"control": r_control, "variant": r_variant},
        "z_alpha": round(z_alpha, 4),
        "z_beta": round(z_beta, 4),
        "formula_params": {
            "baseline_rate": p,
            "mde_pct": mde_pct,
            "mde_fraction": mde_fraction,
            "confidence": confidence,
            "power": power
        }
    }
    
    return PlanningOutput(
        recommendation=recommendation,
        planning=planning_dict,
        warnings=warnings,
        inputs=input_data
    )


def _z_from_alpha(alpha: float) -> float:
    """Get z-score from alpha (two-tailed)."""
    from scipy import stats
    return stats.norm.ppf(1 - alpha / 2)


def _z_from_power(power: float) -> float:
    """Get z-score from power."""
    from scipy import stats
    return stats.norm.ppf(power)


def _compute_mde_ci(p: float, n_traffic: int, mde_fraction: float, confidence: float = 0.95) -> Optional[list]:
    """
    Compute 95% CI on MDE using normal approximation.

    SE(p) = sqrt(p * (1 - p) / n_traffic)
    mde_ci_95 = [MDE(p - 1.96*SE(p)), MDE(p + 1.96*SE(p))]

    If --traffic/daily_traffic not supplied (n_traffic is None or <= 0),
    returns None with an info note (not blocked/warned).
    """
    if n_traffic is None or n_traffic <= 0:
        return None

    from scipy import stats as scipy_stats

    se_p = (p * (1 - p) / n_traffic) ** 0.5
    z = scipy_stats.norm.ppf(1 - (1 - confidence) / 2)  # ~1.96 for 95%

    lower_rate = max(p - z * se_p, 0.0)
    upper_rate = min(p + z * se_p, 1.0)

    mde_lower = lower_rate * mde_fraction
    mde_upper = upper_rate * mde_fraction

    return [round(mde_lower * 100, 4), round(mde_upper * 100, 4)]  # as percentages


if __name__ == "__main__":
    import sys
    data = json.load(sys.stdin)
    result = calculate_plan(data)
    print(result.model_dump_json(indent=2))