"""Generate schema contract JSON for agent-causal-decision-tool."""

import json
from importlib.metadata import version as _pkg_version
from pydantic import BaseModel

from .schema import (
    ABTestInput, DIDInput, PlanningInput,
    ABTestOutput, DIDOutput, PlanningOutput,
    Recommendation, WarningDetail, TrafficStats,
    SequentialSummary, DIDDiagnostics,
    WarningCode,
)


def _pydantic_to_json_schema(model_cls: type[BaseModel]) -> dict:
    """Convert a Pydantic model to a JSON Schema dict."""
    return model_cls.model_json_schema()


def generate_schema() -> dict:
    """
    Generate the schema contract wrapper object.

    This builds a custom wrapper (not raw JSON Schema) containing:
    - schema_version from package metadata
    - schema_coverage: modes with full schema coverage
    - schema_coverage_pending: modes pending full schema coverage
    - severity_contract: canonical severity levels and their meaning
    - definitions: JSON Schema for each Pydantic model, keyed by class name
    """
    schema_version = _pkg_version("agent-causal-decision-tool")

    definitions = {}
    for cls in [
        ABTestInput, DIDInput, PlanningInput,
        ABTestOutput, DIDOutput, PlanningOutput,
        Recommendation, WarningDetail, TrafficStats,
        SequentialSummary, DIDDiagnostics,
    ]:
        definitions[cls.__name__] = _pydantic_to_json_schema(cls)

    # Severity contract
    severity_contract = {
        "info": (
            "Agent should log and continue. No blocking action required. "
            "Informational only — does not prevent shipping or escalation decisions."
        ),
        "warning": (
            "Agent should log and consider but may proceed with caution. "
            "Used when evidence is weaker than ideal or when some assumption is "
            "relaxed but the result is still actionable."
        ),
        "critical": (
            "Agent must log and either block or escalate. Result should not be "
            "treated as reliable without human review. Used when an assumption "
            "fundamental to the analysis is violated or when sample size is "
            "insufficient for any reliable inference."
        ),
    }

    return {
        "schema_version": schema_version,
        "schema_coverage": ["ab", "did", "plan"],
        "schema_coverage_pending": ["bayes", "cohort"],
        "severity_contract": severity_contract,
        "definitions": definitions,
    }


def write_schema_json(path: str = "schema.json") -> None:
    """Write the schema contract to a JSON file at the given path."""
    schema = generate_schema()
    with open(path, "w") as f:
        json.dump(schema, f, indent=2)


if __name__ == "__main__":
    write_schema_json()
    print("schema.json written.")