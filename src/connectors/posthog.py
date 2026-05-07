"""PostHog connector for Agent Causal Decision Tool.

Fetches experiment data from a PostHog Cloud or self-hosted instance
and normalizes it into the internal experiment schema.

Authentication:
  - Set POSTHOG_API_KEY and POSTHOG_PROJECT_ID env vars, OR
  - Set POSTHOG_API_KEY and POSTHOG_PROJECT_ID in ~/.posthogrc (INI format)

PostHog Experiments API:
  - PH Cloud: GET https:// posthog.com/api/projects/{project_id}/experiments/{exp_id}
  - Self-hosted: GET https://your-instance.com/api/experiments/{exp_id}
  - Auth header: Bearer {POSTHOG_API_KEY}
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from ..errors import validation_error, FieldError
from . import (
    BaseConnector,
    ConnectorResult,
    ConnectorAuthError,
    ConnectorNotFoundError,
    InsufficientDataError,
)


# ─── Config ──────────────────────────────────────────────────────────────────

def _load_posthog_config() -> tuple[str, str, str]:
    """Load PostHog credentials from env or ~/.posthogrc.

    Returns:
        (api_key, project_id, instance_url)
    """
    api_key = os.environ.get("POSTHOG_API_KEY", "")
    project_id = os.environ.get("POSTHOG_PROJECT_ID", "")
    instance_url = os.environ.get("POSTHOG_INSTANCE_URL", "https://app.posthog.com")

    # Override from env
    if api_key and project_id:
        return api_key, project_id, instance_url

    # Try ~/.posthogrc (INI format: [posthog] api_key=... project_id=...)
    posthogrc = Path.home() / ".posthogrc"
    if posthogrc.exists():
        try:
            content = posthogrc.read_text()
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("api_key") or line.startswith("api_key="):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        api_key = parts[1].strip().strip('"').strip("'")
                elif line.startswith("project_id") or line.startswith("project_id="):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        project_id = parts[1].strip().strip('"').strip("'")
                elif line.startswith("instance_url") or line.startswith("instance_url="):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        instance_url = parts[1].strip().strip('"').strip("'")
        except Exception:
            pass

    return api_key, project_id, instance_url


# ─── Normalization ────────────────────────────────────────────────────────────

def _extract_count_metric(feature_flag_value: dict, key: str) -> Optional[int]:
    """Extract a numeric count from a feature flag variant breakdown.

    Handles structures like:
      {"key": "control", "rollout_percentage": 100, ...}
      or breakdown values from experiments/funnels.
    """
    if not isinstance(feature_flag_value, dict):
        return None
    val = feature_flag_value.get(key) or feature_flag_value.get("count") or feature_flag_value.get("value")
    if isinstance(val, (int, float)):
        return int(val)
    return None


def _safe_int(value: Any) -> Optional[int]:
    """Coerce a value to int, returning None on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_start_end_dates(exp: dict) -> tuple[Optional[str], Optional[str]]:
    """Extract start_date and end_date from a PostHog experiment dict."""
    start = exp.get("start_date") or exp.get("created_at") or exp.get("effective_from")
    end = exp.get("end_date") or exp.get("updated_at")
    # Normalize to ISO strings if datetime objects
    if hasattr(start, "isoformat"):
        start = start.isoformat()
    if hasattr(end, "isoformat"):
        end = end.isoformat()
    return start, end


def normalize_posthog(payload: dict) -> dict:
    """Convert a PostHog experiment API response into the internal experiment schema.

    Internal schema expects:
      - control_conversions: int
      - control_total: int
      - variant_conversions: int
      - variant_total: int
      - start_date: str (ISO)
      - end_date: str (ISO)
      - variant_name: str (optional)
      - experiment_name: str (optional)

    PostHog experiment structure varies. This handles:
      - PostHog experiments API (feature flag based)
      - Simple key:value count mappings

    Raises InsufficientDataError if required fields are missing.

    Args:
        payload: Raw dict from PostHog experiments API.

    Returns:
        Normalized experiment dict suitable for run_decision_workflow.
    """
    missing = []

    # PostHog stores results in "feature_flag" -> "results" or "exposure" -> "count"
    # The exact shape depends on whether it's a simple experiment or funnel-based.
    feature_flag = payload.get("feature_flag", payload.get("feature_flag_key", ""))
    variants = payload.get("variants", payload.get("results", []))

    # Try to extract control and variant counts
    control_count = None
    variant_count = None
    control_total = None
    variant_total = None
    variant_name = "variant"

    if isinstance(variants, list) and len(variants) >= 2:
        # PostHog funnel/experiment results: [{"key": "control", "count": 123}, {"key": "test", "count": 456}]
        for v in variants:
            if not isinstance(v, dict):
                continue
            key = str(v.get("key", "")).lower()
            count = _safe_int(v.get("count", v.get("value")))
            if count is None:
                continue
            if "control" in key or "baseline" in key:
                control_count = count
            else:
                variant_count = count
                # Try to get the variant name
                variant_name = v.get("key", "test")

    # Try alternate fields for experiments with "exposure" counts
    if control_count is None:
        exposure = payload.get("exposure", {})
        if isinstance(exposure, dict):
            control_count = _safe_int(exposure.get("control") or exposure.get("baseline") or exposure.get("control_count"))
            variant_count = _safe_int(exposure.get("test") or exposure.get("variant") or exposure.get("treatment_count"))

    # Try direct count fields
    if control_count is None:
        control_count = _safe_int(
            payload.get("control_conversions") or payload.get("control_count")
        )
    if variant_count is None:
        variant_count = _safe_int(
            payload.get("variant_conversions") or payload.get("variant_count")
            or payload.get("treatment_conversions") or payload.get("test_conversions")
        )

    # Sample size fields (total exposed)
    if control_total is None:
        control_total = _safe_int(payload.get("control_total") or payload.get("control_exposure") or payload.get("control_sample_size"))
    if variant_total is None:
        variant_total = _safe_int(payload.get("variant_total") or payload.get("variant_exposure") or payload.get("variant_sample_size"))

    # Fallback: use count as both conversion and total if no total is available
    if control_count is not None and control_total is None:
        control_total = control_count
    if variant_count is not None and variant_total is None:
        variant_total = variant_count

    # Check required fields
    if control_count is None:
        missing.append("control_conversions")
    if control_total is None:
        missing.append("control_total")
    if variant_count is None:
        missing.append("variant_conversions")
    if variant_total is None:
        missing.append("variant_total")

    if missing:
        raise InsufficientDataError(
            f"PostHog experiment missing required fields: {missing}",
            missing_fields=missing,
            source="posthog",
        )

    start_date, end_date = _parse_start_end_dates(payload)

    experiment_name = payload.get("name") or payload.get("short_id", "") or payload.get("id", "")

    return {
        "control_conversions": control_count,
        "control_total": control_total,
        "variant_conversions": variant_count,
        "variant_total": variant_total,
        "start_date": start_date,
        "end_date": end_date,
        "variant_name": variant_name,
        "experiment_name": experiment_name,
        "feature_flag_key": feature_flag,
    }


# ─── PostHog HTTP client ───────────────────────────────────────────────────────

def _get_http_client():
    """Lazily import httpx. Install with: pip install httpx"""
    try:
        import httpx
    except ImportError:
        raise ImportError(
            "httpx is required for the PostHog connector. "
            "Install with: pip install httpx"
        )
    return httpx


def _build_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _build_experiments_url(instance_url: str, project_id: str, experiment_id: str) -> str:
    """Build the experiments API URL."""
    # PH Cloud uses /api/projects/{project_id}/experiments/{exp_id}
    # Self-hosted uses /api/experiments/{exp_id} (project_id not needed)
    base = instance_url.rstrip("/")
    if "/api/projects/" in base or "posthog.com" in base:
        # Cloud or newer self-hosted
        return f"{base}/api/projects/{project_id}/experiments/{experiment_id}"
    else:
        # Classic self-hosted
        return f"{base}/api/experiments/{experiment_id}"


# ─── Connector ────────────────────────────────────────────────────────────────

class PostHogConnector(BaseConnector):
    """Fetch experiment data from PostHog."""

    source_name = "posthog"

    def __init__(
        self,
        api_key: Optional[str] = None,
        project_id: Optional[str] = None,
        instance_url: Optional[str] = None,
    ):
        """Initialize the PostHog connector.

        Args:
            api_key: PostHog API key. If omitted, loads from POSTHOG_API_KEY env or ~/.posthogrc.
            project_id: PostHog project ID. If omitted, loads from POSTHOG_PROJECT_ID env or ~/.posthogrc.
            instance_url: PostHog instance URL. If omitted, defaults to https://app.posthog.com.
        """
        self._api_key = api_key or os.environ.get("POSTHOG_API_KEY", "")
        self._project_id = project_id or os.environ.get("POSTHOG_PROJECT_ID", "")
        self._instance_url = instance_url or os.environ.get("POSTHOG_INSTANCE_URL", "https://app.posthog.com")

        # Load from config file if not set
        if not self._api_key or not self._project_id:
            key, pid, url = _load_posthog_config()
            self._api_key = self._api_key or key
            self._project_id = self._project_id or pid
            self._instance_url = self._instance_url or url

    def health_check(self) -> bool:
        """Check if credentials are configured (does not make a live request)."""
        return bool(self._api_key and self._project_id)

    def fetch_experiment(self, experiment_id: str, **kwargs) -> ConnectorResult:
        """Fetch and normalize an experiment from PostHog.

        Args:
            experiment_id: PostHog experiment ID (numeric string or UUID).
            **kwargs: Ignored.

        Returns:
            ConnectorResult with normalized experiment data.

        Raises:
            ConnectorAuthError: Missing or invalid API key.
            ConnectorNotFoundError: Experiment not found in PostHog.
            InsufficientDataError: Experiment found but missing required data.
            ConnectorError: Network or other errors.
        """
        if not self._api_key or not self._project_id:
            raise ConnectorAuthError(
                "PostHog credentials not configured. "
                "Set POSTHOG_API_KEY and POSTHOG_PROJECT_ID env vars, "
                "or add them to ~/.posthogrc",
                source="posthog",
            )

        url = _build_experiments_url(self._instance_url, self._project_id, experiment_id)
        headers = _build_headers(self._api_key)

        try:
            httpx = _get_http_client()
            response = httpx.get(url, headers=headers, timeout=15.0)
        except Exception as exc:
            raise ConnectorError(f"Failed to reach PostHog instance: {exc}", source="posthog") from exc

        if response.status_code == 401:
            raise ConnectorAuthError(
                "PostHog API key is invalid or expired",
                source="posthog",
            )
        if response.status_code == 404:
            raise ConnectorNotFoundError(
                f"Experiment '{experiment_id}' not found in PostHog",
                resource_id=experiment_id,
                source="posthog",
            )
        if response.status_code >= 400:
            raise ConnectorError(
                f"PostHog API error {response.status_code}: {response.text[:200]}",
                source="posthog",
            )

        try:
            raw_payload = response.json()
        except Exception as exc:
            raise ConnectorError(f"PostHog returned invalid JSON: {exc}", source="posthog") from exc

        # Normalize
        try:
            normalized = normalize_posthog(raw_payload)
        except InsufficientDataError:
            raise
        except Exception as exc:
            raise ConnectorError(
                f"Failed to normalize PostHog response: {exc}",
                source="posthog",
            ) from exc

        return ConnectorResult(
            data=normalized,
            source_metadata=self._build_metadata(
                experiment_id,
                extra={
                    "project_id": self._project_id,
                    "instance_url": self._instance_url,
                },
            ),
            raw_payload=raw_payload,
            warnings=[],
        )