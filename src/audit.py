"""Decision Audit module - reconstruct and explain decisions"""

import json
from typing import Optional, Literal
from datetime import datetime


class AuditStep:
    """Single step in the decision audit trail"""
    
    def __init__(
        self,
        step: str,
        passed: bool,
        details: dict,
        warning: Optional[str] = None,
        severity: Optional[Literal["info", "warning", "critical"]] = None
    ):
        self.step = step
        self.passed = passed
        self.details = details
        self.warning = warning
        self.severity = severity or ("info" if passed else "warning")
    
    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "passed": self.passed,
            "details": self.details,
            "warning": self.warning,
            "severity": self.severity
        }


class DecisionAudit:
    """Build audit trail for a decision"""
    
    def __init__(self, mode: str):
        self.mode = mode
        self.steps = []
        self.warnings_triggered = []
        self.limitations = []
    
    def add_step(self, step: AuditStep):
        self.steps.append(step)
        if step.warning:
            self.warnings_triggered.append({
                "code": step.step.upper().replace(" ", "_"),
                "message": step.warning,
                "severity": step.severity
            })
    
    def add_limitation(self, limitation: str):
        self.limitations.append(limitation)
    
    def build(self, inputs: dict, thresholds: dict, final_decision: dict) -> dict:
        """Build complete audit object"""
        return {
            "audit_version": "1.0",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "mode": self.mode,
            "decision_path": [s.to_dict() for s in self.steps],
            "inputs": inputs,
            "thresholds_applied": thresholds,
            "warnings_triggered": self.warnings_triggered,
            "limitations": self.limitations,
            "final_decision": final_decision
        }


def audit_ab_test(inputs: dict, result: dict) -> dict:
    """
    Build detailed audit trail for A/B test decision.
    
    Shows step-by-step how the decision was reached, including:
    - Input validation
    - Traffic checks
    - Statistical tests
    - Decision logic
    """
    audit = DecisionAudit("ab_test")
    
    # Step 1: Input validation
    c_conv = inputs.get("control_conversions", 0)
    c_total = inputs.get("control_total", 0)
    v_conv = inputs.get("variant_conversions", 0)
    v_total = inputs.get("variant_total", 0)
    
    valid = c_total > 0 and v_total > 0
    audit.add_step(AuditStep(
        step="Input validation",
        passed=valid,
        details={
            "control_conversions": c_conv,
            "control_total": c_total,
            "variant_conversions": v_conv,
            "variant_total": v_total
        },
        warning=None if valid else "Invalid input: total must be > 0"
    ))
    
    if not valid:
        audit.add_limitation("Cannot verify statistical validity with invalid inputs")
        return audit.build(inputs, {"alpha": 0.05}, {"decision": "escalate", "reason": "invalid_inputs"})
    
    # Step 2: Traffic check
    min_traffic = 1000
    low_traffic = c_total < min_traffic or v_total < min_traffic
    audit.add_step(AuditStep(
        step="Traffic check",
        passed=not low_traffic,
        details={
            "control_size": c_total,
            "variant_size": v_total,
            "min_required": min_traffic,
            "passed": not low_traffic
        },
        warning=f"Traffic low. Control: {c_total}, Variant: {v_total}" if low_traffic else None,
        severity="warning" if low_traffic else "info"
    ))
    
    if low_traffic:
        audit.add_limitation("Low traffic may result in insufficient statistical power")
    
    # Step 3: Conversion rates
    p_c = c_conv / c_total if c_total > 0 else 0
    p_v = v_conv / v_total if v_total > 0 else 0
    audit.add_step(AuditStep(
        step="Conversion rate calculation",
        passed=True,
        details={
            "control_rate": round(p_c, 6),
            "variant_rate": round(p_v, 6),
            "absolute_difference": round(p_v - p_c, 6),
            "relative_lift_pct": round((p_v - p_c) / p_c * 100, 4) if p_c > 0 else 0
        }
    ))
    
    # Step 4: Statistical test (z-test)
    p_pool = (c_conv + v_conv) / (c_total + v_total) if (c_total + v_total) > 0 else 0
    se = ((p_pool * (1 - p_pool) * (1/c_total + 1/v_total)) ** 0.5) if (c_total > 0 and v_total > 0) else 0
    z = (p_v - p_c) / se if se > 0 else 0
    p_value = 2 * (1 - _norm_cdf(abs(z)))
    
    alpha = 0.05
    significant = p_value < alpha
    
    audit.add_step(AuditStep(
        step="Statistical significance test",
        passed=significant,
        details={
            "test_type": "two-tailed z-test",
            "z_score": round(z, 4),
            "p_value": round(p_value, 6),
            "alpha": alpha,
            "significant": significant
        },
        warning=f"p-value {p_value:.4f} >= {alpha}" if not significant else None,
        severity="warning" if not significant else "info"
    ))
    
    # Step 5: Effect size check
    lift = ((p_v - p_c) / p_c * 100) if p_c > 0 else 0
    small_effect = abs(lift) < 1
    audit.add_step(AuditStep(
        step="Effect size check",
        passed=not small_effect,
        details={
            "relative_lift_pct": round(lift, 4),
            "threshold_pct": 1,
            "is_small_effect": small_effect
        },
        warning=f"Effect size {lift:.2f}% < 1% threshold" if small_effect else None,
        severity="info"
    ))
    
    if small_effect:
        audit.add_limitation("Very small effect may not be practically significant")
    
    # Step 6: Decision logic
    rec = result.get("recommendation", {})
    decision = rec.get("decision", "escalate")
    confidence = rec.get("confidence", "low")
    
    decision_reasons = {
        "ship": "p < 0.05 AND positive lift",
        "reject": "p < 0.05 AND negative lift",
        "keep_running": "p between 0.05-0.3, trending positive",
        "escalate": "Not conclusive or critical warnings"
    }
    
    audit.add_step(AuditStep(
        step="Decision",
        passed=True,
        details={
            "decision": decision,
            "confidence": confidence,
            "reason": decision_reasons.get(decision, "unknown"),
            "p_value": round(p_value, 6),
            "lift_pct": round(lift, 4)
        }
    ))
    
    # Add limitations
    audit.add_limitation("Binary conversion outcome only")
    audit.add_limitation("No multiple testing correction applied")
    audit.add_limitation("No cluster adjustment for non-randomized assignment")
    
    # Final decision summary
    final_decision = {
        "decision": decision,
        "confidence": confidence,
        "summary": rec.get("summary", ""),
        "primary_metric_lift": rec.get("primary_metricLift"),
        "p_value": round(p_value, 6)
    }
    
    return audit.build(inputs, {"alpha": alpha, "min_traffic": min_traffic}, final_decision)


def audit_did(inputs: dict, result: dict) -> dict:
    """
    Build detailed audit trail for DiD decision.
    """
    audit = DecisionAudit("did")
    
    # Step 1: Input validation
    pre_c = inputs.get("pre_control", 0)
    post_c = inputs.get("post_control", 0)
    pre_t = inputs.get("pre_treated", 0)
    post_t = inputs.get("post_treated", 0)
    
    zero_baseline = pre_c == 0 or pre_t == 0
    
    audit.add_step(AuditStep(
        step="Input validation",
        passed=not zero_baseline,
        details={
            "pre_control": pre_c,
            "post_control": post_c,
            "pre_treated": pre_t,
            "post_treated": post_t
        },
        warning="Zero baseline detected" if zero_baseline else None,
        severity="critical" if zero_baseline else "info"
    ))
    
    if zero_baseline:
        audit.add_limitation("Cannot reliably estimate DiD with zero baseline")
        return audit.build(inputs, {}, {"decision": "escalate", "reason": "zero_baseline"})
    
    # Step 2: DiD calculation
    treat_effect = post_t - pre_t
    control_change = post_c - pre_c
    did_estimate = treat_effect - control_change
    relative_did = (did_estimate / pre_t * 100) if pre_t != 0 else 0
    
    audit.add_step(AuditStep(
        step="DiD estimation",
        passed=True,
        details={
            "control_change": round(control_change, 4),
            "treatment_change": round(treat_effect, 4),
            "did_estimate": round(did_estimate, 4),
            "relative_did_pct": round(relative_did, 4)
        }
    ))
    
    # Step 3: Trend analysis
    ctrl_ratio = post_c / pre_c if pre_c > 0 else 0
    treat_ratio = post_t / pre_t if pre_t > 0 else 0
    ratio_diff = abs(ctrl_ratio - treat_ratio)
    
    trends_ok = ratio_diff <= 0.2
    audit.add_step(AuditStep(
        step="Parallel trends check",
        passed=trends_ok,
        details={
            "control_ratio_post_pre": round(ctrl_ratio, 4),
            "treatment_ratio_post_pre": round(treat_ratio, 4),
            "ratio_difference": round(ratio_diff, 4),
            "threshold": 0.2
        },
        warning=f"Trends diverge significantly ({ratio_diff:.2f} > 0.2)" if not trends_ok else None,
        severity="critical" if not trends_ok and ratio_diff > 0.5 else "warning"
    ))
    
    if not trends_ok:
        audit.add_limitation("Parallel trends assumption may not hold")
    
    # Step 4: Effect size check
    _strong_positive = relative_did > 10
    _strong_negative = relative_did < -10
    small_effect = abs(relative_did) < 5
    
    audit.add_step(AuditStep(
        step="Effect magnitude check",
        passed=not small_effect,
        details={
            "relative_did_pct": round(relative_did, 4),
            "thresholds": {"strong_positive": ">10%", "strong_negative": "<-10%", "small": "<5%"},
            "is_small": small_effect
        },
        warning=f"Effect ({relative_did:.2f}%) is small and uncertain" if small_effect else None,
        severity="info"
    ))
    
    # Step 5: Decision
    rec = result.get("recommendation", {})
    decision = rec.get("decision", "escalate")
    confidence = rec.get("confidence", "low")
    
    audit.add_step(AuditStep(
        step="Decision",
        passed=True,
        details={
            "decision": decision,
            "confidence": confidence,
            "did_estimate": round(did_estimate, 4),
            "relative_did_pct": round(relative_did, 4)
        }
    ))
    
    # Limitations
    audit.add_limitation("No standard errors from aggregate data")
    audit.add_limitation("Parallel trends not formally tested")
    audit.add_limitation("No clustered standard errors")
    audit.add_limitation("Analysis performed on aggregated data")
    
    final_decision = {
        "decision": decision,
        "confidence": confidence,
        "summary": rec.get("summary", ""),
        "primary_metric_lift": rec.get("primary_metricLift"),
        "did_estimate": round(did_estimate, 4)
    }
    
    return audit.build(inputs, {"min_significant_effect": 10}, final_decision)


def _norm_cdf(z: float) -> float:
    """Approximation of standard normal CDF"""
    import math
    # Simple approximation using error function
    return 0.5 * (1 + math.erf(z / (2 ** 0.5)))


def check_experiment_maturity(audit: dict, result: dict) -> dict:
    """
    Evaluate experiment maturity and audit readiness.
    
    Checks:
    - All decision path steps passed
    - No critical warnings
    - Limitations documented
    - Sufficient traffic
    - Decision is not speculative
    - Evidence quality score
    """
    mode = audit["mode"]
    traffic_size = audit.get("traffic_size", 0)
    decision_path = audit.get("decision_path", [])
    warnings_triggered = audit.get("warnings_triggered", [])
    limitations = audit.get("limitations", [])
    final_decision = audit.get("final_decision", {})
    
    maturity_score = 100
    maturity_issues = []
    maturity_warnings = []
    
    # 1. Check all decision steps passed
    failed_steps = [s for s in decision_path if not s["passed"]]
    if failed_steps:
        maturity_score -= 20 * len(failed_steps)
        maturity_warnings.append(f"{len(failed_steps)} decision step(s) did not pass")
    
    # 2. Check critical warnings
    critical_warnings = [w for w in warnings_triggered if w.get("severity") == "critical"]
    if critical_warnings:
        maturity_score -= 30 * len(critical_warnings)
        maturity_issues.append(f"{len(critical_warnings)} critical warning(s): " + ", ".join([w["code"] for w in critical_warnings]))
    
    # 3. Check traffic sufficiency
    min_traffic_map = {"ab_test": 1000, "bayesian_ab": 500, "did": 0, "planning": 0}
    min_traffic = min_traffic_map.get(mode, 500)
    if traffic_size < min_traffic and min_traffic > 0:
        maturity_score -= 15
        maturity_warnings.append(f"Traffic ({traffic_size}) below recommended minimum ({min_traffic}) for {mode}")
    
    # 4. Check limitations documented
    if len(limitations) < 2:
        maturity_score -= 10
        maturity_warnings.append("Limited documentation of experiment assumptions and limitations")
    
    # 5. Decision confidence check
    confidence = final_decision.get("confidence", "unknown")
    if confidence == "low":
        maturity_score -= 10
        maturity_warnings.append("Decision made with low confidence — may need human review")
    
    # 6. Information content in decision path
    if len(decision_path) < 4:
        maturity_score -= 10
        maturity_issues.append(f"Decision path has only {len(decision_path)} steps — may be under-documented")
    
    # 7. Check for unacknowledged limitations
    has_critical_assumption = any("parallel trends" in lim.lower() or "randomized" in lim.lower() for lim in limitations)
    if not has_critical_assumption and mode in ("did",):
        maturity_score -= 10
        maturity_warnings.append(f"{mode} mode but key assumptions not documented")
    
    # 8. Warning severity balance
    warning_count = len(warnings_triggered)
    critical_count = len(critical_warnings)
    if warning_count > 3 and critical_count == 0:
        maturity_score -= 5
        maturity_warnings.append(f"Multiple ({warning_count}) non-critical warnings — verify experiment health")
    
    # Clamp score
    maturity_score = max(0, maturity_score)
    
    # Maturity label
    if maturity_score >= 90:
        label = "mature"
        description = "Experiment is well-documented with full audit trail. Decision is reliable."
    elif maturity_score >= 70:
        label = "adequate"
        description = "Experiment has sufficient documentation. Review warnings before making final decision."
    elif maturity_score >= 50:
        label = "immature"
        description = "Experiment has gaps in documentation or warnings. Human review recommended."
    else:
        label = "inadequate"
        description = "Experiment has critical issues or insufficient documentation. Do not rely on decision without review."
    
    return {
        "maturity_score": maturity_score,
        "maturity_label": label,
        "description": description,
        "issues": maturity_issues,
        "warnings": maturity_warnings,
        "checks": {
            "decision_path_complete": len(failed_steps) == 0,
            "no_critical_warnings": len(critical_warnings) == 0,
            "limitations_documented": len(limitations) >= 2,
            "traffic_sufficient": traffic_size >= min_traffic if min_traffic > 0 else True,
            "high_confidence": confidence in ("high", "medium"),
            "steps_documented": len(decision_path) >= 4
        }
    }


def format_audit_text(audit: dict) -> str:
    """Format audit as human-readable text"""
    lines = [
        "=" * 60,
        "DECISION AUDIT REPORT",
        "=" * 60,
        f"Mode: {audit['mode']}",
        f"Generated: {audit['generated_at']}",
        "",
        "-- DECISION PATH --"
    ]
    
    for i, step in enumerate(audit["decision_path"]):
        status = "✓" if step["passed"] else "⚠"
        lines.append(f"{i+1}. {step['step']} [{status}]")
        for k, v in step["details"].items():
            lines.append(f"   {k}: {v}")
        if step.get("warning"):
            lines.append(f"   WARNING: {step['warning']}")
        lines.append("")
    
    if audit["warnings_triggered"]:
        lines.append("-- WARNINGS TRIGGERED --")
        for w in audit["warnings_triggered"]:
            lines.append(f"  [{w['severity'].upper()}] {w['code']}: {w['message']}")
        lines.append("")
    
    if audit["limitations"]:
        lines.append("-- LIMITATIONS --")
        for lim in audit["limitations"]:
            lines.append(f"  - {lim}")
        lines.append("")
    
    fd = audit["final_decision"]
    lines.append("-- FINAL DECISION --")
    lines.append(f"  Decision: {fd['decision'].upper()}")
    lines.append(f"  Confidence: {fd['confidence']}")
    lines.append(f"  Summary: {fd['summary']}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Demo
    import sys
    data = json.load(sys.stdin)
    mode = data.get("mode", "ab_test")
    result = data
    
    if mode == "ab_test":
        audit = audit_ab_test(data.get("inputs", {}), data)
    else:
        audit = audit_did(data.get("inputs", {}), data)
    
    print(format_audit_text(audit))