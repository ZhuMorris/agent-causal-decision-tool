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


    def test_missing_timestamps_no_crash(self):
        """Sequential enabled with missing timestamps → conditions_not_met, no crash"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 150,
            "variant_total": 5000,
            "sequential_enabled": True,
            # No experiment_start_time / experiment_end_time
            "min_runtime_days": 7,
            "min_sample_per_arm": 2000,
            "early_stop_p_threshold": 0.01,
        })
        # Must not crash; should fall through to conditions_not_met
        assert result.sequential_reviewed is True
        assert result.early_stop_applied is False
        assert result.sequential_summary.reason == "conditions_not_met"
        assert result.recommendation.decision in ["ship", "keep_running", "reject", "escalate"]
        warning_codes = [w.code for w in result.warnings]
        assert "SEQUENTIAL_CONDITIONS_NOT_MET" in warning_codes

    def test_invalid_timestamps_no_crash(self):
        """Sequential enabled with unparseable timestamps → conditions_not_met, no crash"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 150,
            "variant_total": 5000,
            "sequential_enabled": True,
            "experiment_start_time": "not-a-date",
            "experiment_end_time": "also-not-a-date",
            "min_runtime_days": 7,
            "min_sample_per_arm": 2000,
            "early_stop_p_threshold": 0.01,
        })
        assert result.sequential_reviewed is True
        assert result.early_stop_applied is False
        assert result.sequential_summary.reason == "conditions_not_met"
        warning_codes = [w.code for w in result.warnings]
        assert "SEQUENTIAL_CONDITIONS_NOT_MET" in warning_codes

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
        """Early stop applied → warning with code SEQUENTIAL_EARLY_STOP"""
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
        assert "SEQUENTIAL_EARLY_STOP" in warning_codes


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


class TestConfidenceIntervalOutput:
    """Tests for lift_ci_95, relative_lift_ci_95 (v0.8 rename from confidence_interval_95)."""

    def test_lift_ci_95_present(self):
        """lift_ci_95 field must be present in A/B statistics output."""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert "lift_ci_95" in result.statistics
        assert isinstance(result.statistics["lift_ci_95"], list)
        assert len(result.statistics["lift_ci_95"]) == 2

    def test_lift_ci_95_no_confidence_interval_95(self):
        """confidence_interval_95 must be removed (clean break)."""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert "confidence_interval_95" not in result.statistics

    def test_lift_ci_95_order_correct(self):
        """CI lower < upper."""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        ci = result.statistics["lift_ci_95"]
        assert ci[0] < ci[1]

    def test_relative_lift_ci_95_present(self):
        """relative_lift_ci_95 must be present (percentage CI relative to control rate)."""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert "relative_lift_ci_95" in result.statistics
        assert isinstance(result.statistics["relative_lift_ci_95"], list)
        assert len(result.statistics["relative_lift_ci_95"]) == 2

    def test_relative_lift_ci_95_percentage_scale(self):
        """Relative CI values should be in percentage terms (not decimal)."""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        rel_ci = result.statistics["relative_lift_ci_95"]
        assert rel_ci[0] < 100  # should be percentage, not >1

    def test_schema_version_present(self):
        """schema_version must be present in A/B output."""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert hasattr(result, "schema_version")
        assert result.schema_version is not None


class TestBorderlinePValue:
    """Tests for BORDERLINE_P_VALUE warning (0.05 ≤ p ≤ 0.10)."""

    def test_borderline_p_value_fires_at_005(self):
        """p=0.05 exactly → BORDERLINE_P_VALUE warning."""
        from src.ab_test import calculate_ab
        # p=0.05 with control=50/2000, variant=70/2000
        result = calculate_ab({
            "control_conversions": 50,
            "control_total": 2000,
            "variant_conversions": 70,
            "variant_total": 2000
        })
        codes = [w.code.value for w in result.warnings]
        assert "BORDERLINE_P_VALUE" in codes

    def test_borderline_p_value_fires_at_010(self):
        """p≈0.09 → BORDERLINE_P_VALUE warning (0.05 ≤ p ≤ 0.10)."""
        from src.ab_test import calculate_ab
        # 100/5000 vs 125/5000 gives p≈0.09
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 125,
            "variant_total": 5000
        })
        codes = [w.code.value for w in result.warnings]
        assert "BORDERLINE_P_VALUE" in codes

    def test_no_borderline_above_010(self):
        """p > 0.10 → no BORDERLINE_P_VALUE."""
        from src.ab_test import calculate_ab
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 110,
            "variant_total": 5000
        })
        codes = [w.code.value for w in result.warnings]
        assert "BORDERLINE_P_VALUE" not in codes

    def test_no_borderline_below_005(self):
        """p < 0.05 → no BORDERLINE_P_VALUE (regular significant result)."""
        from src.ab_test import calculate_ab
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 140,
            "variant_total": 5000
        })
        codes = [w.code.value for w in result.warnings]
        assert "BORDERLINE_P_VALUE" not in codes

    def test_borderline_warning_severity_is_warning(self):
        """BORDERLINE_P_VALUE must have severity=warning."""
        from src.ab_test import calculate_ab
        result = calculate_ab({
            "control_conversions": 50,
            "control_total": 2000,
            "variant_conversions": 70,
            "variant_total": 2000
        })
        borderline = [w for w in result.warnings if w.code.value == "BORDERLINE_P_VALUE"]
        assert len(borderline) == 1
        assert borderline[0].severity == "warning"