"""Difference-in-Differences analysis module"""

import json
from math import sqrt
from typing import Optional
from schema import DIDInput, DIDOutput, Recommendation, WarningDetail


def calculate_did(input_data: dict) -> DIDOutput:
    """
    Run DiD analysis and return structured output.
    """
    did_input = DIDInput(**input_data)
    
    # Extract values
    pre_c = did_input.pre_control
    post_c = did_input.post_control
    pre_t = did_input.pre_treated
    post_t = did_input.post_treated
    
    # DiD calculation
    # DiD = (post_t - pre_t) - (post_c - pre_c)
    treat_effect = post_t - pre_t
    control_change = post_c - pre_c
    did_estimate = treat_effect - control_change
    
    # Relative DiD (percent change vs pre-treated baseline)
    relative_did = (did_estimate / pre_t * 100) if pre_t != 0 else 0
    
    # Warning: parallel trends assumption
    # Without standard errors, we can only do basic sanity checks
    warnings = []
    assumptions = [
        "Parallel trends: Control and treated groups would have evolved similarly without treatment",
        "No spillover: Treatment in treated group doesn't affect control group",
        "No anticipatory effects: Treated group didn't respond before treatment"
    ]
    
    # Basic sanity checks
    if pre_c == 0 or pre_t == 0:
        warnings.append(WarningDetail(
            code="ZERO_BASELINE",
            message="Pre-period values cannot be zero for reliable DiD.",
            severity="critical"
        ))
        return _build_error_output(input_data, "Zero baseline detected", warnings)
    
    # Control group change ratio (should be similar to treatment if trends parallel)
    if pre_c > 0:
        ctrl_ratio = post_c / pre_c
    else:
        ctrl_ratio = 0
    
    if pre_t > 0:
        treat_ratio = post_t / pre_t
    else:
        treat_ratio = 0
    
    # If ratios diverge wildly, warn
    if ctrl_ratio > 0 and treat_ratio > 0:
        ratio_diff = abs(ctrl_ratio - treat_ratio)
        if ratio_diff > 0.5:  # 50% divergence
            warnings.append(WarningDetail(
                code="TRENDS_DIVERGE",
                message=f"Control and treated groups show very different pre-to-post ratios ({ctrl_ratio:.2f} vs {treat_ratio:.2f}). Parallel trends assumption may not hold.",
                severity="critical"
            ))
        elif ratio_diff > 0.2:
            warnings.append(WarningDetail(
                code="TRENDS_SLIGHTLY_DIVERGE",
                message=f"Ratios diverge somewhat ({ctrl_ratio:.2f} vs {treat_ratio:.2f}). Monitor closely.",
                severity="warning"
            ))
    
    # Observation count warning (generic)
    # Since we're working with aggregates, note that individual-level standard errors would be better
    warnings.append(WarningDetail(
        code="AGGREGATE_DATA",
        message="Analysis performed on aggregated data. For robust inference, use individual-level data with clustered SEs.",
        severity="info"
    ))
    
    # Decision logic (heuristic without p-values from aggregate data)
    # We'll use effect size thresholds
    if abs(relative_did) < 5:
        # Small effect - inconclusive
        decision = "escalate"
        confidence = "low"
        summary = f"DiD estimate is {did_estimate:.2f} ({relative_did:.2f}%), too uncertain to act on."
        warnings.append(WarningDetail(
            code="SMALL_EFFECT",
            message=f"Effect size {relative_did:.2f}% is below practical threshold. Escalate for judgment.",
            severity="info"
        ))
    elif relative_did > 10:
        if len([w for w in warnings if w.severity == "critical"]) == 0:
            decision = "ship"
            confidence = "medium"
            summary = f"Treatment effect is {did_estimate:.2f} ({relative_did:.2f}%). Positive and meaningful. Ship."
        else:
            decision = "escalate"
            confidence = "low"
            summary = f"Effect looks positive but critical warnings exist. Escalate."
    elif relative_did < -10:
        decision = "reject"
        confidence = "medium"
        summary = f"Treatment effect is {did_estimate:.2f} ({relative_did:.2f}%). Negative. Reject rollout."
    else:
        # Moderate effect, not conclusive
        if post_t > pre_t and post_c > pre_c:
            # Both grew - could be trend, not treatment
            warnings.append(WarningDetail(
                code="AMBIGUOUS",
                message="Both groups grew. Cannot separate treatment effect from time trend.",
                severity="warning"
            ))
            decision = "escalate"
            confidence = "low"
            summary = f"DiD is {did_estimate:.2f} ({relative_did:.2f}%) but trends ambiguous. Escalate."
        else:
            decision = "keep_running"
            confidence = "low"
            summary = f"DiD is {did_estimate:.2f} ({relative_did:.2f}%). Keep observing."
    
    # Build recommendation
    recommendation = Recommendation(
        decision=decision,
        confidence=confidence,
        summary=summary,
        primary_metricLift=round(relative_did, 4),
        p_value=None,  # No p-value from aggregate DiD
        warning=warnings[0].message if warnings else None
    )
    
    # Traffic stats (aggregated, no sample size)
    traffic_stats = {
        "pre_control": pre_c,
        "post_control": post_c,
        "pre_treated": pre_t,
        "post_treated": post_t,
        "note": "Aggregate data - no individual sample sizes available"
    }
    
    # Statistics
    stats_output = {
        "did_estimate": round(did_estimate, 4),
        "relative_did_pct": round(relative_did, 4),
        "control_change": round(control_change, 4),
        "treatment_change": round(treat_effect, 4),
        "control_ratio_post_pre": round(ctrl_ratio, 4),
        "treatment_ratio_post_pre": round(treat_ratio, 4)
    }
    
    audit = {
        "experiment_type": "difference_in_differences",
        "period": {"analyzed_at": "now"},
        "observation_size": "aggregate (no individual counts)",
        "computed_stats": list(stats_output.keys()),
        "assumptions_applied": assumptions,
        "decision_path": [
            {
                "step": "Input validation",
                "passed": pre_c > 0 and pre_t > 0,
                "details": {"pre_control": pre_c, "pre_treated": pre_t},
                "warning": "Zero baseline" if pre_c == 0 or pre_t == 0 else None,
                "severity": "critical" if pre_c == 0 or pre_t == 0 else "info"
            },
            {
                "step": "DiD estimation",
                "passed": True,
                "details": {
                    "control_change": round(control_change, 4),
                    "treatment_change": round(treat_effect, 4),
                    "did_estimate": round(did_estimate, 4),
                    "relative_did_pct": round(relative_did, 4)
                }
            },
            {
                "step": "Parallel trends check",
                "passed": ratio_diff <= 0.2,
                "details": {
                    "control_ratio_post_pre": round(ctrl_ratio, 4),
                    "treatment_ratio_post_pre": round(treat_ratio, 4),
                    "ratio_difference": round(ratio_diff, 4),
                    "threshold": 0.2
                },
                "warning": f"Trends diverge ({round(ratio_diff, 2)} > 0.2)" if ratio_diff > 0.2 else None,
                "severity": "warning" if ratio_diff > 0.2 else "info"
            },
            {
                "step": "Effect magnitude check",
                "passed": abs(relative_did) >= 5,
                "details": {
                    "relative_did_pct": round(relative_did, 4),
                    "thresholds": {"strong_positive": ">10%", "strong_negative": "<-10%", "small": "<5%"},
                    "is_small": abs(relative_did) < 5
                },
                "warning": f"Small effect ({round(relative_did, 2)}%)" if abs(relative_did) < 5 else None,
                "severity": "info"
            },
            {
                "step": "Decision",
                "passed": True,
                "details": {
                    "decision": decision,
                    "confidence": confidence,
                    "reason": summary
                }
            }
        ],
        "limitations": [
            "No standard errors from aggregate data",
            "Parallel trends not formally tested",
            "No clustered standard errors",
            "No covariates"
        ]
    }
    
    next_steps_map = {
        "ship": ["Deploy change", "Monitor for regression"],
        "keep_running": ["Continue observation", "Gather more data"],
        "reject": ["Rollback", "Investigate negative effect"],
        "escalate": ["Escalate to analyst", "Consider regression with covariates"]
    }
    next_steps = next_steps_map[decision]
    
    return DIDOutput(
        recommendation=recommendation,
        statistics=stats_output,
        traffic_stats=traffic_stats,
        warnings=warnings,
        next_steps=next_steps,
        audit=audit,
        inputs=input_data,
        assumptions=assumptions
    )


def _build_error_output(input_data: dict, error_msg: str, warnings: list) -> DIDOutput:
    """Build error output when calculation fails."""
    return DIDOutput(
        recommendation=Recommendation(
            decision="escalate",
            confidence="low",
            summary=f"Calculation error: {error_msg}",
            primary_metricLift=None,
            p_value=None,
            warning=error_msg
        ),
        statistics={},
        traffic_stats={},
        warnings=warnings,
        next_steps=["Fix input data and retry"],
        audit={"error": error_msg},
        inputs=input_data,
        assumptions=["Could not verify - calculation failed"]
    )


if __name__ == "__main__":
    import sys
    data = json.load(sys.stdin)
    result = calculate_did(data)
    print(result.model_dump_json(indent=2))