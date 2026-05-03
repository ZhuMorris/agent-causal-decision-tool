"""Cohort/segment-level experiment analysis for Agent Causal.

Applies per-segment two-proportion z-tests with Benjamini-Hochberg correction
for 4+ segments. Links to prior ab_compare or did_estimate results for full
audit chain traceability.
"""
from datetime import datetime
from typing import Optional

from .utils.stats import (
    two_proportion_z_test,
    benjamini_hochberg,
    segment_decision,
    sample_size_warning,
)


def cohort_breakdown(input_data: dict) -> dict:
    """Run cohort/segment-level experiment analysis.

    Accepts pre-computed segment data with conversion counts per arm.
    Links to a prior ab_compare or did_estimate result when available.

    Args:
        input_data: JSON dict with experiment_id, metric, segments, and
                    optional prior_result_id / prior_decision / prior_mode.

    Returns:
        dict with method, segments, priority_ranking, summary,
        recommended_next_action, warnings, interaction_flag, and audit.
    """
    # Parse
    experiment_id = input_data.get("experiment_id", "unknown")
    metric = input_data.get("metric", "conversion_rate")
    segments_in = input_data.get("segments", [])
    prior_result_id = input_data.get("prior_result_id")
    prior_decision = input_data.get("prior_decision")
    prior_mode = input_data.get("prior_mode", "ab_test")
    multiple_comparison_method = input_data.get(
        "multiple_comparison_method", "benjamini_hochberg"
    )
    confidence_level = input_data.get("confidence_level", 0.95)
    min_sample_per_segment = input_data.get("min_sample_per_segment", 100)
    alpha = 1 - confidence_level

    if not segments_in:
        raise ValueError("At least one segment is required")

    # Validate required fields
    if not experiment_id or experiment_id == "unknown":
        raise ValueError("experiment_id is required for audit traceability")
    if not metric:
        raise ValueError("metric is required to label what is being measured")

    # ── Per-segment stats ────────────────────────────────────────────────────
    segments_out = []
    p_values_raw = []
    all_warnings = []

    for seg in segments_in:
        c_conv = seg["control_conversions"]
        c_total = seg["control_total"]
        v_conv = seg["variant_conversions"]
        v_total = seg["variant_total"]

        stats_result = two_proportion_z_test(
            c_conv, c_total, v_conv, v_total, alpha=alpha
        )

        # Sample size warning (deserialize Pydantic objects to dicts for JSON output)
        seg_warnings = [
            {"code": w.code, "message": w.message, "severity": w.severity}
            for w in sample_size_warning(c_total, v_total, min_sample_per_segment)
        ]

        # Segment decision
        decision, _ = segment_decision(
            p_value=stats_result["p_value"],
            relative_lift_pct=stats_result["relative_lift_pct"],
            alpha=alpha,
        )

        p_values_raw.append(stats_result["p_value"])

        segments_out.append({
            "segment_name": seg.get("segment_name", "unknown"),
            "segment_definition_note": seg.get("segment_definition_note"),
            "control_rate": stats_result["control_rate"],
            "variant_rate": stats_result["variant_rate"],
            "absolute_lift": stats_result["absolute_lift"],
            "relative_lift_pct": stats_result["relative_lift_pct"],
            "p_value_raw": stats_result["p_value"],
            "p_value_adjusted": stats_result["p_value"],  # may be updated below
            "confidence_interval_95": stats_result["confidence_interval_95"],
            "decision": decision,
            "warnings": seg_warnings,
            "priority_rank": 0,
        })
        all_warnings.extend(seg_warnings)

    n_segs = len(segments_out)

    # ── Multiple-comparison correction ───────────────────────────────────────
    if n_segs >= 4 and multiple_comparison_method == "benjamini_hochberg":
        p_adjusted = benjamini_hochberg(p_values_raw)
        correction_method = "benjamini_hochberg"
        for i, seg in enumerate(segments_out):
            seg["p_value_adjusted"] = p_adjusted[i]
            # Update decision if adjusted p fails
            if p_adjusted[i] >= alpha and seg["decision"] in (
                "strongly_positive", "positive", "strongly_negative", "negative"
            ):
                seg["decision"] = "neutral"
                seg["warnings"] = seg.get("warnings", [])
                if "multiple_comparison_adjusted" not in [w["code"] for w in seg["warnings"]]:
                    seg["warnings"].append({"code": "multiple_comparison_adjusted", "message": "BH correction removed significance", "severity": "warning"})
    elif n_segs >= 5 and multiple_comparison_method == "bonferroni":
        p_adjusted = [p * n_segs for p in p_values_raw]
        correction_method = "bonferroni"
        all_warnings.append(
            {"code": "bonferroni_conservative_warning",
             "message": "Bonferroni correction may suppress true positives with many segments",
             "severity": "warning"}
        )
        for i, seg in enumerate(segments_out):
            seg["p_value_adjusted"] = min(p_adjusted[i], 1.0)
            if p_adjusted[i] >= alpha and seg["decision"] in (
                "strongly_positive", "positive", "strongly_negative", "negative"
            ):
                seg["decision"] = "neutral"
                seg["warnings"] = seg.get("warnings", [])
                if "multiple_comparison_adjusted" not in [w["code"] for w in seg["warnings"]]:
                    seg["warnings"].append({"code": "multiple_comparison_adjusted", "message": "Bonferroni correction removed significance", "severity": "warning"})
    else:
        correction_method = "none" if n_segs <= 3 else "benjamini_hochberg"
        for seg in segments_out:
            seg["p_value_adjusted"] = seg["p_value_raw"]

    # ── Interaction flag — opposing strongly significant directions ───────────
    interaction_flag = _check_interaction(segments_out)

    # ── Priority ranking ──────────────────────────────────────────────────────
    ranked = sorted(
        segments_out,
        key=lambda s: abs(s["relative_lift_pct"]) if s["decision"] != "neutral" else 0,
        reverse=True,
    )
    for rank, seg in enumerate(ranked, start=1):
        seg["priority_rank"] = rank

    priority_ranking = [
        {
            "rank": r["priority_rank"],
            "segment": r["segment_name"],
            "rationale": _build_rationale(r),
        }
        for r in ranked
    ]

    # ── Cohort decision override ─────────────────────────────────────────────
    cohort_decision_override = False
    cohort_override_reason = None

    for seg in segments_out:
        if seg["decision"] == "strongly_positive" and prior_decision in ("wait", "escalate", "keep_running", "reject"):
            cohort_decision_override = True
            cohort_override_reason = (
                f"Strong positive signal in '{seg['segment_name']}' "
                f"(lift={seg['relative_lift_pct']:.1f}%, adj-p={seg['p_value_adjusted']:.4f}) "
                f"contradicts aggregate decision '{prior_decision}'"
            )
            break
        elif seg["decision"] == "strongly_negative" and prior_decision in ("ship", "wait"):
            cohort_decision_override = True
            cohort_override_reason = (
                f"Strong negative signal in '{seg['segment_name']}' "
                f"(lift={seg['relative_lift_pct']:.1f}%) "
                f"contradicts aggregate decision '{prior_decision}'"
            )
            break

    # ── Summary & recommended action ───────────────────────────────────────
    positive = [s for s in segments_out if s["decision"] in ("strongly_positive", "positive")]
    negative = [s for s in segments_out if s["decision"] in ("strongly_negative", "negative")]

    if positive and not negative:
        seg_summary = f"{len(positive)} segment(s) positive"
    elif negative and not positive:
        seg_summary = f"{len(negative)} segment(s) negative"
    elif positive and negative:
        seg_summary = f"Mixed: {len(positive)} positive, {len(negative)} negative"
    else:
        seg_summary = "No significant segment effects detected"

    top_seg = ranked[0] if ranked else None
    if top_seg and top_seg["decision"] != "neutral":
        summary = f"{top_seg['segment_name']} drives the effect. {seg_summary}."
    else:
        summary = f"{seg_summary}."

    recommended_next_action = _recommend_action(
        prior_decision, cohort_decision_override, segments_out
    )

    # ── Warnings ─────────────────────────────────────────────────────────────
    if n_segs >= 4:
        all_warnings.append({
            "code": "multiple_comparisons",
            "message": f"{n_segs} segments tested, correction={correction_method}",
            "severity": "info"
        })
    if n_segs > 0 and alpha / n_segs < 0.01:
        all_warnings.append({
            "code": "CORRECTION_CONSERVATIVE",
            "message": (
                f"Effective per-test alpha after correction ({alpha/n_segs:.4f}) is below 0.01 "
                f"with {n_segs} segments — correction is very conservative; true positives may be suppressed."
            ),
            "severity": "warning"
        })
    if interaction_flag:
        all_warnings.append({
            "code": "interaction_flag",
            "message": "Segments show opposing directions — possible interaction effect",
            "severity": "warning"
        })

    # ── Audit ─────────────────────────────────────────────────────────────────
    segment_def_notes_present = all(
        s.get("segment_definition_note") for s in segments_out
    )

    return {
        "method": "experiment_cohort_breakdown",
        "version": "1.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "experiment_id": experiment_id,
        "metric": metric,
        "prior_result_id": prior_result_id,
        "prior_decision": prior_decision,
        "prior_mode": prior_mode,
        "cohort_decision_override": cohort_decision_override,
        "cohort_override_reason": cohort_override_reason,
        "interaction_flag": interaction_flag,
        "segments": segments_out,
        "priority_ranking": priority_ranking,
        "summary": summary,
        "recommended_next_action": recommended_next_action,
        "warnings": all_warnings,
        "audit": {
            "confidence_level": confidence_level,
            "test_type": "two_proportion_z_test",
            "multiple_comparison_method": correction_method,
            "total_segments_compared": n_segs,
            "prior_result_id": prior_result_id,
            "segment_definition_notes_present": segment_def_notes_present,
            "min_sample_per_segment": min_sample_per_segment,
        },
    }


def _check_interaction(segments: list) -> bool:
    """Check if segments show opposing strongly-significant directions."""
    pos = any(
        s["decision"] == "strongly_positive" for s in segments
    )
    neg = any(
        s["decision"] == "strongly_negative" for s in segments
    )
    return pos and neg


def _build_rationale(seg: dict) -> str:
    """Build one-line rationale for a segment."""
    d = seg["decision"]
    lift = seg["relative_lift_pct"]
    p_raw = seg["p_value_raw"]
    p_adj = seg["p_value_adjusted"]

    if d == "strongly_positive":
        return f"Strong positive effect (lift={lift:.1f}%, adj-p={p_adj:.4f}). Highest priority."
    elif d == "positive":
        return f"Positive effect (lift={lift:.1f}%, adj-p={p_adj:.4f}). Priority candidate."
    elif d == "neutral":
        return f"No meaningful effect (raw-p={p_raw:.4f}). Deprioritize for this variant."
    elif d == "negative":
        return f"Negative effect (lift={lift:.1f}%). Avoid targeting this segment."
    elif d == "strongly_negative":
        return f"Strong negative effect (lift={lift:.1f}%, adj-p={p_adj:.4f}). Do not target."
    return "Unable to determine priority."


def _recommend_action(prior_decision: Optional[str], override: bool, segments: list) -> str:
    """Determine recommended next action based on segment results."""
    if override:
        top = segments[0]
        if top["decision"] == "strongly_positive":
            return "targeted_rollout"
        elif top["decision"] == "strongly_negative":
            return "abandon_segment"

    positive = [s for s in segments if s["decision"] in ("strongly_positive", "positive")]
    negative = [s for s in segments if s["decision"] in ("strongly_negative", "negative")]

    if len(positive) == len(segments) and len(positive) > 0:
        return "full_rollout"
    elif len(negative) == len(segments) and len(negative) > 0:
        return "confirm_rejection"
    elif len(positive) > 0 and len(negative) == 0:
        return "targeted_rollout"
    elif len(negative) > 0:
        return "review_negative_segments"
    else:
        return "continue_monitoring"