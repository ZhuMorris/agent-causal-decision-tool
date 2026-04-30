# Agent Causal Decision Tool

A causal decision and audit tool for AI agents. Plan, evaluate, and audit product experiments using A/B testing, Difference-in-Differences, and Bayesian methods.

**Source:** https://github.com/ZhuMorris/agent-causal-decision-tool

## Features

- **Experiment Planning** — Sample size calculator, MDE, duration estimate, feasibility label
- **Frequentist A/B Testing** — Z-test with decision path and warnings
- **Bayesian A/B Testing** — Beta-Binomial conjugate model with Monte Carlo simulation
- **Difference-in-Differences** — Quasi-experimental analysis for non-randomized settings
- **Decision Audit** — Step-by-step audit trail with experiment maturity scoring
- **Persistent History** — SQLite-backed experiment history and comparison

## Installation

```bash
# Via pip
pip install agent-causal-decision-tool

# Via GitHub
pip install git+https://github.com/ZhuMorris/agent-causal-decision-tool.git

# Via OpenClaw (clawhub)
clawhub install agent-causal
```

## Commands

### Experiment Planning (`plan`)

Estimate required sample size, duration, and feasibility before running an experiment:

```bash
cd ~/clawd/agent-causal-decision-tool
PYTHONPATH=. python3 -m src.cli plan --baseline 0.02 --mde 10 --traffic 5000
PYTHONPATH=. python3 -m src.cli plan --baseline 0.02 --mde 5 --traffic 500 --format text

# Custom traffic allocation
PYTHONPATH=. python3 -m src.cli plan --baseline 0.02 --mde 10 --traffic 5000 --allocation custom --allocation-ratio 0.3/0.7
```

**Parameters:** `--baseline`, `--mde`, `--traffic`, `--confidence` (default 0.95), `--power` (default 0.8), `--allocation`, `--allocation-ratio`

**Feasibility:** `feasible` ≤14 days | `slow` 15–60 days | `not_recommended` >60 days

---

### Frequentist A/B Test (`ab`)

```bash
PYTHONPATH=. python3 -m src.cli ab --control 100/5000 --variant 130/5000
PYTHONPATH=. python3 -m src.cli ab --control 100/5000 --variant 70/5000 --format text

# Auto-save to history
PYTHONPATH=. python3 -m src.cli ab --control 100/5000 --variant 130/5000 --save
```

---

### Bayesian A/B Test (`bayes`)

Beta-Binomial conjugate model with Jeffreys prior — no p-value, returns P(variant wins):

```bash
PYTHONPATH=. python3 -m src.cli bayes --control 100/5000 --variant 130/5000
PYTHONPATH=. python3 -m src.cli bayes --control 80/5000 --variant 85/5000 --format text

# Adjust Monte Carlo samples
PYTHONPATH=. python3 -m src.cli bayes --control 100/5000 --variant 130/5000 --samples 50000 --save
```

**Decision thresholds:** P(variant wins) ≥ 0.95 → ship | ≤ 0.05 → reject

---

### Difference-in-Differences (`did`)

For non-randomized experiments where parallel groups exist:

```bash
PYTHONPATH=. python3 -m src.cli did --pre-control 1000 --post-control 1100 --pre-treated 900 --post-treated 1150
PYTHONPATH=. python3 -m src.cli did --pre-control 1000 --post-control 1100 --pre-treated 900 --post-treated 1150 --save
```

---

### Experiment History & Comparison

```bash
# List recent experiments
PYTHONPATH=. python3 -m src.cli history
PYTHONPATH=. python3 -m src.cli history --mode ab_test --limit 10

# Compare multiple experiments by ID
PYTHONPATH=. python3 -m src.cli compare 1 2 3

# Save a prior JSON result to history
PYTHONPATH=. python3 -m src.cli save /tmp/result.json --name "checkout-v3-test"
```

---

### Decision Audit with Maturity Assessment

```bash
# Save a result first
PYTHONPATH=. python3 -m src.cli ab --control 100/5000 --variant 130/5000 > /tmp/result.json

# Human-readable audit
PYTHONPATH=. python3 -m src.cli audit /tmp/result.json --format text

# Audit with experiment maturity score (0–100)
PYTHONPATH=. python3 -m src.cli audit /tmp/result.json --maturity

# JSON audit with maturity
PYTHONPATH=. python3 -m src.cli audit /tmp/result.json --maturity --format json
```

**Maturity labels:** `mature` ≥90 | `adequate` ≥70 | `immature` ≥50 | `inadequate` <50

---

## Output Schema

All commands return structured JSON:

```json
{
  "version": "1.0",
  "mode": "ab_test",
  "recommendation": {
    "decision": "ship|keep_running|reject|escalate",
    "confidence": "high|medium|low",
    "summary": "..."
  },
  "statistics": {...},
  "traffic_stats": {...},
  "warnings": [...],
  "next_steps": [...],
  "audit": {
    "decision_path": [
      {"step": "...", "passed": true, "details": {...}}
    ]
  }
}
```

---

## Decision Reference

| Decision | Meaning | Trigger |
|----------|---------|---------|
| `ship` | Deploy variant | p < 0.05 + positive lift (frequentist), P(better) ≥ 0.95 (Bayesian) |
| `keep_running` | Continue experiment | Trending positive but inconclusive |
| `reject` | Do not deploy | p < 0.05 + negative lift, or P(better) ≤ 0.05 (Bayesian) |
| `escalate` | Human review needed | Inconclusive or critical warnings |

---

## Python API

```python
import sys
sys.path.insert(0, '~/clawd/agent-causal-decision-tool')

from src.ab_test import calculate_ab
from src.bayes import calculate_bayes_ab
from src.did import calculate_did
from src.planning import calculate_plan

# Frequentist A/B
result = calculate_ab({
    "control_conversions": 100, "control_total": 5000,
    "variant_conversions": 130, "variant_total": 5000
})
if result.recommendation.decision == "ship":
    pass  # Deploy

# Bayesian A/B
result = calculate_bayes_ab({
    "control_conversions": 100, "control_total": 5000,
    "variant_conversions": 130, "variant_total": 5000
})
if result["recommendation"]["decision"] == "ship":
    pass  # Deploy

# Planning
result = calculate_plan({
    "baseline_conversion_rate": 0.02, "mde_pct": 10,
    "daily_traffic": 5000, "confidence_level": 0.95, "power": 0.8,
    "allocation": "equal", "allocation_ratio": None
})
```

---

## Development

```bash
git clone https://github.com/ZhuMorris/agent-causal-decision-tool.git
cd agent-causal-decision-tool

pip install -e .
pip install click scipy numpy pydantic pytest

# Run tests
pytest tests/ -v

# Run CLI
PYTHONPATH=. python3 -m src.cli --help
PYTHONPATH=. python3 -m src.cli plan --baseline 0.02 --mde 5 --traffic 5000
```

---

## Dependencies

- Python 3.9+
- click >= 8.1.0
- scipy >= 1.11.0
- numpy >= 1.24.0
- pydantic >= 2.0.0

---

## License

Copyright 2026 ZHU YUMING. Apache License 2.0.