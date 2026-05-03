"""Tests for schema_version field and generate_schema() in outputs."""

import pytest
from importlib.metadata import version as _pkg_version

from src.schema import (
    ABTestOutput, DIDOutput, PlanningOutput,
)
from src.generate_schema import generate_schema


def _expected_version() -> str:
    return _pkg_version("agent-causal-decision-tool")


class TestSchemaVersionInOutputs:
    """schema_version must be present in all output models."""

    def test_ab_output_has_schema_version(self):
        output = ABTestOutput(
            recommendation={"decision": "ship", "confidence": "high", "summary": "test"},
            statistics={"control_rate": 0.1},
            traffic_stats={"control_size": 1000, "variant_size": 1000, "total_size": 2000},
            next_steps=["ship it"],
            audit={},
            inputs={},
        )
        assert hasattr(output, "schema_version")
        assert output.schema_version == _expected_version()

    def test_did_output_has_schema_version(self):
        output = DIDOutput(
            recommendation={"decision": "ship", "confidence": "high", "summary": "test"},
            statistics={"did_estimate": 5.0},
            traffic_stats={},
            next_steps=["ship it"],
            assumptions=["parallel trends"],
            audit={},
            inputs={},
        )
        assert hasattr(output, "schema_version")
        assert output.schema_version == _expected_version()

    def test_planning_output_has_schema_version(self):
        output = PlanningOutput(
            recommendation={"decision": "ship", "confidence": "high", "summary": "test"},
            planning={"mde_pct": 5},
            warnings=[],
            inputs={},
        )
        assert hasattr(output, "schema_version")
        assert output.schema_version == _expected_version()

    def test_schema_version_matches_package_version(self):
        import src
        expected = _expected_version()
        assert src.__version__ == expected

    def test_schema_version_in_json_output(self):
        output = ABTestOutput(
            recommendation={"decision": "ship", "confidence": "high", "summary": "test"},
            statistics={"control_rate": 0.1},
            traffic_stats={"control_size": 1000, "variant_size": 1000, "total_size": 2000},
            next_steps=["ship it"],
            audit={},
            inputs={},
        )
        json_str = output.model_dump_json()
        import json
        data = json.loads(json_str)
        assert "schema_version" in data
        assert data["schema_version"] == _expected_version()
        assert "version" not in data  # old field removed


class TestGenerateSchema:
    """generate_schema() produces the expected wrapper object."""

    def test_generate_schema_returns_dict(self):
        schema = generate_schema()
        assert isinstance(schema, dict)

    def test_schema_version_present(self):
        schema = generate_schema()
        assert "schema_version" in schema
        assert schema["schema_version"] == _expected_version()

    def test_schema_coverage(self):
        schema = generate_schema()
        assert schema["schema_coverage"] == ["ab", "did", "plan"]

    def test_schema_coverage_pending(self):
        schema = generate_schema()
        assert schema["schema_coverage_pending"] == ["bayes", "cohort"]

    def test_severity_contract_keys(self):
        schema = generate_schema()
        assert set(schema["severity_contract"].keys()) == {"info", "warning", "critical"}

    def test_definitions_contains_all_models(self):
        schema = generate_schema()
        for name in [
            "ABTestInput", "DIDInput", "PlanningInput",
            "ABTestOutput", "DIDOutput", "PlanningOutput",
            "Recommendation", "WarningDetail", "TrafficStats",
            "SequentialSummary", "DIDDiagnostics",
        ]:
            assert name in schema["definitions"], f"{name} missing from definitions"

    def test_definitions_are_valid_json_schemas(self):
        schema = generate_schema()
        import json
        for name, defn in schema["definitions"].items():
            assert isinstance(defn, dict)
            assert "type" in defn
            # Must be valid JSON
            json.dumps(defn)


class TestSchemaJsonFile:
    """schema.json at repo root must be present and valid."""

    def test_schema_json_exists_and_is_valid_json(self):
        import json
        with open("schema.json") as f:
            data = json.load(f)
        assert "schema_version" in data
        assert "definitions" in data

    def test_schema_json_matches_generate_schema_output(self):
        import json
        from src.generate_schema import generate_schema
        with open("schema.json") as f:
            file_data = json.load(f)
        generated = generate_schema()
        # Compare key fields
        assert file_data["schema_version"] == generated["schema_version"]
        assert file_data["schema_coverage"] == generated["schema_coverage"]
        assert set(file_data["definitions"].keys()) == set(generated["definitions"].keys())