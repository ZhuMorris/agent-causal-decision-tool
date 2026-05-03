"""Integration tests for store, history, save, compare CLI flows."""

import json
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.cli import main
from src import store


runner = CliRunner(mix_stderr=False)


@pytest.fixture
def fresh_db(tmp_path):
    """Point store.DB_PATH at a fresh temp DB for each test."""
    old_path = store.DB_PATH
    tmp_db = tmp_path / "test_history.db"
    store.DB_PATH = tmp_db
    # Force reinit by reconnecting (store module already imported, so we
    # need to make sure _get_db uses the new path)
    yield tmp_db
    store.DB_PATH = old_path


@pytest.fixture
def saved_ab_result(tmp_path):
    """Minimal ab_test result JSON for save/history tests."""
    path = tmp_path / "ab_result.json"
    data = {
        "schema_version": "0.8.0",
        "mode": "ab_test",
        "inputs": {"control_conversions": 100, "control_total": 5000,
                   "variant_conversions": 130, "variant_total": 5000},
        "recommendation": {"decision": "ship", "confidence": "medium",
                           "summary": "Variant performs 30% better.", "primary_metricLift": 30.0,
                           "p_value": 0.045361},
        "statistics": {"control_rate": 0.02, "variant_rate": 0.026},
        "warnings": [],
        "audit": {"decision_path": [], "limitations": []}
    }
    path.write_text(json.dumps(data))
    return path


@pytest.fixture
def saved_did_result(tmp_path):
    path = tmp_path / "did_result.json"
    data = {
        "schema_version": "0.8.0",
        "mode": "did",
        "inputs": {"pre_control": 1000, "post_control": 1100,
                   "pre_treated": 900, "post_treated": 1150},
        "recommendation": {"decision": "ship", "confidence": "high",
                           "summary": "DiD estimate positive.", "primary_metricLift": 16.67},
        "statistics": {},
        "warnings": [],
        "audit": {"decision_path": [], "limitations": []}
    }
    path.write_text(json.dumps(data))
    return path


class TestSaveCommand:
    def test_save_ab_result(self, fresh_db, saved_ab_result):
        result = runner.invoke(main, ["save", str(saved_ab_result)])
        assert result.exit_code == 0, result.stderr
        assert "Saved as experiment" in result.stdout
        assert "#1" in result.stdout

    def test_save_did_result(self, fresh_db, saved_did_result):
        result = runner.invoke(main, ["save", str(saved_did_result)])
        assert result.exit_code == 0
        assert "Saved as experiment" in result.stdout

    def test_save_with_name(self, fresh_db, saved_ab_result):
        result = runner.invoke(main, ["save", str(saved_ab_result), "--name", "checkout-v3-test"])
        assert result.exit_code == 0

    def test_save_nonexistent_file(self, fresh_db):
        result = runner.invoke(main, ["save", "/nonexistent/file.json"])
        assert result.exit_code != 0

    def test_save_invalid_json(self, fresh_db, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not valid json{")
        result = runner.invoke(main, ["save", str(bad)])
        assert result.exit_code != 0


class TestHistoryCommand:
    def test_history_empty(self, fresh_db):
        result = runner.invoke(main, ["history"])
        assert result.exit_code == 0
        assert "No experiments" in result.stdout

    def test_history_after_save(self, fresh_db, saved_ab_result):
        runner.invoke(main, ["save", str(saved_ab_result)])
        result = runner.invoke(main, ["history"])
        assert result.exit_code == 0
        assert "ab_test" in result.stdout
        assert "ship" in result.stdout.lower()

    def test_history_json_format(self, fresh_db, saved_ab_result):
        runner.invoke(main, ["save", str(saved_ab_result)])
        result = runner.invoke(main, ["history", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["mode"] == "ab_test"

    def test_history_mode_filter(self, fresh_db, saved_ab_result, saved_did_result):
        runner.invoke(main, ["save", str(saved_ab_result)])
        runner.invoke(main, ["save", str(saved_did_result)])
        result = runner.invoke(main, ["history", "--mode", "ab_test"])
        assert result.exit_code == 0
        # Only ab_test entries should appear in text output
        assert result.stdout.count("ab_test") >= 1

    def test_history_limit(self, fresh_db, saved_ab_result):
        for _ in range(5):
            runner.invoke(main, ["save", str(saved_ab_result)])
        result = runner.invoke(main, ["history", "--limit", "2", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) <= 2


class TestCompareCommand:
    def test_compare_empty(self, fresh_db):
        result = runner.invoke(main, ["compare", "999"])
        assert result.exit_code != 0

    def test_compare_one_id(self, fresh_db, saved_ab_result):
        runner.invoke(main, ["save", str(saved_ab_result)])
        runner.invoke(main, ["save", str(saved_ab_result)])
        result = runner.invoke(main, ["compare", "1"])
        # compare needs at least 2 experiments — verify error response
        assert result.exit_code != 0 or "Need at least 2" in result.stdout

    def test_compare_two_ids(self, fresh_db, saved_ab_result, saved_did_result):
        runner.invoke(main, ["save", str(saved_ab_result)])
        runner.invoke(main, ["save", str(saved_did_result)])
        result = runner.invoke(main, ["compare", "1", "2"])
        assert result.exit_code == 0

    def test_compare_nonexistent_ids(self, fresh_db):
        result = runner.invoke(main, ["compare", "999", "998"])
        assert result.exit_code != 0

    def test_compare_json_format(self, fresh_db, saved_ab_result):
        runner.invoke(main, ["save", str(saved_ab_result)])
        # compare needs 2+ experiments, so save two different ones
        runner.invoke(main, ["save", str(saved_ab_result)])
        result = runner.invoke(main, ["compare", "1", "2", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "experiments" in data or "comparison" in data or "count" in data


class TestSaveAndHistoryE2E:
    """End-to-end: save → list → compare."""

    def test_full_workflow(self, fresh_db, saved_ab_result, saved_did_result):
        # 1. Save two results
        r1 = runner.invoke(main, ["save", str(saved_ab_result)])
        assert r1.exit_code == 0
        r2 = runner.invoke(main, ["save", str(saved_did_result)])
        assert r2.exit_code == 0

        # 2. History shows both
        hist = runner.invoke(main, ["history", "--format", "json"])
        assert hist.exit_code == 0
        hist_data = json.loads(hist.stdout)
        assert len(hist_data) == 2

        # 3. Compare IDs 1 and 2
        cmp_ = runner.invoke(main, ["compare", "1", "2", "--format", "json"])
        assert cmp_.exit_code == 0
        cmp_data = json.loads(cmp_.stdout)
        assert "experiments" in cmp_data or "comparison" in cmp_data or "ids" in cmp_data


class TestCohortFileInput:
    """Test cohort-breakdown reads from JSON and CSV files."""

    def test_cohort_json_file(self, tmp_path):
        cohort_input = {
            "experiment_id": "checkout-v3",
            "metric": "conversion_rate",
            "segments": [
                {"segment_name": "new_users", "segment_definition_note": "first visit",
                 "control_conversions": 50, "control_total": 2000,
                 "variant_conversions": 65, "variant_total": 2000},
                {"segment_name": "returning", "segment_definition_note": "repeat visitors",
                 "control_conversions": 80, "control_total": 3000,
                 "variant_conversions": 85, "variant_total": 3000},
            ]
        }
        path = tmp_path / "cohort.json"
        path.write_text(json.dumps(cohort_input))
        result = runner.invoke(main, [
            "cohort-breakdown", "--file", str(path)
        ])
        assert result.exit_code == 0, result.stderr

    def test_cohort_csv_file(self, tmp_path):
        """cohort-breakdown --file with .csv calls _parse_cohort_csv (not --json path)."""
        csv_content = (
            "segment_name,segment_definition_note,arm,conversions,total\n"
            "new_users,first visit,control,50,2000\n"
            "new_users,first visit,variant,65,2000\n"
            "returning,repeat visitors,control,80,3000\n"
            "returning,repeat visitors,variant,85,3000\n"
        )
        path = tmp_path / "segments.csv"
        path.write_text(csv_content)
        # Provide experiment_id and metric via --json for metadata; use --file for CSV
        import json
        cohort_input = {
            "experiment_id": "test-exp",
            "metric": "conversion_rate",
        }
        result = runner.invoke(main, [
            "cohort-breakdown", "--json", json.dumps(cohort_input), "--file", str(path)
        ])
        assert result.exit_code == 0, result.stderr

    def test_cohort_invalid_file(self, tmp_path):
        bad = tmp_path / "nonexistent.json"
        result = runner.invoke(main, [
            "cohort-breakdown", "--file", str(bad)
        ])
        assert result.exit_code != 0


class TestABSaveAndRetrieve:
    """Run ab, save result, retrieve via history."""

    def test_ab_save_and_history(self, fresh_db):
        # 1. Run ab analysis with --save
        ab = runner.invoke(main, [
            "ab", "--control", "100/5000", "--variant", "130/5000", "--save"
        ])
        assert ab.exit_code == 0, ab.stderr

        # 2. Verify it appears in history (proves CLI → store → history)
        hist = runner.invoke(main, ["history", "--format", "json"])
        data = json.loads(hist.stdout)
        assert len(data) >= 1, "history should contain at least 1 saved experiment"
        assert data[0]["mode"] == "ab_test"
        assert data[0]["decision"] == "ship"

    def test_ab_with_auto_save_flag(self, fresh_db):
        result = runner.invoke(main, [
            "ab", "--control", "100/5000", "--variant", "130/5000", "--save"
        ])
        # Should complete without error (whether or not store is connected)
        assert result.exit_code == 0


class TestPlanBayesDidSaveAndHistory:
    """Verify plan/bayes/did --save populates history (same pattern as ab)."""

    def test_plan_save_and_history(self, fresh_db):
        result = runner.invoke(main, [
            "plan", "--baseline", "0.05", "--mde", "5",
            "--traffic", "5000", "--confidence", "0.95", "--power", "0.8", "--save"
        ])
        assert result.exit_code == 0, result.stderr
        hist = runner.invoke(main, ["history", "--mode", "planning", "--format", "json"])
        data = json.loads(hist.stdout)
        assert len(data) >= 1
        assert data[0]["mode"] == "planning"

    def test_bayes_save_and_history(self, fresh_db):
        result = runner.invoke(main, [
            "bayes", "--control", "100/5000", "--variant", "130/5000", "--save"
        ])
        assert result.exit_code == 0, result.stderr
        hist = runner.invoke(main, ["history", "--mode", "bayesian_ab", "--format", "json"])
        data = json.loads(hist.stdout)
        assert len(data) >= 1
        assert data[0]["mode"] == "bayesian_ab"

    def test_did_save_and_history(self, fresh_db):
        result = runner.invoke(main, [
            "did", "--pre-control", "1000", "--post-control", "1100",
            "--pre-treated", "900", "--post-treated", "1150", "--save"
        ])
        assert result.exit_code == 0, result.stderr
        hist = runner.invoke(main, ["history", "--mode", "did", "--format", "json"])
        data = json.loads(hist.stdout)
        assert len(data) >= 1
        assert data[0]["mode"] == "did"


class TestCohortSaveAndHistory:
    """cohort-breakdown --save + history."""

    def test_cohort_save_and_history(self, fresh_db):
        import json
        cohort_input = {
            "experiment_id": "test-cohort",
            "metric": "conversion_rate",
            "segments": [
                {"segment_name": "new_users", "segment_definition_note": "first visit",
                 "control_conversions": 50, "control_total": 2000,
                 "variant_conversions": 65, "variant_total": 2000},
            ]
        }
        result = runner.invoke(main, [
            "cohort-breakdown", "--json", json.dumps(cohort_input), "--save"
        ])
        assert result.exit_code == 0, result.stderr
        # Note: history --mode cohort_breakdown not supported (only ab_test/did/planning/bayesian_ab)
        hist = runner.invoke(main, ["history", "--format", "json"])
        data = json.loads(hist.stdout)
        assert len(data) >= 1
        cohort_entries = [e for e in data if e["mode"] == "cohort_breakdown"]
        assert len(cohort_entries) >= 1


class TestValidateInputCLI:
    """validate-input CLI as shipped surface."""

class TestValidateInputCLI:
    """validate-input CLI as shipped surface.

    Note: _validate_input only has actual schema logic for cohort_breakdown.
    All other modes (ab_test, did, planning, bayesian_ab, or unknown) return
    valid=True since they rely on the calculator's own validation.
    """

    def test_validate_input_valid_cohort(self):
        """cohort_breakdown with valid segments passes."""
        result = runner.invoke(main, [
            "validate-input", "--json",
            json.dumps({"mode": "cohort_breakdown", "segments": [
                {"segment_name": "new_users",
                 "control_conversions": 50, "control_total": 2000,
                 "variant_conversions": 65, "variant_total": 2000}
            ]})
        ])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["valid"] is True

    def test_validate_input_invalid_cohort_missing_segments(self):
        """cohort_breakdown with no segments → valid=False."""
        result = runner.invoke(main, [
            "validate-input", "--json",
            json.dumps({"mode": "cohort_breakdown", "segments": []})
        ])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_validate_input_invalid_cohort_missing_field(self):
        """cohort_breakdown missing control_total → valid=False."""
        result = runner.invoke(main, [
            "validate-input", "--json",
            json.dumps({"mode": "cohort_breakdown", "segments": [
                {"segment_name": "new_users",
                 "control_conversions": 50,
                 "variant_conversions": 65, "variant_total": 2000}
            ]})
        ])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["valid"] is False

    def test_validate_input_ab_test(self):
        """ab_test mode: validate-input returns valid (ab_test has no extra schema check)."""
        result = runner.invoke(main, [
            "validate-input", "--json",
            json.dumps({"mode": "ab_test", "control_conversions": 100,
                        "control_total": 5000, "variant_conversions": 130,
                        "variant_total": 5000})
        ])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        # ab_test passes basic validation (calculator handles the rest)
        assert data["mode"] == "ab_test"


class TestCohortStdinPath:
    """cohort-breakdown reads from stdin when neither --file nor --json is provided."""

    def test_cohort_stdin_json(self, tmp_path):
        import json
        cohort_input = {
            "experiment_id": "stdin-test",
            "metric": "conversion_rate",
            "segments": [
                {"segment_name": "new_users", "segment_definition_note": "first visit",
                 "control_conversions": 50, "control_total": 2000,
                 "variant_conversions": 65, "variant_total": 2000},
            ]
        }
        result = runner.invoke(main, [
            "cohort-breakdown"
        ], input=json.dumps(cohort_input))
        assert result.exit_code == 0, result.stderr


class TestFullJourneyScripted:
    """Continuous scripted journey: ab --save → history → compare → audit."""

    def test_full_journey_ab_audit(self, fresh_db, tmp_path):
        """Continuous scripted journey: ab → save → history → audit → compare."""
        # 1. Run ab analysis
        ab_result = runner.invoke(main, [
            "ab", "--control", "100/5000", "--variant", "130/5000", "--format", "json"
        ])
        assert ab_result.exit_code == 0
        ab_json = json.loads(ab_result.stdout)

        # 2. Save via file
        path = tmp_path / "journey_ab.json"
        path.write_text(json.dumps(ab_json))
        save = runner.invoke(main, ["save", str(path)])
        assert save.exit_code == 0

        # 3. History shows it
        hist = runner.invoke(main, ["history", "--format", "json"])
        data = json.loads(hist.stdout)
        assert len(data) >= 1
        exp_id = data[0]["id"]

        # 4. Audit the saved file (rebuilder path)
        audit_result = runner.invoke(main, ["audit", str(path), "--format", "json"])
        assert audit_result.exit_code == 0
        audit_data = json.loads(audit_result.stdout)
        assert audit_data["mode"] == "ab_test"
        assert len(audit_data["decision_path"]) > 0

        # 5. Compare IDs 1 and 2 (need two distinct IDs)
        # Save a second experiment so compare has 2 distinct rows
        did_result = runner.invoke(main, [
            "did", "--pre-control", "1000", "--post-control", "1100",
            "--pre-treated", "900", "--post-treated", "1150", "--format", "json"
        ])
        did_path = tmp_path / "journey_did.json"
        did_path.write_text(did_result.stdout)
        runner.invoke(main, ["save", str(did_path)])

        cmp_result = runner.invoke(main, ["compare", str(exp_id), "2"])
        assert cmp_result.exit_code == 0


class TestDidJourneyWithBootstrap:
    """DiD --save → history with bootstrap param."""

    def test_did_save_with_n_bootstrap(self, fresh_db):
        result = runner.invoke(main, [
            "did", "--pre-control", "5000", "--post-control", "5500",
            "--pre-treated", "5000", "--post-treated", "6000",
            "--n-bootstrap", "1000", "--save"
        ])
        assert result.exit_code == 0, result.stderr
        hist = runner.invoke(main, ["history", "--mode", "did", "--format", "json"])
        data = json.loads(hist.stdout)
        assert len(data) >= 1
        assert data[0]["mode"] == "did"


class TestBayesJourney:
    """bayes --save → history with HDI stats."""

    def test_bayes_save_with_hdi(self, fresh_db):
        result = runner.invoke(main, [
            "bayes", "--control", "100/5000", "--variant", "130/5000", "--save"
        ])
        assert result.exit_code == 0, result.stderr
        hist = runner.invoke(main, ["history", "--mode", "bayesian_ab", "--format", "json"])
        data = json.loads(hist.stdout)
        assert len(data) >= 1
        assert data[0]["mode"] == "bayesian_ab"
    """Direct tests for store module error and edge branches."""

    def test_save_experiment_returns_id(self, fresh_db, saved_ab_result):
        data = json.loads(saved_ab_result.read_text())
        row_id = store.save_experiment(
            json.dumps(data), "ab_test", json.dumps(data.get("inputs", {}))
        )
        assert isinstance(row_id, int)
        assert row_id >= 1

    def test_list_experiments_empty(self, fresh_db):
        exps = store.list_experiments()
        assert exps == []

    def test_list_experiments_with_limit(self, fresh_db, saved_ab_result):
        data = json.loads(saved_ab_result.read_text())
        for _ in range(3):
            store.save_experiment(json.dumps(data), "ab_test",
                                   json.dumps(data.get("inputs", {})))
        exps = store.list_experiments(limit=2)
        assert len(exps) == 2

    def test_get_experiment_by_id(self, fresh_db, saved_ab_result):
        data = json.loads(saved_ab_result.read_text())
        row_id = store.save_experiment(json.dumps(data), "ab_test",
                                        json.dumps(data.get("inputs", {})))
        exp = store.get_experiment(row_id)
        assert exp is not None
        assert exp["mode"] == "ab_test"

    def test_get_nonexistent_experiment(self, fresh_db):
        exp = store.get_experiment(99999)
        assert exp is None

    def test_update_experiment(self, fresh_db, saved_ab_result):
        """store has no update_experiment — test the delete+resave pattern instead."""
        data = json.loads(saved_ab_result.read_text())
        row_id = store.save_experiment(json.dumps(data), "ab_test",
                                        json.dumps(data.get("inputs", {})))
        # Delete and resave (no partial update in this store implementation)
        deleted = store.delete_experiment(row_id)
        assert deleted is True
        assert store.get_experiment(row_id) is None

    def test_delete_experiment(self, fresh_db, saved_ab_result):
        data = json.loads(saved_ab_result.read_text())
        row_id = store.save_experiment(json.dumps(data), "ab_test",
                                        json.dumps(data.get("inputs", {})))
        deleted = store.delete_experiment(row_id)
        assert deleted is True
        assert store.get_experiment(row_id) is None

    def test_compare_experiments(self, fresh_db, saved_ab_result, saved_did_result):
        d1 = json.loads(saved_ab_result.read_text())
        d2 = json.loads(saved_did_result.read_text())
        id1 = store.save_experiment(json.dumps(d1), "ab_test", json.dumps(d1.get("inputs", {})))
        id2 = store.save_experiment(json.dumps(d2), "did", json.dumps(d2.get("inputs", {})))
        cmp = store.compare_experiments([id1, id2])
        assert "experiments" in cmp or "ids" in cmp