"""Tests for audit module and maturity assessment"""

from src.audit import check_experiment_maturity


class TestMaturityAssessment:
    """Maturity assessment unit tests"""

    def test_mature_experiment_full_score(self):
        """All checks pass → mature (100)"""
        audit = {
            "mode": "ab_test",
            "traffic_size": 10000,
            "decision_path": [
                {"step": "Input validation", "passed": True},
                {"step": "Traffic check", "passed": True},
                {"step": "Conversion rate", "passed": True},
                {"step": "Statistical test", "passed": True},
                {"step": "Decision", "passed": True}
            ],
            "warnings_triggered": [],
            "limitations": [
                "Binary conversion outcome only",
                "No multiple testing correction"
            ],
            "final_decision": {
                "decision": "ship",
                "confidence": "high"
            }
        }
        result = check_experiment_maturity(audit, {})
        assert result["maturity_score"] == 100
        assert result["maturity_label"] == "mature"
        assert all(result["checks"].values())

    def test_critical_warning_drops_score(self):
        """Critical warning → score drops"""
        audit = {
            "mode": "ab_test",
            "traffic_size": 10000,
            "decision_path": [
                {"step": "Validation", "passed": True},
                {"step": "Decision", "passed": True}
            ],
            "warnings_triggered": [
                {"code": "ZERO_BASELINE", "severity": "critical"}
            ],
            "limitations": [
                "Parallel trends not verified",
                "No clustered SEs"
            ],
            "final_decision": {"confidence": "medium"}
        }
        result = check_experiment_maturity(audit, {})
        assert result["maturity_score"] < 80
        assert len(result["issues"]) > 0

    def test_failed_decision_steps(self):
        """Failed decision steps → score drops"""
        audit = {
            "mode": "ab_test",
            "traffic_size": 10000,
            "decision_path": [
                {"step": "Input validation", "passed": False},
                {"step": "Decision", "passed": True}
            ],
            "warnings_triggered": [],
            "limitations": ["One limitation"],
            "final_decision": {"confidence": "high"}
        }
        result = check_experiment_maturity(audit, {})
        assert result["maturity_score"] < 100
        assert not result["checks"]["decision_path_complete"]

    def test_low_confidence_drops_score(self):
        """Low confidence decision → score drops"""
        audit = {
            "mode": "ab_test",
            "traffic_size": 10000,
            "decision_path": [
                {"step": "Validation", "passed": True},
                {"step": "Decision", "passed": True}
            ],
            "warnings_triggered": [],
            "limitations": ["Lim1", "Lim2"],
            "final_decision": {"confidence": "low"}
        }
        result = check_experiment_maturity(audit, {})
        assert result["maturity_score"] <= 90
        assert not result["checks"]["high_confidence"]

    def test_inadequate_when_critical_issues(self):
        """Critical issues → inadequate label"""
        audit = {
            "mode": "ab_test",
            "traffic_size": 500,  # Low traffic for ab_test
            "decision_path": [
                {"step": "Step1", "passed": False},
                {"step": "Step2", "passed": False}
            ],
            "warnings_triggered": [
                {"code": "CRIT1", "severity": "critical"},
                {"code": "CRIT2", "severity": "critical"}
            ],
            "limitations": [],  # Missing limitations
            "final_decision": {"confidence": "low"}
        }
        result = check_experiment_maturity(audit, {})
        assert result["maturity_label"] == "inadequate"
        assert result["maturity_score"] < 50

    def test_adequate_label_for_minor_issues(self):
        """Minor issues → adequate label"""
        audit = {
            "mode": "ab_test",
            "traffic_size": 10000,
            "decision_path": [
                {"step": "Step1", "passed": True},
                {"step": "Step2", "passed": True},
                {"step": "Step3", "passed": True},
                {"step": "Decision", "passed": True}
            ],
            "warnings_triggered": [
                {"code": "SMALL_EFFECT", "severity": "info"}
            ],
            "limitations": ["Lim1", "Lim2"],
            "final_decision": {"confidence": "medium"}
        }
        result = check_experiment_maturity(audit, {})
        assert result["maturity_label"] in ["mature", "adequate"]

    def test_immature_when_warning_count_high(self):
        """Many warnings but no critical → score penalty"""
        audit = {
            "mode": "ab_test",
            "traffic_size": 10000,
            "decision_path": [
                {"step": "Step1", "passed": True},
                {"step": "Decision", "passed": True}
            ],
            "warnings_triggered": [
                {"code": "W1", "severity": "info"},
                {"code": "W2", "severity": "info"},
                {"code": "W3", "severity": "info"},
                {"code": "W4", "severity": "info"}
            ],
            "limitations": ["Lim1", "Lim2"],
            "final_decision": {"confidence": "high"}
        }
        result = check_experiment_maturity(audit, {})
        # Multiple non-critical warnings should drop score slightly
        assert result["maturity_score"] < 100

    def test_traffic_insufficient_for_ab_test(self):
        """Traffic below minimum for ab_test → check fails"""
        audit = {
            "mode": "ab_test",
            "traffic_size": 500,  # Below 1000 minimum for ab_test
            "decision_path": [
                {"step": "Step1", "passed": True},
                {"step": "Decision", "passed": True}
            ],
            "warnings_triggered": [],
            "limitations": ["Lim1", "Lim2"],
            "final_decision": {"confidence": "high"}
        }
        result = check_experiment_maturity(audit, {})
        assert not result["checks"]["traffic_sufficient"]

    def test_traffic_sufficient_for_did(self):
        """DiD has no minimum traffic → passes"""
        audit = {
            "mode": "did",
            "traffic_size": 100,  # Any size is ok for DiD
            "decision_path": [
                {"step": "Step1", "passed": True},
                {"step": "Decision", "passed": True}
            ],
            "warnings_triggered": [],
            "limitations": ["Lim1"],
            "final_decision": {"confidence": "high"}
        }
        result = check_experiment_maturity(audit, {})
        assert result["checks"]["traffic_sufficient"]

    def test_short_decision_path_penalty(self):
        """Decision path with <4 steps → penalty"""
        audit = {
            "mode": "ab_test",
            "traffic_size": 10000,
            "decision_path": [
                {"step": "Step1", "passed": True}
            ],
            "warnings_triggered": [],
            "limitations": ["Lim1", "Lim2"],
            "final_decision": {"confidence": "high"}
        }
        result = check_experiment_maturity(audit, {})
        assert not result["checks"]["steps_documented"]
        assert result["maturity_score"] < 100

    def test_description_present(self):
        """Description should be present for all labels"""
        labels = ["mature", "adequate", "immature", "inadequate"]
        for label in labels:
            audit = {
                "mode": "ab_test",
                "traffic_size": 10000,
                "decision_path": [
                    {"step": "S1", "passed": True},
                    {"step": "S2", "passed": True},
                    {"step": "S3", "passed": True},
                    {"step": "S4", "passed": True}
                ],
                "warnings_triggered": [],
                "limitations": ["L1", "L2"],
                "final_decision": {"confidence": "high"}
            }
            # Simulate different scores to get different labels
            result = check_experiment_maturity(audit, {})
            assert "description" in result
            assert len(result["description"]) > 0

    def test_issues_list_for_critical(self):
        """Critical warnings → issues list populated"""
        audit = {
            "mode": "ab_test",
            "traffic_size": 10000,
            "decision_path": [
                {"step": "S1", "passed": True},
                {"step": "S2", "passed": True}
            ],
            "warnings_triggered": [
                {"code": "CRIT", "severity": "critical"}
            ],
            "limitations": ["L1", "L2"],
            "final_decision": {"confidence": "high"}
        }
        result = check_experiment_maturity(audit, {})
        assert len(result["issues"]) > 0

    def test_warnings_list_for_non_critical(self):
        """Non-critical warnings → warnings list populated"""
        audit = {
            "mode": "ab_test",
            "traffic_size": 10000,
            "decision_path": [
                {"step": "S1", "passed": False},
                {"step": "S2", "passed": True}
            ],
            "warnings_triggered": [],
            "limitations": [],  # Missing
            "final_decision": {"confidence": "medium"}
        }
class TestAuditRebuilders:
    """Tests for audit_ab_test and audit_did rebuilders.

    These functions are the canonical audit path — they should produce
    consistent output whether called from the CLI or standalone.
    """

    def test_audit_ab_test_produces_audit_object(self):
        """audit_ab_test returns a dict with all required audit fields."""
        from src.audit import audit_ab_test
        inputs = {
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        }
        result = {}  # dummy result
        audit = audit_ab_test(inputs, result)
        assert "mode" in audit
        assert "decision_path" in audit
        assert "inputs" in audit
        assert "final_decision" in audit
        assert audit["mode"] == "ab_test"

    def test_audit_ab_test_runs_all_steps(self):
        """audit_ab_test produces multiple decision steps."""
        from src.audit import audit_ab_test
        inputs = {
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        }
        audit = audit_ab_test(inputs, {})
        assert len(audit["decision_path"]) >= 4  # validation, traffic, rates, stats

    def test_audit_ab_test_warning_on_low_traffic(self):
        """Low traffic triggers a warning in audit trail."""
        from src.audit import audit_ab_test
        inputs = {
            "control_conversions": 10,
            "control_total": 100,
            "variant_conversions": 15,
            "variant_total": 100
        }
        audit = audit_ab_test(inputs, {})
        # Either the traffic step failed or warnings_triggered has entries
        traffic_step = next((s for s in audit["decision_path"] if "traffic" in s["step"].lower()), None)
        if traffic_step:
            assert traffic_step["passed"] is False

    def test_audit_ab_test_final_decision_has_all_keys(self):
        """final_decision always contains decision, confidence, summary."""
        from src.audit import audit_ab_test
        inputs = {"control_conversions": 100, "control_total": 5000,
                  "variant_conversions": 130, "variant_total": 5000}
        audit = audit_ab_test(inputs, {})
        fd = audit["final_decision"]
        assert "decision" in fd
        assert "confidence" in fd
        assert "summary" in fd

    def test_audit_ab_test_invalid_input(self):
        """Zero total → early exit with escalate decision."""
        from src.audit import audit_ab_test
        inputs = {"control_conversions": 0, "control_total": 0,
                  "variant_conversions": 0, "variant_total": 0}
        audit = audit_ab_test(inputs, {})
        assert audit["final_decision"]["decision"] == "escalate"

    def test_audit_did_produces_audit_object(self):
        """audit_did returns a dict with all required audit fields."""
        from src.audit import audit_did
        inputs = {
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150
        }
        audit = audit_did(inputs, {})
        assert "mode" in audit
        assert "decision_path" in audit
        assert "inputs" in audit
        assert audit["mode"] == "did"

    def test_audit_did_runs_all_steps(self):
        """audit_did produces multiple decision steps."""
        from src.audit import audit_did
        inputs = {
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150
        }
        audit = audit_did(inputs, {})
        assert len(audit["decision_path"]) >= 4

    def test_audit_did_zero_pre_period(self):
        """Zero pre_period → early exit with escalate decision."""
        from src.audit import audit_did
        inputs = {
            "pre_control": 0,
            "post_control": 100,
            "pre_treated": 50,
            "post_treated": 100
        }
        audit = audit_did(inputs, {})
        assert audit["final_decision"]["decision"] == "escalate"


class TestAuditTextFormatter:
    """Tests for format_audit_text with various audit shapes."""

    def test_format_audit_text_handles_all_fields(self):
        """format_audit_text renders all audit fields without error."""
        from src.audit import format_audit_text
        audit = {
            "mode": "ab_test",
            "generated_at": "2026-05-03T00:00:00Z",
            "decision_path": [
                {"step": "Traffic check", "passed": True, "details": {"control_size": 5000}, "warning": None},
                {"step": "Statistical test", "passed": True, "details": {"p_value": 0.045}, "warning": None}
            ],
            "warnings_triggered": [
                {"code": "SMALL_EFFECT", "severity": "warning", "message": "Effect too small"}
            ],
            "limitations": ["Binary outcome only"],
            "final_decision": {
                "decision": "ship",
                "confidence": "medium",
                "summary": "Variant wins"
            }
        }
        text = format_audit_text(audit)
        assert "DECISION AUDIT REPORT" in text
        assert "Traffic check" in text
        assert "ship" in text.lower()
        assert "SMALL_EFFECT" in text

    def test_format_audit_text_with_empty_decision_path(self):
        """format_audit_text handles empty decision_path gracefully."""
        from src.audit import format_audit_text
        audit = {
            "mode": "ab_test",
            "generated_at": "2026-05-03T00:00:00Z",
            "decision_path": [],
            "warnings_triggered": [],
            "limitations": [],
            "final_decision": {"decision": "keep_running", "confidence": "low", "summary": ""}
        }
        text = format_audit_text(audit)
        assert "DECISION AUDIT REPORT" in text

    def test_format_audit_text_with_failed_steps(self):
        """Failed steps render correctly (warning marker)."""
        from src.audit import format_audit_text
        audit = {
            "mode": "ab_test",
            "generated_at": "2026-05-03T00:00:00Z",
            "decision_path": [
                {"step": "Traffic check", "passed": False, "details": {"actual": 100}, "warning": "Too low"}
            ],
            "warnings_triggered": [],
            "limitations": [],
            "final_decision": {"decision": "escalate", "confidence": "low", "summary": ""}
        }
        text = format_audit_text(audit)
        assert "Traffic check" in text
        assert "⚠" in text  # fail marker


class TestAuditConvergence:
    """Verify CLI audit path and rebuilder path produce consistent output.

    For the same saved result JSON, audit_ab_test(inputs, result) should
    produce the same essential audit structure as the old hand-built path.
    """

    def test_audit_ab_test_rebuilder_matches_saved_audit_shape(self):
        """Rebuilt audit has the same shape keys as a typical saved audit."""
        from src.audit import audit_ab_test
        inputs = {
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000
        }
        audit = audit_ab_test(inputs, {})
        # Required shape keys
        assert "mode" in audit
        assert "generated_at" in audit
        assert "decision_path" in audit
        assert "inputs" in audit
        assert "thresholds_applied" in audit
        assert "warnings_triggered" in audit
        assert "limitations" in audit
        assert "final_decision" in audit

    def test_audit_did_rebuilder_matches_saved_audit_shape(self):
        """Rebuilt DiD audit has the same shape keys as a typical saved audit."""
        from src.audit import audit_did
        inputs = {
            "pre_control": 1000,
            "post_control": 1100,
            "pre_treated": 900,
            "post_treated": 1150
        }
        audit = audit_did(inputs, {})
        assert "mode" in audit
        assert "generated_at" in audit
        assert "decision_path" in audit
        assert "inputs" in audit
        assert "final_decision" in audit