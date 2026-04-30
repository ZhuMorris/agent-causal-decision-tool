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


class TestSequentialEarlyStopping:
    """Tests for sequential / early stopping logic"""

    def test_early_stop_applied_when_conditions_met_and_p_below_threshold(self):
        """Sequential enabled, runtime/sample ok, p < threshold → early stop applied"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 150,
            "variant_total": 5000,
            "variant_name": "variant_1",
            "sequential_enabled": True,
            "experiment_start_time": "2026-04-01T00:00:00Z",
            "experiment_end_time": "2026-04-15T00:00:00Z",  # 14 days
            "min_runtime_days": 7,
            "min_sample_per_arm": 2000,
            "early_stop_p_threshold": 0.01,
            "max_runtime_days": 30,
        })
        # 14 days runtime, 5000 per arm, p will be very small → early stop
        assert result.sequential_reviewed is True
        assert result.early_stop_applied is True
        assert result.sequential_summary.reason == "p_below_threshold"
        assert result.recommendation.decision == "ship"

    def test_no_early_stop_before_min_runtime(self):
        """Sequential enabled but only 3 days in → conditions not met, normal logic"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 150,
            "variant_total": 5000,
            "variant_name": "variant_1",
            "sequential_enabled": True,
            "experiment_start_time": "2026-04-01T00:00:00Z",
            "experiment_end_time": "2026-04-04T00:00:00Z",  # 3 days < 7-day min
            "min_runtime_days": 7,
            "min_sample_per_arm": 2000,
            "early_stop_p_threshold": 0.01,
            "max_runtime_days": 30,
        })
        assert result.sequential_reviewed is True
        assert result.early_stop_applied is False
        assert result.sequential_summary.reason == "conditions_not_met"
        # Decision from normal logic, not early-stop logic
        assert result.recommendation.decision in ["ship", "keep_running", "reject", "escalate"]

    def test_no_early_stop_before_min_sample(self):
        """Sequential enabled but only 500 per arm → conditions not met"""
        result = calculate_ab({
            "control_conversions": 10,
            "control_total": 500,
            "variant_conversions": 15,
            "variant_total": 500,
            "variant_name": "variant_1",
            "sequential_enabled": True,
            "experiment_start_time": "2026-04-01T00:00:00Z",
            "experiment_end_time": "2026-04-20T00:00:00Z",  # 19 days
            "min_runtime_days": 7,
            "min_sample_per_arm": 2000,  # 500 < 2000
            "early_stop_p_threshold": 0.01,
            "max_runtime_days": 30,
        })
        assert result.sequential_reviewed is True
        assert result.early_stop_applied is False
        assert result.sequential_summary.reason == "conditions_not_met"

    def test_no_early_stop_when_p_not_significant(self):
        """Sequential conditions met but p > threshold → no early stop, normal logic"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 105,  # small effect, not significant
            "variant_total": 5000,
            "variant_name": "variant_1",
            "sequential_enabled": True,
            "experiment_start_time": "2026-04-01T00:00:00Z",
            "experiment_end_time": "2026-04-15T00:00:00Z",
            "min_runtime_days": 7,
            "min_sample_per_arm": 2000,
            "early_stop_p_threshold": 0.01,
            "max_runtime_days": 30,
        })
        assert result.sequential_reviewed is True
        assert result.early_stop_applied is False
        # p not small enough for early stop → normal inconclusive decision
        assert result.recommendation.decision in ["keep_running", "escalate"]

    def test_max_runtime_exceeded_escalates(self):
        """Runtime exceeded max without strong result → escalate"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 105,
            "variant_total": 5000,
            "variant_name": "variant_1",
            "sequential_enabled": True,
            "experiment_start_time": "2026-04-01T00:00:00Z",
            "experiment_end_time": "2026-04-25T00:00:00Z",  # 24 days > 21-day max
            "min_runtime_days": 7,
            "min_sample_per_arm": 2000,
            "early_stop_p_threshold": 0.01,
            "max_runtime_days": 21,
        })
        assert result.sequential_reviewed is True
        assert result.early_stop_applied is False
        assert result.sequential_summary.reason == "max_runtime_exceeded"
        assert result.recommendation.decision == "escalate"

    def test_sequential_disabled_no_sequential_fields(self):
        """Sequential disabled → sequential_reviewed=False, sequential_summary=None"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000,
        })
        assert result.sequential_reviewed is False
        assert result.early_stop_applied is False
        assert result.sequential_summary is None

    def test_early_stop_with_negative_lift_rejects(self):
        """Early stop when p < threshold but lift is negative → reject"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 60,  # very strong negative, p ~ 0.003
            "variant_total": 5000,
            "variant_name": "variant_1",
            "sequential_enabled": True,
            "experiment_start_time": "2026-04-01T00:00:00Z",
            "experiment_end_time": "2026-04-15T00:00:00Z",
            "min_runtime_days": 7,
            "min_sample_per_arm": 2000,
            "early_stop_p_threshold": 0.01,
            "max_runtime_days": 30,
        })
        assert result.early_stop_applied is True
        assert result.sequential_summary.reason == "p_below_threshold"
        assert result.recommendation.decision == "reject"

    def test_early_stop_warning_in_warnings(self):
        """Early stop applied → warning with code 'early_stop_applied'"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 150,
            "variant_total": 5000,
            "variant_name": "variant_1",
            "sequential_enabled": True,
            "experiment_start_time": "2026-04-01T00:00:00Z",
            "experiment_end_time": "2026-04-15T00:00:00Z",
            "min_runtime_days": 7,
            "min_sample_per_arm": 2000,
            "early_stop_p_threshold": 0.01,
            "max_runtime_days": 30,
        })
        warning_codes = [w.code for w in result.warnings]
        assert "early_stop_applied" in warning_codes


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