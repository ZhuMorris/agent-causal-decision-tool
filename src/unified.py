"""Unified Agent-facing output schema — wraps all method outputs into a consistent shape.

The AgentDecisionOutput overlay adds the Phase IV unified fields on top of the existing
Pydantic outputs (ABTestOutput, DIDOutput, PlanningOutput, BayesOutput) without modifying
those models. This preserves backward compatibility while providing a consistent
interface for agent workflows.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Any, Literal
from datetime import datetime


class UnifiedWarning(BaseModel):
    """Unified warning block matching the PRD contract."""
    code: str = Field(..., description="Warning code string")
    message: str = Field(..., description="Human-readable warning message")
    severity: str = Field(..., description="info | warning | critical")

    model_config = ConfigDict(extra="forbid")


class AgentDecisionOutput(BaseModel):
    """Unified agent-facing decision output.

    Maps all internal output types (ABTestOutput, DIDOutput, PlanningOutput,
    BayesOutput) into this shape so agents get a consistent interface.
    """
    schema_version: str = Field(
        default="0.9.0",
        description="Schema contract version"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z",
        description="ISO 8601 timestamp of when the decision was computed"
    )
    # Core decision fields (from PRD unified schema)
    decision: Literal["ship", "keep_running", "reject", "escalate"] = Field(..., description="Recommended action")
    recommended_next_action: str = Field(
        ...,
        description="Plain-language next action for the agent"
    )
    selected_method: str = Field(
        ...,
        description="Which decision method was used (e.g. ab_test, bayesian_ab, did, planning)"
    )
    selection_reason: str = Field(
        ...,
        description="Why this method was selected"
    )
    confidence: Literal["high", "medium", "low"] = Field(..., description="Confidence level")
    effect_summary: str = Field(
        ...,
        description="One-line description of the estimated effect"
    )
    warnings: list[UnifiedWarning] = Field(
        default_factory=list,
        description="Warnings that affect the decision"
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Known limitations of this analysis"
    )
    audit_summary: str = Field(
        ...,
        description="Short audit description of how the decision was reached"
    )
    source_metadata: Optional[dict] = Field(
        default=None,
        description="Metadata about the source of the data (connector name, dataset_id, etc.)"
    )
    # Full structured result for tooling (not exposed to lightweight agents)
    internal_result: Optional[dict] = Field(
        default=None,
        description="Full internal output (ABTestOutput/DIDOutput/etc as dict). "
                    "Agents should use the unified fields above. "
                    "This field is prefixed with 'internal_' to signal it is for tooling, not agents."
    )

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )


def _decision_from_recommendation(rec: Any) -> str:
    """Extract decision string from any Recommendation-like object."""
    if hasattr(rec, "decision"):
        return rec.decision
    if isinstance(rec, dict):
        return rec.get("decision", "escalate")
    return "escalate"


def _confidence_from_recommendation(rec: Any) -> str:
    """Extract confidence from any Recommendation-like object."""
    if hasattr(rec, "confidence"):
        return rec.confidence
    if isinstance(rec, dict):
        return rec.get("confidence", "low")
    return "low"


def _lift_summary(rec: Any, stats: Any) -> str:
    """Build effect_summary string."""
    lift = None
    if hasattr(rec, "primary_metricLift") and rec.primary_metricLift is not None:
        lift = rec.primary_metricLift
    elif isinstance(rec, dict) and rec.get("primary_metricLift") is not None:
        lift = rec["primary_metricLift"]

    p_val = None
    if hasattr(rec, "p_value") and rec.p_value is not None:
        p_val = rec.p_value
    elif isinstance(rec, dict) and rec.get("p_value") is not None:
        p_val = rec["p_value"]

    if lift is not None:
        direction = "positive" if lift >= 0 else "negative"
        return f"Estimated lift: {lift:+.2f}% ({direction})"
    if p_val is not None:
        return f"p-value: {p_val:.4f}"
    return "Effect size unknown"


def _warnings_from_result(result: Any) -> list[UnifiedWarning]:
    """Extract unified warnings from any result object."""
    warnings = []
    if hasattr(result, "warnings"):
        raw = result.warnings
    elif isinstance(result, dict) and "warnings" in result:
        raw = result["warnings"]
    else:
        return []

    for w in raw:
        if hasattr(w, "code"):
            code = w.code.value if hasattr(w.code, "value") else str(w.code)
            message = w.message
            severity = w.severity
        elif isinstance(w, dict):
            code = w.get("code", "")
            code = code.value if hasattr(code, "value") else str(code)
            message = w.get("message", "")
            severity = w.get("severity", "warning")
        else:
            continue
        warnings.append(UnifiedWarning(code=code, message=message, severity=severity))
    return warnings


def _limitations_from_audit(audit: Any) -> list[str]:
    """Extract limitations from audit block."""
    if audit is None:
        return []
    if hasattr(audit, "limitations"):
        return audit.limitations
    if isinstance(audit, dict):
        return audit.get("limitations", [])
    return []


def _audit_summary_from_audit(audit: Any, mode: str) -> str:
    """Build audit_summary string."""
    if audit is None:
        return f"{mode} analysis complete"
    if hasattr(audit, "decision_path"):
        steps = audit.decision_path
        if isinstance(steps, list) and steps:
            last_step = steps[-1].get("step", steps[-1].get("action", "")) if isinstance(steps[-1], dict) else ""
            return f"{mode}: {last_step}"
    if isinstance(audit, dict):
        dp = audit.get("decision_path", [])
        if dp and isinstance(dp[-1], dict):
            return f"{mode}: {dp[-1].get('step', '')}"
    return f"{mode} analysis complete"


def _next_action_for_decision(decision: str, method: str) -> str:
    """Map decision + method to recommended_next_action."""
    action_map = {
        "ship": {
            "ab_test": "Deploy variant — statistical significance achieved with positive lift.",
            "bayesian_ab": "Deploy variant — P(better) ≥ 0.95 threshold met.",
            "did": "Deploy rollout — DiD estimate is positive and assumptions hold.",
            "planning": "Run the experiment as planned.",
        },
        "reject": {
            "ab_test": "Do not deploy — statistical significance with negative lift.",
            "bayesian_ab": "Do not deploy — P(better) ≤ 0.05 threshold met.",
            "did": "Do not deploy — DiD estimate is negative or assumptions violated.",
            "planning": "Revise experiment design before running.",
        },
        "keep_running": {
            "ab_test": "Continue the experiment — results are inconclusive so far.",
            "bayesian_ab": "Continue the experiment — probability thresholds not yet met.",
            "did": "Continue collecting data — DiD estimate is uncertain.",
            "planning": "Increase traffic or adjust MDE before running.",
        },
        "escalate": {
            "ab_test": "Request human review — evidence is insufficient or assumptions are violated.",
            "bayesian_ab": "Request human review — uncertainty is too high.",
            "did": "Request human review — DiD assumptions are fragile or violated.",
            "planning": "Consult a statistician — experiment design needs review.",
        },
    }
    return action_map.get(decision, {}).get(
        method,
        f"Action for decision={decision}, method={method} needs review."
    )


def to_unified(result: Any, method: str, selection_reason: str, source_metadata: Optional[dict] = None) -> AgentDecisionOutput:
    """Convert any internal output (ABTestOutput, DIDOutput, BayesOutput, PlanningOutput) to AgentDecisionOutput.

    Args:
        result: Any of ABTestOutput, DIDOutput, BayesOutput, PlanningOutput (or raw dict)
        method: One of ab_test, bayesian_ab, did, planning, cohort_breakdown
        selection_reason: Why this method was selected
        source_metadata: Optional metadata about the data source (connector name, dataset_id, etc.)
    """
    # Extract recommendation
    rec = result.recommendation if hasattr(result, "recommendation") else (result.get("recommendation") if isinstance(result, dict) else None)
    if rec is None:
        rec = {"decision": "escalate", "confidence": "low", "summary": "No recommendation available"}

    decision = _decision_from_recommendation(rec)
    confidence = _confidence_from_recommendation(rec)

    # Extract audit
    audit = result.audit if hasattr(result, "audit") else (result.get("audit") if isinstance(result, dict) else None)

    # Extract statistics for effect summary
    stats = result.statistics if hasattr(result, "statistics") else (result.get("statistics") if isinstance(result, dict) else None)

    return AgentDecisionOutput(
        decision=decision,
        recommended_next_action=_next_action_for_decision(decision, method),
        selected_method=method,
        selection_reason=selection_reason,
        confidence=confidence,
        effect_summary=_lift_summary(rec, stats),
        warnings=_warnings_from_result(result),
        limitations=_limitations_from_audit(audit),
        audit_summary=_audit_summary_from_audit(audit, method),
        source_metadata=source_metadata,
        internal_result=result.model_dump() if hasattr(result, "model_dump") else (result if isinstance(result, dict) else None),
    )