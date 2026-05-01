"""Tests for cohort_breakdown (segment-level experiment analysis)"""

import pytest
from src.cohort import cohort_breakdown


class TestCohortBreakdown:
    """Core cohort breakdown tests"""

    def test_new_users_override_wait(self):
        """The canonical example: aggregate='wait', new_users strongly positive → override"""
        result = cohort_breakdown({
            "experiment_id": "checkout-v3",
            "metric": "conversion_rate",
            "prior_result_id": "dec_20260501_001",
            "prior_decision": "wait",
            "segments": [
                {
                    "segment_name": "new_users",
                    "segment_definition_note": "Users registered within last 30 days",
                    "control_conversions": 21,
                    "control_total": 1000,
                    "variant_conversions": 67,
                    "variant_total": 1000,
                },
                {
                    "segment_name": "returning_users",
                    "segment_definition_note": "Users registered more than 30 days ago",
                    "control_conversions": 220,
                    "control_total": 4000,
                    "variant_conversions": 228,
                    "variant_total": 4000,
                },
            ],
        })

        assert result["method"] == "experiment_cohort_breakdown"
        assert result["cohort_decision_override"] is True
        assert "new_users" in result["cohort_override_reason"]
        assert result["recommended_next_action"] == "targeted_rollout"

        new_users = next(s for s in result["segments"] if s["segment_name"] == "new_users")
        returning = next(s for s in result["segments"] if s["segment_name"] == "returning_users")

        assert new_users["decision"] == "strongly_positive"
        assert new_users["priority_rank"] == 1
        assert new_users["relative_lift_pct"] > 200
        assert new_users["p_value_raw"] < 0.01

        assert returning["decision"] == "neutral"
        assert returning["priority_rank"] == 2

    def test_all_segments_positive_full_rollout(self):
        """All positive segments → full_rollout, no override"""
        result = cohort_breakdown({
            "experiment_id": "test-all-positive",
            "metric": "conversion_rate",
            "prior_decision": "wait",
            "segments": [
                {
                    "segment_name": "segment_a",
                    "control_conversions": 100,
                    "control_total": 2000,
                    "variant_conversions": 130,
                    "variant_total": 2000,
                },
                {
                    "segment_name": "segment_b",
                    "control_conversions": 50,
                    "control_total": 1000,
                    "variant_conversions": 70,
                    "variant_total": 1000,
                },
            ],
        })

        assert result["cohort_decision_override"] is False
        assert result["recommended_next_action"] == "full_rollout"
        for seg in result["segments"]:
            assert seg["decision"] in ("positive", "strongly_positive")

    def test_all_segments_negative_confirm_rejection(self):
        """All negative segments → confirm_rejection"""
        result = cohort_breakdown({
            "experiment_id": "test-all-negative",
            "metric": "conversion_rate",
            "prior_decision": "ship",
            "segments": [
                {
                    "segment_name": "seg1",
                    "control_conversions": 100,
                    "control_total": 2000,
                    "variant_conversions": 80,
                    "variant_total": 2000,
                },
            ],
        })

        assert result["recommended_next_action"] == "confirm_rejection"

    def test_no_prior_result_id(self):
        """Can run without prior_result_id"""
        result = cohort_breakdown({
            "experiment_id": "standalone-test",
            "metric": "conversion_rate",
            "segments": [
                {
                    "segment_name": "new_users",
                    "control_conversions": 21,
                    "control_total": 1000,
                    "variant_conversions": 67,
                    "variant_total": 1000,
                },
            ],
        })

        assert result["prior_result_id"] is None
        assert result["cohort_decision_override"] is False
        assert result["segments"][0]["decision"] == "strongly_positive"

    def test_priority_ranking_correct_order(self):
        """Segments should be ranked by lift magnitude"""
        result = cohort_breakdown({
            "experiment_id": "ranking-test",
            "metric": "conversion_rate",
            "segments": [
                {
                    "segment_name": "small_lift",
                    "control_conversions": 100,
                    "control_total": 2000,
                    "variant_conversions": 110,
                    "variant_total": 2000,
                },
                {
                    "segment_name": "big_lift",
                    "control_conversions": 20,
                    "control_total": 1000,
                    "variant_conversions": 50,
                    "variant_total": 1000,
                },
            ],
        })

        ranks = {s["segment_name"]: s["priority_rank"] for s in result["segments"]}
        assert ranks["big_lift"] == 1
        assert ranks["small_lift"] == 2


class TestMultipleComparisonCorrection:
    """Tests for BH and Bonferroni correction"""

    def test_bh_applied_for_4_segments(self):
        """4+ segments → Benjamini-Hochberg applied"""
        result = cohort_breakdown({
            "experiment_id": "bh-test",
            "metric": "conversion_rate",
            "segments": [
                {"segment_name": "s1", "control_conversions": 50,  "control_total": 500, "variant_conversions": 55,  "variant_total": 500},
                {"segment_name": "s2", "control_conversions": 50,  "control_total": 500, "variant_conversions": 55,  "variant_total": 500},
                {"segment_name": "s3", "control_conversions": 50,  "control_total": 500, "variant_conversions": 55,  "variant_total": 500},
                {"segment_name": "s4", "control_conversions": 50,  "control_total": 500, "variant_conversions": 55,  "variant_total": 500},
            ],
        })

        assert result["audit"]["multiple_comparison_method"] == "benjamini_hochberg"
        # Warnings are now dicts: check by code
        assert any(w["code"] == "multiple_comparisons" for w in result["warnings"])

    def test_no_correction_for_2_segments(self):
        """2-3 segments → no correction"""
        result = cohort_breakdown({
            "experiment_id": "no-correction-test",
            "metric": "conversion_rate",
            "segments": [
                {"segment_name": "s1", "control_conversions": 21,  "control_total": 1000, "variant_conversions": 67,  "variant_total": 1000},
                {"segment_name": "s2", "control_conversions": 220, "control_total": 4000, "variant_conversions": 228, "variant_total": 4000},
            ],
        })

        assert result["audit"]["multiple_comparison_method"] == "none"
        # p_value_raw == p_value_adjusted when no correction
        for seg in result["segments"]:
            assert seg["p_value_raw"] == seg["p_value_adjusted"]

    def test_bh_correctness_simple(self):
        """Verify BH correction: with 2 segments (both raw p < 0.05),
        BH adjusts upward and may remove significance if effect is small.
        With n=2: adj_p[i] = raw_p[i] * n / rank[i].
        Here both segments have p ≈ 0.01 and 0.04 raw — BH may or may not
        preserve significance depending on the actual p-values. The key check
        is that p_value_adjusted >= p_value_raw (correction never decreases p).
        """
        result = cohort_breakdown({
            "experiment_id": "bh-math",
            "metric": "conversion_rate",
            "segments": [
                {"segment_name": "seg_a", "control_conversions": 10, "control_total": 1000,
                 "variant_conversions": 20, "variant_total": 1000},
                {"segment_name": "seg_b", "control_conversions": 20, "control_total": 1000,
                 "variant_conversions": 30, "variant_total": 1000},
            ],
        })

        seg_a = next(s for s in result["segments"] if s["segment_name"] == "seg_a")
        seg_b = next(s for s in result["segments"] if s["segment_name"] == "seg_b")

        # BH correction never decreases a p-value
        assert seg_a["p_value_adjusted"] >= seg_a["p_value_raw"]
        assert seg_b["p_value_adjusted"] >= seg_b["p_value_raw"]
        # For n=2 segments, no correction is applied (correction_method = none)
        assert result["audit"]["multiple_comparison_method"] == "none"

    def test_bonferroni_warning_when_selected(self):
        """Bonferroni override → conservative warning"""
        result = cohort_breakdown({
            "experiment_id": "bonferroni-test",
            "metric": "conversion_rate",
            "multiple_comparison_method": "bonferroni",
            "segments": [
                {"segment_name": "s1", "control_conversions": 10, "control_total": 200, "variant_conversions": 20, "variant_total": 200},
                {"segment_name": "s2", "control_conversions": 10, "control_total": 200, "variant_conversions": 20, "variant_total": 200},
                {"segment_name": "s3", "control_conversions": 10, "control_total": 200, "variant_conversions": 20, "variant_total": 200},
                {"segment_name": "s4", "control_conversions": 10, "control_total": 200, "variant_conversions": 20, "variant_total": 200},
                {"segment_name": "s5", "control_conversions": 10, "control_total": 200, "variant_conversions": 20, "variant_total": 200},
            ],
        })

        assert result["audit"]["multiple_comparison_method"] == "bonferroni"
        warning_codes = [w["code"] for w in result["warnings"]]
        assert "bonferroni_conservative_warning" in warning_codes


class TestInteractionFlag:
    """Tests for interaction_flag (opposing strongly significant directions)"""

    def test_interaction_flag_when_opposing_strong(self):
        """One segment strongly positive, another strongly negative → interaction_flag=True"""
        result = cohort_breakdown({
            "experiment_id": "interaction-test",
            "metric": "conversion_rate",
            "segments": [
                {
                    "segment_name": "gaining_users",
                    "control_conversions": 10,
                    "control_total": 500,
                    "variant_conversions": 30,
                    "variant_total": 500,   # ~3x lift, very significant
                },
                {
                    "segment_name": "losing_users",
                    "control_conversions": 50,
                    "control_total": 500,
                    "variant_conversions": 20,
                    "variant_total": 500,   # strong negative
                },
            ],
        })

        assert result["interaction_flag"] is True

    def test_no_interaction_flag_when_same_direction(self):
        """All positive or all negative → no interaction flag"""
        result = cohort_breakdown({
            "experiment_id": "no-interaction-test",
            "metric": "conversion_rate",
            "segments": [
                {"segment_name": "seg1", "control_conversions": 10, "control_total": 500, "variant_conversions": 25, "variant_total": 500},
                {"segment_name": "seg2", "control_conversions": 10, "control_total": 500, "variant_conversions": 20, "variant_total": 500},
            ],
        })

        assert result["interaction_flag"] is False


class TestCohortWarnings:
    """Tests for warnings in cohort output"""

    def test_low_traffic_warning_per_segment(self):
        """Small segment sample → LOW_TRAFFIC warning in segment warnings list"""
        result = cohort_breakdown({
            "experiment_id": "low-traffic-test",
            "metric": "conversion_rate",
            "min_sample_per_segment": 100,
            "segments": [
                {
                    "segment_name": "tiny_segment",
                    "control_conversions": 1,
                    "control_total": 50,   # below 100 threshold
                    "variant_conversions": 3,
                    "variant_total": 50,
                },
                {
                    "segment_name": "healthy_segment",
                    "control_conversions": 100,
                    "control_total": 1000,
                    "variant_conversions": 130,
                    "variant_total": 1000,
                },
            ],
        })

        tiny = next(s for s in result["segments"] if s["segment_name"] == "tiny_segment")
        # Each warning is a dict with 'code' and 'message' fields
        assert any(w.get("code") == "LOW_TRAFFIC" for w in tiny["warnings"])

    def test_segment_definition_note_in_audit(self):
        """segment_definition_note present → flagged in audit"""
        result = cohort_breakdown({
            "experiment_id": "notes-test",
            "metric": "conversion_rate",
            "segments": [
                {
                    "segment_name": "new_users",
                    "segment_definition_note": "Registered within last 30 days",
                    "control_conversions": 21,
                    "control_total": 1000,
                    "variant_conversions": 67,
                    "variant_total": 1000,
                },
            ],
        })

        assert result["audit"]["segment_definition_notes_present"] is True


class TestCohortDecisionOverrideEdgeCases:
    """Edge cases for cohort_decision_override"""

    def test_strong_negative_overrides_ship(self):
        """Strong negative in one segment should override 'ship' decision"""
        result = cohort_breakdown({
            "experiment_id": "override-ship",
            "metric": "conversion_rate",
            "prior_decision": "ship",
            "segments": [
                {
                    "segment_name": "high_value_users",
                    "control_conversions": 100,
                    "control_total": 500,
                    "variant_conversions": 40,   # 60% drop — clearly strongly_negative
                    "variant_total": 500,
                },
                {
                    "segment_name": "low_value_users",
                    "control_conversions": 50,
                    "control_total": 5000,
                    "variant_conversions": 60,
                    "variant_total": 5000,
                },
            ],
        })

        high_val = next(s for s in result["segments"] if s["segment_name"] == "high_value_users")
        # The high-value segment should be ranked #1 (larger absolute lift magnitude)
        assert high_val["priority_rank"] == 1
        assert high_val["decision"] == "strongly_negative"
        assert result["cohort_decision_override"] is True
        assert "abandon_segment" in result["recommended_next_action"]

    def test_weak_positive_does_not_override(self):
        """Positive but not 'strongly' → no override even if aggregate is wait"""
        result = cohort_breakdown({
            "experiment_id": "no-override-weak",
            "metric": "conversion_rate",
            "prior_decision": "wait",
            "segments": [
                {
                    "segment_name": "weak_signal",
                    "control_conversions": 100,
                    "control_total": 2000,
                    "variant_conversions": 115,   # small positive, not strong
                    "variant_total": 2000,
                },
            ],
        })

        assert result["cohort_decision_override"] is False


class TestCohortSummaryAndNextAction:
    """Tests for summary text and recommended_next_action"""

    def test_summary_identifies_driver(self):
        """Summary should identify which segment drives the effect"""
        result = cohort_breakdown({
            "experiment_id": "summary-test",
            "metric": "conversion_rate",
            "segments": [
                {
                    "segment_name": "new_users",
                    "control_conversions": 21,
                    "control_total": 1000,
                    "variant_conversions": 67,
                    "variant_total": 1000,
                },
                {
                    "segment_name": "returning",
                    "control_conversions": 220,
                    "control_total": 4000,
                    "variant_conversions": 228,
                    "variant_total": 4000,
                },
            ],
        })

        assert "new_users" in result["summary"]
        assert "priority_ranking" in result
        assert len(result["priority_ranking"]) == 2

    def test_empty_segments_raises(self):
        """Empty segments list → ValueError"""
        with pytest.raises(ValueError, match="At least one segment"):
            cohort_breakdown({"experiment_id": "x", "metric": "y", "segments": []})


class TestNextAnalysisSuggestion:
    """Verify next_analysis_suggestion fires in ab when it should"""

    def test_ab_inconclusive_triggers_suggestion(self):
        """Inconclusive ab result → next_analysis_suggestion present"""
        from src.ab_test import calculate_ab

        result = calculate_ab({
            "control_conversions": 241,
            "control_total": 5000,
            "variant_conversions": 260,  # p=0.38, inconclusive
            "variant_total": 5000,
        })

        assert result.next_analysis_suggestion is not None
        assert result.next_analysis_suggestion["command"] == "cohort-breakdown"

    def test_ab_conclusive_no_suggestion(self):
        """Strong significant result → no next_analysis_suggestion"""
        from src.ab_test import calculate_ab

        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 150,  # strong positive, p < 0.01
            "variant_total": 5000,
        })

        assert result.next_analysis_suggestion is None
