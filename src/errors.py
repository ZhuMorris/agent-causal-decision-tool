"""Structured error contract for the Agent Causal JSON-RPC API.

All errors follow a consistent envelope so agents can parse failures
programmatically and surface field-level issues clearly.

Error codes:
  -32700  Parse error          — JSON is malformed
  -32600  Invalid request     — envelope is valid but not a valid JSON-RPC request
  -32601  Method not found    — action name is not recognized
  -32602  Invalid params      — params fail validation (field-level detail included)
  -32603  Internal error      — unexpected error in the server (not client input)
"""

from __future__ import annotations

from typing import Optional, Any, List
from enum import Enum


# ─── Exception (not a Pydantic model — raised by actions.py) ─────────────────

class APIException(Exception):
    """Raised by actions.py when a structured API error should be returned.

    The .error attribute carries the error data as a plain dict.
    """
    def __init__(self, code: str, message: str, details: Optional[list[dict]] = None, request_id: Optional[str] = None):
        self.code = code
        self.message = message
        self.details = details or []
        self.request_id = request_id
        super().__init__(message)

    def to_jsonrpc(self, request_id: Optional[str] = None) -> dict:
        """Render as a JSON-RPC error response dict."""
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": self.code,
                "message": self.message,
                "data": {
                    "details": self.details,
                    "request_id": request_id if request_id is not None else self.request_id,
                }
            },
            "id": request_id,
        }


class ErrorCode(str, Enum):
    """JSON-RPC error codes used by Agent Causal."""
    PARSE_ERROR = "PARSE_ERROR"          # -32700
    INVALID_REQUEST = "INVALID_REQUEST"  # -32600
    METHOD_NOT_FOUND = "METHOD_NOT_FOUND"  # -32601
    INVALID_PARAMS = "INVALID_PARAMS"    # -32602
    INTERNAL_ERROR = "INTERNAL_ERROR"    # -32603

    # Extended codes (use code + message for these)
    VALIDATION_ERROR = "VALIDATION_ERROR"    # field-level input validation
    UNSUPPORTED_MEDIA = "UNSUPPORTED_MEDIA"  # content-type not application/json
    RESULT_NOT_FOUND = "RESULT_NOT_FOUND"    # get_result / audit_result on unknown ID
    SAVE_FAILED = "SAVE_FAILED"             # could not persist to SQLite


class FieldError:
    """Single field validation error."""
    def __init__(self, field: str, issue: str):
        self.field = field
        self.issue = issue

    def to_dict(self) -> dict:
        return {"field": self.field, "issue": self.issue}


# ─── Error builders ──────────────────────────────────────────────────────────

def validation_error(message: str, details: list[FieldError], request_id: Optional[str] = None) -> APIException:
    """Build a VALIDATION_ERROR exception."""
    return APIException(
        code=ErrorCode.VALIDATION_ERROR.value,
        message=message,
        details=[fe.to_dict() for fe in details],
        request_id=request_id,
    )


def invalid_params(message: str, details: list[FieldError], request_id: Optional[str] = None) -> APIException:
    """Build an INVALID_PARAMS exception."""
    return APIException(
        code=ErrorCode.INVALID_PARAMS.value,
        message=message,
        details=[fe.to_dict() for fe in details],
        request_id=request_id,
    )


def method_not_found(method: str, request_id: Optional[str] = None) -> APIException:
    """Build a METHOD_NOT_FOUND exception."""
    return APIException(
        code=ErrorCode.METHOD_NOT_FOUND.value,
        message=f"Unknown action: '{method}'. Valid actions are: decide, decide_ab, decide_rollout, plan_test, audit_result, save_result, get_result, compare_results, connect",
        details=[],
        request_id=request_id,
    )


def internal_error(message: str, request_id: Optional[str] = None) -> APIException:
    """Build an INTERNAL_ERROR exception."""
    return APIException(
        code=ErrorCode.INTERNAL_ERROR.value,
        message=message,
        details=[],
        request_id=request_id,
    )


def parse_error(message: str) -> dict:
    """Build a raw JSON-RPC parse error (no request_id available)."""
    return {
        "jsonrpc": "2.0",
        "error": {"code": -32700, "message": message},
        "id": None,
    }


def result_not_found(resource_id: Any, request_id: Optional[str] = None) -> APIException:
    """Build a RESULT_NOT_FOUND exception."""
    return APIException(
        code=ErrorCode.RESULT_NOT_FOUND.value,
        message=f"Resource not found: {resource_id}",
        details=[],
        request_id=request_id,
    )


def save_failed(message: str, request_id: Optional[str] = None) -> APIException:
    """Build a SAVE_FAILED exception."""
    return APIException(
        code=ErrorCode.SAVE_FAILED.value,
        message=message,
        details=[],
        request_id=request_id,
    )


# ─── Pydantic validation helper ─────────────────────────────────────────────

def pydantic_to_field_errors(ve) -> list[FieldError]:
    """Convert a Pydantic ValidationError to a list of FieldErrors.

    Used by both errors.py (for direct error construction) and actions.py
    (for action-level validation errors).
    """
    details = []
    for err in ve.errors():
        loc = ".".join(str(l) for l in err["loc"])
        details.append(FieldError(field=loc, issue=err["msg"]))
    return details


# ─── APIErrorResponse (Pydantic model for structured response schema) ─────────
# Keep a Pydantic model for the structured error response schema — used by
# tests and for documentation. This is NOT raised as an exception.

from pydantic import BaseModel, Field


class APIErrorResponse(BaseModel):
    """Standard JSON-RPC error response (for schema documentation and tests)."""
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    details: list[dict] = Field(
        default_factory=list,
        description="Per-field validation errors. Empty for non-validation errors."
    )
    request_id: Optional[str] = Field(
        default=None,
        description="The id of the request that caused this error, if available."
    )

    def to_jsonrpc(self, request_id: Optional[str] = None) -> dict:
        """Render as a JSON-RPC error response dict."""
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": self.code,
                "message": self.message,
                "data": {
                    "details": self.details,
                    "request_id": request_id if request_id is not None else self.request_id,
                }
            },
            "id": request_id,
        }