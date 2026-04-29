---
name: agent-causal
description: Causal decision and audit tool for AI agents. Run A/B tests and Difference-in-Differences analysis with structured JSON output, decision paths, and audit trails.
metadata:
  {
    "openclaw": {
      "category": "data-science",
      "version": "0.1.0",
      "tools": ["exec"],
      "requires": {
        "bins": ["python3"],
        "python packages": ["click", "scipy", "numpy", "pydantic"]
      }
    }
  }
---

# Agent Causal Decision Tool

A causal decision and audit tool for AI agents. Evaluate product changes using A/B testing and Difference-in-Differences methods.

## Capabilities

- **A/B Testing**: Analyze randomized experiments with statistical significance (z-test, p-values, confidence intervals)
- **Difference-in-Differences (DiD)**: Analyze observational rollout changes when A/B testing isn't feasible
- **Decision Audit**: Reconstruct and explain any previous decision with step-by-step reasoning
- **Structured Output**: Machine-readable JSON recommendations for agent workflows
- **Agent-Native**: Designed for AI agent consumption, not human dashboards

## Commands

### A/B Test Analysis

```bash
python3 -m src.cli ab --control 100/5000 --variant 130/5000
```

**Parameters:**
- `--control`: Control group conversions/total (e.g., `100/5000`)
- `--variant`: Variant group conversions/total (e.g., `130/5000`)
- `--name`: Variant name (optional, default: `variant_1`)
- `--format`: Output format `json` or `text` (default: `json`)

**Example Input:**
```json
{
  "control_conversions": 100,
  "control_total": 5000,
  "variant_conversions": 130,
  "variant_total": 5000
}
```

**Example Output:**
```json
{
  "recommendation": {
    "decision": "ship",
    "confidence": "medium",
    "summary": "Variant performs 30.00% better (p=0.0454). Ship it."
  },
  "statistics": {
    "control_rate": 0.02,
    "variant_rate": 0.026,
    "relative_lift_pct": 30.0,
    "p_value": 0.045361
  },
  "audit": {
    "decision_path": [
      {"step": "Input validation", "passed": true},
      {"step": "Traffic check", "passed": true},
      {"step": "Statistical significance test", "passed": true, "p_value": 0.045361, "alpha": 0.05},
      {"step": "Decision", "decision": "ship"}
    ]
  }
}
```

### DiD Analysis

```bash
python3 -m src.cli did --pre-control 1000 --post-control 1100 --pre-treated 900 --post-treated 1150
```

**Parameters:**
- `--pre-control`: Control group metric before treatment
- `--post-control`: Control group metric after treatment
- `--pre-treated`: Treated group metric before treatment
- `--post-treated`: Treated group metric after treatment

### Decision Audit

```bash
python3 -m src.cli audit <output_file.json>
python3 -m src.cli audit <output_file.json> --format text
```

Reconstruct and explain how a previous decision was made.

## Decision Values

| Decision | Meaning |
|-----------|---------|
| `ship` | Statistically significant positive effect - ready to deploy |
| `keep_running` | Trending positive but not yet significant - continue experiment |
| `reject` | Statistically significant negative effect - do not deploy |
| `escalate` | Inconclusive or critical warnings - needs human review |

## Installation

This skill is installed in the agent-causal-decision-tool repository.

To reinstall dependencies:
```bash
pip install click scipy numpy pydantic
```

## Location

```
~/clawd/agent-causal-decision-tool/
```

Source code and tests available in the GitHub repository.