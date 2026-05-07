"""Tests for the easy-mode dispatcher."""

import pytest

from src.dispatcher import run_decision_workflow, _detect_method


class TestDetectMethod:
    def test_detects_ab(self):
        data = {
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 120,
            "variant_total": 5000,
        }
        assert _detect_method(data) == "ab"

    def test_detects_bayesian_flag(self):
        data = {
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 120,
            "variant_total": 5000,
            "bayesian": True,
        }
        assert _detect_method(data) == "bayesian"

    def test_detects_did(self):
        # DIDInput takes scalar floats (not lists) — matches schema
        data = {
            "pre_control": 1000.0,
            "post_control": 1200.0,
            "pre_treated": 200.0,
            "post_treated": 280.0,
        }
        assert _detect_method(data) == "did"

    def test_detects_planning(self):
        data = {
            "baseline_conversion_rate": 0.05,
            "mde_pct": 10,
        }
        assert _detect_method(data) == "planning"

    def test_detects_cohort_segments(self):
        data = {"segments": [{"name": "new_users", "control_conversions": 10, "control_total": 1000}]}
        assert _detect_method(data) == "cohort"

    def test_detects_cohort_breakdown(self):
        data = {"breakdown": [{"segment": "mobile", "control_conversions": 5, "control_total": 500}]}
        assert _detect_method(data) == "cohort"

    def test_unknown_input(self):
        data = {"foo": "bar"}
        assert _detect_method(data) == "unknown"

    def test_partial_ab_fields(self):
        data = {"control_conversions": 100, "control_total": 5000}
        assert _detect_method(data) == "unknown"

    def test_bayesian_flag_detected_as_bayesian(self):
        # bayesian=True signals Bayesian intent to the detector
        # Missing AB fields will surface as a validation error from run_workflow
        data = {"bayesian": True}
        assert _detect_method(data) == "bayesian"

    def test_planning_partial_missing_mde(self):
        data = {"baseline_conversion_rate": 0.05}
        assert _detect_method(data) == "unknown"


class TestRunDecisionWorkflowAB:
    def test_ab_returns_unified_output(self):
        result = run_decision_workflow({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 120,
            "variant_total": 5000,
        })
        assert result.decision in ("ship", "keep_running", "reject", "escalate")
        assert result.selected_method == "ab_test"
        assert result.schema_version is not None
        assert result.timestamp is not None
        assert result.internal_result is not None

    def test_ab_internal_result_contains_inputs(self):
        result = run_decision_workflow({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 120,
            "variant_total": 5000,
        })
        # inputs are stored inside internal_result
        assert result.internal_result["inputs"]["control_conversions"] == 100
        assert result.internal_result["inputs"]["control_total"] == 5000

    def test_ab_rejects_negative_conversions(self):
        with pytest.raises(Exception):  # Pydantic validation error
            run_decision_workflow({
                "control_conversions": -1,
                "control_total": 5000,
                "variant_conversions": 120,
                "variant_total": 5000,
            })


class TestRunDecisionWorkflowBayesian:
    def test_bayesian_returns_unified_output(self):
        result = run_decision_workflow({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 120,
            "variant_total": 5000,
            "bayesian": True,
        })
        assert result.decision in ("ship", "keep_running", "reject", "escalate")
        assert result.selected_method == "bayesian_ab"
        assert result.internal_result is not None


class TestRunDecisionWorkflowDiD:
    def test_did_returns_unified_output(self):
        # DIDInput takes scalar floats (not lists)
        result = run_decision_workflow({
            "pre_control": 1000.0,
            "post_control": 1200.0,
            "pre_treated": 200.0,
            "post_treated": 280.0,
        })
        assert result.decision in ("ship", "keep_running", "reject", "escalate")
        assert result.selected_method == "did"
        assert result.internal_result is not None

    def test_did_has_selection_reason(self):
        result = run_decision_workflow({
            "pre_control": 1000.0,
            "post_control": 1200.0,
            "pre_treated": 200.0,
            "post_treated": 280.0,
        })
        assert "DiD" in result.selection_reason or "did" in result.selection_reason.lower()


class TestRunDecisionWorkflowPlanning:
    def test_planning_returns_unified_output(self):
        result = run_decision_workflow({
            "baseline_conversion_rate": 0.05,
            "mde_pct": 10,
            "daily_traffic": 10000,
        })
        assert result.selected_method == "planning"
        assert result.decision in ("ship", "keep_running", "reject", "escalate")
        assert result.internal_result is not None


class TestRunDecisionWorkflowErrors:
    def test_unknown_input_raises_value_error(self):
        with pytest.raises(ValueError) as exc_info:
            run_decision_workflow({"foo": "bar"})
        assert "Cannot determine method" in str(exc_info.value)

    def test_error_includes_supported_methods(self):
        with pytest.raises(ValueError) as exc_info:
            run_decision_workflow({"foo": "bar"})
        msg = str(exc_info.value)
        assert "control_conversions" in msg or "A/B" in msg
        assert "pre_control" in msg or "DiD" in msg
        assert "baseline" in msg or "Planning" in msg

    def test_bayesian_flag_missing_ab_fields_raises(self):
        # detect returns bayesian, but run_workflow fails due to missing AB fields
        with pytest.raises(Exception):  # Pydantic validation error
            run_decision_workflow({"bayesian": True})
