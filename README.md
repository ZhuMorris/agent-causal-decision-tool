# Agent Causal Decision Tool

A causal decision and audit tool for AI agents. Evaluate product changes using A/B testing and Difference-in-Differences methods.

## Installation

### Via pip (Python package)

```bash
pip install agent-causal-decision-tool
```

### Via GitHub

```bash
pip install git+https://github.com/ZhuMorris/agent-causal-decision-tool.git
```

### Via OpenClaw Skill

Install as an OpenClaw skill:
```bash
clawhub install agent-causal
```

## Usage

### A/B Test Analysis

```bash
# Using CLI
agent-causal ab --control 100/5000 --variant 130/5000

# Or using JSON input
python3 -m src.cli ab --control 100/5000 --variant 130/5000 --format text
```

**Parameters:**
- `--control`: Control group in format `conversions/total` (e.g., `100/5000`)
- `--variant`: Variant group in format `conversions/total` (e.g., `130/5000`)
- `--name`: Variant name (optional)
- `--format`: Output format `json` (default) or `text`

### Difference-in-Differences

```bash
python3 -m src.cli did \
  --pre-control 1000 --post-control 1100 \
  --pre-treated 900 --post-treated 1150
```

### Decision Audit

```bash
# Save result first
python3 -m src.cli ab --control 100/5000 --variant 130/5000 > result.json

# Then audit it
python3 -m src.cli audit result.json --format text
```

## Output Schema

Every output includes:
- **recommendation**: Decision (ship/keep_running/reject/escalate) + confidence + summary
- **statistics**: Computed metrics (rates, p-value, lift, confidence intervals)
- **traffic_stats**: Sample sizes
- **warnings**: Any issues detected (low traffic, small effects, etc.)
- **next_steps**: Suggested actions based on decision
- **audit**: Complete decision_path with step-by-step reasoning
- **inputs**: Original inputs preserved for reproducibility

## Decision Reference

| Decision | Meaning | When |
|----------|---------|------|
| `ship` | Deploy variant | p < 0.05 AND positive lift |
| `keep_running` | Continue experiment | p < 0.3, trending positive |
| `reject` | Do not deploy | p < 0.05 AND negative lift |
| `escalate` | Needs human review | Not conclusive or critical warnings |

## Python API

```python
from agent_causal_decision_tool import calculate_ab

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

## Development

```bash
# Clone
git clone https://github.com/ZhuMorris/agent-causal-decision-tool.git
cd agent-causal-decision-tool

# Install dependencies
pip install -e .

# Run tests
pytest tests/ -v

# Run CLI
PYTHONPATH=. python3 -m src.cli ab --control 100/5000 --variant 130/5000
```

## License

Copyright 2026 ZHU YUMING

Licensed under the Apache License, Version 2.0