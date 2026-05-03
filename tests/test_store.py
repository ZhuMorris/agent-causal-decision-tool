"""Tests for persistent storage / store module"""

import importlib
import json
import tempfile
from pathlib import Path

# Patch DB_PATH to a temp file for isolation BEFORE importing store
_temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
_temp_db.close()

from src import store as store_module  # noqa: E402

store_module.DB_PATH = Path(_temp_db.name)
# Force re-init with temp path
importlib.reload(store_module)


class TestStore:
    """Store module unit tests"""

    def setup_method(self):
        """Reset DB before each test — drop and recreate to reset auto-increment."""
        conn = store_module._get_db()
        conn.execute("DROP TABLE IF EXISTS experiments")
        conn.commit()
        store_module._init_db(conn)
        conn.close()

    def test_save_experiment_ab(self):
        """Save an A/B test result"""
        result_json = json.dumps({
            "mode": "ab_test",
            "recommendation": {"decision": "ship", "confidence": "medium", "summary": "Test", "primary_metricLift": 30.0, "p_value": 0.045},
            "inputs": {"control_conversions": 100, "control_total": 5000, "variant_conversions": 130, "variant_total": 5000}
        })
        row_id = store_module.save_experiment(result_json, "ab_test", '{"control_conversions": 100}')
        assert row_id == 1

    def test_save_experiment_did(self):
        """Save a DiD result"""
        result_json = json.dumps({
            "mode": "did",
            "recommendation": {"decision": "ship", "confidence": "medium", "summary": "DiD test", "primary_metricLift": 16.67, "p_value": None},
            "inputs": {"pre_control": 1000, "post_control": 1100, "pre_treated": 900, "post_treated": 1150}
        })
        row_id = store_module.save_experiment(result_json, "did", '{"pre_control": 1000}')
        assert row_id == 1

    def test_save_experiment_planning(self):
        """Save a planning result"""
        result_json = json.dumps({
            "mode": "planning",
            "recommendation": {"decision": "slow", "confidence": "medium", "summary": "Slow experiment"},
            "planning": {"feasibility": "slow", "estimated_days": 36.5},
            "inputs": {"baseline_conversion_rate": 0.02, "mde_pct": 10}
        })
        row_id = store_module.save_experiment(result_json, "planning", '{"baseline_conversion_rate": 0.02}')
        assert row_id == 1

    def test_list_experiments_empty(self):
        """Empty DB returns empty list"""
        experiments = store_module.list_experiments()
        assert experiments == []

    def test_list_experiments_all_modes(self):
        """List all experiments across modes"""
        for mode in ["ab_test", "did", "planning"]:
            result_json = json.dumps({
                "mode": mode,
                "recommendation": {"decision": "ship", "confidence": "high", "summary": f"{mode} test"},
                "inputs": {"test": mode}
            })
            store_module.save_experiment(result_json, mode, '{"test": "x"}')
        
        experiments = store_module.list_experiments()
        assert len(experiments) == 3

    def test_list_experiments_filter_by_mode(self):
        """Filter by mode works"""
        for mode in ["ab_test", "did", "ab_test"]:
            result_json = json.dumps({
                "mode": mode,
                "recommendation": {"decision": "ship", "confidence": "high", "summary": "x"},
                "inputs": {}
            })
            store_module.save_experiment(result_json, mode, '{}')
        
        ab_experiments = store_module.list_experiments(mode="ab_test")
        assert len(ab_experiments) == 2

    def test_list_experiments_respects_limit(self):
        """Limit parameter works"""
        for i in range(5):
            result_json = json.dumps({
                "mode": "ab_test",
                "recommendation": {"decision": "ship", "confidence": "high", "summary": f"test{i}"},
                "inputs": {}
            })
            store_module.save_experiment(result_json, "ab_test", '{}')
        
        experiments = store_module.list_experiments(limit=3)
        assert len(experiments) == 3

    def test_get_experiment_by_id(self):
        """Get single experiment by ID"""
        result_json = json.dumps({
            "mode": "ab_test",
            "recommendation": {"decision": "ship", "confidence": "medium", "summary": "Test"},
            "inputs": {"control_conversions": 100}
        })
        row_id = store_module.save_experiment(result_json, "ab_test", '{"control_conversions": 100}')
        
        exp = store_module.get_experiment(row_id)
        assert exp is not None
        assert exp["id"] == row_id
        assert exp["mode"] == "ab_test"
        assert exp["decision"] == "ship"

    def test_get_experiment_not_found(self):
        """Get non-existent experiment returns None"""
        exp = store_module.get_experiment(9999)
        assert exp is None

    def test_delete_experiment(self):
        """Delete experiment by ID"""
        result_json = json.dumps({
            "mode": "ab_test",
            "recommendation": {"decision": "ship", "confidence": "high", "summary": "Test"},
            "inputs": {}
        })
        row_id = store_module.save_experiment(result_json, "ab_test", '{}')
        
        deleted = store_module.delete_experiment(row_id)
        assert deleted is True
        assert store_module.get_experiment(row_id) is None

    def test_delete_experiment_not_found(self):
        """Delete non-existent experiment returns False"""
        deleted = store_module.delete_experiment(9999)
        assert deleted is False

    def test_compare_experiments_two_ab_tests(self):
        """Compare two A/B experiments"""
        ship_json = json.dumps({
            "mode": "ab_test",
            "recommendation": {"decision": "ship", "confidence": "high", "summary": "Ship"},
            "inputs": {"control_conversions": 100}
        })
        reject_json = json.dumps({
            "mode": "ab_test",
            "recommendation": {"decision": "reject", "confidence": "high", "summary": "Reject"},
            "inputs": {"control_conversions": 80}
        })
        id1 = store_module.save_experiment(ship_json, "ab_test", '{"control_conversions": 100}')
        id2 = store_module.save_experiment(reject_json, "ab_test", '{"control_conversions": 80}')
        
        comparison = store_module.compare_experiments([id1, id2])
        assert comparison["count"] == 2
        assert "ship" in comparison["by_decision"]
        assert "reject" in comparison["by_decision"]
        assert len(comparison["by_decision"]["ship"]) == 1
        assert len(comparison["by_decision"]["reject"]) == 1

    def test_compare_experiments_attention_flag(self):
        """Conflicting decisions set attention flag"""
        ship_json = json.dumps({
            "mode": "ab_test",
            "recommendation": {"decision": "ship", "confidence": "high", "summary": "Ship"},
            "inputs": {}
        })
        reject_json = json.dumps({
            "mode": "ab_test",
            "recommendation": {"decision": "reject", "confidence": "high", "summary": "Reject"},
            "inputs": {}
        })
        id1 = store_module.save_experiment(ship_json, "ab_test", '{}')
        id2 = store_module.save_experiment(reject_json, "ab_test", '{}')
        
        comparison = store_module.compare_experiments([id1, id2])
        assert comparison["attention"]["conflicting_decisions"] is True
        assert comparison["attention"]["ship_count"] == 1
        assert comparison["attention"]["reject_count"] == 1

    def test_compare_experiments_lift_summary(self):
        """Lift summary computed correctly"""
        result_json = json.dumps({
            "mode": "ab_test",
            "recommendation": {"decision": "ship", "confidence": "high", "summary": "Ship", "primary_metricLift": 30.0, "p_value": 0.045},
            "inputs": {}
        })
        id1 = store_module.save_experiment(result_json, "ab_test", '{}')
        result_json2 = json.dumps({
            "mode": "ab_test",
            "recommendation": {"decision": "ship", "confidence": "high", "summary": "Ship", "primary_metricLift": 10.0, "p_value": 0.02},
            "inputs": {}
        })
        id2 = store_module.save_experiment(result_json2, "ab_test", '{}')
        
        comparison = store_module.compare_experiments([id1, id2])
        ls = comparison["lift_summary"]
        assert ls["max"] == 30.0
        assert ls["min"] == 10.0
        assert ls["count"] == 2

    def test_compare_experiments_needs_two(self):
        """Less than 2 experiments returns error"""
        result_json = json.dumps({
            "mode": "ab_test",
            "recommendation": {"decision": "ship", "confidence": "high", "summary": "Ship"},
            "inputs": {}
        })
        id1 = store_module.save_experiment(result_json, "ab_test", '{}')
        
        comparison = store_module.compare_experiments([id1])
        assert "error" in comparison

    def test_save_experiment_with_name(self):
        """Save experiment with experiment_name"""
        result_json = json.dumps({
            "mode": "ab_test",
            "recommendation": {"decision": "ship", "confidence": "high", "summary": "Checkout test"},
            "inputs": {"experiment_name": "checkout-v3-test", "control_conversions": 100}
        })
        row_id = store_module.save_experiment(result_json, "ab_test", '{"experiment_name": "checkout-v3-test"}')
        
        exp = store_module.get_experiment(row_id)
        assert exp["experiment_name"] == "checkout-v3-test"

    def test_traffic_stats_from_bayes(self):
        """Bayesian results save correctly with planning metadata"""
        result_json = json.dumps({
            "mode": "bayesian_ab",
            "recommendation": {"decision": "ship", "confidence": "medium", "summary": "Variant wins", "primary_metricLift": 29.9, "p_value": 0.976},
            "planning": {"feasibility": "feasible", "estimated_days": 7},
            "inputs": {"control_conversions": 100, "control_total": 5000}
        })
        row_id = store_module.save_experiment(result_json, "bayesian_ab", '{"control_conversions": 100}')
        
        exp = store_module.get_experiment(row_id)
        assert exp["mode"] == "bayesian_ab"
        assert exp["decision"] == "ship"

    def test_raw_json_preserved(self):
        """Full raw JSON is preserved for audit replay"""
        raw = {
            "version": "1.0",
            "mode": "ab_test",
            "recommendation": {"decision": "ship", "confidence": "high", "summary": "Full test"},
            "statistics": {"p_value": 0.045},
            "inputs": {"control_conversions": 100, "control_total": 5000, "variant_conversions": 130, "variant_total": 5000}
        }
        row_id = store_module.save_experiment(json.dumps(raw), "ab_test", json.dumps(raw["inputs"]))
        
        exp = store_module.get_experiment(row_id)
        restored = json.loads(exp["raw_json"])
        assert restored["statistics"]["p_value"] == 0.045

    def test_multiple_experiments_ordered_by_created_at(self):
        """Most recent experiments come first"""
        for i in range(3):
            result_json = json.dumps({
                "mode": "ab_test",
                "recommendation": {"decision": "ship", "confidence": "high", "summary": f"test{i}"},
                "inputs": {}
            })
            store_module.save_experiment(result_json, "ab_test", '{}')
        
        experiments = store_module.list_experiments()
        assert len(experiments) == 3
        # Most recent is last saved (id=3) but comes first in DESC order
        assert experiments[0]["id"] == 3


class TestStoreEdgeCases:
    """Edge cases for store module"""

    def setup_method(self):
        """Reset DB before each test — drop and recreate to reset auto-increment."""
        conn = store_module._get_db()
        conn.execute("DROP TABLE IF EXISTS experiments")
        conn.commit()
        store_module._init_db(conn)
        conn.close()

    def test_save_with_null_p_value(self):
        """DiD has null p_value - should not crash"""
        result_json = json.dumps({
            "mode": "did",
            "recommendation": {"decision": "ship", "confidence": "medium", "summary": "DiD test", "primary_metricLift": 16.67, "p_value": None},
            "inputs": {"pre_control": 1000}
        })
        row_id = store_module.save_experiment(result_json, "did", '{"pre_control": 1000}')
        assert row_id > 0

    def test_save_with_null_lift(self):
        """Planning results have null primary_metricLift"""
        result_json = json.dumps({
            "mode": "planning",
            "recommendation": {"decision": "not_recommended", "confidence": "low", "summary": "Not enough traffic", "primary_metricLift": None, "p_value": None},
            "inputs": {"baseline_conversion_rate": 0.02}
        })
        row_id = store_module.save_experiment(result_json, "planning", '{"baseline_conversion_rate": 0.02}')
        exp = store_module.get_experiment(row_id)
        assert exp["primary_lift"] is None

    def test_empty_inputs_json(self):
        """Empty inputs JSON should not crash"""
        result_json = json.dumps({
            "mode": "ab_test",
            "recommendation": {"decision": "ship", "confidence": "high", "summary": "Test"},
            "inputs": {}
        })
        row_id = store_module.save_experiment(result_json, "ab_test", '{}')
        assert row_id > 0

    def test_mixed_mode_comparison(self):
        """Compare across ab_test, did, and bayesian modes"""
        modes = ["ab_test", "did", "bayesian_ab"]
        ids = []
        for mode in modes:
            result_json = json.dumps({
                "mode": mode,
                "recommendation": {"decision": "ship", "confidence": "high", "summary": f"{mode} test"},
                "inputs": {}
            })
            row_id = store_module.save_experiment(result_json, mode, '{}')
            ids.append(row_id)
        
        comparison = store_module.compare_experiments(ids)
        assert comparison["count"] == 3
        assert len(comparison["by_mode"]) == 3

    def test_all_decisions_represented(self):
        """All four decisions appear correctly in comparison"""
        decisions = ["ship", "keep_running", "reject", "escalate"]
        ids = []
        for decision in decisions:
            result_json = json.dumps({
                "mode": "ab_test",
                "recommendation": {"decision": decision, "confidence": "low", "summary": f"{decision} test"},
                "inputs": {}
            })
            row_id = store_module.save_experiment(result_json, "ab_test", '{}')
            ids.append(row_id)
        
        comparison = store_module.compare_experiments(ids)
        assert set(comparison["by_decision"].keys()) == set(decisions)