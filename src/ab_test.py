"""A/B Test analysis module"""

import json
from math import sqrt
from datetime import datetime
from scipy import stats
from typing import Optional
from schema import (
    ABTestInput, ABTestOutput, Recommendation, WarningDetail, TrafficStats,
    SequentialSummary
)


def calculate_ab(input_data: dict) -> ABTestOutput:
    """
    Run A/B test analysis and return structured output.
    Supports optional sequential / early stopping when sequential_enabled=true.
    """
    ab_input = ABTestInput(**input_data)

    # Extract core values
    c_conv = ab_input.control_conversions
    c_total = ab_input.control_total
    v_conv = ab_input.variant_conversions
    v_total = ab_input.variant_total

    # Conversion rates
    p_c = c_conv / c_total if c_total > 0 else 0
    p_v = v_conv / v_total if v_total > 0 else 0

    # Pooled proportion & standard error
    p_pool = (c_conv + v_conv) / (c_total + v_total) if (c_total + v_total) > 0 else 0
    se = sqrt(p_pool * (1 - p_pool) * (1 / c_total + 1 / v_total)) if (c_total > 0 and v_total > 0) else 0

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

    # MDE
    alpha = 0.05
    power = 0.8
    min_sample = 1000
    mde = 1.96 * sqrt((p_c * (1 - p_c) + p_v * (1 - p_v)) / min(c_total, v_total)) * 100 if min(c_total, v_total) > 0 else 0

    warnings = []
    next_steps = []

    # Traffic warnings
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

    # ── Sequential / early stopping evaluation ─────────────────────────────
    seq_summary, early_stop_applied, seq_warning = _evaluate_sequential(
        ab_input=ab_input,
        p_value=p_value,
        lift=lift,
        warnings=warnings,
    )

    if seq_warning:
        warnings.append(seq_warning)

    # ── Base decision logic (unchanged when early stop not applied) ─────────
    # When early_stop_applied=True, the sequential block has already set decision/confidence.
    # Otherwise run normal logic.
    if not early_stop_applied:
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
    else:
        # Early stop was applied — decision already set in _evaluate_sequential
        decision = seq_summary.reason  # will be overwritten below
        confidence = "high"  # will be overwritten below

    # Recalculate decision from sequential_summary when early stop was applied
    if early_stop_applied:
        if seq_summary.reason == "p_below_threshold":
            if lift > 0:
                decision = "ship"
                confidence = "high"
            else:
                decision = "reject"
                confidence = "high"
        elif seq_summary.reason == "max_runtime_exceeded":
            decision = "escalate"
            confidence = "low"
        else:
            decision = "escalate"
            confidence = "low"

    summary_map = {
        "ship": f"Variant performs {lift:.2f}% better (p={p_value:.4f}). Ship it.",
        "keep_running": f"Variant performs {lift:.2f}% better but not significant yet. Keep running.",
        "reject": f"Variant performs {lift:.2f}% worse (p={p_value:.4f}). Reject.",
        "escalate": f"Results not conclusive. p={p_value:.4f}, lift={lift:.2f}%. Escalate for review."
    }

    if not next_steps:
        next_steps_map = {
            "ship": ["Deploy variant", "Monitor over time for regression"],
            "keep_running": ["Continue experiment", "Check back when traffic increases"],
            "reject": ["Rollback variant", "Investigate why variant underperformed"],
            "escalate": ["Escalate to product manager", "Consider qualitative feedback"]
        }
        next_steps = next_steps_map[decision]

    # next_analysis_suggestion — fires when aggregate result is inconclusive
    next_analysis_suggestion = None
    if decision in ("keep_running", "escalate"):
        next_analysis_suggestion = {
            "command": "cohort-breakdown",
            "reason": "Aggregate result is inconclusive. A segment-level breakdown may reveal hidden signal.",
            "trigger": f"decision={decision}",
        }

    recommendation = Recommendation(
        decision=decision,
        confidence=confidence,
        summary=summary_map[decision],
        primary_metricLift=round(lift, 4),
        p_value=round(p_value, 6),
        warning=warnings[0].message if warnings else None
    )

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

    # Build audit with decision path
    decision_path = [
        {
            "step": "Input validation",
            "passed": bool(c_total > 0 and v_total > 0),
            "details": {"control_total": int(c_total), "variant_total": int(v_total)}
        },
        {
            "step": "Traffic check",
            "passed": bool(c_total >= min_sample and v_total >= min_sample),
            "details": {"control_size": int(c_total), "variant_size": int(v_total), "min_required": int(min_sample)},
            "warning": "Traffic low" if bool(c_total < min_sample or v_total < min_sample) else None,
            "severity": "warning"
        },
        {
            "step": "Conversion rate calculation",
            "passed": True,
            "details": {"control_rate": float(round(p_c, 6)), "variant_rate": float(round(p_v, 6))}
        },
        {
            "step": "Statistical significance test",
            "passed": bool(p_value < alpha),
            "details": {"p_value": float(round(p_value, 6)), "alpha": float(alpha), "z_score": float(round(z, 4))},
            "warning": f"p={p_value:.4f} >= {alpha}" if p_value >= alpha else None,
            "severity": "info"
        },
        {
            "step": "Effect size check",
            "passed": bool(abs(lift) >= 1),
            "details": {"lift_pct": float(round(lift, 4)), "threshold": 1},
            "warning": f"Effect small ({lift:.2f}%)" if abs(lift) < 1 else None,
            "severity": "info"
        },
        {
            "step": "Decision",
            "passed": True,
            "details": {"decision": decision, "confidence": confidence, "reason": summary_map[decision]}
        }
    ]

    # Add sequential section to audit when enabled
    if ab_input.sequential_enabled:
        decision_path.append({
            "step": "Sequential early stopping review",
            "passed": True,
            "details": {
                "sequential_enabled": True,
                "early_stop_applied": early_stop_applied,
                "reason": seq_summary.reason,
                "min_runtime_days": ab_input.min_runtime_days,
                "observed_runtime_days": seq_summary.observed_runtime_days,
                "min_sample_per_arm": ab_input.min_sample_per_arm,
                "observed_sample_per_arm": seq_summary.observed_sample_per_arm,
                "early_stop_p_threshold": ab_input.early_stop_p_threshold,
                "max_runtime_days": ab_input.max_runtime_days,
            },
            "warning": f"Early stop applied: {seq_summary.reason}" if early_stop_applied else None,
            "severity": "info"
        })
        # Append limitation note when early stop applied
        if early_stop_applied:
            decision_path.append({
                "step": "Sequential stopping caveat",
                "passed": True,
                "details": {},
                "warning": (
                    "Sequential stopping can slightly increase false-positive risk compared to "
                    "a fixed-sample test; thresholds are set conservatively to mitigate this risk."
                ),
                "severity": "info"
            })

    audit = {
        "experiment_type": "ab_test",
        "period": {"analyzed_at": datetime.utcnow().isoformat() + "Z"},
        "traffic_size": c_total + v_total,
        "computed_stats": list(stats_output.keys()),
        "thresholds_applied": {
            "alpha": alpha, "power": power, "min_traffic": min_sample,
            "sequential_enabled": ab_input.sequential_enabled,
            "early_stop_p_threshold": ab_input.early_stop_p_threshold,
            "min_runtime_days": ab_input.min_runtime_days,
            "min_sample_per_arm": ab_input.min_sample_per_arm,
            "max_runtime_days": ab_input.max_runtime_days,
        },
        "decision_path": decision_path,
        "assumptions": [
            "Randomized assignment",
            "Independent observations",
            "Sample size adequate for effect"
        ],
        "limitations": [
            "Binary conversion outcome only",
            "No multiple testing correction applied",
            "No cluster adjustment",
            "Sequential stopping slightly inflates false-positive rate vs fixed-sample design"
        ]
    }

    return ABTestOutput(
        recommendation=recommendation,
        statistics=stats_output,
        traffic_stats=traffic_stats,
        warnings=warnings,
        next_steps=next_steps,
        next_analysis_suggestion=next_analysis_suggestion,
        audit=audit,
        inputs=input_data,
        sequential_reviewed=ab_input.sequential_enabled,
        early_stop_applied=early_stop_applied,
        sequential_summary=seq_summary,
    )


def _evaluate_sequential(
    ab_input: ABTestInput,
    p_value: float,
    lift: float,
    warnings: list,
) -> tuple[SequentialSummary, bool, Optional[WarningDetail]]:
    """
    Evaluate sequential / early stopping conditions.
    Returns (seq_summary, early_stop_applied, seq_warning).
    """
    seq_summary: SequentialSummary
    early_stop_applied = False
    seq_warning: Optional[WarningDetail] = None

    if not ab_input.sequential_enabled:
        return None, False, None

    # Compute observed runtime
    observed_runtime_days: Optional[float] = None
    if ab_input.experiment_start_time and ab_input.experiment_end_time:
        try:
            start = datetime.fromisoformat(ab_input.experiment_start_time.replace("Z", "+00:00"))
            end = datetime.fromisoformat(ab_input.experiment_end_time.replace("Z", "+00:00"))
            observed_runtime_days = (end - start).total_seconds() / 86400
        except ValueError:
            observed_runtime_days = None

    observed_sample_per_arm = min(ab_input.control_total, ab_input.variant_total)

    # Check conditions not met
    runtime_ok = observed_runtime_days is not None and observed_runtime_days >= ab_input.min_runtime_days
    sample_ok = observed_sample_per_arm >= ab_input.min_sample_per_arm

    if not (runtime_ok and sample_ok):
        reason_str = []
        if not runtime_ok:
            if observed_runtime_days is not None:
                reason_str.append(f"runtime {observed_runtime_days:.1f}d < {ab_input.min_runtime_days}d")
            else:
                reason_str.append("runtime unknown (missing timestamps)")
        if not sample_ok:
            reason_str.append(f"sample {observed_sample_per_arm} < {ab_input.min_sample_per_arm}")
        seq_warning = WarningDetail(
            code="sequential_conditions_not_met",
            message=f"Sequential conditions not met ({'; '.join(reason_str)}). Normal decision applied.",
            severity="info"
        )
        seq_summary = SequentialSummary(
            min_runtime_days=ab_input.min_runtime_days,
            observed_runtime_days=observed_runtime_days,
            min_sample_per_arm=ab_input.min_sample_per_arm,
            observed_sample_per_arm=observed_sample_per_arm,
            early_stop_p_threshold=ab_input.early_stop_p_threshold,
            max_runtime_days=ab_input.max_runtime_days,
            reason="conditions_not_met",
        )
        return seq_summary, False, seq_warning

    # Check max runtime exceeded
    if ab_input.max_runtime_days is not None and observed_runtime_days > ab_input.max_runtime_days:
        seq_warning = WarningDetail(
            code="max_runtime_exceeded",
            message=f"Max runtime {ab_input.max_runtime_days}d exceeded ({observed_runtime_days:.1f}d) without strong result. Escalating.",
            severity="warning"
        )
        seq_summary = SequentialSummary(
            min_runtime_days=ab_input.min_runtime_days,
            observed_runtime_days=observed_runtime_days,
            min_sample_per_arm=ab_input.min_sample_per_arm,
            observed_sample_per_arm=observed_sample_per_arm,
            early_stop_p_threshold=ab_input.early_stop_p_threshold,
            max_runtime_days=ab_input.max_runtime_days,
            reason="max_runtime_exceeded",
        )
        return seq_summary, False, seq_warning

    # Primary early stop trigger: p below threshold AND directionally favorable
    if p_value < ab_input.early_stop_p_threshold:
        if lift > 0:
            reason = "p_below_threshold"
        elif lift < 0:
            reason = "p_below_threshold"
        else:
            # lift == 0, no effect — don't early stop
            reason = "no_early_stop"

        if reason == "p_below_threshold":
            seq_summary = SequentialSummary(
                min_runtime_days=ab_input.min_runtime_days,
                observed_runtime_days=observed_runtime_days,
                min_sample_per_arm=ab_input.min_sample_per_arm,
                observed_sample_per_arm=observed_sample_per_arm,
                early_stop_p_threshold=ab_input.early_stop_p_threshold,
                max_runtime_days=ab_input.max_runtime_days,
                reason=reason,
            )
            early_stop_applied = True
            seq_warning = WarningDetail(
                code="early_stop_applied",
                message=(
                    f"Early stop applied (p={p_value:.4f} < {ab_input.early_stop_p_threshold}). "
                    f"Decision triggered by p-value threshold."
                ),
                severity="info"
            )
            return seq_summary, early_stop_applied, seq_warning

    # No early stop — sequential reviewed but not triggered
    seq_summary = SequentialSummary(
        min_runtime_days=ab_input.min_runtime_days,
        observed_runtime_days=observed_runtime_days,
        min_sample_per_arm=ab_input.min_sample_per_arm,
        observed_sample_per_arm=observed_sample_per_arm,
        early_stop_p_threshold=ab_input.early_stop_p_threshold,
        max_runtime_days=ab_input.max_runtime_days,
        reason="no_early_stop",
    )
    return seq_summary, False, None


if __name__ == "__main__":
    import sys
    data = json.load(sys.stdin)
    result = calculate_ab(data)
    print(result.model_dump_json(indent=2))
