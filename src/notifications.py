"""Non-blocking webhook notifications for decision events."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

_logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="webhook-")


def _fire_webhook_sync(url: str, payload: dict) -> None:
    """Synchronously fire a webhook. Logs errors and returns silently."""
    try:
        client = httpx.Client(timeout=10.0)
        try:
            response = client.post(url, json=payload, timeout=10.0)
            response.raise_for_status()
            _logger.info("Webhook fired to %s — %d", url, response.status_code)
        finally:
            client.close()
    except Exception as exc:
        _logger.warning("Webhook to %s failed: %s", url, exc)


def fire_webhook(url: str | None, payload: dict) -> None:
    """Fire a webhook asynchronously (fire-and-forget).

    Silently ignores if AGENT_CAUSAL_WEBHOOK_URL is not set or if the request fails.
    """
    if not url:
        return
    if httpx is None:
        _logger.warning("httpx not installed — cannot fire webhook to %s", url)
        return
    _executor.submit(_fire_webhook_sync, url, payload.copy())


def build_webhook_payload(
    decision: str,
    summary: str,
    method: str,
    statistics: dict,
    result_id: str | None,
    timestamp: str | None = None,
) -> dict:
    """Build the standard webhook payload."""
    return {
        "decision": decision,
        "summary": summary,
        "method": method,
        "statistics": statistics,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "result_id": result_id,
    }
