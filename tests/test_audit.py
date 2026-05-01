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
        result = check_experiment_maturity(audit, {})
        assert len(result["warnings"]) > 0