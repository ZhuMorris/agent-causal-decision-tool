"""Statistical utilities for Agent Causal — two-proportion z-test and helpers."""
from scipy import stats
import numpy as np
from typing import Tuple


def two_proportion_z_test(
    control_conversions: int,
    control_total: int,
    variant_conversions: int,
    variant_total: int,
    alpha: float = 0.05,
) -> dict:
    """Run a two-proportion z-test on segment results.

    Returns rate estimates, z-score, p-value, and confidence interval.
    """
    if control_total == 0 or variant_total == 0:
        raise ValueError("Total counts must be greater than zero")

    p_control = control_conversions / control_total
    p_variant = variant_conversions / variant_total

    p_pool = (control_conversions + variant_conversions) / (control_total + variant_total)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / control_total + 1 / variant_total))

    if se == 0:
        return {
            "control_rate": p_control,
            "variant_rate": p_variant,
            "absolute_lift": 0.0,
            "relative_lift_pct": 0.0,
            "z_score": 0.0,
            "p_value": 1.0,
            "confidence_interval_95": [0.0, 0.0],
        }

    z = (p_variant - p_control) / se
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    se_diff = np.sqrt(
        (p_control * (1 - p_control) / control_total) +
        (p_variant * (1 - p_variant) / variant_total)
    )
    z_crit = stats.norm.ppf(1 - alpha / 2)
    ci_lower = (p_variant - p_control) - z_crit * se_diff
    ci_upper = (p_variant - p_control) + z_crit * se_diff

    if p_control > 0:
        relative_lift_pct = ((p_variant - p_control) / p_control) * 100
    else:
        relative_lift_pct = 0.0 if p_variant == 0 else float("inf")

    return {
        "control_rate": round(p_control, 6),
        "variant_rate": round(p_variant, 6),
        "absolute_lift": round(p_variant - p_control, 6),
        "relative_lift_pct": round(relative_lift_pct, 4),
        "z_score": round(z, 4),
        "p_value": round(p_value, 6),
        "confidence_interval_95": [round(ci_lower, 6), round(ci_upper, 6)],
    }


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    """Apply Benjamini-Hochberg FDR correction.

    Controls false-discovery rate across multiple comparisons.
    Returns adjusted p-values.
    """
    n = len(p_values)
    if n == 0:
        return []
    sorted_indices = np.argsort(p_values)
    sorted_p = np.array(p_values)[sorted_indices]

    # BH procedure
    adjusted = np.zeros(n)
    for i in range(n - 1, -1, -1):
        # BH critical value: (i+1)/n * q  (q=0.05 for FDR 5%)
        # Work backwards to find largest i where p[i] < (i+1)/n * alpha
        adjusted_i = sorted_p[i] * n / (i + 1)
        adjusted[sorted_indices[i]] = min(adjusted_i, 1.0)

    # Pass 2: ensure monotonicity (adjusted p-values must be non-decreasing)
    for i in range(1, n):
        idx = sorted_indices[i]
        prev_idx = sorted_indices[i - 1]
        adjusted[idx] = max(adjusted[idx], adjusted[prev_idx])

    return adjusted.tolist()


def bonferroni_warning() -> str:
    """Return warning text for when Bonferroni is manually selected."""
    return (
        "bonferroni_conservative_warning: Bonferroni correction may suppress "
        "true positives with many segments. Consider Benjamini-Hochberg (BH) "
        "which controls false-discovery rate more powerfully."
    )


def segment_decision(
    p_value: float,
    relative_lift_pct: float,
    alpha: float = 0.05,
    positive_threshold: float = 5.0,
    negative_threshold: float = -5.0,
) -> Tuple[str, str]:
    """Determine segment decision from p-value and lift.

    Returns (decision, confidence) tuple.
    Decision values: strongly_positive, positive, neutral, negative, strongly_negative
    """
    significant = p_value < alpha

    if not significant:
        if relative_lift_pct > positive_threshold:
            return "positive", "low"
        elif relative_lift_pct < negative_threshold:
            return "negative", "low"
        else:
            return "neutral", "low"

    # Significant
    if relative_lift_pct > positive_threshold:
        if relative_lift_pct > 50:
            return "strongly_positive", "high"
        else:
            return "positive", "medium"
    elif relative_lift_pct < negative_threshold:
        if relative_lift_pct < -50:
            return "strongly_negative", "high"
        else:
            return "negative", "medium"
    else:
        return "neutral", "medium"


def sample_size_warning(control_total: int, variant_total: int, threshold: int = 100) -> list:
    """Check for sample-size warnings per segment."""
    from schema import WarningDetail
    warnings = []
    if control_total < threshold:
        warnings.append(WarningDetail(
            code="LOW_TRAFFIC",
            message=f"Segment control sample ({control_total}) below recommended threshold ({threshold})",
            severity="warning"
        ))
    if variant_total < threshold:
        warnings.append(WarningDetail(
            code="LOW_TRAFFIC",
            message=f"Segment variant sample ({variant_total}) below recommended threshold ({threshold})",
            severity="warning"
        ))
    return warnings