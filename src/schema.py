"""Input/Output Schema definitions for Agent Causal Decision Tool"""

from importlib.metadata import version as _pkg_version

from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class WarningCode(str, Enum):
    """Canonical warning codes for all analysis modules."""
    # A/B Test
    LOW_TRAFFIC = "LOW_TRAFFIC"
    SMALL_EFFECT = "SMALL_EFFECT"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_SIGNIFICANT = "NOT_SIGNIFICANT"
    BORDERLINE_P_VALUE = "BORDERLINE_P_VALUE"
    CORRECTION_CONSERVATIVE = "CORRECTION_CONSERVATIVE"
    SEQUENTIAL_EARLY_STOP = "SEQUENTIAL_EARLY_STOP"
    SEQUENTIAL_CONDITIONS_NOT_MET = "SEQUENTIAL_CONDITIONS_NOT_MET"
    MAX_RUNTIME_EXCEEDED = "MAX_RUNTIME_EXCEEDED"
    # DiD
    ZERO_BASELINE = "ZERO_BASELINE"
    PARALLEL_TRENDS_VIOLATED = "PARALLEL_TRENDS_VIOLATED"
    PARALLEL_TRENDS_WEAK = "PARALLEL_TRENDS_WEAK"
    BOTH_GROUPS_GREW = "BOTH_GROUPS_GREW"
    AGGREGATE_DATA = "AGGREGATE_DATA"
    AGGREGATE_DATA_DID = "AGGREGATE_DATA_DID"
    SINGLE_PRE_PERIOD = "SINGLE_PRE_PERIOD"
    SMALL_SAMPLE = "SMALL_SAMPLE"
    IMBALANCED_GROUPS = "IMBALANCED_GROUPS"
    LARGE_EFFECT_SMALL_SAMPLE = "LARGE_EFFECT_SMALL_SAMPLE"
    PARALLEL_TRENDS_NO_DATA = "PARALLEL_TRENDS_NO_DATA"
    BOOTSTRAP_CI_UNRELIABLE = "BOOTSTRAP_CI_UNRELIABLE"
    BOOTSTRAP_CI_WIDE = "BOOTSTRAP_CI_WIDE"
    # Planning
    SLOW_EXPERIMENT = "SLOW_EXPERIMENT"
    INFEASIBLE_EXPERIMENT = "INFEASIBLE_EXPERIMENT"
    SMALL_MDE = "SMALL_MDE"
    BASELINE_VERY_LOW = "BASELINE_VERY_LOW"
    # Bayesian
    PRIOR_DOMINATES = "PRIOR_DOMINATES"
    CREDIBLE_INTERVAL_WIDE = "CREDIBLE_INTERVAL_WIDE"
    # Q6 / Q16 additions
    DID_CI_CROSSES_ZERO = "DID_CI_CROSSES_ZERO"
    BASELINE_NEAR_ZERO = "BASELINE_NEAR_ZERO"


class ABTestInput(BaseModel):
    """A/B test input schema"""
    control_conversions: int = Field(..., description="Conversions in control group")
    control_total: int = Field(..., description="Total users in control group")
    variant_conversions: int = Field(..., description="Conversions in variant group")
    variant_total: int = Field(..., description="Total users in variant group")
    variant_name: Optional[str] = Field(default="variant_1", description="Name of variant")
    # Sequential / early stopping settings
    sequential_enabled: bool = Field(default=False, description="Enable sequential early stopping logic")
    experiment_start_time: Optional[str] = Field(default=None, description="ISO 8601 start timestamp")
    experiment_end_time: Optional[str] = Field(default=None, description="ISO 8601 end timestamp")
    min_runtime_days: int = Field(default=7, description="Minimum days before early stop is considered")
    min_sample_per_arm: int = Field(default=2000, description="Minimum sample per arm before early stop is considered")
    early_stop_p_threshold: float = Field(default=0.01, description="p-value threshold for early stop (conservative)")
    max_runtime_days: Optional[int] = Field(default=None, description="Hard cap on runtime; escalate if exceeded without strong result")
    # Override for practical significance threshold
    practical_significance_threshold: float = Field(default=0.01, description="Practical significance threshold for lift")


class DIDInput(BaseModel):
    """Difference-in-Differences input schema"""
    pre_control: float = Field(..., description="Control group metric before treatment")
    post_control: float = Field(..., description="Control group metric after treatment")
    pre_treated: float = Field(..., description="Treated group metric before treatment")
    post_treated: float = Field(..., description="Treated group metric after treatment")
    # Bootstrap CI settings
    n_bootstrap: int = Field(default=2000, ge=500, le=10000, description="Number of bootstrap resamples for DiD CI (500–10000)")
    # DiD diagnostics metadata
    pre_periods: Optional[int] = Field(default=None, description="Number of pre-period observations (e.g. days/weeks)")
    post_periods: Optional[int] = Field(default=None, description="Number of post-period observations")
    treatment_observation_count: Optional[int] = Field(default=None, description="Total underlying observations for treatment")
    control_observation_count: Optional[int] = Field(default=None, description="Total underlying observations for control")
    notes: Optional[str] = Field(default=None, description="Context string passed through to audit only")


class Recommendation(BaseModel):
    """Decision recommendation output"""
    decision: Literal["ship", "keep_running", "reject", "escalate"] = Field(
        ...,
        description="Recommended action"
    )
    confidence: Literal["high", "medium", "low"] = Field(..., description="Confidence level")
    summary: str = Field(..., description="Human-readable summary")
    primary_metricLift: Optional[float] = Field(default=None, description="Estimated lift percentage")
    p_value: Optional[float] = Field(default=None, description="P-value if applicable")
    warning: Optional[str] = Field(default=None, description="Warning if evidence is weak")


class WarningDetail(BaseModel):
    """Warning detail"""
    code: WarningCode = Field(..., description="Warning code")
    message: str = Field(..., description="Warning message")
    severity: Literal["info", "warning", "critical"]


class TrafficStats(BaseModel):
    """Traffic/observation size summary"""
    control_size: int
    variant_size: int
    total_size: int


# ─── Sequential Early Stopping ────────────────────────────────────────────────

class SequentialSummary(BaseModel):
    """Summary of sequential early stopping evaluation"""
    min_runtime_days: int
    observed_runtime_days: Optional[float] = None
    min_sample_per_arm: int
    observed_sample_per_arm: int
    early_stop_p_threshold: float
    max_runtime_days: Optional[int] = None
    reason: Literal["conditions_not_met", "p_below_threshold", "max_runtime_exceeded", "no_early_stop"]


class ABTestOutput(BaseModel):
    """A/B test output schema"""
    schema_version: str = Field(default_factory=lambda: _pkg_version("agent-causal-decision-tool"), description="Schema contract version for this output")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    mode: Literal["ab_test"] = "ab_test"
    recommendation: Recommendation
    statistics: dict = Field(..., description="Computed statistics")
    traffic_stats: TrafficStats
    warnings: list[WarningDetail] = Field(default_factory=list)
    next_steps: list[str] = Field(..., description="Suggested next steps")
    next_analysis_suggestion: Optional[dict] = Field(default=None, description="Suggested next analysis command if result is inconclusive")
    audit: dict = Field(..., description="Audit record")
    inputs: dict = Field(..., description="Original inputs for audit")
    # Sequential early stopping fields
    sequential_reviewed: bool = Field(default=False, description="Whether sequential logic was evaluated")
    early_stop_applied: bool = Field(default=False, description="Whether early stop was triggered")
    sequential_summary: Optional[SequentialSummary] = Field(default=None, description="Sequential evaluation details")


class PlanningInput(BaseModel):
    """Experiment planning input schema"""
    baseline_conversion_rate: float = Field(..., description="Baseline conversion rate (0-1)")
    mde_pct: float = Field(..., description="Minimum detectable effect as percentage (e.g., 5 for 5% lift)")
    daily_traffic: int = Field(default=1000, description="Daily traffic per arm (used for mde_ci_95 calculation)")
    confidence_level: float = Field(default=0.95, description="Confidence level")
    power: float = Field(default=0.8, description="Statistical power")
    allocation: Literal["equal", "custom"] = Field(default="equal")
    allocation_ratio: Optional[str] = Field(default=None, description="e.g. 0.5/0.5")


class PlanningOutput(BaseModel):
    """Experiment planning output schema"""
    schema_version: str = Field(default_factory=lambda: _pkg_version("agent-causal-decision-tool"), description="Schema contract version for this output")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    mode: Literal["planning"] = "planning"
    recommendation: Recommendation
    planning: dict = Field(..., description="Planning computed values")
    warnings: list[WarningDetail] = Field(default_factory=list)
    inputs: dict


# ─── DiD Diagnostics ─────────────────────────────────────────────────────────

class DIDDiagnostics(BaseModel):
    """DiD setup quality and fragility diagnostics"""
    pre_periods: Optional[int] = None
    post_periods: Optional[int] = None
    treatment_observation_count: Optional[int] = None
    control_observation_count: Optional[int] = None
    parallel_trends_evidence: Literal["none", "weak", "moderate", "strong"] = "none"
    fragility_flags: list[str] = Field(default_factory=list)
    recommended_caution_level: Literal["low", "medium", "high"] = "low"


class DIDOutput(BaseModel):
    """DiD output schema"""
    schema_version: str = Field(default_factory=lambda: _pkg_version("agent-causal-decision-tool"), description="Schema contract version for this output")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    mode: Literal["did"] = "did"
    recommendation: Recommendation
    statistics: dict = Field(..., description="Computed DiD statistics")
    traffic_stats: dict = Field(..., description="Observation size info")
    warnings: list[WarningDetail] = Field(default_factory=list)
    next_steps: list[str] = Field(..., description="Suggested next steps")
    audit: dict = Field(..., description="Audit record")
    inputs: dict = Field(..., description="Original inputs for audit")
    assumptions: list[str] = Field(..., description="DiD assumptions that must hold")
    # DiD diagnostics
    did_diagnostics: Optional[DIDDiagnostics] = Field(default=None, description="DiD setup quality diagnostics")
    recommended_next_action: Optional[str] = Field(default=None, description="Suggested next action based on diagnostics")
    explanation: Optional[str] = Field(default=None, description="Plain-language explanation of result and caution level")
    next_analysis_suggestion: Optional[dict] = Field(default=None, description="Suggested next analysis to run when result is inconclusive or caution is high")
