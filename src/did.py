"""Difference-in-Differences analysis module"""

import json
from math import sqrt
from typing import Optional
from schema import DIDInput, DIDOutput, Recommendation, WarningDetail, DIDDiagnostics


def calculate_did(input_data: dict) -> DIDOutput:
    """
    Run DiD analysis with robustness diagnostics.
    """
    did_input = DIDInput(**input_data)

    # Extract values
    pre_c = did_input.pre_control
    post_c = did_input.post_control
    pre_t = did_input.pre_treated
    post_t = did_input.post_treated

    # DiD calculation
    treat_effect = post_t - pre_t
    control_change = post_c - pre_c
    did_estimate = treat_effect - control_change
    relative_did = (did_estimate / pre_t * 100) if pre_t != 0 else 0

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

    # Parallel trends ratio check
    ctrl_ratio = post_c / pre_c if pre_c > 0 else 0
    treat_ratio = post_t / pre_t if pre_t > 0 else 0
    ratio_diff = abs(ctrl_ratio - treat_ratio) if (ctrl_ratio > 0 and treat_ratio > 0) else 0

    if ratio_diff > 0.5:
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

    warnings.append(WarningDetail(
        code="AGGREGATE_DATA",
        message="Analysis performed on aggregated data. For robust inference, use individual-level data with clustered SEs.",
        severity="info"
    ))

    # Decision logic
    if abs(relative_did) < 5:
        decision = "escalate"
        confidence = "low"
        summary = f"DiD estimate is {did_estimate:.2f} ({relative_did:.2f}%), too uncertain to act on."
        warnings.append(WarningDetail(
            code="SMALL_EFFECT",
            message=f"Effect size {relative_did:.2f}% is below practical threshold. Escalate for judgment.",
            severity="info"
        ))
    elif relative_did > 10:
        if not any(w.severity == "critical" for w in warnings):
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
        if post_t > pre_t and post_c > pre_c:
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

    # ── Diagnostics ─────────────────────────────────────────────────────────────
    diagnostics = _compute_did_diagnostics(did_input, did_estimate)

    # recommended_next_action & explanation based on caution level
    recommended_next_action, explanation = _build_did_narrative(
        decision, relative_did, diagnostics
    )

    if diagnostics.recommended_caution_level == "high":
        if "did_result_should_be_reviewed_by_human" not in [w.code for w in warnings]:
            warnings.append(WarningDetail(
                code="did_result_should_be_reviewed_by_human",
                message="Caution is high; this result should be reviewed by a human. Do not treat this as equivalent to a randomized experiment.",
                severity="warning"
            ))
        if decision == "ship":
            decision = "escalate"
            summary = f"Effect is positive but caution level is high — escalate for human review."

    recommendation = Recommendation(
        decision=decision,
        confidence=confidence,
        summary=summary,
        primary_metricLift=round(relative_did, 4),
        p_value=None,
        warning=warnings[0].message if warnings else None
    )

    traffic_stats = {
        "pre_control": pre_c,
        "post_control": post_c,
        "pre_treated": pre_t,
        "post_treated": post_t,
        "note": "Aggregate data - no individual sample sizes available"
    }

    stats_output = {
        "did_estimate": round(did_estimate, 4),
        "relative_did_pct": round(relative_did, 4),
        "control_change": round(control_change, 4),
        "treatment_change": round(treat_effect, 4),
        "control_ratio_post_pre": round(ctrl_ratio, 4),
        "treatment_ratio_post_pre": round(treat_ratio, 4)
    }

    # Build audit with diagnostics section
    decision_path = [
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
            "step": "Diagnostics evaluation",
            "passed": diagnostics.recommended_caution_level != "high",
            "details": {
                "parallel_trends_evidence": diagnostics.parallel_trends_evidence,
                "fragility_flags": diagnostics.fragility_flags,
                "recommended_caution_level": diagnostics.recommended_caution_level,
            },
            "warning": f"Caution level: {diagnostics.recommended_caution_level}" if diagnostics.recommended_caution_level != "low" else None,
            "severity": "warning" if diagnostics.recommended_caution_level == "high" else "info"
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
    ]

    audit = {
        "experiment_type": "difference_in_differences",
        "period": {"analyzed_at": "now"},
        "observation_size": "aggregate (no individual counts)",
        "computed_stats": list(stats_output.keys()),
        "assumptions_applied": assumptions,
        "diagnostics": diagnostics.model_dump(),
        "decision_path": decision_path,
        "limitations": [
            "No standard errors from aggregate data",
            "Parallel trends not formally tested",
            "No clustered standard errors",
            "No covariates",
            "Single pre-period prevents pre-trend verification"
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
        assumptions=assumptions,
        did_diagnostics=diagnostics,
        recommended_next_action=recommended_next_action,
        explanation=explanation,
    )


def _compute_did_diagnostics(did_input: DIDInput, did_estimate: float) -> DIDDiagnostics:
    """
    Compute DiD setup quality diagnostics from input metadata.
    Returns a DIDDiagnostics object (all fields nullable if metadata not provided).
    """
    fragility_flags: list[str] = []
    caution_level: str = "low"
    pre_periods = did_input.pre_periods
    post_periods = did_input.post_periods
    t_count = did_input.treatment_observation_count
    c_count = did_input.control_observation_count

    # Single pre-period → parallel trends unverifiable
    if pre_periods is not None and pre_periods <= 1:
        fragility_flags.append("single_pre_period")
        caution_level = "high"

    # Small sample in either group
    for label, count in [("treatment", t_count), ("control", c_count)]:
        if count is not None and count < 100:
            fragility_flags.append("small_sample")
            if caution_level != "high":
                caution_level = "medium"
            break

    # Imbalanced groups
    if t_count is not None and c_count is not None and c_count > 0:
        ratio = t_count / c_count
        if ratio > 3 or ratio < 1 / 3:
            fragility_flags.append("imbalanced_groups")
            if caution_level != "high":
                caution_level = "medium"

    # Large effect + small sample
    if abs(did_estimate) > 0.05 and (t_count is not None and t_count < 200) and (c_count is not None and c_count < 200):
        fragility_flags.append("large_effect_small_sample")
        caution_level = "high"

    # Parallel trends evidence (heuristic — only informative with multiple pre-periods)
    if pre_periods is not None and pre_periods >= 3:
        trends_evidence: str = "moderate"
    elif pre_periods is not None and pre_periods == 2:
        trends_evidence = "weak"
    elif pre_periods is not None and pre_periods == 1:
        trends_evidence = "none"
    else:
        trends_evidence = "none"  # unknown

    return DIDDiagnostics(
        pre_periods=pre_periods,
        post_periods=post_periods,
        treatment_observation_count=t_count,
        control_observation_count=c_count,
        parallel_trends_evidence=trends_evidence,
        fragility_flags=fragility_flags,
        recommended_caution_level=caution_level,
    )


def _build_did_narrative(
    decision: str, relative_did: float, diagnostics: DIDDiagnostics
) -> tuple[str, str]:
    """Derive recommended_next_action and explanation from diagnostics."""
    caution = diagnostics.recommended_caution_level
    flags = diagnostics.fragility_flags

    if caution == "high":
        flag_desc = "; ".join(_flag_explanation(f) for f in flags) if flags else "multiple fragility signals"
        explanation = (
            f"Observed uplift is {relative_did:.2f}%, but the DiD setup is fragile ({flag_desc}). "
            f"Parallel trends cannot be verified; treat this result as indicative only. "
            f"Caution is high; this result should be reviewed by a human."
        )
        return "escalate_to_human", explanation
    elif caution == "medium":
        explanation = (
            f"DiD estimate is {relative_did:.2f}%. "
            f"Setup has some fragility ({'; '.join(flags)}). "
            f"Use with caution and monitor closely."
        )
        return "use_with_caution", explanation
    else:
        explanation = f"DiD estimate is {relative_did:.2f}%. Setup appears adequate."
        return "proceed", explanation


def _flag_explanation(flag: str) -> str:
    """Translate fragility flag to plain-language explanation."""
    return {
        "single_pre_period": "only one pre-period — cannot verify parallel trends",
        "small_sample": "observation count < 100 in at least one group — results unreliable",
        "imbalanced_groups": "treatment/control ratio > 3x or < 1/3x — groups not comparable",
        "large_effect_small_sample": "large effect with small sample — possible confounding",
    }.get(flag, flag)


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
