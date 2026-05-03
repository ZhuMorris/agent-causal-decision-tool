"""Tests for experiment planning module"""

import pytest
from src.planning import calculate_plan


class TestPlanning:
    """Planning unit tests"""

    def test_feasible_experiment(self):
        """High traffic, large MDE → feasible"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 20,
            "daily_traffic": 10000,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "equal",
            "allocation_ratio": None
        })
        assert result.planning["feasibility"] == "feasible"
        assert result.planning["estimated_days"] <= 14

    def test_slow_experiment(self):
        """Medium traffic, medium MDE → slow"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 10,
            "daily_traffic": 5000,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "equal",
            "allocation_ratio": None
        })
        assert result.planning["feasibility"] == "slow"
        assert 15 <= result.planning["estimated_days"] <= 60

    def test_not_recommended_experiment(self):
        """Low traffic, small MDE → not_recommended"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 5,
            "daily_traffic": 500,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "equal",
            "allocation_ratio": None
        })
        assert result.planning["feasibility"] == "not_recommended"
        assert result.planning["estimated_days"] > 60

    def test_custom_allocation(self):
        """Custom allocation ratio changes required sample"""
        result_equal = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 10,
            "daily_traffic": 5000,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "equal",
            "allocation_ratio": None
        })
        result_custom = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 10,
            "daily_traffic": 5000,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "custom",
            "allocation_ratio": "0.3/0.7"
        })
        # Custom allocation should require more total sample (inefficient split)
        assert result_custom.planning["allocation_used"]["control"] == 0.3
        assert result_custom.planning["allocation_used"]["variant"] == 0.7
        assert result_custom.planning["total_required"] >= result_equal.planning["total_required"]

    def test_warns_on_low_traffic(self):
        """Daily traffic < 100 per arm → LOW_TRAFFIC warning"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 10,
            "daily_traffic": 50,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "equal",
            "allocation_ratio": None
        })
        warning_codes = [w.code for w in result.warnings]
        assert "LOW_TRAFFIC" in warning_codes

    def test_warns_on_long_experiment(self):
        """Estimated days > 30 → SLOW_EXPERIMENT warning"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 10,
            "daily_traffic": 500,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "equal",
            "allocation_ratio": None
        })
        warning_codes = [w.code for w in result.warnings]
        assert "SLOW_EXPERIMENT" in warning_codes

    def test_not_recommended_suggests_did(self):
        """When infeasible, should suggest DiD"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 5,
            "daily_traffic": 100,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "equal",
            "allocation_ratio": None
        })
        warning_codes = [w.code for w in result.warnings]
        assert "INFEASIBLE_EXPERIMENT" in warning_codes
        did_warning = next((w for w in result.warnings if w.code == "INFEASIBLE_EXPERIMENT"), None)
        assert did_warning is not None
        assert "DiD" in did_warning.message

    def test_decision_ship_for_feasible(self):
        """Feasible experiments should recommend ship"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 20,
            "daily_traffic": 20000,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "equal",
            "allocation_ratio": None
        })
        assert result.recommendation.decision == "ship"

    def test_decision_escalate_for_not_recommended(self):
        """Not recommended experiments should escalate"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 5,
            "daily_traffic": 100,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "equal",
            "allocation_ratio": None
        })
        assert result.recommendation.decision == "escalate"

    def test_allocation_used_correct(self):
        """Allocation used should be correct"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 10,
            "daily_traffic": 5000,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "equal",
            "allocation_ratio": None
        })
        alloc = result.planning["allocation_used"]
        assert alloc["control"] == 0.5
        assert alloc["variant"] == 0.5


    def test_custom_allocation_total_required_equals_sum_of_weighted_arms(self):
        """total_required should equal required_per_arm/r_control + required_per_arm/r_variant"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 20,
            "daily_traffic": 10000,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "custom",
            "allocation_ratio": "0.3/0.7"  # r_control=0.3, r_variant=0.7
        })
        required_per_arm = result.planning["required_sample_per_arm"]
        total_required = result.planning["total_required"]
        # Verify total_required matches weighted sum
        expected_total = required_per_arm / 0.3 + required_per_arm / 0.7
        assert total_required == __import__('math').ceil(expected_total)

    def test_equal_allocation_total_required_reflects_ratio_factor_baked_into_per_arm(self):
        """For equal allocation, ratio_factor=4 is already in per_arm, total = per_arm/r_c + per_arm/r_v = 4*per_arm"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 20,
            "daily_traffic": 10000,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "equal",
        })
        required_per_arm = result.planning["required_sample_per_arm"]
        total_required = result.planning["total_required"]
        # Equal 0.5/0.5: total = per_arm/0.5 + per_arm/0.5 = 4 * per_arm
        assert total_required == required_per_arm / 0.5 + required_per_arm / 0.5

    def test_custom_allocation_rejects_invalid_ratio(self):
        """Invalid ratio (not summing to 1) should raise"""
        with pytest.raises(ValueError):
            calculate_plan({
                "baseline_conversion_rate": 0.02,
                "mde_pct": 10,
                "daily_traffic": 5000,
                "confidence_level": 0.95,
                "power": 0.8,
                "allocation": "custom",
                "allocation_ratio": "0.5/0.3"  # Does not sum to 1
            })

    def test_inputs_preserved(self):
        """Original inputs should be preserved"""
        input_data = {
            "baseline_conversion_rate": 0.02,
            "mde_pct": 10,
            "daily_traffic": 5000,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "equal",
            "allocation_ratio": None
        }
        result = calculate_plan(input_data)
        assert result.inputs == input_data

    def test_mode_is_planning(self):
        """Mode should be planning"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 10,
            "daily_traffic": 5000,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "equal",
            "allocation_ratio": None
        })
        assert result.mode == "planning"


class TestPlanningEdgeCases:
    """Edge cases for planning"""

    def test_custom_allocation_requires_ratio(self):
        """Custom allocation without ratio should raise"""
        with pytest.raises(ValueError):
            calculate_plan({
                "baseline_conversion_rate": 0.02,
                "mde_pct": 10,
                "daily_traffic": 5000,
                "confidence_level": 0.95,
                "power": 0.8,
                "allocation": "custom",
                "allocation_ratio": None
            })

    def test_very_high_traffic_feasible(self):
        """Very high traffic should be feasible"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 5,
            "daily_traffic": 100000,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "equal",
            "allocation_ratio": None
        })
        assert result.planning["feasibility"] == "feasible"

    def test_very_low_baseline_rate(self):
        """Very low baseline rate (0.001 = 0.1%) should still compute"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.001,
            "mde_pct": 20,
            "daily_traffic": 50000,
            "confidence_level": 0.95,
            "power": 0.8,
            "allocation": "equal",
            "allocation_ratio": None
        })
        assert result.planning["required_sample_per_arm"] > 0
        assert result.planning["feasibility"] in ["feasible", "slow", "not_recommended"]


class TestMdeConfidenceInterval:
    """Tests for mde_ci_95 (v0.8 planning feature)."""

    def test_mde_ci_95_present(self):
        """mde_ci_95 must be present in planning output when daily_traffic provided."""
        result = calculate_plan({
            "baseline_conversion_rate": 0.05,
            "mde_pct": 5,
            "daily_traffic": 5000,
        })
        assert "mde_ci_95" in result.planning

    def test_mde_ci_95_is_list_of_two(self):
        """mde_ci_95 must be [lower, upper]."""
        result = calculate_plan({
            "baseline_conversion_rate": 0.05,
            "mde_pct": 5,
            "daily_traffic": 5000,
        })
        ci = result.planning["mde_ci_95"]
        assert isinstance(ci, list)
        assert len(ci) == 2

    def test_mde_ci_95_lower_less_than_upper(self):
        """CI lower bound must be less than upper bound."""
        result = calculate_plan({
            "baseline_conversion_rate": 0.05,
            "mde_pct": 5,
            "daily_traffic": 5000,
        })
        ci = result.planning["mde_ci_95"]
        assert ci[0] < ci[1]

    def test_mde_ci_95_percentage_scale(self):
        """mde_ci_95 values should be in percentage terms."""
        result = calculate_plan({
            "baseline_conversion_rate": 0.05,
            "mde_pct": 5,
            "daily_traffic": 5000,
        })
        ci = result.planning["mde_ci_95"]
        assert all(v < 100 for v in ci)  # percentage scale

    def test_mde_ci_95_null_when_no_traffic(self):
        """mde_ci_95 is null when daily_traffic not provided."""
        result = calculate_plan({
            "baseline_conversion_rate": 0.05,
            "mde_pct": 5,
            "daily_traffic": 0,
        })
        assert result.planning["mde_ci_95"] is None

    def test_mde_ci_95_wider_ci_for_small_traffic(self):
        """Smaller traffic → wider mde_ci_95."""
        result_small = calculate_plan({
            "baseline_conversion_rate": 0.05,
            "mde_pct": 5,
            "daily_traffic": 500,
        })
        result_large = calculate_plan({
            "baseline_conversion_rate": 0.05,
            "mde_pct": 5,
            "daily_traffic": 50000,
        })
        small_range = result_small.planning["mde_ci_95"][1] - result_small.planning["mde_ci_95"][0]
        large_range = result_large.planning["mde_ci_95"][1] - result_large.planning["mde_ci_95"][0]
        assert small_range > large_range


class TestBaselineWarnings:
    """Tests for BASELINE_VERY_LOW and BASELINE_NEAR_ZERO (v0.8)."""

    def test_baseline_very_low_warning(self):
        """Baseline rate < 0.005 → BASELINE_VERY_LOW (warning)."""
        result = calculate_plan({
            "baseline_conversion_rate": 0.003,
            "mde_pct": 10,
            "daily_traffic": 10000,
        })
        codes = [w.code.value for w in result.warnings]
        assert "BASELINE_VERY_LOW" in codes

    def test_baseline_very_low_severity_warning(self):
        """BASELINE_VERY_LOW must have severity=warning."""
        result = calculate_plan({
            "baseline_conversion_rate": 0.003,
            "mde_pct": 10,
            "daily_traffic": 10000,
        })
        bl = [w for w in result.warnings if w.code.value == "BASELINE_VERY_LOW"]
        assert len(bl) == 1
        assert bl[0].severity == "warning"

    def test_no_baseline_very_low_above_threshold(self):
        """Baseline rate ≥ 0.005 → no BASELINE_VERY_LOW."""
        result = calculate_plan({
            "baseline_conversion_rate": 0.005,
            "mde_pct": 10,
            "daily_traffic": 10000,
        })
        codes = [w.code.value for w in result.warnings]
        assert "BASELINE_VERY_LOW" not in codes

    def test_baseline_near_zero_critical(self):
        """Baseline rate < 0.001 → BASELINE_NEAR_ZERO (critical)."""
        result = calculate_plan({
            "baseline_conversion_rate": 0.0005,
            "mde_pct": 20,
            "daily_traffic": 10000,
        })
        codes = [w.code.value for w in result.warnings]
        assert "BASELINE_NEAR_ZERO" in codes

    def test_baseline_near_zero_severity_critical(self):
        """BASELINE_NEAR_ZERO must have severity=critical."""
        result = calculate_plan({
            "baseline_conversion_rate": 0.0005,
            "mde_pct": 20,
            "daily_traffic": 10000,
        })
        bnz = [w for w in result.warnings if w.code.value == "BASELINE_NEAR_ZERO"]
        assert len(bnz) == 1
        assert bnz[0].severity == "critical"

    def test_both_baseline_codes_can_fire(self):
        """Baseline < 0.001 should fire both BASELINE_VERY_LOW and BASELINE_NEAR_ZERO."""
        result = calculate_plan({
            "baseline_conversion_rate": 0.0005,
            "mde_pct": 20,
            "daily_traffic": 10000,
        })
        codes = [w.code.value for w in result.warnings]
        assert "BASELINE_VERY_LOW" in codes
        assert "BASELINE_NEAR_ZERO" in codes

    def test_baseline_near_zero_only_at_extreme(self):
        """Baseline 0.001 ≤ rate < 0.005 → BASELINE_VERY_LOW only (not NEAR_ZERO)."""
        result = calculate_plan({
            "baseline_conversion_rate": 0.001,
            "mde_pct": 20,
            "daily_traffic": 10000,
        })
        codes = [w.code.value for w in result.warnings]
        assert "BASELINE_NEAR_ZERO" not in codes
        # BASELINE_VERY_LOW should still fire since 0.001 < 0.005
        assert "BASELINE_VERY_LOW" in codes

class TestPlanningEdgeCases:
    """Edge cases for planning calculator."""

    def test_zero_traffic(self):
        """Zero daily traffic should be handled gracefully."""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 20,
            "daily_traffic": 0,
        })
        # Should not crash; feasibility decision may be not_recommended or escalate
        assert result.planning["feasibility"] in ["not_recommended", "infeasible"]

    def test_mde_over_100_percent(self):
        """MDE > 100% should be capped or handled gracefully."""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 200,
            "daily_traffic": 10000,
        })
        # Should not crash; planning should complete
        assert "estimated_days" in result.planning or "total_required" in result.planning

    def test_allocation_ratio_uneven(self):
        """Highly uneven allocation (90/10) should work."""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 10,
            "daily_traffic": 5000,
            "allocation": "custom",
            "allocation_ratio": "0.9/0.1"
        })
        assert result.planning["allocation_used"]["control"] == 0.9
        assert result.planning["allocation_used"]["variant"] == 0.1

    def test_mde_ci_95_order(self):
        """mde_ci_95 lower < upper."""
        result = calculate_plan({
            "baseline_conversion_rate": 0.05,
            "mde_pct": 10,
            "daily_traffic": 10000,
        })
        ci = result.planning.get("mde_ci_95")
        if ci:
            assert ci[0] < ci[1]

    def test_power_extreme_values(self):
        """Power very close to 1 or very low values."""
        result_low = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 20,
            "daily_traffic": 10000,
            "power": 0.5,
        })
        result_high = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 20,
            "daily_traffic": 10000,
            "power": 0.99,
        })
        # Higher power → larger required sample
        assert result_high.planning["total_required"] >= result_low.planning["total_required"]
