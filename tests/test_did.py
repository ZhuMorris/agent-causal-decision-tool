"""Tests for DiD analysis"""

import pytest
from src.did import calculate_did


class TestDiD:
    """DiD unit tests"""

    def test_positive_significant_effect(self):
        """Positive DiD → should ship"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150
        })
        assert result.recommendation.decision == "ship"
        assert result.statistics["relative_did_pct"] > 10

    def test_negative_effect(self):
        """Strong negative DiD → should reject"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1200,  # +20% control
            "pre_treated": 1000,
            "post_treated": 1000   # No change in treated = -20% relative!
        })
        # DiD = (1000-1000) - (1200-1000) = 0 - 200 = -200
        # relative_did = -200/1000 * 100 = -20% < -10% → reject
        assert result.recommendation.decision == "reject"

    def test_small_effect_escalate(self):
        """Small effect → escalate"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1050,
            "pre_treated": 900,
            "post_treated": 950
        })
        # Small relative effect should escalate
        assert result.recommendation.decision in ["escalate", "keep_running"]

    def test_trends_diverge_warning(self):
        """When control and treatment trends diverge sharply"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 2000,  # 100% growth
            "pre_treated": 900,
            "post_treated": 950   # Only 5% growth - diverges!
        })
        warning_codes = [w.code for w in result.warnings]
        assert any("DIVERGE" in code for code in warning_codes)

    def test_zero_baseline_critical_warning(self):
        """Zero baseline should trigger critical warning"""
        result = calculate_did({
            "pre_control": 0,
            "post_control": 100,
            "pre_treated": 0,
            "post_treated": 150
        })
        warning_codes = [w.code for w in result.warnings]
        assert "ZERO_BASELINE" in warning_codes

    def test_aggregate_data_warning(self):
        """Aggregate data should always warn"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150
        })
        warning_codes = [w.code for w in result.warnings]
        assert "AGGREGATE_DATA" in warning_codes

    def test_assumptions_listed(self):
        """DiD assumptions should be listed"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150
        })
        assert len(result.assumptions) > 0
        assert "Parallel trends" in result.assumptions[0]

    def test_audit_present(self):
        """Audit record should be present"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150
        })
        assert "experiment_type" in result.audit
        assert result.audit["experiment_type"] == "difference_in_differences"

    def test_inputs_preserved(self):
        """Original inputs should be preserved"""
        input_data = {
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150
        }
        result = calculate_did(input_data)
        assert result.inputs == input_data

    def test_did_estimate_correct(self):
        """DiD estimate = (post_t - pre_t) - (post_c - pre_c)"""
        result = calculate_did({
            "pre_control": 100,
            "post_control": 110,
            "pre_treated": 80,
            "post_treated": 100
        })
        # (100 - 80) - (110 - 100) = 20 - 10 = 10
        assert result.statistics["did_estimate"] == 10

    def test_relative_did_correct(self):
        """Relative DiD should be (DiD / pre_treated) * 100"""
        result = calculate_did({
            "pre_control": 100,
            "post_control": 110,
            "pre_treated": 80,
            "post_treated": 100
        })
        # DiD = 10, pre_treated = 80 → 12.5%
        assert result.statistics["relative_did_pct"] == pytest.approx(12.5, rel=1e-2)


class TestDiDEdgeCases:
    """Edge cases for DiD"""

    def test_identical_pre_post(self):
        """No change in either group"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1000,
            "pre_treated": 900,
            "post_treated": 900
        })
        # DiD = 0, should escalate due to small effect
        assert result.recommendation.decision in ["escalate", "keep_running"]

    def test_both_grow_same_rate(self):
        """Parallel growth - no treatment effect"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 1000,
            "post_treated": 1100
        })
        # DiD = 0, parallel trends
        assert result.statistics["did_estimate"] == 0