"""Connector base layer for Agent Causal Decision Tool.

Defines the contract all external data source connectors must implement,
plus shared exception types and result schemas.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime, timezone


# ─── Exceptions ──────────────────────────────────────────────────────────────

class ConnectorError(Exception):
    """Base exception for connector failures (auth, network, etc.)."""
    pass


class InsufficientDataError(ConnectorError):
    """Raised when the source has experiment data but it's missing required fields."""

    def __init__(self, message: str, missing_fields: list[str], source: str = "unknown"):
        super().__init__(message)
        self.missing_fields = missing_fields
        self.source = source

    def to_dict(self) -> dict:
        return {
            "error": "INSUFFICIENT_DATA",
            "message": self.message,
            "missing_fields": self.missing_fields,
            "source": self.source,
        }


class ConnectorAuthError(ConnectorError):
    """Raised when credentials or auth to the source fail."""

    def __init__(self, message: str, source: str = "unknown"):
        super().__init__(message)
        self.source = source


class ConnectorNotFoundError(ConnectorError):
    """Raised when the experiment/resource is not found in the source."""

    def __init__(self, message: str, resource_id: str, source: str = "unknown"):
        super().__init__(message)
        self.resource_id = resource_id
        self.source = source


# ─── Result schema ────────────────────────────────────────────────────────────

@dataclass
class ConnectorResult:
    """Normalized output from any connector fetch operation."""

    # Raw or normalized experiment data suitable for run_decision_workflow
    data: dict

    # Metadata about where the data came from
    source_metadata: dict = field(default_factory=dict)

    # Original/raw payload as returned by the source (for audit/debugging)
    raw_payload: Optional[dict] = None

    # ISO timestamp of when the fetch completed
    fetch_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Warning messages (e.g. "exposure data missing, using impressions")
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "data": self.data,
            "source_metadata": self.source_metadata,
            "raw_payload": self.raw_payload,
            "fetch_timestamp": self.fetch_timestamp,
            "warnings": self.warnings,
        }


# ─── Base connector ────────────────────────────────────────────────────────────

class BaseConnector(ABC):
    """Abstract base class for all data source connectors.

    Implementors must:
      - Implement `fetch_experiment` returning a ConnectorResult
      - Implement `health_check` returning a bool
      - Populate `source_name` with the connector identifier (e.g. "posthog")
    """

    source_name: str = "base"

    @abstractmethod
    def fetch_experiment(self, experiment_id: str, **kwargs) -> ConnectorResult:
        """Fetch and normalize an experiment from the source.

        Args:
            experiment_id: Source-specific experiment identifier.
            **kwargs: Additional parameters (project_id, etc.).

        Returns:
            ConnectorResult with normalized data.

        Raises:
            ConnectorAuthError: Auth failure.
            ConnectorNotFoundError: Experiment not found.
            InsufficientDataError: Data present but missing required fields.
            ConnectorError: Other failures.
        """
        ...

    def health_check(self) -> bool:
        """Check if the connector is configured and can reach the source.

        Returns:
            True if credentials/config are present and source responds.
        """
        return False

    def _build_metadata(self, experiment_id: str, extra: Optional[dict] = None) -> dict:
        """Build standard source_metadata dict."""
        meta = {
            "connector": self.source_name,
            "experiment_id": experiment_id,
            "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            meta.update(extra)
        return meta