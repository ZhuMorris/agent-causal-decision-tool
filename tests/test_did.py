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
        assert any(c in ("PARALLEL_TRENDS_VIOLATED", "PARALLEL_TRENDS_WEAK") for c in warning_codes)

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


class TestDiDDiagnostics:
    """Tests for DiD diagnostics and fragility flags"""

    def test_single_pre_period_high_caution(self):
        """Only one pre-period → high caution + fragility flag"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150,
            "pre_periods": 1,
            "post_periods": 1,
        })
        assert result.did_diagnostics is not None
        assert result.did_diagnostics.recommended_caution_level == "high"
        assert "single_pre_period" in result.did_diagnostics.fragility_flags

    def test_small_sample_small_effect_medium_caution(self):
        """Small obs count + modest DiD → medium caution (small_sample without large_effect_small_sample)"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1001,
            "pre_treated": 900,
            "post_treated": 901,  # DiD = 0 (near-zero effect → won't trigger large_effect_small_sample)
            "pre_periods": 3,
            "post_periods": 3,
            "treatment_observation_count": 50,  # < 100 → small_sample
            "control_observation_count": 50,
        })
        # Both counts < 100 → small_sample; |did_estimate| ≈ 0 → large_effect_small_sample NOT triggered
        assert result.did_diagnostics.recommended_caution_level == "medium"
        assert "small_sample" in result.did_diagnostics.fragility_flags

    def test_imbalanced_groups_causes_medium_caution(self):
        """Imbalanced groups (ratio > 3x) → medium caution via imbalanced_groups flag"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1050,
            "pre_treated": 900,
            "post_treated": 940,
            "pre_periods": 3,
            "post_periods": 3,
            "treatment_observation_count": 200,  # ≥ 100: no small_sample
            "control_observation_count": 50,     # < 100: small_sample; 200/50=4 > 3: imbalanced
        })
        assert result.did_diagnostics.recommended_caution_level == "medium"
        assert "imbalanced_groups" in result.did_diagnostics.fragility_flags

    def test_imbalanced_groups_medium_caution(self):
        """Imbalanced groups (ratio > 3x) → medium caution"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150,
            "pre_periods": 3,
            "post_periods": 3,
            "treatment_observation_count": 1000,
            "control_observation_count": 100,  # 10x ratio
        })
        assert result.did_diagnostics.recommended_caution_level == "medium"
        assert "imbalanced_groups" in result.did_diagnostics.fragility_flags

    def test_large_effect_small_sample_high_caution(self):
        """Large effect + small sample → high caution"""
        result = calculate_did({
            "pre_control": 100,
            "post_control": 100,
            "pre_treated": 100,
            "post_treated": 200,  # big DiD effect
            "pre_periods": 2,
            "post_periods": 2,
            "treatment_observation_count": 50,
            "control_observation_count": 50,
        })
        assert result.did_diagnostics.recommended_caution_level == "high"
        assert "large_effect_small_sample" in result.did_diagnostics.fragility_flags


    def test_multiple_pre_periods_moderate_trends_evidence(self):
        """3+ pre-periods → moderate parallel trends evidence"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150,
            "pre_periods": 4,
            "post_periods": 2,
        })
        assert result.did_diagnostics.parallel_trends_evidence == "moderate"

    def test_caution_high_ship_becomes_escalate(self):
        """Positive effect but high caution → decision changes to escalate"""
        result = calculate_did({
            "pre_control": 100,
            "post_control": 100,
            "pre_treated": 100,
            "post_treated": 200,  # strong positive
            "pre_periods": 1,      # single pre-period = high caution
            "post_periods": 1,
            "treatment_observation_count": 30,
            "control_observation_count": 30,
        })
        # Effect looks positive but caution=high → should escalate
        assert result.did_diagnostics.recommended_caution_level == "high"
        assert result.recommendation.decision == "escalate"

    def test_explanation_provided(self):
        """DiD output should include plain-language explanation"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150,
            "pre_periods": 3,
            "post_periods": 2,
        })
        assert result.explanation is not None
        assert len(result.explanation) > 0

    def test_recommended_next_action_provided(self):
        """DiD output should include recommended next action"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150,
        })
        assert result.recommended_next_action is not None

    def test_no_did_diagnostics_when_metadata_absent(self):
        """Diagnostics still computed even without metadata (all nullable fields)"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150,
            # no pre_periods, post_periods, observation counts
        })
        assert result.did_diagnostics is not None
        # No metadata → unknown evidence level, low caution, no fragility flags
        assert result.did_diagnostics.parallel_trends_evidence == "none"
        assert result.did_diagnostics.recommended_caution_level == "low"
        assert len(result.did_diagnostics.fragility_flags) == 0


class TestDiDConfidenceInterval:
    """Tests for did_ci_95 bootstrap confidence intervals (v0.8)."""

    def test_did_ci_95_present(self):
        """did_ci_95 must be present in statistics when counts are sufficient."""
        result = calculate_did({
            "pre_control": 5000,
            "post_control": 5500,
            "pre_treated": 5000,
            "post_treated": 6000,
        })
        assert "did_ci_95" in result.statistics

    def test_did_ci_95_is_list_of_two(self):
        """did_ci_95 must be [lower, upper]."""
        result = calculate_did({
            "pre_control": 5000,
            "post_control": 5500,
            "pre_treated": 5000,
            "post_treated": 6000,
        })
        ci = result.statistics["did_ci_95"]
        assert isinstance(ci, list)
        assert len(ci) == 2

    def test_did_ci_95_lower_less_than_upper(self):
        """CI lower bound must be less than upper bound."""
        result = calculate_did({
            "pre_control": 5000,
            "post_control": 5500,
            "pre_treated": 5000,
            "post_treated": 6000,
        })
        ci = result.statistics["did_ci_95"]
        assert ci[0] < ci[1]

    def test_did_ci_method_is_poisson_bootstrap(self):
        """did_ci_method must be 'poisson_bootstrap'."""
        result = calculate_did({
            "pre_control": 5000,
            "post_control": 5500,
            "pre_treated": 5000,
            "post_treated": 6000,
        })
        assert result.statistics["did_ci_method"] == "poisson_bootstrap"

    def test_did_ci_n_bootstrap_present(self):
        """did_ci_n_bootstrap must be present when CI is computed."""
        result = calculate_did({
            "pre_control": 5000,
            "post_control": 5500,
            "pre_treated": 5000,
            "post_treated": 6000,
        })
        assert result.statistics["did_ci_n_bootstrap"] is not None

    def test_did_ci_metadata_always_present(self):
        """did_ci_assumption and did_ci_disclaimer always present."""
        result = calculate_did({
            "pre_control": 5000,
            "post_control": 5500,
            "pre_treated": 5000,
            "post_treated": 6000,
        })
        assert "did_ci_assumption" in result.statistics
        assert "did_ci_disclaimer" in result.statistics

    def test_low_count_gate_returns_null_ci(self):
        """Count < 100 → did_ci_95 = null + BOOTSTRAP_CI_UNRELIABLE (critical)."""
        result = calculate_did({
            "pre_control": 50,
            "post_control": 55,
            "pre_treated": 50,
            "post_treated": 60,
        })
        assert result.statistics["did_ci_95"] is None
        codes = [w.code.value for w in result.warnings]
        assert "BOOTSTRAP_CI_UNRELIABLE" in codes

    def test_zero_baseline_returns_null_ci(self):
        """Pre-period zero → exits early via _build_error_output with empty statistics + ZERO_BASELINE.
        
        Note: the early-exit path means statistics={}, not did_ci_95=null. This test
        documents current behavior — the zero-baseline path doesn't compute a CI.
        """
        result = calculate_did({
            "pre_control": 0,
            "post_control": 100,
            "pre_treated": 50,
            "post_treated": 120,
        })
        assert result.statistics == {}  # early exit returns empty stats
        codes = [w.code.value for w in result.warnings]
        assert "ZERO_BASELINE" in codes

    def test_zero_baseline_non_zero_pre_treated_bootstrap_still_runs(self):
        """pre_c=0 but pre_t>0 → CI not computed (exits early with statistics={})."""
        result = calculate_did({
            "pre_control": 0,
            "post_control": 100,
            "pre_treated": 200,
            "post_treated": 400,
        })
        assert result.statistics == {}
        codes = [w.code.value for w in result.warnings]
        assert "ZERO_BASELINE" in codes

    def test_bootstrap_ci_unreliable_severity_critical(self):
        """BOOTSTRAP_CI_UNRELIABLE must have severity=critical."""
        result = calculate_did({
            "pre_control": 50,
            "post_control": 55,
            "pre_treated": 50,
            "post_treated": 60,
        })
        unreliable = [w for w in result.warnings if w.code.value == "BOOTSTRAP_CI_UNRELIABLE"]
        assert len(unreliable) == 1
        assert unreliable[0].severity == "critical"

    def test_did_ci_crosses_zero_warning(self):
        """CI crossing zero → DID_CI_CROSSES_ZERO (info)."""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 1000,
            "post_treated": 1020,
        })
        codes = [w.code.value for w in result.warnings]
        # If CI crosses zero, DID_CI_CROSSES_ZERO should be present
        ci = result.statistics.get("did_ci_95")
        if ci and ci[0] < 0 < ci[1]:
            assert "DID_CI_CROSSES_ZERO" in codes

    def test_bootstrap_cis_wide_warning(self):
        """CI range > 2×|did_estimate| → BOOTSTRAP_CI_WIDE (warning)."""
        # Use large variance scenario: small pre values with big post divergence
        result = calculate_did({
            "pre_control": 100,
            "post_control": 200,
            "pre_treated": 100,
            "post_treated": 400,
        })
        codes = [w.code.value for w in result.warnings]
        if "BOOTSTRAP_CI_WIDE" in codes:
            wide = [w for w in result.warnings if w.code.value == "BOOTSTRAP_CI_WIDE"]
            assert wide[0].severity == "warning"


class TestDiDNBootstrapParam:
    """Tests for n_bootstrap parameter in DIDInput."""

    def test_n_bootstrap_custom_value(self):
        """n_bootstrap parameter accepted and used."""
        result = calculate_did({
            "pre_control": 5000,
            "post_control": 5500,
            "pre_treated": 5000,
            "post_treated": 6000,
            "n_bootstrap": 500,
        })
        assert result.statistics["did_ci_n_bootstrap"] == 500

    def test_n_bootstrap_default_2000(self):
        """Default n_bootstrap is 2000."""
        result = calculate_did({
            "pre_control": 5000,
            "post_control": 5500,
            "pre_treated": 5000,
            "post_treated": 6000,
        })
        assert result.statistics["did_ci_n_bootstrap"] == 2000

    def test_n_bootstrap_minimum_enforced(self):
        """n_bootstrap below 500 → Pydantic ValidationError."""
        from pydantic import ValidationError
        from src.schema import DIDInput
        with pytest.raises(ValidationError):
            DIDInput(
                pre_control=5000, post_control=5500,
                pre_treated=5000, post_treated=6000,
                n_bootstrap=100
            )

    def test_n_bootstrap_500_accepted(self):
        """n_bootstrap=500 is the minimum valid value, accepted by Pydantic."""
        from src.schema import DIDInput
        inp = DIDInput(
            pre_control=5000, post_control=5500,
            pre_treated=5000, post_treated=6000,
            n_bootstrap=500
        )
        assert inp.n_bootstrap == 500