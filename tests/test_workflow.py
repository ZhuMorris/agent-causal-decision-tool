"""Tests for run_workflow action and notifications module."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from src.actions import run_workflow, run_action


class TestRunWorkflow:
    """Tests for the run_workflow orchestrator action."""

    def test_run_workflow_basic_ab(self):
        """run_workflow with explicit A/B input runs and returns all expected keys."""
        params = {
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000,
            "save": False,
            "notify": False,
        }
        result = run_workflow(params)

        assert "selected_method" in result
        assert "decision_result" in result
        assert "audit_result" in result
        assert "saved_result_id" in result
        assert "comparison_summary" in result
        assert "source_metadata" in result
        assert result["selected_method"] in ("ab_test", "bayesian_ab")

    def test_run_workflow_dry_run_no_source(self):
        """dry_run without a source returns validation passed without running decision."""
        params = {
            "dry_run": True,
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000,
        }
        result = run_workflow(params)

        assert result["dry_run"] is True
        assert result["validation"] == "passed (no connector used)"

    def test_run_workflow_save_enabled(self):
        """save=True persists the result and returns the saved ID."""
        params = {
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000,
            "save": True,
            "notify": False,
        }
        result = run_workflow(params)

        assert result["saved_result_id"] is not None
        # Verify it was actually saved
        from src.store import get_experiment
        exp = get_experiment(result["saved_result_id"])
        assert exp is not None

    def test_run_workflow_notify_flag_no_url(self):
        """notify=True with no AGENT_CAUSAL_WEBHOOK_URL set does not raise."""
        env_backup = os.environ.get("AGENT_CAUSAL_WEBHOOK_URL")
        if "AGENT_CAUSAL_WEBHOOK_URL" in os.environ:
            del os.environ["AGENT_CAUSAL_WEBHOOK_URL"]

        try:
            params = {
                "control_conversions": 100,
                "control_total": 5000,
                "variant_conversions": 130,
                "variant_total": 5000,
                "save": False,
                "notify": True,
            }
            # Should not raise — silently skips
            result = run_workflow(params)
            assert "decision_result" in result
        finally:
            if env_backup is not None:
                os.environ["AGENT_CAUSAL_WEBHOOK_URL"] = env_backup

    def test_run_workflow_compare_with(self):
        """compare_with compares the new result with prior experiments."""
        # First save a result to compare with
        params_save = {
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000,
            "save": True,
            "notify": False,
        }
        first = run_workflow(params_save)
        first_id = first["saved_result_id"]

        # Now run workflow with compare_with
        params_compare = {
            "control_conversions": 110,
            "control_total": 5000,
            "variant_conversions": 140,
            "variant_total": 5000,
            "save": True,
            "notify": False,
            "compare_with": [first_id],
        }
        result = run_workflow(params_compare)

        assert result["comparison_summary"] is not None
        assert result["comparison_summary"]["count"] == 2

    def test_run_workflow_did(self):
        """run_workflow with DiD fields selects DiD method."""
        params = {
            "pre_control": 1000.0,
            "post_control": 1200.0,
            "pre_treated": 800.0,
            "post_treated": 1100.0,
            "save": False,
            "notify": False,
        }
        result = run_workflow(params)
        assert result["selected_method"] == "did"
        assert result["decision_result"]["decision"] in ("ship", "keep_running", "reject", "escalate")

    def test_run_workflow_json_rpc(self):
        """run_workflow exposed as JSON-RPC action returns proper envelope."""
        params = {
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 130,
            "variant_total": 5000,
            "save": False,
            "notify": False,
        }
        response = run_action("run_workflow", params, request_id="test-1")

        assert response["jsonrpc"] == "2.0"
        assert "result" in response
        assert response["id"] == "test-1"
        assert "selected_method" in response["result"]

    def test_run_workflow_unknown_action(self):
        """Unknown action raises method_not_found."""
        response = run_action("nonexistent_action", {}, request_id="test-2")
        assert response["jsonrpc"] == "2.0"
        assert "error" in response


class TestNotifications:
    """Tests for the webhook notifications module."""

    def test_build_webhook_payload(self):
        """build_webhook_payload returns correctly structured dict."""
        from src.notifications import build_webhook_payload

        payload = build_webhook_payload(
            decision="ship",
            summary="Lift +3.2%",
            method="frequentist_ab",
            statistics={"p_value": 0.002, "lift": 3.2},
            result_id="42",
            timestamp="2026-05-07T10:00:00Z",
        )

        assert payload["decision"] == "ship"
        assert payload["summary"] == "Lift +3.2%"
        assert payload["method"] == "frequentist_ab"
        assert payload["statistics"]["p_value"] == 0.002
        assert payload["result_id"] == "42"
        assert payload["timestamp"] == "2026-05-07T10:00:00Z"

    def test_fire_webhook_no_url(self):
        """fire_webhook with no URL returns silently."""
        from src.notifications import fire_webhook

        # Should not raise
        fire_webhook(None, {"decision": "ship"})
        fire_webhook("", {"decision": "ship"})

    @patch("httpx.Client")
    def test_fire_webhook_success(self, mock_client_cls):
        """fire_webhook posts the correct payload."""
        from src.notifications import fire_webhook

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        fire_webhook("https://example.com/webhook", {"decision": "ship", "summary": "test"})
        # Wait for the thread pool to complete
        import time
        time.sleep(0.5)
        mock_client.post.assert_called_once()

    @patch("httpx.Client", side_effect=ImportError("httpx not installed"))
    def test_fire_webhook_failure_silent(self, mock_client_cls):
        """fire_webhook failures are logged but do not raise."""
        from src.notifications import fire_webhook

        # Should not raise — silent failure
        fire_webhook("https://example.com/webhook", {"decision": "ship"})
