# Agent Causal Decision Tool

**Source:** https://github.com/ZhuMorris/agent-causal-decision-tool

---

## What is this?

Agent Causal Decision Tool helps you and your AI agents answer one question from experiment data: "should we ship this change, keep running the test, or roll it back?" It takes in simple A/B or rollout summaries and returns a structured JSON decision, key statistics, and an audit record you can store or review later.

Rather than being a full experimentation platform, it is a **decision engine**. You bring the data (from your logs, BI tool, or CSV); it handles the stats, decision logic, and audit trail.

### Why it exists

In many teams, experiment decisions happen in ad hoc spreadsheets or dashboards. People glance at lift, argue about whether the sample size is enough, and sometimes ship features based on noisy or biased results. Agents make this worse if they are wired to react to any small uplift they see.

This tool wraps a few standard methods into one consistent, agent‑friendly interface:

- **Frequentist A/B testing** for classic "control vs variant" questions.
- **Bayesian A/B testing** when you want answers like "there is a 93% chance B is better than A" instead of only p‑values.
- **Difference‑in‑differences (DiD)** for quasi‑experiments like staged rollouts or region‑based launches where you cannot randomize perfectly.
- **Cohort / segment breakdown** when an aggregate result is inconclusive — you can slice by user segment to find hidden signals, with Benjamini-Hochberg correction for 4+ segments.
- **Planning and power checks** so you can see if a test is realistic before you start it.
- **Decision audit** so humans can see what the agent did, why it did it, and how strong the evidence really was..

The goal is not to replace your analytics stack, but to give agents a small, reliable decision block they can call inside workflows.

### When to use it

Use this tool whenever you or your agents have experiment or rollout results and need a decision you can defend:

- You ran an A/B test and want to know whether to ship, keep running, or reject the variant.
- You ran an A/B test and it was inconclusive — you want to know if a specific user segment is driving (or diluting) the effect.
- You rolled out a feature to one region or cohort first and want a DiD estimate of impact compared to a similar control group.
- You prefer a Bayesian summary ("95% chance B is better; expected lift 3–5%") to drive thresholds in automated workflows.
- You need an audit trail with experiment period, traffic size, assumptions, thresholds, and warnings so product, data, or risk teams can review agent decisions later.
- You want to plan an experiment (sample size, minimum detectable effect, expected duration) or compare current results to previous experiments to see which wins are robust.

---

## Features

- **Experiment Planning** — Sample size calculator, MDE, duration estimate, feasibility label
- **Frequentist A/B Testing** — Z-test with decision path and warnings
- **Bayesian A/B Testing** — Beta-Binomial conjugate model with Monte Carlo simulation
- **Difference-in-Differences** — Quasi-experimental analysis for non-randomized settings
- **Cohort Breakdown Analysis** — Segment-level analysis with Benjamini-Hochberg correction and decision override
- **Decision Audit** — Step-by-step audit trail with experiment maturity scoring
- **Persistent History** — SQLite-backed experiment history and comparison.

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
  "schema_version": "0.8.0",
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

### Cohort Breakdown Analysis (`cohort-breakdown`)

Segment-level A/B analysis with Benjamini-Hochberg correction for multiple comparisons:

```bash
PYTHONPATH=. python3 -m src.cli cohort-breakdown --segments seg_a.json seg_b.json

# Or pass JSON directly via stdin
echo '[{"segment_name":"seg_a","control_conversions":100,"control_total":1000,"variant_conversions":130,"variant_total":1000}]' | PYTHONPATH=. python3 -m src.cli cohort-breakdown

# Validate segment data
PYTHONPATH=. python3 -m src.cli validate-input --file segments.json
```

**Segmentation correction policy (PRD v2.2):**
- 2–3 segments: no correction
- 4+ segments: Benjamini-Hochberg (controls FDR, less conservative)
- 5+ segments: Bonferroni available as optional override (with conservative warning)

**Outputs:** `p_value_raw`, `p_value_adjusted`, `cohort_decision_override`, `interaction_flag`, `priority_rank`, `next_analysis_suggestion`

---

## Python API

```python
import sys
sys.path.insert(0, '~/clawd/agent-causal-decision-tool')

from src.ab_test import calculate_ab
from src.bayes import calculate_bayes_ab
from src.did import calculate_did
from src.cohort import cohort_breakdown
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

# Difference-in-Differences
result = calculate_did({
    "pre_control": 1000, "post_control": 1100,
    "pre_treated": 900, "post_treated": 1150
})

# Cohort Breakdown
result = cohort_breakdown({
    "experiment_id": "exp-001",
    "metric": "conversion_rate",
    "segments": [
        {
            "segment_name": "new_users",
            "control_conversions": 100, "control_total": 1000,
            "variant_conversions": 130, "variant_total": 1000,
        },
        {
            "segment_name": "returning_users",
            "control_conversions": 200, "control_total": 2000,
            "variant_conversions": 190, "variant_total": 2000,
        },
    ],
    "prior_decision": "keep_running",
})
if result.get("cohort_decision_override"):
    print(f"Override triggered: {result['cohort_override_reason']}")

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

# Run all tests
pytest tests/ -v

# Run cohort tests specifically
pytest tests/test_cohort.py -v

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
