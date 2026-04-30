---
name: agent-causal
description: Causal decision and audit tool for AI agents. Run A/B tests and Difference-in-Differences analysis with structured JSON output, decision paths, and audit trails.
metadata:
  {
    "openclaw": {
      "category": "data-science",
      "version": "0.2.0",
      "tools": ["exec"],
      "requires": {
        "bins": ["python3", "git", "pip"],
        "python packages": ["click", "scipy", "numpy", "pydantic"]
      },
      "source": "https://github.com/ZhuMorris/agent-causal-decision-tool"
    }
  }
---

# Agent Causal Decision Tool

A causal decision and audit tool for AI agents. Evaluate product changes using A/B testing and Difference-in-Differences methods.

**Source:** https://github.com/ZhuMorris/agent-causal-decision-tool

## Setup

Before using this skill, install the tool:

```bash
# Clone the repository (if not already present)
git clone https://github.com/ZhuMorris/agent-causal-decision-tool.git ~/clawd/agent-causal-decision-tool 2>/dev/null || true

# Install dependencies
pip install click scipy numpy pydantic -q

# Navigate to the tool directory
cd ~/clawd/agent-causal-decision-tool
```

Alternatively, install as a Python package:
```bash
pip install git+https://github.com/ZhuMorris/agent-causal-decision-tool.git -q
```

## Commands

### Experiment Planning (ab_plan)

Estimate required sample size, duration, and feasibility before running an experiment:

```bash
cd ~/clawd/agent-causal-decision-tool
PYTHONPATH=. python3 -m src.cli plan --baseline 0.02 --mde 5 --traffic 5000
```

**Parameters:**
- `--baseline` (required): Baseline conversion rate (e.g., `0.02` for 2%)
- `--mde` (required): Minimum detectable effect as % lift (e.g., `5` for 5% lift)
- `--traffic` (required): Daily traffic per arm
- `--confidence` (default `0.95`): Confidence level
- `--power` (default `0.8`): Statistical power
- `--allocation`: `equal` (default) or `custom`
- `--allocation-ratio`: Custom ratio when allocation=custom (e.g., `0.3/0.7`)
- `--format`: `json` (default) or `text`

**Planning output:**
```json
{
  "mode": "planning",
  "recommendation": {
    "decision": "feasible|slow|not_recommended",
    "confidence": "high|medium|low",
    "summary": "..."
  },
  "planning": {
    "required_sample_per_arm": 182934,
    "total_required": 365868,
    "estimated_days": 36.6,
    "feasibility": "slow",
    "allocation_used": {"control": 0.5, "variant": 0.5}
  },
  "warnings": [...]
}
```

**Feasibility thresholds:**
- `feasible`: ≤14 days
- `slow`: 15–60 days
- `not_recommended`: >60 days

### A/B Test Analysis

```bash
cd ~/clawd/agent-causal-decision-tool
PYTHONPATH=. python3 -m src.cli ab --control 100/5000 --variant 130/5000
```

**Parameters:**
- `--control`: Control group conversions/total (e.g., `100/5000`)
- `--variant`: Variant group conversions/total (e.g., `130/5000`)
- `--name`: Variant name (optional, default: `variant_1`)
- `--format`: Output format `json` (default) or `text`

**Example:**
```bash
PYTHONPATH=. python3 -m src.cli ab --control 100/5000 --variant 130/5000
```

**Example Output:**
```json
{
  "version": "1.0",
  "mode": "ab_test",
  "recommendation": {
    "decision": "ship",
    "confidence": "medium",
    "summary": "Variant performs 30.00% better (p=0.0454). Ship it.",
    "primary_metricLift": 30.0,
    "p_value": 0.045361
  },
  "statistics": {
    "control_rate": 0.02,
    "variant_rate": 0.026,
    "relative_lift_pct": 30.0,
    "z_score": 2.0013,
    "p_value": 0.045361,
    "confidence_interval_95": [0.000124, 0.011876]
  },
  "traffic_stats": {
    "control_size": 5000,
    "variant_size": 5000,
    "total_size": 10000
  },
  "warnings": [],
  "next_steps": ["Deploy variant", "Monitor over time for regression"],
  "audit": {
    "decision_path": [
      {"step": "Input validation", "passed": true},
      {"step": "Traffic check", "passed": true},
      {"step": "Conversion rate calculation", "passed": true},
      {"step": "Statistical significance test", "passed": true},
      {"step": "Effect size check", "passed": true},
      {"step": "Decision", "passed": true}
    ]
  }
}
```

### DiD Analysis

```bash
cd ~/clawd/agent-causal-decision-tool
PYTHONPATH=. python3 -m src.cli did --pre-control 1000 --post-control 1100 --pre-treated 900 --post-treated 1150
```

**Parameters:**
- `--pre-control`: Control group metric before treatment
- `--post-control`: Control group metric after treatment
- `--pre-treated`: Treated group metric before treatment
- `--post-treated`: Treated group metric after treatment

### Decision Audit

Reconstruct and explain a previous decision:

```bash
# Save result to file
PYTHONPATH=. python3 -m src.cli ab --control 100/5000 --variant 130/5000 > /tmp/result.json

# Audit it (human-readable)
PYTHONPATH=. python3 -m src.cli audit /tmp/result.json --format text

# Audit it (JSON)
PYTHONPATH=. python3 -m src.cli audit /tmp/result.json --format json
```

**Example audit output:**
```
-- DECISION PATH --
1. Input validation [✓]
   control_total: 5000, variant_total: 5000
2. Traffic check [✓]
   control_size: 5000, min_required: 1000
3. Conversion rate calculation [✓]
   control_rate: 0.02, variant_rate: 0.026
4. Statistical significance test [✓]
   p_value: 0.045361, alpha: 0.05
5. Effect size check [✓]
   lift_pct: 30.0, threshold: 1
6. Decision [✓]
   decision: ship, confidence: medium

-- FINAL DECISION --
  Decision: SHIP
```

## Decision Reference

| Decision | Meaning | When |
|----------|---------|------|
| `ship` | Deploy variant | p < 0.05 AND positive lift |
| `keep_running` | Continue experiment | p < 0.3, trending positive |
| `reject` | Do not deploy | p < 0.05 AND negative lift |
| `escalate` | Needs human review | Not conclusive or critical warnings |

## Python API

```python
import sys
sys.path.insert(0, '~/clawd/agent-causal-decision-tool')

from src.ab_test import calculate_ab

result = calculate_ab({
    "control_conversions": 100,
    "control_total": 5000,
    "variant_conversions": 130,
    "variant_total": 5000
})

if result.recommendation.decision == "ship":
    # Deploy variant
    pass
```

## Warnings & Limitations

- **LOW_TRAFFIC**: Sample size below 1000 per group
- **SMALL_EFFECT**: Lift < 1%, may not be practically significant
- **AGGREGATE_DATA**: DiD performed on aggregated data (use individual-level data for robust inference)
- **TRENDS_DIVERGE**: DiD parallel trends assumption may not hold

## Location

- **GitHub:** https://github.com/ZhuMorris/agent-causal-decision-tool
- **Local:** `~/clawd/agent-causal-decision-tool/`

## Dependencies

- Python 3.9+
- click >= 8.1.0
- scipy >= 1.11.0
- numpy >= 1.24.0
- pydantic >= 2.0.0