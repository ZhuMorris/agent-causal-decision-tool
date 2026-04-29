"""Tests for A/B test analysis"""

import pytest
from src.ab_test import calculate_ab


class TestABTest:
    """A/B test unit tests"""

    def test_significant_positive_result(self):
        """Control: 100/5000, Variant: 130/5000 → should ship"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result.recommendation.decision == "ship"
        assert result.recommendation.p_value < 0.05
        assert result.recommendation.primary_metricLift > 0

    def test_significant_negative_result(self):
        """Control: 100/5000, Variant: 70/5000 → should reject (strong negative)"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 70,
            "variant_total": 5000
        })
        # Lift = -30%, p < 0.05 → should reject
        assert result.recommendation.decision == "reject"
        assert result.recommendation.primary_metricLift < 0

    def test_not_significant_keeps_running(self):
        """Control: 100/5000, Variant: 105/5000 → p > 0.3, should escalate"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 105,
            "variant_total": 5000
        })
        # Small effect, not significant - should escalate
        assert result.recommendation.decision in ["keep_running", "escalate"]

    def test_low_traffic_warning(self):
        """Traffic below 1000 per group should warn"""
        result = calculate_ab({
            "control_conversions": 10,
            "control_total": 100,
            "variant_conversions": 15,
            "variant_total": 100
        })
        warning_codes = [w.code for w in result.warnings]
        assert "LOW_TRAFFIC" in warning_codes

    def test_small_effect_warning(self):
        """Lift < 1% should warn"""
        result = calculate_ab({
            "control_conversions": 1000,
            "control_total": 50000,
            "variant_conversions": 1010,
            "variant_total": 50000
        })
        warning_codes = [w.code for w in result.warnings]
        assert "SMALL_EFFECT" in warning_codes

    def test_statistics_correct(self):
        """Verify computed statistics are correct"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result.statistics["control_rate"] == pytest.approx(0.02, rel=1e-3)
        assert result.statistics["variant_rate"] == pytest.approx(0.026, rel=1e-3)
        assert result.statistics["relative_lift_pct"] == pytest.approx(30.0, rel=1e-2)

    def test_audit_present(self):
        """Audit record should be present"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert "experiment_type" in result.audit
        assert result.audit["experiment_type"] == "ab_test"
        assert "traffic_size" in result.audit
        assert "thresholds_applied" in result.audit

    def test_inputs_preserved(self):
        """Original inputs should be preserved for audit"""
        input_data = {
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        }
        result = calculate_ab(input_data)
        assert result.inputs == input_data

    def test_traffic_stats_correct(self):
        """Traffic stats should be correct"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result.traffic_stats.control_size == 5000
        assert result.traffic_stats.variant_size == 5000
        assert result.traffic_stats.total_size == 10000

    def test_next_steps_present(self):
        """Next steps should be present"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert len(result.next_steps) > 0


class TestABTestEdgeCases:
    """Edge cases for A/B testing"""

    def test_zero_total(self):
        """Zero total should not crash"""
        result = calculate_ab({
            "control_conversions": 0,
            "control_total": 0,
            "variant_conversions": 0,
            "variant_total": 0
        })
        assert result.recommendation.decision == "escalate"

    def test_perfect_rate(self):
        """100% conversion rate"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 100,
            "variant_conversions": 100,
            "variant_total": 100
        })
        # Both perfect, should be inconclusive or ship based on exact match
        assert result.recommendation.decision in ["ship", "escalate"]

    def test_zero_conversions(self):
        """Zero conversions in both groups"""
        result = calculate_ab({
            "control_conversions": 0,
            "control_total": 5000,
            "variant_conversions": 0,
            "variant_total": 5000
        })
        # Both zero - should handle gracefully
        assert "p_value" in result.statistics