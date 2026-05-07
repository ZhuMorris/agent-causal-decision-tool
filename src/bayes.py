"""Bayesian A/B test analysis using Beta-Binomial conjugate model"""

import numpy as np
from datetime import datetime, timezone

from .schema import (
    ABTestInput, BayesOutput, Recommendation, WarningDetail, TrafficStats,
    PosteriorStats, BayesianStatistics, WarningCode,
)


def calculate_bayes_ab(input_data: dict, n_samples: int = 20000) -> BayesOutput:
    """
    Run Bayesian A/B test analysis.

    Uses Beta-Binomial conjugate model:
    - Prior: Beta(alpha_prior, beta_prior) — weak Jeffreys prior by default
    - Posterior after data: Beta(alpha_prior + successes, beta_prior + failures)
    - P(variant > control) computed via Monte Carlo simulation
    """
    ab_input = ABTestInput(**input_data)

    # Extract observed data
    c_conv = ab_input.control_conversions
    c_total = ab_input.control_total
    v_conv = ab_input.variant_conversions
    v_total = ab_input.variant_total

    # Guard: totals must be positive (Pydantic ge=1 on ABTestInput is first defense)
    if c_total < 1 or v_total < 1:
        raise ValueError(f"control_total and variant_total must be >= 1, got control={c_total}, variant={v_total}")

    # Conversion rates
    p_c = c_conv / c_total if c_total > 0 else 0
    p_v = v_conv / v_total if v_total > 0 else 0

    # Prior: Jeffrey's prior Beta(0.5, 0.5) — uninformative
    alpha_prior = 0.5
    beta_prior = 0.5

    # Posterior parameters
    alpha_c = alpha_prior + c_conv
    beta_c = beta_prior + (c_total - c_conv)
    alpha_v = alpha_prior + v_conv
    beta_v = beta_prior + (v_total - v_conv)

    # Monte Carlo simulation: sample from posteriors and compare
    if n_samples < 1:
        raise ValueError(f"n_samples must be >= 1, got {n_samples}")

    rng = np.random.default_rng()
    samples_control = rng.beta(alpha_c, beta_c, n_samples)
    samples_variant = rng.beta(alpha_v, beta_v, n_samples)

    # Compute probabilities
    p_variant_wins = np.mean(samples_variant > samples_control)
    p_control_wins = np.mean(samples_control > samples_variant)
    p_tie = np.mean(np.abs(samples_variant - samples_control) < 1e-10)

    # Relative lift distribution
    lifts = (samples_variant - samples_control) / samples_control * 100
    lift_median = float(np.median(lifts))
    lift_95ci = [float(np.percentile(lifts, 2.5)), float(np.percentile(lifts, 97.5))]

    # Expected absolute lift HDI (2.5th–97.5th percentiles of variant − control)
    abs_lifts = samples_variant - samples_control
    expected_lift_hdi_95 = [float(np.percentile(abs_lifts, 2.5)), float(np.percentile(abs_lifts, 97.5))]
    # Guard: prevent division by zero in relative lift HDI (p_c may be 0)
    relative_lift_hdi_95 = (
        [round((expected_lift_hdi_95[0] / p_c) * 100, 4), round((expected_lift_hdi_95[1] / p_c) * 100, 4)]
        if p_c > 0 else None
    )

    # Expected values
    expected_control = np.mean(samples_control)
    expected_variant = np.mean(samples_variant)

    # Decision thresholds
    SHIP_THRESHOLD = 0.95
    REJECT_THRESHOLD = 0.05

    # Warnings
    warnings = []

    min_sample = 500
    if c_total < min_sample or v_total < min_sample:
        warnings.append(WarningDetail(
            code=WarningCode.LOW_TRAFFIC,
            message=f"Traffic relatively low (control={c_total}, variant={v_total}). Prior heavily influences posterior.",
            severity="warning"
        ))

    if c_total + v_total < 200:
        warnings.append(WarningDetail(
            code=WarningCode.PRIOR_DOMINATES,
            message=f"Very low total traffic ({c_total + v_total}). Jeffreys prior dominates posterior; interpret with caution.",
            severity="warning"
        ))

    if p_variant_wins > 0.5 and p_variant_wins < SHIP_THRESHOLD:
        warnings.append(WarningDetail(
            code=WarningCode.INCONCLUSIVE,
            message=f"P(variant wins)={p_variant_wins:.3f} — not conclusive enough to ship. Need >={SHIP_THRESHOLD}.",
            severity="warning"
        ))

    # Small effect check
    if p_variant_wins > 0.5:
        lift_pct = (p_v - p_c) / p_c * 100 if p_c > 0 else 0
        if abs(lift_pct) < 1:
            warnings.append(WarningDetail(
                code=WarningCode.SMALL_EFFECT,
                message=f"Observed lift {lift_pct:.2f}% is very small. May not be practically significant.",
                severity="info"
            ))

    # Compute decision
    if p_variant_wins >= SHIP_THRESHOLD:
        if lift_median > 0:
            decision = "ship"
            confidence = "high" if p_variant_wins >= 0.99 else "medium"
            summary = f"Variant wins with P(better)={p_variant_wins:.3f}. Median lift={lift_median:.2f}%. Ship."
        else:
            decision = "reject"
            confidence = "high" if p_variant_wins >= 0.99 else "medium"
            summary = f"Variant wins but negative median lift={lift_median:.2f}%. Reject."
    elif p_variant_wins <= REJECT_THRESHOLD:
        if lift_median < 0:
            decision = "reject"
            confidence = "high" if p_control_wins >= 0.99 else "medium"
            summary = f"Control wins with P(better)={p_control_wins:.3f}. Variant performs worse. Reject."
        else:
            decision = "escalate"
            confidence = "low"
            summary = "Results inverted unexpectedly. Escalate for review."
    else:
        decision = "keep_running"
        confidence = "low"
        summary = f"No clear winner. P(variant wins)={p_variant_wins:.3f}. Keep running to collect more data."

    # Recommendation
    recommendation = Recommendation(
        decision=decision,
        confidence=confidence,
        summary=summary,
        primary_metricLift=round(lift_median, 4),
        p_value=round(p_variant_wins, 6),
        warning=warnings[0].message if warnings else None
    )

    # Statistics
    statistics = BayesianStatistics(
        control_rate_observed=round(p_c, 6),
        variant_rate_observed=round(p_v, 6),
        relative_lift_pct=round((p_v - p_c) / p_c * 100, 4) if p_c > 0 else 0,
        posterior_control=PosteriorStats(
            alpha=alpha_c, beta=beta_c, mean=round(expected_control, 6)
        ),
        posterior_variant=PosteriorStats(
            alpha=alpha_v, beta=beta_v, mean=round(expected_variant, 6)
        ),
        p_variant_wins=round(p_variant_wins, 6),
        p_control_wins=round(p_control_wins, 6),
        p_tie=round(p_tie, 6),
        lift_median_pct=round(lift_median, 4),
        lift_95ci_pct=[round(lift_95ci[0], 4), round(lift_95ci[1], 4)],
        expected_lift_hdi_95=[round(expected_lift_hdi_95[0], 6), round(expected_lift_hdi_95[1], 6)],
        relative_lift_hdi_95=relative_lift_hdi_95,
        monte_carlo_samples=n_samples,
        prior_used={"alpha": alpha_prior, "beta": beta_prior, "type": "Jeffreys"}
    )

    # Traffic stats
    traffic_stats = TrafficStats(
        control_size=c_total,
        variant_size=v_total,
        total_size=c_total + v_total
    )

    # Next steps
    next_steps_map = {
        "ship": ["Deploy variant", "Monitor for regression"],
        "keep_running": ["Continue data collection", "Re-run Bayesian analysis when traffic increases"],
        "reject": ["Rollback variant", "Investigate why variant underperformed"],
        "escalate": ["Escalate to analyst", "Review for data quality or segment issues"]
    }
    next_steps = next_steps_map[decision]

    # Decision path for audit
    decision_path = [
        {
            "step": "Prior selection",
            "passed": True,
            "details": {"prior": "Jeffreys Beta(0.5,0.5)", "reason": "Uninformative, suitable for conversion rates"},
            "warning": None,
            "severity": "info"
        },
        {
            "step": "Posterior computation",
            "passed": True,
            "details": {
                "control_posterior": f"Beta(α={alpha_c}, β={beta_c})",
                "variant_posterior": f"Beta(α={alpha_v}, β={beta_v})",
                "control_mean": round(expected_control, 6),
                "variant_mean": round(expected_variant, 6)
            },
            "warning": None,
            "severity": "info"
        },
        {
            "step": "Monte Carlo simulation",
            "passed": True,
            "details": {
                "samples": n_samples,
                "p_variant_wins": round(p_variant_wins, 6),
                "p_control_wins": round(p_control_wins, 6),
                "thresholds": {"ship": SHIP_THRESHOLD, "reject": REJECT_THRESHOLD}
            },
            "warning": None,
            "severity": "info"
        },
        {
            "step": "Effect magnitude check",
            "passed": abs(lift_median) >= 1,
            "details": {"median_lift_pct": round(lift_median, 4), "threshold": 1},
            "warning": f"Small median lift ({round(lift_median, 2)}%)" if abs(lift_median) < 1 else None,
            "severity": "info"
        },
        {
            "step": "Decision",
            "passed": True,
            "details": {"decision": decision, "confidence": confidence, "reason": summary}
        }
    ]

    audit = {
        "experiment_type": "bayesian_ab",
        "period": {"analyzed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
        "traffic_size": c_total + v_total,
        "computed_stats": ["p_variant_wins", "p_control_wins", "p_tie", "lift_median_pct",
                           "lift_95ci_pct", "expected_lift_hdi_95", "relative_lift_hdi_95"],
        "method": "Beta-Binomial conjugate model with Monte Carlo simulation",
        "thresholds_applied": {"ship": SHIP_THRESHOLD, "reject": REJECT_THRESHOLD},
        "decision_path": decision_path,
        "assumptions": [
            "Independent observations between groups",
            "No selection bias in group assignment",
            "Conversion events are independent",
            "Jeffrey's prior is appropriate for conversion rates"
        ],
        "limitations": [
            "Point estimate posterior means may not reflect full distribution",
            "Monte Carlo simulation has finite sampling error",
            "No multiple testing correction applied",
            "No cluster adjustment for correlated observations"
        ]
    }

    return BayesOutput(
        recommendation=recommendation,
        statistics=statistics,
        traffic_stats=traffic_stats,
        warnings=warnings,
        next_steps=next_steps,
        audit=audit,
        inputs=input_data
    )