"""Tests for the PostHog connector."""

import pytest
from unittest.mock import patch, MagicMock

from src.connectors.posthog import (
    PostHogConnector,
    normalize_posthog,
    _load_posthog_config,
    _build_experiments_url,
    _safe_int,
)
from src.connectors import (
    ConnectorResult,
    InsufficientDataError,
    ConnectorAuthError,
    ConnectorNotFoundError,
    ConnectorError,
)


# ─── normalize_posthog tests ──────────────────────────────────────────────────

class TestNormalizePosthog:
    def test_normalizes_variant_list_format(self):
        """PostHog funnel results: list of {key, count} dicts."""
        payload = {
            "id": "exp-123",
            "name": "Test Experiment",
            "feature_flag_key": "my-flag",
            "variants": [
                {"key": "control", "count": 120, "rollout_percentage": 50},
                {"key": "test", "count": 145, "rollout_percentage": 50},
            ],
        }
        result = normalize_posthog(payload)
        assert result["control_conversions"] == 120
        assert result["control_total"] == 120  # falls back to count
        assert result["variant_conversions"] == 145
        assert result["variant_total"] == 145
        assert result["experiment_name"] == "Test Experiment"
        assert result["feature_flag_key"] == "my-flag"

    def test_normalizes_exposure_dict_format(self):
        """PostHog experiment with exposure breakdown dict."""
        payload = {
            "id": "exp-456",
            "name": "Exposure Test",
            "feature_flag_key": "other-flag",
            "exposure": {
                "control": 500,
                "test": 620,
            },
            "control_total": 10000,
            "variant_total": 10000,
        }
        result = normalize_posthog(payload)
        assert result["control_conversions"] == 500
        assert result["control_total"] == 10000
        assert result["variant_conversions"] == 620
        assert result["variant_total"] == 10000

    def test_normalizes_direct_count_fields(self):
        """PostHog with flat count fields."""
        payload = {
            "id": "exp-789",
            "name": "Direct Count Test",
            "control_conversions": 200,
            "control_total": 8000,
            "variant_conversions": 250,
            "variant_total": 8000,
        }
        result = normalize_posthog(payload)
        assert result["control_conversions"] == 200
        assert result["variant_conversions"] == 250

    def test_raises_insufficient_data_on_missing_fields(self):
        """Missing required fields raises InsufficientDataError."""
        payload = {"id": "exp-incomplete", "name": "Incomplete"}
        with pytest.raises(InsufficientDataError) as exc_info:
            normalize_posthog(payload)
        err = exc_info.value
        assert "control_conversions" in err.missing_fields
        assert "variant_conversions" in err.missing_fields
        assert err.source == "posthog"

    def test_partial_data_raises_with_field_list(self):
        """Partial data (only control counts) still fails clearly."""
        payload = {
            "id": "exp-partial",
            "control_conversions": 100,
            # missing variant
        }
        with pytest.raises(InsufficientDataError) as exc_info:
            normalize_posthog(payload)
        missing = exc_info.value.missing_fields
        assert "variant_conversions" in missing

    def test_dates_extracted(self):
        """start_date and end_date are extracted from payload."""
        payload = {
            "id": "exp-dates",
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 120,
            "variant_total": 5000,
            "start_date": "2026-04-01T00:00:00Z",
            "end_date": "2026-04-14T23:59:59Z",
        }
        result = normalize_posthog(payload)
        assert result["start_date"] == "2026-04-01T00:00:00Z"
        assert result["end_date"] == "2026-04-14T23:59:59Z"

    def test_variant_name_extracted(self):
        """Non-control variant name is captured."""
        payload = {
            "id": "exp-vname",
            "control_conversions": 100,
            "control_total": 5000,
            "variant_conversions": 120,
            "variant_total": 5000,
            "variants": [
                {"key": "control", "count": 100},
                {"key": "variant-a", "count": 120},
            ],
        }
        result = normalize_posthog(payload)
        assert result["variant_name"] == "variant-a"


# ─── _safe_int tests ─────────────────────────────────────────────────────────

class TestSafeInt:
    def test_passes_int(self):
        assert _safe_int(42) == 42

    def test_passes_float_rounded(self):
        assert _safe_int(42.7) == 42

    def test_parses_string_int(self):
        assert _safe_int("123") == 123

    def test_returns_none_for_none(self):
        assert _safe_int(None) is None

    def test_returns_none_for_nonsense(self):
        assert _safe_int("abc") is None


# ─── PostHogConnector tests ───────────────────────────────────────────────────

class TestPostHogConnector:
    def test_health_check_false_without_credentials(self):
        """No credentials = health check fails."""
        with patch.dict("os.environ", {}, clear=True):
            conn = PostHogConnector(api_key="", project_id="")
            assert conn.health_check() is False

    def test_health_check_true_with_credentials(self):
        """Credentials present = health check passes."""
        conn = PostHogConnector(api_key="phx_test123", project_id="proj_123")
        assert conn.health_check() is True

    def test_raises_auth_error_without_credentials(self):
        """fetch_experiment without credentials raises ConnectorAuthError."""
        conn = PostHogConnector(api_key="", project_id="")
        with pytest.raises(ConnectorAuthError):
            conn.fetch_experiment("exp-123")

    def test_raises_not_found_on_404(self):
        """404 from PostHog raises ConnectorNotFoundError."""
        conn = PostHogConnector(api_key="phx_test123", project_id="proj_123")
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not found"

        with patch("src.connectors.posthog._get_http_client") as mock_get:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_resp
            mock_get.return_value = mock_client

            with pytest.raises(ConnectorNotFoundError) as exc_info:
                conn.fetch_experiment("exp-nonexistent")
            assert exc_info.value.resource_id == "exp-nonexistent"

    def test_raises_auth_error_on_401(self):
        """401 from PostHog raises ConnectorAuthError."""
        conn = PostHogConnector(api_key="phx_bad", project_id="proj_123")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        with patch("src.connectors.posthog._get_http_client") as mock_get:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_resp
            mock_get.return_value = mock_client

            with pytest.raises(ConnectorAuthError):
                conn.fetch_experiment("exp-123")

    def test_fetch_experiment_returns_connector_result(self):
        """Successful fetch returns ConnectorResult with normalized data."""
        conn = PostHogConnector(api_key="phx_test", project_id="proj_123")
        mock_payload = {
            "id": "exp-123",
            "name": "Success Test",
            "variants": [
                {"key": "control", "count": 100},
                {"key": "test", "count": 130},
            ],
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload

        with patch("src.connectors.posthog._get_http_client") as mock_get:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_resp
            mock_get.return_value = mock_client

            result = conn.fetch_experiment("exp-123")
            assert isinstance(result, ConnectorResult)
            assert result.data["control_conversions"] == 100
            assert result.data["variant_conversions"] == 130
            assert result.source_metadata["connector"] == "posthog"
            assert result.source_metadata["experiment_id"] == "exp-123"

    def test_fetch_experiment_normalizes_and_raises_insufficient(self):
        """Successful HTTP but missing data raises InsufficientDataError."""
        conn = PostHogConnector(api_key="phx_test", project_id="proj_123")
        mock_payload = {"id": "exp-incomplete", "name": "Incomplete"}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload

        with patch("src.connectors.posthog._get_http_client") as mock_get:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_resp
            mock_get.return_value = mock_client

            with pytest.raises(InsufficientDataError):
                conn.fetch_experiment("exp-incomplete")


# ─── URL building tests ───────────────────────────────────────────────────────

class TestBuildExperimentsUrl:
    def test_cloud_url(self):
        url = _build_experiments_url(
            "https://app.posthog.com",
            "proj_abc123",
            "exp-456",
        )
        assert "proj_abc123" in url
        assert "exp-456" in url
        assert "posthog.com" in url

    def test_self_hosted_url(self):
        url = _build_experiments_url(
            "https://analytics.internal.co",
            "proj_abc123",
            "exp-789",
        )
        assert "experiments" in url
        assert "exp-789" in url