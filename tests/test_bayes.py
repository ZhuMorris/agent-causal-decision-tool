"""Tests for Bayesian A/B test module"""

import pytest
from src.bayes import calculate_bayes_ab


class TestBayesAB:
    """Bayesian A/B test unit tests"""

    def test_strong_positive_result_ships(self):
        """Strong positive effect → ship"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result["recommendation"]["decision"] == "ship"
        assert result["statistics"]["p_variant_wins"] > 0.95
        assert result["statistics"]["lift_median_pct"] > 0

    def test_strong_negative_result_rejects(self):
        """Strong negative effect → reject"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 70,
            "variant_total": 5000
        })
        assert result["recommendation"]["decision"] == "reject"
        assert result["statistics"]["p_variant_wins"] < 0.05

    def test_inconclusive_result_keeps_running(self):
        """Weak evidence → keep_running"""
        result = calculate_bayes_ab({
            "control_conversions": 80,
            "control_total": 5000,
            "variant_conversions": 85,
            "variant_total": 5000
        })
        assert result["recommendation"]["decision"] in ["keep_running", "escalate"]
        assert 0.05 < result["statistics"]["p_variant_wins"] < 0.95

    def test_p_variant_wins_high_for_strong_variant(self):
        """Variant clearly better → P(variant wins) close to 1"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 150,
            "variant_total": 5000
        })
        assert result["statistics"]["p_variant_wins"] > 0.99

    def test_posterior_alpha_beta_correct(self):
        """Posterior parameters should be alpha = prior + successes"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        pc = result["statistics"]["posterior_control"]
        pv = result["statistics"]["posterior_variant"]
        # Jeffreys prior: alpha=0.5, beta=0.5
        assert pc["alpha"] == pytest.approx(100.5, rel=1e-3)
        assert pc["beta"] == pytest.approx(4900.5, rel=1e-3)
        assert pv["alpha"] == pytest.approx(130.5, rel=1e-3)
        assert pv["beta"] == pytest.approx(4870.5, rel=1e-3)

    def test_lift_95ci_present(self):
        """Lift 95% CI should be present"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        ci = result["statistics"]["lift_95ci_pct"]
        assert len(ci) == 2
        assert ci[0] < ci[1]  # Lower bound < upper bound

    def test_p_tie_small(self):
        """P(tie) should be very small for different rates"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result["statistics"]["p_tie"] < 0.01

    def test_prior_is_jeffreys(self):
        """Prior should be Jeffreys Beta(0.5, 0.5)"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        prior = result["statistics"]["prior_used"]
        assert prior["type"] == "Jeffreys"
        assert prior["alpha"] == 0.5
        assert prior["beta"] == 0.5

    def test_decision_path_present(self):
        """Decision path should be present in audit"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert "decision_path" in result["audit"]
        steps = result["audit"]["decision_path"]
        step_names = [s["step"] for s in steps]
        assert "Prior selection" in step_names
        assert "Posterior computation" in step_names
        assert "Monte Carlo simulation" in step_names
        assert "Decision" in step_names

    def test_mode_is_bayesian_ab(self):
        """Mode should be bayesian_ab"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result["mode"] == "bayesian_ab"

    def test_traffic_stats_present(self):
        """Traffic stats should be present"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result["traffic_stats"]["control_size"] == 5000
        assert result["traffic_stats"]["variant_size"] == 5000
        assert result["traffic_stats"]["total_size"] == 10000

    def test_warnings_low_traffic(self):
        """Low traffic should produce LOW_TRAFFIC warning"""
        result = calculate_bayes_ab({
            "control_conversions": 5,
            "control_total": 100,
            "variant_conversions": 8,
            "variant_total": 100
        })
        warning_codes = [w["code"] for w in result.get("warnings", [])]
        assert "LOW_TRAFFIC" in warning_codes

    def test_inconclusive_warning_when_between_thresholds(self):
        """P(variant wins) between 0.5 and 0.95 should produce INCONCLUSIVE warning"""
        result = calculate_bayes_ab({
            "control_conversions": 80,
            "control_total": 5000,
            "variant_conversions": 90,
            "variant_total": 5000
        })
        p_vw = result["statistics"]["p_variant_wins"]
        if 0.5 < p_vw < 0.95 and result["recommendation"]["decision"] in ["keep_running", "escalate"]:
            warning_codes = [w["code"] for w in result.get("warnings", [])]
            assert "INCONCLUSIVE" in warning_codes

    def test_inputs_preserved(self):
        """Original inputs should be preserved"""
        input_data = {
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        }
        result = calculate_bayes_ab(input_data)
        assert result["inputs"] == input_data

    def test_next_steps_present(self):
        """Next steps should be present"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert len(result["next_steps"]) > 0


class TestBayesABEdgeCases:
    """Edge cases for Bayesian A/B test"""

    def test_zero_conversions_both_groups(self):
        """Zero conversions in both groups should not crash"""
        result = calculate_bayes_ab({
            "control_conversions": 0,
            "control_total": 5000,
            "variant_conversions": 0,
            "variant_total": 5000
        })
        assert result["recommendation"]["decision"] in ["ship", "keep_running", "escalate", "reject"]
        assert "p_variant_wins" in result["statistics"]

    def test_perfect_conversion_both(self):
        """100% conversion rate in both groups"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 100,
            "variant_conversions": 100,
            "variant_total": 100
        })
        # Both perfect - tie or near-tie
        assert result["statistics"]["p_tie"] > 0.5 or 0.4 < result["statistics"]["p_variant_wins"] < 0.6

    def test_identical_rates(self):
        """Identical conversion rates → P(variant wins) ≈ 0.5"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 100,
            "variant_total": 5000
        })
        # Should be close to 0.5 (within MC noise)
        assert 0.3 < result["statistics"]["p_variant_wins"] < 0.7
        # Decision should be keep_running or escalate (inconclusive)
        assert result["recommendation"]["decision"] in ["keep_running", "escalate"]

    def test_one_sided_test_negative_variant(self):
        """Variant performs much worse → control wins"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 40,
            "variant_total": 5000
        })
        assert result["statistics"]["p_variant_wins"] < 0.01
        assert result["recommendation"]["decision"] == "reject"

    def test_assumptions_documented(self):
        """Assumptions should be documented"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assumptions = result["audit"]["assumptions"]
        assert len(assumptions) >= 3

    def test_limitations_documented(self):
        """Limitations should be documented"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        limitations = result["audit"]["limitations"]
        assert len(limitations) >= 2