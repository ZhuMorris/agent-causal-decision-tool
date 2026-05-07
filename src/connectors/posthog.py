"""PostHog connector for Agent Causal Decision Tool.

Fetches experiment data from a PostHog Cloud or self-hosted instance
and normalizes it into the internal experiment schema.

Authentication:
  - Set POSTHOG_API_KEY and POSTHOG_PROJECT_ID env vars, OR
  - Set api_key, project_id, instance_url in ~/.posthogrc (INI format)

PostHog Experiments API:
  - PH Cloud: GET https://app.posthog.com/api/projects/{project_id}/experiments/{exp_id}
  - Self-hosted: GET https://your-instance.com/api/experiments/{exp_id}
  - Auth header: Bearer {POSTHOG_API_KEY}
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Any

from ..errors import validation_error, FieldError
from . import (
    BaseConnector,
    ConnectorResult,
    ConnectorAuthError,
    ConnectorNotFoundError,
    ConnectorError,
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

    # Override from env if both are present
    if api_key and project_id:
        return api_key, project_id, instance_url

    # Try ~/.posthogrc (INI format: key=value pairs, no sections needed)
    posthogrc = Path.home() / ".posthogrc"
    if posthogrc.exists():
        try:
            for line in posthogrc.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key == "api_key":
                        api_key = val
                    elif key == "project_id":
                        project_id = val
                    elif key == "instance_url":
                        instance_url = val
        except Exception:
            pass

    return api_key, project_id, instance_url


# ─── Normalization ────────────────────────────────────────────────────────────

def _safe_int(value: Any) -> Optional[int]:
    """Coerce a value to int, returning None on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_optional_int(payload: dict, *keys) -> tuple[Optional[int], bool]:
    """Extract an int from the first key that has a non-None value.

    Returns (value, found). found is False if no key had a non-None value.
    Treats 0 as a valid value (not missing).
    """
    for key in keys:
        val = payload.get(key)
        if val is not None:
            result = _safe_int(val)
            if result is not None:
                return result, True
    return None, False


def _parse_start_end_dates(exp: dict) -> tuple[Optional[str], Optional[str]]:
    """Extract start_date and end_date from a PostHog experiment dict.

    Only uses actual end-date fields, not updated_at (which is a
    modification timestamp, not an experiment end date).
    """
    start = exp.get("start_date") or exp.get("created_at") or exp.get("effective_from")
    end = exp.get("end_date")
    # Normalize datetime objects to ISO strings
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
      - start_date: str (ISO, optional)
      - end_date: str (ISO, optional)
      - variant_name: str (optional)
      - experiment_name: str (optional)

    Raises InsufficientDataError if required fields are missing.
    """
    missing = []

    # ── Variant list format ──────────────────────────────────────────────
    # PostHog funnel/experiment results: [{"key": "control", "count": 123}, {"key": "test", "count": 456}]
    control_count: Optional[int] = None
    variant_count: Optional[int] = None
    control_total: Optional[int] = None
    variant_total: Optional[int] = None
    variant_name = "variant"

    variants = payload.get("variants") or payload.get("results") or []
    if isinstance(variants, list) and len(variants) >= 2:
        for v in variants:
            if not isinstance(v, dict):
                continue
            key = str(v.get("key", "")).lower()
            count = _safe_int(v.get("count") or v.get("value"))
            if count is None:
                continue
            if "control" in key or "baseline" in key:
                control_count = count
            else:
                variant_count = count
                variant_name = v.get("key", "test")

    # ── Exposure dict format ──────────────────────────────────────────────
    if control_count is None or variant_count is None:
        exposure = payload.get("exposure") or {}
        if isinstance(exposure, dict):
            cc, cc_found = _get_optional_int(
                exposure, "control", "baseline", "control_count"
            )
            vc, vc_found = _get_optional_int(
                exposure, "test", "variant", "treatment_count"
            )
            if cc_found:
                control_count = cc
            if vc_found:
                variant_count = vc

    # ── Direct count fields ───────────────────────────────────────────────
    if control_count is None:
        cc, _ = _get_optional_int(payload, "control_conversions", "control_count")
        if cc is not None:
            control_count = cc
    if variant_count is None:
        vc, _ = _get_optional_int(
            payload, "variant_conversions", "variant_count",
            "treatment_conversions", "test_conversions"
        )
        if vc is not None:
            variant_count = vc

    # ── Total / exposure fields ─────────────────────────────────────────
    ct, ct_found = _get_optional_int(
        payload, "control_total", "control_exposure", "control_sample_size"
    )
    vt, vt_found = _get_optional_int(
        payload, "variant_total", "variant_exposure", "variant_sample_size"
    )
    if ct_found:
        control_total = ct
    if vt_found:
        variant_total = vt

    # ── Fallback: use conversions as total if no total available ──────────
    if control_count is not None and control_total is None:
        control_total = control_count
    if variant_count is not None and variant_total is None:
        variant_total = variant_count

    # ── Validate required fields ─────────────────────────────────────────
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

    # ── Validate non-zero totals (avoid division by zero downstream) ───────
    if control_total == 0 or variant_total == 0:
        raise InsufficientDataError(
            "PostHog experiment has zero total for one or both arms (would cause division by zero)",
            missing_fields=["control_total" if control_total == 0 else "variant_total"],
            source="posthog",
        )

    start_date, end_date = _parse_start_end_dates(payload)
    experiment_name = (
        payload.get("name") or payload.get("short_id") or payload.get("id") or ""
    )
    feature_flag = payload.get("feature_flag") or payload.get("feature_flag_key") or ""

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


# ─── HTTP client helpers ──────────────────────────────────────────────────────

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
    """Build the experiments API URL.

    Distinguishes between:
    - PostHog Cloud (app.posthog.com): uses /api/projects/{project_id}/experiments/{id}
    - Self-hosted: uses /api/experiments/{id}
    """
    base = instance_url.rstrip("/")
    # Check for cloud explicitly (not just "posthog.com" substring which is too broad)
    if base == "https://app.posthog.com" or base.startswith("https://app.posthog.com/"):
        return f"{base}/api/projects/{project_id}/experiments/{experiment_id}"
    # Check if it's a custom PostHog Cloud endpoint (has project_id in path already)
    if "/api/projects/" in base:
        # URL already contains /api/projects/ — assume it's a complete self-hosted URL
        # Just append /experiments/{id} to the base
        return f"{base}/experiments/{experiment_id}"
    # Classic self-hosted (no /api/projects/ in URL)
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
        self._instance_url = instance_url or os.environ.get(
            "POSTHOG_INSTANCE_URL", "https://app.posthog.com"
        )

        # Load from config file if not set
        if not self._api_key or not self._project_id:
            key, pid, url = _load_posthog_config()
            self._api_key = self._api_key or key
            self._project_id = self._project_id or pid
            self._instance_url = self._instance_url or url

    def health_check(self) -> bool:
        """Check if credentials are configured (does not make a live request)."""
        return bool(self._api_key and self._project_id)

    @property
    def masked_api_key(self) -> str:
        """Return a display-safe version of the API key."""
        if self._api_key:
            return self._api_key[:8] + "..."
        return "(not set)"

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
            raise ConnectorError(
                f"Failed to reach PostHog instance: {exc}",
                source="posthog",
            ) from exc

        if response.status_code == 401:
            raise ConnectorAuthError(
                "PostHog API key is invalid or expired",
                source="posthog",
            )
        if response.status_code == 403:
            raise ConnectorAuthError(
                f"PostHog access denied (403). Check API key permissions and project ID. "
                f"Response: {response.text[:200]}",
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
            raise ConnectorError(
                f"PostHog returned invalid JSON: {exc}",
                source="posthog",
            ) from exc

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