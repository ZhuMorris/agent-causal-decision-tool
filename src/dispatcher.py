"""Easy-mode decision dispatcher — auto-selects the right method from input fields.

This is the "I don't know which method I need" entry point. It inspects the
incoming data and routes to the appropriate internal function.
"""

from __future__ import annotations

from typing import Any

from .ab_test import calculate_ab
from .bayes import calculate_bayes_ab
from .did import calculate_did
from .planning import calculate_plan
from .unified import to_unified, AgentDecisionOutput


# ─── Detection heuristics ────────────────────────────────────────────────────

_DID_FIELDS = {"pre_control", "post_control", "pre_treated", "post_treated"}
_PLANNING_FIELDS = {"baseline_conversion_rate", "mde_pct"}
_AB_FIELDS = {"control_conversions", "control_total", "variant_conversions", "variant_total"}


def _detect_method(data: dict) -> str:
    """Detect which method to use based on present fields.

    Returns: "did" | "planning" | "ab" | "bayesian" | "cohort" | "unknown"
    """
    keys = set(data.keys())

    # DiD: pre/post control + pre/post treated
    if _DID_FIELDS.issubset(keys):
        return "did"

    # Planning: baseline conversion rate + MDE
    if _PLANNING_FIELDS.issubset(keys):
        return "planning"

    # Cohort: segment or breakdown field
    if "segments" in keys or "breakdown" in keys:
        return "cohort"

    # Bayesian: explicit flag
    if data.get("bayesian"):
        return "bayesian"

    # A/B: control/variant conversions + totals
    if _AB_FIELDS.issubset(keys):
        return "ab"

    return "unknown"


def run_decision_workflow(data: dict, samples: int = 20000) -> AgentDecisionOutput:
    """Auto-detect method and run the appropriate decision.

    Args:
        data: Input fields. Detection logic:
              - DiD fields (pre_control, post_control, pre_treated, post_treated) → DiD
              - bayesian=true → Bayesian A/B
              - baseline_conversion_rate + mde_pct → Planning
              - segments/breakdown → Cohort
              - control_conversions + variant_conversions + totals → Frequentist A/B
        samples: Monte Carlo samples for Bayesian (default 20000)

    Returns:
        AgentDecisionOutput — unified schema output

    Raises:
        ValueError: When input doesn't match any known method
    """
    method = _detect_method(data)

    if method == "did":
        return _run_did_workflow(data)
    if method == "planning":
        return _run_plan_workflow(data)
    if method == "cohort":
        return _run_cohort_workflow(data)
    if method == "bayesian":
        return _run_bayes_workflow(data, samples)
    if method == "ab":
        return _run_ab_workflow(data)
    raise ValueError(
        f"Cannot determine method from input fields. "
        f"Supported: A/B test (control_conversions, control_total, variant_conversions, variant_total), "
        f"DiD (pre_control, post_control, pre_treated, post_treated), "
        f"Planning (baseline_conversion_rate, mde_pct), "
        f"Cohort (segments or breakdown). "
        f"Got keys: {sorted(data.keys())}"
    )


# ─── Internal runners ────────────────────────────────────────────────────────

def _run_ab_workflow(data: dict) -> AgentDecisionOutput:
    """Frequentist A/B test via dispatcher."""
    # Strip internal/auto-detection keys before passing to ab_test
    ab_data = {k: v for k, v in data.items()
               if k not in ("bayesian", "mode", "samples", "action", "request_id")}
    result = calculate_ab(ab_data)
    return to_unified(result, "ab_test", "Auto-selected frequentist A/B test via decide workflow")


def _run_bayes_workflow(data: dict, samples: int) -> AgentDecisionOutput:
    """Bayesian A/B test via dispatcher."""
    ab_data = {k: v for k, v in data.items()
               if k not in ("bayesian", "mode", "samples", "action", "request_id")}
    result = calculate_bayes_ab(ab_data, n_samples=samples)
    return to_unified(result, "bayesian_ab", "Auto-selected Bayesian A/B test via decide workflow")


def _run_did_workflow(data: dict) -> AgentDecisionOutput:
    """DiD via dispatcher."""
    did_data = {k: v for k, v in data.items()
                if k not in ("bayesian", "mode", "samples", "action", "request_id")}
    result = calculate_did(did_data)
    return to_unified(result, "did", "Auto-selected DiD (Difference-in-Differences) via decide workflow")


def _run_plan_workflow(data: dict) -> AgentDecisionOutput:
    """Experiment planning via dispatcher."""
    plan_data = {k: v for k, v in data.items()
                 if k not in ("bayesian", "mode", "samples", "action", "request_id")}
    result = calculate_plan(plan_data)
    return to_unified(result, "planning", "Auto-selected experiment planning via decide workflow")


def _run_cohort_workflow(data: dict) -> AgentDecisionOutput:
    """Cohort analysis via dispatcher."""
    # Import here to avoid circular dependency at module load time
    from .cohort import calculate_cohort_breakdown
    cohort_data = {k: v for k, v in data.items()
                   if k not in ("bayesian", "mode", "samples", "action", "request_id")}
    result = calculate_cohort_breakdown(cohort_data)
    return to_unified(result, "cohort", "Auto-selected cohort analysis via decide workflow")