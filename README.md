# Agent Causal Decision Tool

A causal decision and audit tool for AI agents. Evaluate product changes using A/B testing and Difference-in-Differences methods.

## Features

- **A/B Testing**: Randomized experiment analysis with statistical significance
- **Difference-in-Differences**: Observational rollout analysis when A/B testing isn't feasible
- **Structured Output**: Machine-readable JSON recommendations
- **Audit Trail**: Complete record of inputs, statistics, thresholds, and warnings
- **Agent-Native**: Designed for AI agent workflows, not human dashboards

## Installation

```bash
# Clone
git clone https://github.com/your-repo/agent-causal-decision-tool.git
cd agent-causal-decision-tool

# Install
pip install -e .

# Or build from source
pip install build
python -m build
```

## Usage

### A/B Test Analysis

```bash
# Using command-line arguments
agent-causal ab --control 100/5000 --variant 130/5000

# Using JSON input
agent-causal ab < examples/ab_sample.json

# Pretty text output
agent-causal ab --control 100/5000 --variant 130/5000 --format text
```

### Difference-in-Differences

```bash
agent-causal did \
  --pre-control 1000 \
  --post-control 1100 \
  --pre-treated 900 \
  --post-treated 1150
```

### Audit Mode

```bash
agent-causal audit previous_result.json
```

## Input Schema

### A/B Test Input

```json
{
  "control_conversions": 100,
  "control_total": 5000,
  "variant_conversions": 130,
  "variant_total": 5000,
  "variant_name": "variant_1"
}
```

### DiD Input

```json
{
  "pre_control": 1000,
  "post_control": 1100,
  "pre_treated": 900,
  "post_treated": 1150
}
```

## Output Schema

Every output includes:

- **recommendation**: Decision (ship/keep_running/reject/escalate) + confidence + summary
- **statistics**: Computed metrics (rates, p-value, lift, confidence intervals)
- **traffic_stats**: Sample sizes
- **warnings**: Any issues detected (low traffic, small effects, assumption violations)
- **next_steps**: Suggested actions based on decision
- **audit**: Full audit trail for downstream review
- **inputs**: Original inputs preserved for reproducibility

## Decision Logic

| Decision | When |
|----------|------|
| `ship` | p < 0.05 and positive lift |
| `keep_running` | p < 0.3 but not significant, trending positive |
| `reject` | p < 0.05 and negative lift |
| `escalate` | Not conclusive, or critical warnings |

## Warnings

- `LOW_TRAFFIC`: Sample size below recommended minimum (1000 per group)
- `SMALL_EFFECT`: Lift < 1%, may not be practically significant
- `INCONCLUSIVE`: p-value between 0.05 and 0.3, needs more data
- `TRENDS_DIVERGE`: DiD parallel trends assumption may not hold

## For AI Agents

This tool is designed to be called programmatically from agent workflows:

```python
from agent_causal_decision_tool import calculate_ab

result = calculate_ab({
    "control_conversions": 100,
    "control_total": 5000,
    "variant_conversions": 130,
    "variant_total": 5000
})

if result.recommendation.decision == "ship":
    # deploy variant
    pass
```

## License

MIT