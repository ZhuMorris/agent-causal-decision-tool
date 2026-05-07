"""Agent-native actions for the JSON-RPC API.

Each action wraps an existing internal function and returns a unified
AgentDecisionOutput. Input validation uses the existing Pydantic input models.

Actions:
  decide          — Easy-mode dispatcher (auto-selects A/B, Bayesian, DiD, planning)
  decide_ab       — Frequentist A/B test
  decide_rollout   — DiD (staged rollout / quasi-experiment)
  plan_test       — Experiment planning
  audit_result    — Full audit of a stored result
  save_result     — Persist a decision result to SQLite
  get_result      — Retrieve a stored result by ID
  compare_results — Compare multiple stored experiments
  connect         — Fetch experiment data from external connectors (e.g. PostHog)
  run_workflow    — Orchestrator: fetch + decide + save + notify + compare in one call
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from pydantic import ValidationError as PydanticValidationError

from .ab_test import calculate_ab
from .bayes import calculate_bayes_ab
from .did import calculate_did
from .planning import calculate_plan
from .dispatcher import run_decision_workflow
from .audit import audit_ab_test, audit_did
from .store import save_experiment as _store_save, get_experiment as _store_get, compare_experiments as _store_compare
from .unified import to_unified, AgentDecisionOutput
from .errors import (
    APIErrorResponse, APIException, validation_error, invalid_params, method_not_found,
    internal_error, result_not_found, save_failed,
    FieldError,
)
from .notifications import fire_webhook, build_webhook_payload

_logger = logging.getLogger(__name__)


# ─── Input dispatch ──────────────────────────────────────────────────────────

def _run_ab(input_data: dict, samples: int) -> AgentDecisionOutput:
    """decide_ab — frequentist A/B test."""
    try:
        ab_input = _validate_ab_input(input_data)
    except PydanticValidationError as ve:
        details = _pydantic_to_field_errors(ve)
        raise validation_error("Invalid A/B test inputs", details)

    result = calculate_ab({
        "control_conversions": ab_input.control_conversions,
        "control_total": ab_input.control_total,
        "variant_conversions": ab_input.variant_conversions,
        "variant_total": ab_input.variant_total,
        "variant_name": ab_input.variant_name,
        "sequential_enabled": ab_input.sequential_enabled,
        "experiment_start_time": ab_input.experiment_start_time,
        "experiment_end_time": ab_input.experiment_end_time,
        "min_runtime_days": ab_input.min_runtime_days,
        "min_sample_per_arm": ab_input.min_sample_per_arm,
        "early_stop_p_threshold": ab_input.early_stop_p_threshold,
        "max_runtime_days": ab_input.max_runtime_days,
        "practical_significance_threshold": ab_input.practical_significance_threshold,
    })
    return to_unified(result, "ab_test", "User requested frequentist A/B test via decide_ab action")


def _run_bayes(input_data: dict, samples: int) -> AgentDecisionOutput:
    """decide_ab (bayesian) — Bayesian A/B test."""
    try:
        ab_input = _validate_ab_input(input_data)
    except PydanticValidationError as ve:
        details = _pydantic_to_field_errors(ve)
        raise validation_error("Invalid Bayesian A/B test inputs", details)

    result = calculate_bayes_ab({
        "control_conversions": ab_input.control_conversions,
        "control_total": ab_input.control_total,
        "variant_conversions": ab_input.variant_conversions,
        "variant_total": ab_input.variant_total,
    }, n_samples=samples)
    return to_unified(result, "bayesian_ab", "User requested Bayesian A/B test via decide_ab with bayesian=true")


def _run_did(input_data: dict) -> AgentDecisionOutput:
    """decide_rollout — DiD for staged rollouts / quasi-experiments."""
    from .schema import DIDInput as _DIDInput

    try:
        did_input = _DIDInput(**input_data)
    except PydanticValidationError as ve:
        details = _pydantic_to_field_errors(ve)
        raise validation_error("Invalid DiD inputs", details)

    result = calculate_did({
        "pre_control": did_input.pre_control,
        "post_control": did_input.post_control,
        "pre_treated": did_input.pre_treated,
        "post_treated": did_input.post_treated,
        "pre_periods": did_input.pre_periods,
        "post_periods": did_input.post_periods,
        "treatment_observation_count": did_input.treatment_observation_count,
        "control_observation_count": did_input.control_observation_count,
        "notes": did_input.notes,
        "n_bootstrap": did_input.n_bootstrap,
    })
    return to_unified(result, "did", "User requested DiD analysis via decide_rollout (staged rollout/quasi-experiment)")


def _run_plan(input_data: dict) -> AgentDecisionOutput:
    """plan_test — experiment planning."""
    from .schema import PlanningInput as _PlanningInput

    try:
        plan_input = _PlanningInput(**input_data)
    except PydanticValidationError as ve:
        details = _pydantic_to_field_errors(ve)
        raise validation_error("Invalid planning inputs", details)

    try:
        result = calculate_plan({
            "baseline_conversion_rate": plan_input.baseline_conversion_rate,
            "mde_pct": plan_input.mde_pct,
            "daily_traffic": plan_input.daily_traffic,
            "confidence_level": plan_input.confidence_level,
            "power": plan_input.power,
            "allocation": plan_input.allocation,
            "allocation_ratio": plan_input.allocation_ratio,
        })
    except ValueError as ve:
        raise validation_error(str(ve), [FieldError(field="input", issue=str(ve))])
    return to_unified(result, "planning", "User requested experiment planning via plan_test action")


# ─── Validation helpers ──────────────────────────────────────────────────────

def _validate_ab_input(input_data: dict) -> "ABTestInput":
    """Validate input_data against ABTestInput schema.

    Returns ABTestInput on success. Raises PydanticValidationError on failure.
    """
    from .schema import ABTestInput as _ABTestInput
    return _ABTestInput(**input_data)


# ─── Field error mapping ──────────────────────────────────────────────────────

def _pydantic_to_field_errors(ve: PydanticValidationError) -> list[FieldError]:
    """Convert a Pydantic ValidationError to a list of FieldErrors."""
    details = []
    for err in ve.errors():
        loc = ".".join(str(l) for l in err["loc"])
        details.append(FieldError(field=loc, issue=err["msg"]))
    return details


# ─── Public action interface ──────────────────────────────────────────────────

def run_action(action: str, params: dict, request_id: Optional[str] = None) -> dict:
    """Run an agent action and return a JSON-RPC success or error response dict.

    Args:
        action: One of the 9 supported actions
        params: Dict of action parameters
        request_id: Optional request ID for tracking

    Returns:
        A dict ready to be serialized as a JSON-RPC response (success or error).
    """
    try:
        outcome = _dispatch_action(action, params)
        # Pydantic models must be converted to dict for JSON-RPC serialization
        if hasattr(outcome, "model_dump"):
            outcome = outcome.model_dump()
        return {
            "jsonrpc": "2.0",
            "result": outcome,
            "id": request_id,
        }
    except APIException as e:
        return e.to_jsonrpc(request_id)
    except PydanticValidationError as ve:
        err = validation_error(
            "Input validation failed",
            _pydantic_to_field_errors(ve),
            request_id
        )
        return err.to_jsonrpc(request_id)
    except Exception as exc:
        err = internal_error(f"Unexpected error in {action}: {type(exc).__name__}: {exc}")
        return err.to_jsonrpc(request_id)


def _dispatch_action(action: str, params: dict) -> AgentDecisionOutput | list[dict] | dict:
    """Dispatch to the appropriate action handler.

    Raises APIErrorResponse on known errors.
    Returns the appropriate Python object for the response result.
    """
    # decide_ab: supports both frequentist and bayesian modes
    if action == "decide_ab":
        mode = params.get("mode", "frequentist")
        samples = params.get("samples", 20000)
        input_data = params.get("input", params)

        # Remove internal keys that aren't part of ABTestInput
        input_data = {k: v for k, v in input_data.items()
                      if k not in ("mode", "samples", "action", "request_id")}

        if mode == "bayesian":
            return _run_bayes(input_data, samples)
        return _run_ab(input_data, samples)

    # decide_rollout: DiD for staged rollouts
    if action == "decide_rollout":
        input_data = {k: v for k, v in params.items()
                      if k not in ("action", "request_id")}
        return _run_did(input_data)

    # plan_test: experiment planning
    if action == "plan_test":
        input_data = {k: v for k, v in params.items()
                      if k not in ("action", "request_id")}
        return _run_plan(input_data)

    # audit_result: full audit of a stored experiment
    if action == "audit_result":
        result_id = params.get("result_id")
        if result_id is None:
            raise validation_error(
                "Missing required field: result_id",
                [FieldError(field="result_id", issue="result_id is required")]
            )
        experiment = _store_get(result_id)
        if experiment is None:
            raise result_not_found(f"experiment id={result_id}", request_id=None)

        raw = json.loads(experiment["raw_json"])
        inputs = json.loads(experiment["inputs_json"])
        mode = experiment["mode"]

        # Select correct audit function
        if mode == "ab_test":
            audit_out = audit_ab_test(inputs, raw)
        elif mode == "did":
            audit_out = audit_did(inputs, raw)
        else:
            audit_out = {"experiment_type": mode, "note": f"Audit for mode={mode} not yet implemented"}

        return audit_out

    # save_result: persist a decision result to SQLite
    if action == "save_result":
        result_data = params.get("result")
        if result_data is None:
            raise validation_error(
                "Missing required field: result",
                [FieldError(field="result", issue="result object is required")]
            )

        mode = params.get("mode", result_data.get("mode", "unknown"))
        inputs = params.get("inputs", result_data.get("inputs", {}))
        result_json = json.dumps(result_data) if isinstance(result_data, dict) else result_data
        inputs_json = json.dumps(inputs) if isinstance(inputs, dict) else inputs

        try:
            row_id = _store_save(result_json, mode, inputs_json)
        except Exception as exc:
            raise save_failed(f"Failed to save experiment: {exc}")

        return {"saved_id": row_id, "mode": mode}

    # get_result: retrieve a stored result by ID
    if action == "get_result":
        result_id = params.get("result_id")
        if result_id is None:
            raise validation_error(
                "Missing required field: result_id",
                [FieldError(field="result_id", issue="result_id is required")]
            )
        experiment = _store_get(result_id)
        if experiment is None:
            raise result_not_found(f"experiment id={result_id}")
        return experiment

    # compare_results: compare multiple stored experiments
    if action == "compare_results":
        experiment_ids = params.get("experiment_ids", [])
        if not experiment_ids:
            raise validation_error(
                "Missing required field: experiment_ids",
                [FieldError(field="experiment_ids", issue="experiment_ids must be a non-empty list of integers")]
            )
        comparison = _store_compare(experiment_ids)
        if "error" in comparison:
            raise validation_error(
                comparison["error"],
                [FieldError(field="experiment_ids", issue=comparison["error"])]
            )
        return comparison  # decide: easy-mode dispatcher — auto-selects the right method
    if action == "decide":
        samples = params.get("samples", 20000)
        input_data = params.get("input", params)
        input_data = {k: v for k, v in input_data.items()
                      if k not in ("mode", "samples", "action", "request_id")}
        return run_decision_workflow(input_data, samples=samples)

    # connect: fetch experiment data from an external connector
    if action == "connect":
        from .connectors import (
            PostHogConnector,
            ConnectorAuthError,
            ConnectorNotFoundError,
            InsufficientDataError,
            ConnectorError,
        )
        source = params.get("source", "")
        experiment_id = params.get("experiment_id", "")
        if not experiment_id:
            raise validation_error(
                "Missing required field: experiment_id",
                [FieldError(field="experiment_id", issue="experiment_id is required")]
            )
        if source == "posthog":
            try:
                connector = PostHogConnector()
                result = connector.fetch_experiment(experiment_id)
                return {"result": result.to_dict()}
            except ConnectorAuthError as exc:
                raise validation_error(
                    f"PostHog auth error: {exc}",
                    [FieldError(field="source", issue="Invalid or insufficient PostHog credentials")]
                )
            except ConnectorNotFoundError as exc:
                raise validation_error(
                    f"Experiment '{experiment_id}' not found in PostHog",
                    [FieldError(field="experiment_id", issue=str(exc))]
                )
            except InsufficientDataError as exc:
                raise validation_error(
                    str(exc),
                    [FieldError(field=f, issue=f"missing or invalid") for f in exc.missing_fields]
                )
            except ConnectorError as exc:
                raise internal_error(f"Connector error ({exc.source}): {exc}")
        else:
            raise validation_error(
                f"Unknown connector source: '{source}'. Valid sources: posthog",
                [FieldError(field="source", issue=f"Unknown source: {source}")]
            )

    # run_workflow: orchestrator — fetch + decide + save + notify + compare
    if action == "run_workflow":
        return run_workflow(params)


    # Unknown action
    raise method_not_found(action)


def run_workflow(params: dict) -> dict:
    """run_workflow — orchestrator action: fetch + decide + save + notify + compare.

    Args:
        params dict with keys:
          source          — "posthog" to fetch from PostHog before running; omit to use input data directly
          experiment_id  — required when source="posthog"
          input          — decision input (same fields as decide action); ignored when source is set
          control_conversions, control_total, variant_conversions, variant_total — A/B fields
          bayesian       — bool, optional
          samples        — int, Monte Carlo samples for Bayesian (default 20000)
          dry_run        — bool, if True validate connector + normalize data without running decision
          save           — bool, whether to persist result to SQLite (default True)
          notify         — bool, whether to fire webhook on decision (default False)
          compare_with   — list of prior result IDs to compare against (optional)

    Returns:
        dict with keys: selected_method, decision_result, audit_result,
                        saved_result_id (or None), comparison_summary (or None), source_metadata
    """
    dry_run = params.get("dry_run", False)
    source = params.get("source", "")
    save = params.get("save", True)
    notify = params.get("notify", False)
    compare_with = params.get("compare_with", [])
    samples = params.get("samples", 20000)

    # ── 1. Fetch from connector if source is set ──────────────────────────
    experiment_id = params.get("experiment_id", "")
    normalized_data = None
    source_metadata = None

    if source == "posthog":
        from .connectors import (
            PostHogConnector,
            ConnectorAuthError,
            ConnectorNotFoundError,
            InsufficientDataError,
            ConnectorError,
        )
        connector = PostHogConnector()

        # Dry-run: just validate connectivity and normalize
        if dry_run:
            health = connector.health_check()
            validation_result = {
                "dry_run": True,
                "connector_connected": health,
                "source": source,
                "experiment_id": experiment_id,
                "validation": "passed" if health else "connector not configured or unreachable",
            }
            if health and experiment_id:
                try:
                    result = connector.fetch_experiment(experiment_id)
                    validation_result["normalized_data"] = result.data
                    validation_result["source_metadata"] = result.source_metadata
                except (ConnectorAuthError, ConnectorNotFoundError, InsufficientDataError, ConnectorError) as exc:
                    validation_result["validation"] = f"failed: {exc}"
            return validation_result

        # Normal fetch
        try:
            result = connector.fetch_experiment(experiment_id)
            normalized_data = result.data
            source_metadata = result.source_metadata
        except ConnectorAuthError as exc:
            raise validation_error(
                f"PostHog auth error: {exc}",
                [FieldError(field="source", issue="Invalid or insufficient PostHog credentials")]
            )
        except ConnectorNotFoundError as exc:
            raise validation_error(
                f"Experiment '{experiment_id}' not found in PostHog",
                [FieldError(field="experiment_id", issue=str(exc))]
            )
        except InsufficientDataError as exc:
            raise validation_error(
                str(exc),
                [FieldError(field=f, issue=f"missing or invalid") for f in exc.missing_fields]
            )
        except ConnectorError as exc:
            raise internal_error(f"Connector error ({exc.source}): {exc}")
    else:
        # No source — use input data directly
        if dry_run:
            # In dry_run without a source, just return validation passed
            return {
                "dry_run": True,
                "connector_connected": None,
                "source": None,
                "validation": "passed (no connector used)",
            }

    # ── 2. Build decision input ───────────────────────────────────────────
    if normalized_data is not None:
        # Data already normalized from connector
        input_data = normalized_data
    else:
        # Use explicit input fields (same as decide action)
        input_data = {
            k: v for k, v in params.items()
            if k not in ("source", "experiment_id", "dry_run", "save", "notify", "compare_with", "samples", "action", "request_id")
        }
        # Allow nested input dict
        if "input" in params:
            input_data = {**params["input"], **input_data}

    # ── 3. Run decision ────────────────────────────────────────────────────
    decision_result = run_decision_workflow(input_data, samples=samples)
    method = decision_result.selected_method
    decision = decision_result.decision

    # ── 4. Audit ────────────────────────────────────────────────────────────
    internal = decision_result.internal_result
    if internal is None:
        audit_result = {"note": "no internal result available for audit"}
    elif method == "ab_test":
        audit_result = audit_ab_test(input_data, internal)
    elif method == "did":
        audit_result = audit_did(input_data, internal)
    else:
        audit_result = {"experiment_type": method, "note": "audit not yet implemented for this method"}

    # ── 5. Save ─────────────────────────────────────────────────────────────
    saved_result_id = None
    if save:
        result_json = json.dumps(internal) if isinstance(internal, dict) else internal
        inputs_json = json.dumps(input_data)
        mode = method
        saved_result_id = _store_save(result_json, mode, inputs_json)

    # ── 6. Notify webhook ────────────────────────────────────────────────────
    if notify and decision in ("ship", "reject", "escalate"):
        webhook_url = os.environ.get("AGENT_CAUSAL_WEBHOOK_URL")
        if webhook_url:
            statistics = {}
            if internal and isinstance(internal, dict):
                stats = internal.get("statistics", {})
                if hasattr(stats, "model_dump"):
                    statistics = stats.model_dump()
                elif isinstance(stats, dict):
                    statistics = stats

            payload = build_webhook_payload(
                decision=decision,
                summary=decision_result.effect_summary,
                method=method,
                statistics=statistics,
                result_id=str(saved_result_id) if saved_result_id else None,
                timestamp=decision_result.timestamp,
            )
            fire_webhook(webhook_url, payload)

    # ── 7. Compare with prior experiments ─────────────────────────────────
    comparison_summary = None
    if compare_with:
        comparison = _store_compare(list(compare_with) + ([saved_result_id] if saved_result_id else []))
        if "error" not in comparison:
            comparison_summary = comparison

    return {
        "selected_method": method,
        "decision_result": decision_result.model_dump() if hasattr(decision_result, "model_dump") else decision_result,
        "audit_result": audit_result,
        "saved_result_id": saved_result_id,
        "comparison_summary": comparison_summary,
        "source_metadata": source_metadata,
    }
