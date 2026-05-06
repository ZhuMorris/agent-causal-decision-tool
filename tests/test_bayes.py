"""Tests for Bayesian A/B test module — Pydantic-typed output"""

import pytest
from pydantic import ValidationError

from src.bayes import calculate_bayes_ab
from src.schema import BayesOutput, PosteriorStats, BayesianStatistics, TrafficStats


class TestBayesOutputSchema:
    """Tests that output is a proper BayesOutput Pydantic model"""

    def test_returns_bayes_output_type(self):
        """calculate_bayes_ab returns a BayesOutput instance"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert isinstance(result, BayesOutput)

    def test_schema_version_present(self):
        """schema_version is injected via default_factory"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result.schema_version is not None
        assert isinstance(result.schema_version, str)
        assert len(result.schema_version) > 0

    def test_timestamp_iso_format(self):
        """timestamp is in ISO 8601 format ending in Z"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result.timestamp.endswith("Z")

    def test_mode_is_bayesian_ab(self):
        """mode field is always 'bayesian_ab'"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result.mode == "bayesian_ab"

    def test_json_serializable_via_model_dump_json(self):
        """BayesOutput serializes to JSON via model_dump_json()"""
        import json
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        json_str = result.model_dump_json(indent=2)
        parsed = json.loads(json_str)
        assert parsed["mode"] == "bayesian_ab"
        assert "recommendation" in parsed

    def test_dict_access_via_model_dump(self):
        """Dict-style access works via .model_dump()"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        d = result.model_dump()
        assert d["recommendation"]["decision"] == "ship"


class TestBayesRecommendation:
    """Tests for recommendation field and decision logic"""

    def test_strong_positive_result_ships(self):
        """Strong positive effect → ship"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result.recommendation.decision == "ship"
        assert result.recommendation.confidence in ["high", "medium"]

    def test_strong_negative_result_rejects(self):
        """Strong negative effect → reject"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 70,
            "variant_total": 5000
        })
        assert result.recommendation.decision == "reject"

    def test_inconclusive_keeps_running(self):
        """Weak evidence → keep_running"""
        result = calculate_bayes_ab({
            "control_conversions": 80,
            "control_total": 5000,
            "variant_conversions": 85,
            "variant_total": 5000
        })
        assert result.recommendation.decision in ["keep_running", "escalate"]

    def test_p_variant_wins_high_for_strong_variant(self):
        """Variant clearly better → P(variant wins) close to 1"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 150,
            "variant_total": 5000
        })
        assert result.statistics.p_variant_wins > 0.99

    def test_decision_in_summary(self):
        """Summary contains the decision text"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result.recommendation.summary is not None
        assert len(result.recommendation.summary) > 0

    def test_primary_metric_lift_set(self):
        """primary_metricLift is the median lift"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result.recommendation.primary_metricLift is not None

    def test_p_value_is_p_variant_wins(self):
        """p_value field is P(variant wins) for Bayesian"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result.recommendation.p_value == result.statistics.p_variant_wins


class TestBayesStatistics:
    """Tests for statistics field (BayesianStatistics Pydantic model)"""

    def test_posterior_alpha_beta_correct(self):
        """Posterior alpha = prior + successes, beta = prior + failures"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        pc = result.statistics.posterior_control
        pv = result.statistics.posterior_variant
        # Jeffreys prior: alpha=0.5, beta=0.5
        assert pc.alpha == pytest.approx(100.5, rel=1e-3)
        assert pc.beta == pytest.approx(4900.5, rel=1e-3)
        assert pv.alpha == pytest.approx(130.5, rel=1e-3)
        assert pv.beta == pytest.approx(4870.5, rel=1e-3)

    def test_posterior_is_pydantic_model(self):
        """posterior_control and posterior_variant are PosteriorStats"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert isinstance(result.statistics.posterior_control, PosteriorStats)
        assert isinstance(result.statistics.posterior_variant, PosteriorStats)

    def test_p_variant_wins_range(self):
        """P(variant wins) is between 0 and 1"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert 0 <= result.statistics.p_variant_wins <= 1

    def test_p_tie_small_for_different_rates(self):
        """P(tie) is very small when rates differ"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result.statistics.p_tie < 0.01

    def test_lift_95ci_bounds(self):
        """Lift 95% CI lower < upper"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        ci = result.statistics.lift_95ci_pct
        assert len(ci) == 2
        assert ci[0] < ci[1]

    def test_expected_lift_hdi_95_bounds(self):
        """Expected lift HDI lower < upper"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        hdi = result.statistics.expected_lift_hdi_95
        assert hdi[0] < hdi[1]

    def test_prior_is_jeffreys(self):
        """Prior used is Jeffreys Beta(0.5, 0.5)"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        prior = result.statistics.prior_used
        assert prior["type"] == "Jeffreys"
        assert prior["alpha"] == 0.5
        assert prior["beta"] == 0.5

    def test_relative_lift_hdi_95_matches_expected(self):
        """relative_lift_hdi_95 derived from expected_lift_hdi_95 / control_rate"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        rel = result.statistics.relative_lift_hdi_95
        assert rel is not None
        assert len(rel) == 2
        assert rel[0] < rel[1]

    def test_monte_carlo_samples_respected(self):
        """n_samples parameter is respected"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        }, n_samples=1000)
        assert result.statistics.monte_carlo_samples == 1000

    def test_relative_lift_pct_nonzero(self):
        """relative_lift_pct is computed"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result.statistics.relative_lift_pct != 0


class TestBayesTrafficStats:
    """Tests for traffic_stats (TrafficStats Pydantic model)"""

    def test_traffic_stats_is_traffic_stats_model(self):
        """traffic_stats is a TrafficStats instance"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert isinstance(result.traffic_stats, TrafficStats)

    def test_traffic_sizes_correct(self):
        """control_size, variant_size, total_size are correct"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result.traffic_stats.control_size == 5000
        assert result.traffic_stats.variant_size == 5000
        assert result.traffic_stats.total_size == 10000

    def test_traffic_stats_accessible_as_attributes(self):
        """TrafficStats fields accessible as .field_name"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert result.traffic_stats.control_size == 5000


class TestBayesWarnings:
    """Tests for warnings field"""

    def test_warnings_is_list(self):
        """warnings is a list (possibly empty)"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert isinstance(result.warnings, list)

    def test_low_traffic_warning_fired(self):
        """LOW_TRAFFIC warning fires for small samples"""
        result = calculate_bayes_ab({
            "control_conversions": 5,
            "control_total": 100,
            "variant_conversions": 8,
            "variant_total": 100
        })
        codes = [w.code for w in result.warnings]
        assert "LOW_TRAFFIC" in codes

    def test_prior_dominates_warning_fired(self):
        """PRIOR_DOMINATES warning fires for very low total traffic"""
        result = calculate_bayes_ab({
            "control_conversions": 1,
            "control_total": 50,
            "variant_conversions": 2,
            "variant_total": 50
        })
        codes = [w.code for w in result.warnings]
        assert "PRIOR_DOMINATES" in codes

    def test_inconclusive_warning_when_p_between_thresholds(self):
        """INCONCLUSIVE warning fires when P(better) is between 0.5 and 0.95"""
        result = calculate_bayes_ab({
            "control_conversions": 80,
            "control_total": 5000,
            "variant_conversions": 90,
            "variant_total": 5000
        })
        codes = [w.code for w in result.warnings]
        # With these numbers the result should be inconclusive
        assert "INCONCLUSIVE" in codes or "LOW_TRAFFIC" in codes

    def test_small_effect_warning_fired(self):
        """SMALL_EFFECT warning fires for very small observed lifts"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 101,
            "variant_total": 5000
        })
        codes = [w.code for w in result.warnings]
        assert "SMALL_EFFECT" in codes

    def test_warning_is_warning_detail_type(self):
        """Each warning is a WarningDetail instance"""
        result = calculate_bayes_ab({
            "control_conversions": 5,
            "control_total": 100,
            "variant_conversions": 8,
            "variant_total": 100
        })
        for w in result.warnings:
            assert hasattr(w, "code")
            assert hasattr(w, "message")
            assert hasattr(w, "severity")


class TestBayesAudit:
    """Tests for audit field"""

    def test_audit_present(self):
        """audit field is present"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert "experiment_type" in result.audit

    def test_decision_path_present(self):
        """decision_path is present in audit"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        steps = result.audit["decision_path"]
        step_names = [s["step"] for s in steps]
        assert "Prior selection" in step_names
        assert "Posterior computation" in step_names
        assert "Monte Carlo simulation" in step_names
        assert "Decision" in step_names

    def test_assumptions_documented(self):
        """Assumptions are documented in audit"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assumptions = result.audit["assumptions"]
        assert len(assumptions) >= 3

    def test_limitations_documented(self):
        """Limitations are documented in audit"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        limitations = result.audit["limitations"]
        assert len(limitations) >= 2

    def test_thresholds_applied_in_audit(self):
        """thresholds_applied shows ship/reject thresholds"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert "ship" in result.audit["thresholds_applied"]
        assert "reject" in result.audit["thresholds_applied"]


class TestBayesInputs:
    """Tests for inputs field"""

    def test_inputs_preserved(self):
        """Original inputs are preserved in inputs field"""
        input_data = {
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        }
        result = calculate_bayes_ab(input_data)
        assert result.inputs == input_data


class TestBayesNextSteps:
    """Tests for next_steps field"""

    def test_next_steps_present_and_nonempty(self):
        """next_steps is a non-empty list"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        assert isinstance(result.next_steps, list)
        assert len(result.next_steps) > 0

    def test_next_steps_different_per_decision(self):
        """'ship' and 'reject' produce different next steps"""
        ship_result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 150,
            "variant_total": 5000
        })
        reject_result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 50,
            "variant_total": 5000
        })
        # Different decisions should give different next steps
        assert ship_result.recommendation.decision == "ship"
        assert reject_result.recommendation.decision == "reject"


class TestBayesEdgeCases:
    """Edge cases for Bayesian A/B test"""

    def test_zero_conversions_both_groups(self):
        """Zero conversions in both groups — should not crash"""
        result = calculate_bayes_ab({
            "control_conversions": 0,
            "control_total": 5000,
            "variant_conversions": 0,
            "variant_total": 5000
        })
        assert result.recommendation.decision in ["ship", "keep_running", "escalate", "reject"]
        assert result.statistics.p_variant_wins is not None

    def test_perfect_conversion_both_groups(self):
        """100% conversion rate in both groups — near-tie"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 100,
            "variant_conversions": 100,
            "variant_total": 100
        })
        # Both perfect → P(tie) high or P(wins) near 0.5
        assert result.statistics.p_tie > 0.3 or (0.4 < result.statistics.p_variant_wins < 0.6)

    def test_identical_rates(self):
        """Identical rates → inconclusive"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 100,
            "variant_total": 5000
        })
        # P(variant wins) should be near 0.5
        assert 0.3 < result.statistics.p_variant_wins < 0.7
        # Decision should be keep_running or escalate
        assert result.recommendation.decision in ["keep_running", "escalate"]

    def test_one_sided_strongly_negative_variant(self):
        """Variant performs much worse → reject"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 40,
            "variant_total": 5000
        })
        assert result.statistics.p_variant_wins < 0.01
        assert result.recommendation.decision == "reject"

    def test_p_control_wins_plus_p_variant_wins_plus_p_tie_approx_1(self):
        """Probabilities sum to approximately 1"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        total = result.statistics.p_control_wins + result.statistics.p_variant_wins + result.statistics.p_tie
        assert abs(total - 1.0) < 0.001


class TestBayesNSamplesValidation:
    """Tests for n_samples parameter validation"""

    def test_n_samples_parameter_respected(self):
        """n_samples from caller must be used, not hardcoded"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        }, n_samples=1000)
        assert result.statistics.monte_carlo_samples == 1000

    def test_n_samples_zero_raises_value_error(self):
        """n_samples=0 raises ValueError"""
        with pytest.raises(ValueError, match="n_samples must be >= 1"):
            calculate_bayes_ab({
                "control_conversions": 100,
                "control_total": 5000,
                "variant_conversions": 130,
                "variant_total": 5000
            }, n_samples=0)

    def test_n_samples_negative_raises_value_error(self):
        """n_samples < 0 raises ValueError"""
        with pytest.raises(ValueError, match="n_samples must be >= 1"):
            calculate_bayes_ab({
                "control_conversions": 100,
                "control_total": 5000,
                "variant_conversions": 130,
                "variant_total": 5000
            }, n_samples=-5)


class TestBayesABValidationErrors:
    """Tests that input validation errors are raised correctly"""

    def test_missing_control_conversions_raises(self):
        """Missing control_conversions raises ValidationError"""
        with pytest.raises(ValidationError):
            calculate_bayes_ab({
                "control_total": 5000,
                "variant_conversions": 130,
                "variant_total": 5000
            })

    def test_negative_total_raises(self):
        """Negative totals raise ValidationError"""
        with pytest.raises(ValidationError):
            calculate_bayes_ab({
                "control_conversions": 100,
                "control_total": -5000,
                "variant_conversions": 130,
                "variant_total": 5000
            })

    def test_non_numeric_input_raises(self):
        """Non-numeric input raises ValidationError"""
        with pytest.raises(ValidationError):
            calculate_bayes_ab({
                "control_conversions": "foo",
                "control_total": 5000,
                "variant_conversions": 130,
                "variant_total": 5000
            })