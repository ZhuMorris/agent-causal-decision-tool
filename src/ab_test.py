"""A/B Test analysis module"""

import json
from math import sqrt
from scipy import stats
from typing import Optional
from schema import ABTestInput, ABTestOutput, Recommendation, WarningDetail, TrafficStats


def calculate_ab(input_data: dict) -> ABTestOutput:
    """
    Run A/B test analysis and return structured output.
    """
    ab_input = ABTestInput(**input_data)
    
    # Extract values
    c_conv = ab_input.control_conversions
    c_total = ab_input.control_total
    v_conv = ab_input.variant_conversions
    v_total = ab_input.variant_total
    
    # Conversion rates
    p_c = c_conv / c_total if c_total > 0 else 0
    p_v = v_conv / v_total if v_total > 0 else 0
    
    # Pooled proportion
    p_pool = (c_conv + v_conv) / (c_total + v_total) if (c_total + v_total) > 0 else 0
    
    # Standard error
    se = sqrt(p_pool * (1 - p_pool) * (1/c_total + 1/v_total)) if (c_total > 0 and v_total > 0) else 0
    
    # Z-score and p-value (two-tailed)
    if se > 0:
        z = (p_v - p_c) / se
        p_value = 2 * (1 - stats.norm.cdf(abs(z)))
    else:
        z = 0
        p_value = 1.0
    
    # Relative lift
    lift = ((p_v - p_c) / p_c * 100) if p_c > 0 else 0
    
    # Confidence interval (95%)
    diff = p_v - p_c
    margin = 1.96 * se
    ci_lower = diff - margin
    ci_upper = diff + margin
    
    # Effect size (Cohen's h)
    import numpy as np
    h = 2 * (np.arcsin(sqrt(p_v)) - np.arcsin(sqrt(p_c))) if (p_v >= 0 and p_v <= 1 and p_c >= 0 and p_c <= 1) else 0

    # Decision logic
    warnings = []
    next_steps = []
    
    # Traffic warnings
    min_sample = 1000
    if c_total < min_sample or v_total < min_sample:
        warnings.append(WarningDetail(
            code="LOW_TRAFFIC",
            message=f"Traffic too low. Control: {c_total}, Variant: {v_total}. Minimum recommended: {min_sample}",
            severity="warning"
        ))
    
    # Small effect warning
    if abs(lift) < 1:
        warnings.append(WarningDetail(
            code="SMALL_EFFECT",
            message=f"Effect size is very small ({lift:.2f}%). May not be practically significant.",
            severity="info"
        ))
    
    # Compute recommendation
    alpha = 0.05
    power = 0.8
    
    # Minimum detectable effect check
    mde = 1.96 * sqrt((p_c * (1 - p_c) + p_v * (1 - p_v)) / min(c_total, v_total)) * 100 if min(c_total, v_total) > 0 else 0
    
    if p_value < alpha:
        if lift > 0:
            decision = "ship"
            confidence = "high" if p_value < 0.01 else "medium"
        else:
            decision = "reject"
            confidence = "high" if p_value < 0.01 else "medium"
    else:
        if p_value < 0.3:
            decision = "keep_running"
            confidence = "low"
            warnings.append(WarningDetail(
                code="INCONCLUSIVE",
                message=f"p-value={p_value:.4f} not significant but trending. Keep running.",
                severity="info"
            ))
            next_steps.append("Collect more traffic before making decision")
        else:
            decision = "escalate"
            confidence = "low"
            warnings.append(WarningDetail(
                code="NOT_SIGNIFICANT",
                message=f"p-value={p_value:.4f} far from significant. Consider stopping.",
                severity="warning"
            ))
            next_steps.append("Review if variant has other benefits before escalating")

    # Build recommendation
    summary_map = {
        "ship": f"Variant performs {lift:.2f}% better (p={p_value:.4f}). Ship it.",
        "keep_running": f"Variant performs {lift:.2f}% better but not significant yet. Keep running.",
        "reject": f"Variant performs {lift:.2f}% worse (p={p_value:.4f}). Reject.",
        "escalate": f"Results not conclusive. p={p_value:.4f}, lift={lift:.2f}%. Escalate for review."
    }
    
    recommendation = Recommendation(
        decision=decision,
        confidence=confidence,
        summary=summary_map[decision],
        primary_metricLift=round(lift, 4),
        p_value=round(p_value, 6),
        warning=warnings[0].message if warnings else None
    )
    
    # Build output
    traffic_stats = TrafficStats(
        control_size=c_total,
        variant_size=v_total,
        total_size=c_total + v_total
    )
    
    stats_output = {
        "control_rate": round(p_c, 6),
        "variant_rate": round(p_v, 6),
        "absolute_difference": round(diff, 6),
        "relative_lift_pct": round(lift, 4),
        "z_score": round(z, 4),
        "p_value": round(p_value, 6),
        "confidence_interval_95": [round(ci_lower, 6), round(ci_upper, 6)],
        "cohens_h": round(h, 4),
        "minimum_detectable_effect_pct": round(mde, 4)
    }
    
    audit = {
        "experiment_type": "ab_test",
        "period": {"analyzed_at": "now"},
        "traffic_size": c_total + v_total,
        "computed_stats": list(stats_output.keys()),
        "thresholds_applied": {"alpha": alpha, "power": power},
        "assumptions": [
            "Randomized assignment",
            "Independent observations",
            "Sample size adequate for effect"
        ],
        "limitations": [
            "Binary conversion outcome only",
            "No multiple testing correction applied",
            "No cluster adjustment"
        ]
    }
    
    if not next_steps:
        next_steps_map = {
            "ship": ["Deploy variant", "Monitor over time for regression"],
            "keep_running": ["Continue experiment", "Check back when traffic increases"],
            "reject": ["Rollback variant", "Investigate why variant underperformed"],
            "escalate": ["Escalate to product manager", "Consider qualitative feedback"]
        }
        next_steps = next_steps_map[decision]
    
    return ABTestOutput(
        recommendation=recommendation,
        statistics=stats_output,
        traffic_stats=traffic_stats,
        warnings=warnings,
        next_steps=next_steps,
        audit=audit,
        inputs=input_data
    )


if __name__ == "__main__":
    # CLI test
    import sys
    data = json.load(sys.stdin)
    result = calculate_ab(data)
    print(result.model_dump_json(indent=2))