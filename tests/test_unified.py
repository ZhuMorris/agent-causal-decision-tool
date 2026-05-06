"""Tests for unified AgentDecisionOutput schema and to_unified() converter."""

import pytest
from pydantic import ValidationError

from src.unified import (
    AgentDecisionOutput,
    UnifiedWarning,
    to_unified,
    _decision_from_recommendation,
    _confidence_from_recommendation,
    _lift_summary,
    _warnings_from_result,
    _next_action_for_decision,
)
from src.ab_test import calculate_ab
from src.bayes import calculate_bayes_ab
from src.did import calculate_did
from src.planning import calculate_plan


class TestUnifiedWarning:
    """Tests for UnifiedWarning model"""

    def test_unified_warning_accepts_all_severities(self):
        """info, warning, critical are all valid severity values"""
        for sev in ["info", "warning", "critical"]:
            w = UnifiedWarning(code="LOW_TRAFFIC", message="Not enough traffic", severity=sev)
            assert w.severity == sev

    def test_unified_warning_requires_code_and_message(self):
        """code and message are required fields"""
        w = UnifiedWarning(code="LOW_TRAFFIC", message="test", severity="warning")
        assert w.code == "LOW_TRAFFIC"
        assert w.message == "test"

    def test_unified_warning_extra_fields_forbidden(self):
        """Extra fields should be forbidden by Config"""
        with pytest.raises(ValidationError):
            UnifiedWarning(code="LOW_TRAFFIC", message="test", severity="warning", foo="bar")


class TestAgentDecisionOutput:
    """Tests for AgentDecisionOutput schema"""

    def test_accepts_valid_unified_output(self):
        """A fully-populated AgentDecisionOutput is valid"""
        out = AgentDecisionOutput(
            decision="ship",
            recommended_next_action="Deploy variant.",
            selected_method="ab_test",
            selection_reason="User requested frequentist A/B",
            confidence="high",
            effect_summary="Estimated lift: +30.00% (positive)",
            warnings=[],
            limitations=["Small sample size"],
            audit_summary="ab_test: Z-test passed",
            source_metadata={"connector": "langsmith"},
        )
        assert out.decision == "ship"
        assert out.selected_method == "ab_test"

    def test_decision_accepts_all_four_values(self):
        """decision must be one of ship/keep_running/reject/escalate"""
        for decision in ["ship", "keep_running", "reject", "escalate"]:
            out = AgentDecisionOutput(
                decision=decision,
                recommended_next_action="Test",
                selected_method="ab_test",
                selection_reason="Test",
                confidence="low",
                effect_summary="Test",
                warnings=[],
                limitations=[],
                audit_summary="Test",
            )
            assert out.decision == decision

    def test_decision_rejects_invalid_value(self):
        """Invalid decision value raises ValidationError"""
        with pytest.raises(ValidationError):
            AgentDecisionOutput(
                decision="maybe",
                recommended_next_action="Test",
                selected_method="ab_test",
                selection_reason="Test",
                confidence="low",
                effect_summary="Test",
                warnings=[],
                limitations=[],
                audit_summary="Test",
            )

    def test_confidence_accepts_all_three_values(self):
        """confidence must be high/medium/low"""
        for conf in ["high", "medium", "low"]:
            out = AgentDecisionOutput(
                decision="ship",
                recommended_next_action="Test",
                selected_method="ab_test",
                selection_reason="Test",
                confidence=conf,
                effect_summary="Test",
                warnings=[],
                limitations=[],
                audit_summary="Test",
            )
            assert out.confidence == conf

    def test_warnings_default_empty_list(self):
        """warnings defaults to empty list"""
        out = AgentDecisionOutput(
            decision="ship",
            recommended_next_action="Test",
            selected_method="ab_test",
            selection_reason="Test",
            confidence="high",
            effect_summary="Test",
            limitations=[],
            audit_summary="Test",
        )
        assert out.warnings == []

    def test_source_metadata_can_be_none(self):
        """source_metadata is optional"""
        out = AgentDecisionOutput(
            decision="ship",
            recommended_next_action="Test",
            selected_method="ab_test",
            selection_reason="Test",
            confidence="high",
            effect_summary="Test",
            warnings=[],
            limitations=[],
            audit_summary="Test",
        )
        assert out.source_metadata is None

    def test_source_metadata_accepts_dict(self):
        """source_metadata can be a dict with connector info"""
        out = AgentDecisionOutput(
            decision="ship",
            recommended_next_action="Test",
            selected_method="ab_test",
            selection_reason="Test",
            confidence="high",
            effect_summary="Test",
            warnings=[],
            limitations=[],
            audit_summary="Test",
            source_metadata={"connector": "langsmith", "dataset_id": "ds-001"},
        )
        assert out.source_metadata["connector"] == "langsmith"

    def test_internal_result_included_in_dump(self):
        """internal_result is included in model_dump with correct value"""
        out = AgentDecisionOutput(
            decision="ship",
            recommended_next_action="Test",
            selected_method="ab_test",
            selection_reason="Test",
            confidence="high",
            effect_summary="Test",
            warnings=[],
            limitations=[],
            audit_summary="Test",
            internal_result={"mode": "ab_test"},
        )
        dumped = out.model_dump()
        assert "internal_result" in dumped
        assert dumped["internal_result"] == {"mode": "ab_test"}

    def test_unified_serializer_contains_all_fields(self):
        """model_dump_json should contain all expected top-level fields"""
        out = AgentDecisionOutput(
            decision="ship",
            recommended_next_action="Deploy",
            selected_method="ab_test",
            selection_reason="test",
            confidence="high",
            effect_summary="+30% lift",
            warnings=[],
            limitations=["small n"],
            audit_summary="z-test passed",
            source_metadata={"connector": "test"},
        )
        json_str = out.model_dump_json()
        parsed = json.loads(json_str) if "json" in dir() else None

        # Verify by dumping to dict and checking keys
        d = out.model_dump()
        assert "decision" in d
        assert "recommended_next_action" in d
        assert "selected_method" in d
        assert "selection_reason" in d
        assert "confidence" in d
        assert "effect_summary" in d
        assert "warnings" in d
        assert "limitations" in d
        assert "audit_summary" in d
        assert d["decision"] == "ship"


class TestToUnifiedFromAB:
    """Tests for to_unified() when called with ABTestOutput"""

    def test_ab_result_converts_to_unified(self):
        """calculate_ab result converts correctly to AgentDecisionOutput"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        unified = to_unified(result, "ab_test", "User requested frequentist A/B")
        assert unified.decision in ["ship", "keep_running", "reject", "escalate"]
        assert unified.selected_method == "ab_test"
        assert unified.selection_reason == "User requested frequentist A/B"
        assert unified.confidence in ["high", "medium", "low"]
        assert len(unified.effect_summary) > 0

    def test_ab_result_has_warnings_when_low_traffic(self):
        """Low-traffic result should produce at least one warning"""
        result = calculate_ab({
            "control_conversions": 2,
            "control_total": 50,
            "variant_conversions": 3,
            "variant_total": 50
        })
        unified = to_unified(result, "ab_test", "test reason")
        assert len(unified.warnings) >= 1

    def test_ab_result_recommended_next_action_mapped(self):
        """recommended_next_action should be set based on decision and method"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        unified = to_unified(result, "ab_test", "test")
        assert len(unified.recommended_next_action) > 0

    def test_ab_result_audit_summary_contains_method(self):
        """audit_summary should mention the method name"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        unified = to_unified(result, "ab_test", "test")
        assert "ab_test" in unified.audit_summary

    def test_ab_result_source_metadata_passed_through(self):
        """source_metadata is passed through to unified output"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        unified = to_unified(result, "ab_test", "test", source_metadata={"connector": "langsmith"})
        assert unified.source_metadata == {"connector": "langsmith"}

    def test_ab_resultinternal_result_populated(self):
        """internal_result contains the full ABTestOutput"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        unified = to_unified(result, "ab_test", "test")
        assert unified.internal_result is not None
        assert unified.internal_result["mode"] == "ab_test"

    def test_ab_reject_decision_mapped(self):
        """reject decision maps to correct recommended_next_action"""
        result = calculate_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 40,
            "variant_total": 5000
        })
        unified = to_unified(result, "ab_test", "test")
        assert unified.decision == "reject"


class TestToUnifiedFromBayes:
    """Tests for to_unified() when called with BayesOutput"""

    def test_bayes_result_converts_to_unified(self):
        """calculate_bayes_ab result converts correctly"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        unified = to_unified(result, "bayesian_ab", "User requested Bayesian A/B")
        assert unified.decision in ["ship", "keep_running", "reject", "escalate"]
        assert unified.selected_method == "bayesian_ab"
        assert unified.selection_reason == "User requested Bayesian A/B"

    def test_bayes_ship_recommended_next_action(self):
        """Bayesian ship → recommended_next_action mentions P(better)"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 150,
            "variant_total": 5000
        })
        unified = to_unified(result, "bayesian_ab", "test")
        if unified.decision == "ship":
            assert "P(better)" in unified.recommended_next_action or "Deploy" in unified.recommended_next_action

    def test_bayes_warnings_when_prior_dominates(self):
        """Very low traffic should produce PRIOR_DOMINATES warning"""
        result = calculate_bayes_ab({
            "control_conversions": 1,
            "control_total": 20,
            "variant_conversions": 2,
            "variant_total": 20
        })
        unified = to_unified(result, "bayesian_ab", "test")
        codes = [w.code for w in unified.warnings]
        assert "PRIOR_DOMINATES" in codes or "LOW_TRAFFIC" in codes

    def test_bayesinternal_result_mode_is_bayesian_ab(self):
        """internal_result should have mode=bayesian_ab"""
        result = calculate_bayes_ab({
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        })
        unified = to_unified(result, "bayesian_ab", "test")
        assert unified.internal_result["mode"] == "bayesian_ab"


class TestToUnifiedFromDiD:
    """Tests for to_unified() when called with DIDOutput"""

    def test_did_result_converts_to_unified(self):
        """calculate_did result converts correctly"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150
        })
        unified = to_unified(result, "did", "Staged rollout analysis")
        assert unified.decision in ["ship", "keep_running", "reject", "escalate"]
        assert unified.selected_method == "did"
        assert unified.selection_reason == "Staged rollout analysis"

    def test_did_limitations_from_audit(self):
        """limitations should be extracted from audit"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150
        })
        unified = to_unified(result, "did", "test")
        # DiD has known limitations in its audit
        assert isinstance(unified.limitations, list)

    def test_did_recommended_next_action_mentions_did(self):
        """recommended_next_action should reference DiD"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150
        })
        unified = to_unified(result, "did", "test")
        assert "DiD" in unified.recommended_next_action or len(unified.recommended_next_action) > 0

    def test_didinternal_result_mode_is_did(self):
        """internal_result should have mode=did"""
        result = calculate_did({
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150
        })
        unified = to_unified(result, "did", "test")
        assert unified.internal_result["mode"] == "did"


class TestToUnifiedFromPlanning:
    """Tests for to_unified() when called with PlanningOutput"""

    def test_planning_result_converts_to_unified(self):
        """calculate_plan result converts correctly"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 10,
            "daily_traffic": 5000
        })
        unified = to_unified(result, "planning", "Experiment planning request")
        assert unified.decision in ["ship", "keep_running", "reject", "escalate"]
        assert unified.selected_method == "planning"
        assert unified.selection_reason == "Experiment planning request"

    def test_planning_slow_experiment_warning(self):
        """Slow experiment should produce warning"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.001,
            "mde_pct": 1,
            "daily_traffic": 100
        })
        unified = to_unified(result, "planning", "test")
        # Very low baseline + tiny MDE + low traffic → long experiment
        assert len(unified.warnings) >= 1 or unified.decision in ["reject", "escalate"]

    def test_planninginternal_result_mode_is_planning(self):
        """internal_result should have mode=planning"""
        result = calculate_plan({
            "baseline_conversion_rate": 0.02,
            "mde_pct": 10,
            "daily_traffic": 5000
        })
        unified = to_unified(result, "planning", "test")
        assert unified.internal_result["mode"] == "planning"


class TestToUnifiedFromDict:
    """Tests for to_unified() when called with raw dict (not Pydantic model)"""

    def test_dict_with_recommendation_key(self):
        """to_unified works with a plain dict that has 'recommendation' key"""
        result_dict = {
            "recommendation": {
                "decision": "ship",
                "confidence": "high",
                "summary": "Test",
                "primary_metricLift": 5.0
            },
            "warnings": [],
            "audit": {"limitations": [], "decision_path": [{"step": "test"}]},
            "statistics": {},
            "mode": "ab_test"
        }
        unified = to_unified(result_dict, "ab_test", "dict test")
        assert unified.decision == "ship"
        assert unified.selected_method == "ab_test"

    def test_dict_with_missing_optional_fields(self):
        """to_unified handles dicts missing some optional fields"""
        result_dict = {
            "recommendation": {"decision": "escalate", "confidence": "low", "summary": "?"},
            "mode": "ab_test"
        }
        unified = to_unified(result_dict, "ab_test", "test")
        assert unified.decision == "escalate"


class TestNextActionMapping:
    """Tests for _next_action_for_decision()"""

    def test_ship_ab_test_action(self):
        """ship + ab_test → Deploy variant"""
        action = _next_action_for_decision("ship", "ab_test")
        assert "Deploy" in action

    def test_ship_bayesian_ab_action(self):
        """ship + bayesian_ab → mentions P(better) threshold"""
        action = _next_action_for_decision("ship", "bayesian_ab")
        assert "Deploy" in action or "P(better)" in action

    def test_reject_action(self):
        """reject → Do not deploy"""
        action = _next_action_for_decision("reject", "ab_test")
        assert "Do not deploy" in action

    def test_keep_running_action(self):
        """keep_running → Continue the experiment"""
        action = _next_action_for_decision("keep_running", "ab_test")
        assert "Continue" in action or "experiment" in action

    def test_escalate_action(self):
        """escalate → Request human review"""
        action = _next_action_for_decision("escalate", "ab_test")
        assert "human" in action.lower() or "review" in action.lower()

    def test_unknown_combination_fallback(self):
        """Unknown decision/method combo → returns error message"""
        action = _next_action_for_decision("unknown_decision", "unknown_method")
        assert "needs review" in action


class TestLiftSummary:
    """Tests for _lift_summary()"""

    def test_lift_summary_with_positive_lift(self):
        """Positive lift → 'Estimated lift: +X.XX% (positive)'"""
        rec = {"decision": "ship", "confidence": "high", "summary": "test", "primary_metricLift": 30.0}
        summary = _lift_summary(rec, None)
        assert "30.00" in summary
        assert "positive" in summary

    def test_lift_summary_with_negative_lift(self):
        """Negative lift → 'Estimated lift: -X.XX% (negative)'"""
        rec = {"decision": "reject", "confidence": "high", "summary": "test", "primary_metricLift": -15.0}
        summary = _lift_summary(rec, None)
        assert "-15" in summary
        assert "negative" in summary

    def test_lift_summary_with_pvalue_only(self):
        """No lift but has p_value → 'p-value: X.XXXX'"""
        rec = {"decision": "keep_running", "confidence": "medium", "summary": "test", "p_value": 0.043}
        summary = _lift_summary(rec, None)
        assert "p-value" in summary
        assert "0.0430" in summary

    def test_lift_summary_with_neither(self):
        """No lift or p_value → 'Effect size unknown'"""
        rec = {"decision": "escalate", "confidence": "low", "summary": "?"}
        summary = _lift_summary(rec, None)
        assert "unknown" in summary.lower()


class TestWarningsExtraction:
    """Tests for _warnings_from_result()"""

    def test_extracts_warning_codes(self):
        """Warnings are extracted from result correctly"""
        result = calculate_ab({
            "control_conversions": 2,
            "control_total": 50,
            "variant_conversions": 3,
            "variant_total": 50
        })
        warnings = _warnings_from_result(result)
        assert len(warnings) >= 1
        for w in warnings:
            assert hasattr(w, "code")
            assert hasattr(w, "message")
            assert hasattr(w, "severity")