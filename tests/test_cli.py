"""Smoke tests for CLI — all commands, argument parsing, and output shape."""

import json
import tempfile
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.cli import main


runner = CliRunner(mix_stderr=False)


class TestABCommand:
    def test_ab_basic_output(self, tmp_path):
        """ab command produces valid JSON with expected top-level keys."""
        result = runner.invoke(main, ["ab", "--control", "100/5000", "--variant", "130/5000"])
        assert result.exit_code == 0, result.stderr
        data = json.loads(result.stdout)
        assert "recommendation" in data
        assert "statistics" in data
        assert "schema_version" in data
        assert data["recommendation"]["decision"] in ("ship", "keep_running", "reject", "escalate")

    def test_ab_lift_ci_95_present(self):
        """lift_ci_95 must be present in ab statistics (v0.8)."""
        result = runner.invoke(main, ["ab", "--control", "100/5000", "--variant", "130/5000"])
        data = json.loads(result.stdout)
        assert "lift_ci_95" in data["statistics"]

    def test_ab_no_confidence_interval_95(self):
        """Old confidence_interval_95 field must be gone (clean break)."""
        result = runner.invoke(main, ["ab", "--control", "100/5000", "--variant", "130/5000"])
        data = json.loads(result.stdout)
        assert "confidence_interval_95" not in data["statistics"]

    def test_ab_text_format(self):
        """--format text produces readable text output."""
        result = runner.invoke(main, ["ab", "--control", "100/5000", "--variant", "130/5000", "--format", "text"])
        assert result.exit_code == 0
        assert "control" in result.stdout.lower()

    def test_ab_bad_input(self):
        """Malformed control/variant strings produce error."""
        result = runner.invoke(main, ["ab", "--control", "bad", "--variant", "130/5000"])
        assert result.exit_code != 0

    def test_ab_zero_conversions_handled(self):
        """Both groups zero conversions → graceful handling, no crash."""
        result = runner.invoke(main, ["ab", "--control", "0/1000", "--variant", "0/1000"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "recommendation" in data


class TestDidCommand:
    def test_did_basic_output(self):
        """did command produces valid JSON."""
        result = runner.invoke(main, [
            "did", "--pre-control", "1000", "--post-control", "1100",
            "--pre-treated", "900", "--post-treated", "1150"
        ])
        assert result.exit_code == 0, result.stderr
        data = json.loads(result.stdout)
        assert "recommendation" in data
        assert "statistics" in data

    def test_did_did_ci_95_present(self):
        """did_ci_95 must be present in did statistics (v0.8)."""
        result = runner.invoke(main, [
            "did", "--pre-control", "5000", "--post-control", "5500",
            "--pre-treated", "5000", "--post-treated", "6000"
        ])
        data = json.loads(result.stdout)
        assert "did_ci_95" in data["statistics"]

    def test_did_n_bootstrap_flag(self):
        """--n-bootstrap flag accepted and affects n_bootstrap output."""
        result = runner.invoke(main, [
            "did", "--pre-control", "5000", "--post-control", "5500",
            "--pre-treated", "5000", "--post-treated", "6000",
            "--n-bootstrap", "500"
        ])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["statistics"]["did_ci_n_bootstrap"] == 500

    def test_did_low_count_warning(self):
        """Low count (< 100) triggers BOOTSTRAP_CI_UNRELIABLE."""
        result = runner.invoke(main, [
            "did", "--pre-control", "50", "--post-control", "55",
            "--pre-treated", "50", "--post-treated", "60"
        ])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        codes = [w["code"] for w in data.get("warnings", [])]
        assert "BOOTSTRAP_CI_UNRELIABLE" in codes

    def test_did_text_format(self):
        result = runner.invoke(main, [
            "did", "--pre-control", "1000", "--post-control", "1100",
            "--pre-treated", "900", "--post-treated", "1150", "--format", "text"
        ])
        assert result.exit_code == 0
        assert "control" in result.stdout.lower()


class TestPlanCommand:
    def test_plan_basic_output(self):
        result = runner.invoke(main, [
            "plan", "--baseline", "0.05", "--mde", "5",
            "--traffic", "5000", "--confidence", "0.95", "--power", "0.8"
        ])
        assert result.exit_code == 0, result.stderr
        data = json.loads(result.stdout)
        assert "planning" in data

    def test_plan_mde_ci_95_present(self):
        """mde_ci_95 must be present in planning output (v0.8)."""
        result = runner.invoke(main, [
            "plan", "--baseline", "0.05", "--mde", "5", "--traffic", "5000"
        ])
        data = json.loads(result.stdout)
        assert "mde_ci_95" in data["planning"]

    def test_plan_baseline_very_low_warning(self):
        """Baseline < 0.005 triggers BASELINE_VERY_LOW."""
        result = runner.invoke(main, [
            "plan", "--baseline", "0.003", "--mde", "10", "--traffic", "10000"
        ])
        data = json.loads(result.stdout)
        codes = [w["code"] for w in data.get("warnings", [])]
        assert "BASELINE_VERY_LOW" in codes

    def test_plan_baseline_near_zero_critical(self):
        """Baseline < 0.001 triggers BASELINE_NEAR_ZERO (critical)."""
        result = runner.invoke(main, [
            "plan", "--baseline", "0.0005", "--mde", "20", "--traffic", "10000"
        ])
        data = json.loads(result.stdout)
        codes = [w["code"] for w in data.get("warnings", [])]
        assert "BASELINE_NEAR_ZERO" in codes
        nz = [w for w in data["warnings"] if w["code"] == "BASELINE_NEAR_ZERO"]
        assert nz[0]["severity"] == "critical"


class TestBayesCommand:
    def test_bayes_basic_output(self):
        result = runner.invoke(main, ["bayes", "--control", "100/5000", "--variant", "130/5000"])
        assert result.exit_code == 0, result.stderr
        data = json.loads(result.stdout)
        assert "recommendation" in data

    def test_bayes_hdi_present(self):
        """expected_lift_hdi_95 must be present (v0.8)."""
        result = runner.invoke(main, ["bayes", "--control", "100/5000", "--variant", "130/5000"])
        data = json.loads(result.stdout)
        assert "expected_lift_hdi_95" in data["statistics"]


class TestSchemaCommand:
    def test_schema_command(self):
        """agent-causal schema prints schema JSON."""
        result = runner.invoke(main, ["schema"])
        assert result.exit_code == 0, result.stderr
        data = json.loads(result.stdout)
        assert "schema_version" in data
        assert "definitions" in data
        assert data["schema_version"] == "0.8.0"

    def test_schema_definitions_contain_ab_did_plan(self):
        result = runner.invoke(main, ["schema"])
        data = json.loads(result.stdout)
        defs = data.get("definitions", {})
        assert "ABTestOutput" in defs or "ab_test" in str(data.get("schema_coverage", [])).lower()


class TestAuditCommand:
    def test_audit_json_mode(self):
        """audit --format json on a valid saved result."""
        saved = {
            "mode": "ab_test",
            "schema_version": "0.8.0",
            "inputs": {"control_conversions": 100, "control_total": 5000,
                       "variant_conversions": 130, "variant_total": 5000},
            "recommendation": {"decision": "ship", "confidence": "medium",
                               "summary": "Variant performs 30.00% better."},
            "statistics": {"control_rate": 0.02, "variant_rate": 0.026,
                           "relative_lift_pct": 30.0},
            "warnings": [],
            "audit": {
                "decision_path": [
                    {"step": "Traffic check", "passed": True}
                ],
                "limitations": []
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(saved, f)
            f.flush()
            result = runner.invoke(main, ["audit", f.name, "--format", "json"])
        os.unlink(f.name)
        assert result.exit_code == 0, result.stderr
        out = json.loads(result.stdout)
        assert "mode" in out

    def test_audit_text_mode(self):
        """audit --format text produces readable output."""
        saved = {
            "mode": "ab_test",
            "schema_version": "0.8.0",
            "inputs": {"control_conversions": 100, "control_total": 5000,
                       "variant_conversions": 130, "variant_total": 5000},
            "recommendation": {"decision": "ship", "confidence": "medium",
                               "summary": "Variant performs 30.00% better."},
            "warnings": [],
            "audit": {
                "decision_path": [{
                    "step": "Traffic check",
                    "passed": True,
                    "details": {"control_size": 5000, "variant_size": 5000}
                }],
                "limitations": ["Test limitation"],
                "warnings_triggered": []
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(saved, f)
            f.flush()
            result = runner.invoke(main, ["audit", f.name, "--format", "text"])
        os.unlink(f.name)
        assert result.exit_code == 0, result.stderr

    def test_audit_nonexistent_file(self):
        result = runner.invoke(main, ["audit", "/nonexistent/path.json"])
        assert result.exit_code != 0


class TestVersionAndHelp:
    def test_version_flag(self):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0

    def test_help_flag(self):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Commands:" in result.stdout


class TestABSaveFlag:
    """Test --save flag on ab/did/plan/bayes commands."""

    def test_ab_save_flag(self, tmp_path):
        """ab --save writes experiment to store."""
        from src import store
        old_path = store.DB_PATH
        db = tmp_path / "hist.db"
        store.DB_PATH = db
        result = runner.invoke(main, [
            "ab", "--control", "100/5000", "--variant", "130/5000", "--save"
        ])
        assert result.exit_code == 0
        store.DB_PATH = old_path

    def test_did_save_flag(self, tmp_path):
        """did --save writes experiment to store."""
        from src import store
        old_path = store.DB_PATH
        db = tmp_path / "hist.db"
        store.DB_PATH = db
        result = runner.invoke(main, [
            "did", "--pre-control", "1000", "--post-control", "1100",
            "--pre-treated", "900", "--post-treated", "1150", "--save"
        ])
        assert result.exit_code == 0
        store.DB_PATH = old_path


class TestHistoryTextMode:
    """Test history --format text (text formatter path)."""

    def test_history_text_mode(self, tmp_path):
        """history --format text shows a table."""
        from src import store
        old_path = store.DB_PATH
        db = tmp_path / "hist.db"
        store.DB_PATH = db
        import json
        # Save an experiment first
        data = {
            "mode": "ab_test",
            "inputs": {"control_conversions": 100, "control_total": 5000,
                       "variant_conversions": 130, "variant_total": 5000},
            "recommendation": {"decision": "ship", "confidence": "medium", "summary": "test"},
            "statistics": {},
            "warnings": [],
            "audit": {}
        }
        store.save_experiment(json.dumps(data), "ab_test", json.dumps(data["inputs"]))
        result = runner.invoke(main, ["history", "--format", "text"])
        assert result.exit_code == 0
        assert "ID" in result.stdout
        store.DB_PATH = old_path


class TestDidNBootstrapBoundary:
    """Test --n-bootstrap edge values."""

    def test_did_n_bootstrap_minimum(self):
        """--n-bootstrap 500 should not crash (minimum allowed value)."""
        result = runner.invoke(main, [
            "did", "--pre-control", "5000", "--post-control", "5500",
            "--pre-treated", "5000", "--post-treated", "6000",
            "--n-bootstrap", "500"
        ])
        assert result.exit_code == 0

    def test_did_n_bootstrap_large(self):
        """--n-bootstrap 5000 should work."""
        result = runner.invoke(main, [
            "did", "--pre-control", "5000", "--post-control", "5500",
            "--pre-treated", "5000", "--post-treated", "6000",
            "--n-bootstrap", "5000"
        ])
        assert result.exit_code == 0


class TestCohortBreakdownJsonInput:
    """Test cohort-breakdown --json with valid JSON input."""

    def test_cohort_json_option(self):
        """cohort-breakdown --json with valid segment JSON."""
        import json
        cohort = {
            "experiment_id": "test-exp",
            "metric": "conversion_rate",
            "segments": [
                {"segment_name": "new_users", "segment_definition_note": "first visit",
                 "control_conversions": 50, "control_total": 2000,
                 "variant_conversions": 65, "variant_total": 2000}
            ]
        }
        result = runner.invoke(main, [
            "cohort-breakdown", "--json", json.dumps(cohort)
        ])
        assert result.exit_code == 0, result.stderr


class TestABTextFormatter:
    """Test --format text path for ab command."""

    def test_ab_format_text_shows_recommendation(self):
        result = runner.invoke(main, [
            "ab", "--control", "100/5000", "--variant", "130/5000", "--format", "text"
        ])
        assert result.exit_code == 0
        # Text formatter should show decision
        assert any(k in result.stdout.lower() for k in ["ship", "reject", "keep_running", "decision"])


class TestBayesTextFormatter:
    """Test --format text path for bayes command."""

    def test_bayes_format_text_shows_recommendation(self):
        result = runner.invoke(main, [
            "bayes", "--control", "100/5000", "--variant", "130/5000", "--format", "text"
        ])
        assert result.exit_code == 0
        assert any(k in result.stdout.lower() for k in ["ship", "reject", "keep_running", "decision"])


class TestCompareWithMultipleExperiments:
    """Test compare with 3+ experiments via store."""

    def test_compare_three_experiments(self, tmp_path):
        from src import store
        old_path = store.DB_PATH
        db = tmp_path / "hist.db"
        store.DB_PATH = db
        import json
        for i in range(3):
            data = {
                "mode": "ab_test",
                "inputs": {"control_conversions": 100, "control_total": 5000,
                           "variant_conversions": 130 + i*5, "variant_total": 5000},
                "recommendation": {"decision": "ship", "confidence": "medium", "summary": f"exp{i}"},
                "statistics": {}, "warnings": [], "audit": {}
            }
            store.save_experiment(json.dumps(data), "ab_test", json.dumps(data["inputs"]))
        result = runner.invoke(main, ["compare", "1", "2", "3"])
        assert result.exit_code == 0
        store.DB_PATH = old_path
    def test_validate_valid_ab_input(self):
        result = runner.invoke(main, [
            "validate-input", "--json",
            '{"mode":"ab_test","control_conversions":100,"control_total":5000,"variant_conversions":130,"variant_total":5000}'
        ])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["valid"] is True

    def test_validate_invalid_cohort(self):
        result = runner.invoke(main, [
            "validate-input", "--json",
            '{"mode":"cohort_breakdown","segments":[]}'
        ])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert len(data["errors"]) > 0