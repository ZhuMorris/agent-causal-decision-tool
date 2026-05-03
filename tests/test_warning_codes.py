"""Tests for WarningCode enum — exhaustive, no bare string literals."""

import ast
import re
from pathlib import Path

from src.schema import WarningCode, WarningDetail


# ─── WarningCode Enum Completeness ─────────────────────────────────────────

class TestWarningCodeEnum:
    """All 30 canonical warning codes must be present in WarningCode enum."""

    EXPECTED_CODES = {
        # A/B Test
        "LOW_TRAFFIC",
        "SMALL_EFFECT",
        "INCONCLUSIVE",
        "NOT_SIGNIFICANT",
        "BORDERLINE_P_VALUE",
        "CORRECTION_CONSERVATIVE",
        "SEQUENTIAL_EARLY_STOP",
        "SEQUENTIAL_CONDITIONS_NOT_MET",
        "MAX_RUNTIME_EXCEEDED",
        # DiD
        "ZERO_BASELINE",
        "PARALLEL_TRENDS_VIOLATED",
        "PARALLEL_TRENDS_WEAK",
        "BOTH_GROUPS_GREW",
        "AGGREGATE_DATA",
        "AGGREGATE_DATA_DID",
        "SINGLE_PRE_PERIOD",
        "SMALL_SAMPLE",
        "IMBALANCED_GROUPS",
        "LARGE_EFFECT_SMALL_SAMPLE",
        "PARALLEL_TRENDS_NO_DATA",
        "BOOTSTRAP_CI_UNRELIABLE",
        "BOOTSTRAP_CI_WIDE",
        # Planning
        "SLOW_EXPERIMENT",
        "INFEASIBLE_EXPERIMENT",
        "SMALL_MDE",
        "BASELINE_VERY_LOW",
        # Bayesian
        "PRIOR_DOMINATES",
        "CREDIBLE_INTERVAL_WIDE",
        # Q6 / Q16 additions
        "DID_CI_CROSSES_ZERO",
        "BASELINE_NEAR_ZERO",
    }

    def test_all_expected_codes_present(self):
        actual_codes = {c.value for c in WarningCode}
        missing = self.EXPECTED_CODES - actual_codes
        extra = actual_codes - self.EXPECTED_CODES
        assert not missing, f"Missing warning codes: {missing}"
        assert not extra, f"Extra codes not in spec: {extra}"

    def test_exactly_30_codes(self):
        assert len(WarningCode) == 30, f"Expected 30 codes, got {len(WarningCode)}"

    def test_warning_code_is_str_enum(self):
        """Each WarningCode must be a str so WarningDetail accepts it as code."""
        for code in WarningCode:
            assert isinstance(code.value, str)
            assert isinstance(code, str)  # str(Enum) behavior

    def test_warning_detail_accepts_warning_code(self):
        """WarningDetail.code must accept a WarningCode value."""
        detail = WarningDetail(
            code=WarningCode.LOW_TRAFFIC,
            message="Traffic too low",
            severity="warning"
        )
        assert detail.code == WarningCode.LOW_TRAFFIC


# ─── Warning Detail Code Typing ────────────────────────────────────────────────

class TestWarningDetailCodeTyping:
    """WarningDetail.code must be typed as WarningCode (not bare str)."""

    def test_warning_detail_code_accepts_all_enum_values(self):
        for code in WarningCode:
            detail = WarningDetail(code=code, message="test", severity="info")
            assert detail.code == code

    def test_warning_detail_json_serializes_code_as_string(self):
        detail = WarningDetail(
            code=WarningCode.BOOTSTRAP_CI_WIDE,
            message="CI is wide",
            severity="warning"
        )
        json_str = detail.model_dump_json()
        import json
        data = json.loads(json_str)
        assert data["code"] == "BOOTSTRAP_CI_WIDE"
        assert isinstance(data["code"], str)


# ─── No Bare String Literals ──────────────────────────────────────────────────

class TestNoBareStringLiterals:
    """Warning codes must only appear via WarningCode enum — no bare string literals."""

    SRC_DIR = Path("src")

    def test_no_bare_warning_code_strings_in_src(self):
        """
        Grep check: any bare string matching a WarningCode value in src/*.py
        indicates the enum is not being used.

        Note: schema.py itself is skipped — it defines the enum via
        CODE = "CODE" assignments which would otherwise trigger this check.
        """
        code_values = {c.value for c in WarningCode}
        violations = []

        for py_file in self.SRC_DIR.glob("*.py"):
            if py_file.name == "schema.py":
                continue  # enum is defined here; skip
            content = py_file.read_text()
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            if node.value and isinstance(node.value, ast.Constant):
                                val = node.value.value
                                if val in code_values:
                                    violations.append(f"{py_file.name}:{target.id} = '{val}'")

        assert not violations, f"Bare string literals for warning codes found:\n" + "\n".join(violations)

    def test_no_string_literal_codes_in_warning_detail_construction(self):
        """
        Detect direct string literals being passed as code= in WarningDetail calls.
        """
        code_values = {c.value for c in WarningCode}
        violations = []

        for py_file in self.SRC_DIR.glob("*.py"):
            content = py_file.read_text()

            # Find all code="..." patterns that are not code=WarningCode.XXX
            pattern = re.compile(r'code\s*=\s*"([A-Z_][A-Z_]{3,})"')
            for match in pattern.finditer(content):
                code_str = match.group(1)
                # Make sure it's not already using the enum
                # Look for surrounding context
                start = max(0, match.start() - 20)
                end = min(len(content), match.end() + 20)
                ctx = content[start:end]
                if "WarningCode." not in ctx:
                    violations.append(f"{py_file.name}: {match.group(0)}")

        assert not violations, f"Bare string code literals found:\n" + "\n".join(violations)


# ─── Code Migration Sanity ─────────────────────────────────────────────────────

class TestCodeMigration:
    """Verify old codes are replaced by canonical names."""

    SRC_DIR = Path("src")
    OLD_CODE_MIGRATIONS = {
        "TRENDS_DIVERGE": "PARALLEL_TRENDS_VIOLATED",
        "TRENDS_SLIGHTLY_DIVERGE": "PARALLEL_TRENDS_WEAK",
        "AMBIGUOUS": "BOTH_GROUPS_GREW",
        "early_stop_applied": "SEQUENTIAL_EARLY_STOP",
        "did_result_should_be_reviewed_by_human": "AGGREGATE_DATA_DID",
    }

    def test_no_old_codes_in_source(self):
        """Old code strings must not appear in src/ as bare literals."""
        violations = []
        src_dir = Path("src")
        for old_code in self.OLD_CODE_MIGRATIONS:
            for py_file in src_dir.glob("*.py"):
                content = py_file.read_text()
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    # Skip dictionary key declarations like "old_code": value
                    if ':' in line:
                        # Check if old_code appears as a dictionary key on this line
                        key_match = re.match(rf'^\s*["\']{old_code}["\']\s*:', line)
                        if key_match:
                            continue
                    if f'"{old_code}"' in line or f"'{old_code}'" in line:
                        violations.append(f"{py_file.name}:{i}: contains old code '{old_code}' in: {line.strip()}")
        assert not violations, "Old warning code strings still in source:\n" + "\n".join(violations)