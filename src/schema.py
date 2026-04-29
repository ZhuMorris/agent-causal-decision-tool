"""Input/Output Schema definitions for Agent Causal Decision Tool"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class ABTestInput(BaseModel):
    """A/B test input schema"""
    control_conversions: int = Field(..., description="Conversions in control group")
    control_total: int = Field(..., description="Total users in control group")
    variant_conversions: int = Field(..., description="Conversions in variant group")
    variant_total: int = Field(..., description="Total users in variant group")
    variant_name: Optional[str] = Field(default="variant_1", description="Name of variant")


class DIDInput(BaseModel):
    """Difference-in-Differences input schema"""
    pre_control: float = Field(..., description="Control group metric before treatment")
    post_control: float = Field(..., description="Control group metric after treatment")
    pre_treated: float = Field(..., description="Treated group metric before treatment")
    post_treated: float = Field(..., description="Treated group metric after treatment")


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
    code: str = Field(..., description="Warning code")
    message: str = Field(..., description="Warning message")
    severity: Literal["info", "warning", "critical"]


class TrafficStats(BaseModel):
    """Traffic/observation size summary"""
    control_size: int
    variant_size: int
    total_size: int


class ABTestOutput(BaseModel):
    """A/B test output schema"""
    version: str = "1.0"
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    mode: Literal["ab_test"] = "ab_test"
    recommendation: Recommendation
    statistics: dict = Field(..., description="Computed statistics")
    traffic_stats: TrafficStats
    warnings: list[WarningDetail] = Field(default_factory=list)
    next_steps: list[str] = Field(..., description="Suggested next steps")
    audit: dict = Field(..., description="Audit record")
    inputs: dict = Field(..., description="Original inputs for audit")


class DIDOutput(BaseModel):
    """DiD output schema"""
    version: str = "1.0"
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