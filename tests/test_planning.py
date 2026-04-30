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
        """Estimated days > 30 → LONG_EXP warning"""
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
        assert "LONG_EXP" in warning_codes

    def test_not_recommended_suggests_did(self):
        """When not_recommended, should suggest DiD"""
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
        assert "NOT_RECOMMENDED" in warning_codes
        did_warning = next((w for w in result.warnings if w.code == "NOT_RECOMMENDED"), None)
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