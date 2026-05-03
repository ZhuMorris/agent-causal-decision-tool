---
name: agent-causal
description: "Agent Causal Decision Tool helps you and your AI agents answer one question from experiment data: should we ship this change, keep running the test, or roll it back? Returns structured JSON decisions, key statistics, and audit trails from A/B tests (frequentist + Bayesian), DiD, cohort/segment analysis, and sequential early stopping."
metadata:
  openclaw:
    category: data-science
    version: "0.8.0"
    license: Apache-2.0
    tools: [exec]
    requires:
      bins: [python3, git, pip]
      python_packages: [click, scipy, numpy, pydantic]
    source: https://github.com/ZhuMorris/agent-causal-decision-tool
---

# Agent Causal Decision Tool

A causal decision and audit tool for AI agents. Evaluate product changes using A/B testing, Difference-in-Differences, and sequential early stopping.

**Source:** https://github.com/ZhuMorris/agent-causal-decision-tool

## Setup

Before using this skill, install the tool:

```bash
# Option 1 (recommended): clone once, install locally — no remote fetch at runtime
git clone https://github.com/ZhuMorris/agent-causal-decision-tool.git ~/clawd/agent-causal-decision-tool
cd ~/clawd/agent-causal-decision-tool && pip install . -q

# Option 2: install directly from Git (one-liner)
pip install git+https://github.com/ZhuMorris/agent-causal-decision-tool.git -q
```

## When to Use It

Use this skill whenever you or your agents have experiment or rollout results and need a decision you can defend:

- You ran an A/B test and want to know whether to ship, keep running, or reject the variant.
- You ran an A/B test and it was inconclusive — you want to know if a specific user segment is driving (or diluting) the effect.
- You did a staged / regional rollout and want a DiD estimate of impact vs a similar control group.
- You prefer a Bayesian summary ("95% chance B is better; expected lift 3–5%") to drive thresholds in automated workflows.
- You need an audit trail with period, traffic, assumptions, thresholds, and warnings for product/data/risk review.
- You want to plan an experiment (sample size, MDE, duration) or compare current results to previous experiments.
- You want to **stop an A/B test early** when evidence is overwhelmingly strong (sequential early stopping), without losing audit integrity.

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

### A/B Test Analysis (Frequentist)

```bash
cd ~/clawd/agent-causal-decision-tool
PYTHONPATH=. python3 -m src.cli ab --control 100/5000 --variant 130/5000
```

**Parameters:**
- `--control`: Control group conversions/total (e.g., `100/5000`)
- `--variant`: Variant group conversions/total (e.g., `130/5000`)
- `--name`: Variant name (optional, default: `variant_1`)
- `--format`: Output format `json` (default) or `text`

**Sequential / Early Stopping (optional):**
- `--sequential/--no-sequential`: Enable sequential early stopping evaluation
- `--experiment-start`, `--experiment-end`: ISO 8601 timestamps for runtime calculation
- `--min-runtime-days` (default 7): Minimum days before early stop is considered
- `--min-sample-per-arm` (default 2000): Minimum sample per arm before early stop
- `--early-stop-p` (default 0.01): p-value threshold for early stop
- `--max-runtime-days`: Hard cap; escalates if exceeded without strong result

**Trigger logic:** Both min-runtime AND min-sample-per-arm must be met, AND p-value below `--early-stop-p`. Max runtime exceeded always escalates.
```bash
PYTHONPATH=. python3 -m src.cli ab --control 100/5000 --variant 130/5000
```

**Example Output:**
```json
{
  "schema_version": "0.8.0",
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
    "lift_ci_95": [0.000124, 0.011876],
    "relative_lift_ci_95": [0.619, 59.381]
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

### A/B Test Analysis (Frequentist)

```bash
cd ~/clawd/agent-causal-decision-tool
PYTHONPATH=. python3 -m src.cli ab --control 100/5000 --variant 130/5000
```

**Parameters:**
- `--control`: Control group conversions/total (e.g., `100/5000`)
- `--variant`: Variant group conversions/total (e.g., `130/5000`)
- `--name`: Variant name (optional, default: `variant_1`)
- `--format`: Output format `json` (default) or `text`

### Bayesian A/B Test

```bash
cd ~/clawd/agent-causal-decision-tool
PYTHONPATH=. python3 -m src.cli bayes --control 100/5000 --variant 130/5000
```

**Uses Beta-Binomial conjugate model with Jeffreys prior.**
- Prior: Beta(0.5, 0.5) — uninformative
- Posterior: Beta(α + successes, β + failures)
- Decision via Monte Carlo simulation (20k samples)
- Thresholds: P(variant wins) ≥ 0.95 → ship, ≤ 0.05 → reject

**Parameters:**
- `--control`, `--variant`: Conversions/total (same as `ab`)
- `--name`: Variant name
- `--format`: `json` (default) or `text`
- `--samples`: Monte Carlo samples (default: 20000)

**Example output:**
```json
{
  "mode": "bayesian_ab",
  "recommendation": {
    "decision": "ship",
    "confidence": "medium",
    "summary": "Variant wins with P(better)=0.976. Median lift=30.10%. Ship."
  },
  "statistics": {
    "p_variant_wins": 0.9758,
    "lift_median_pct": 30.10,
    "lift_95ci_pct": [0.20, 69.15],
    "posterior_control": {"alpha": 100.5, "beta": 4900.5, "mean": 0.0201},
    "posterior_variant": {"alpha": 130.5, "beta": 4870.5, "mean": 0.0261}
  }
}
```

**When to use Bayesian vs Frequentist:**
- Bayesian: small data, need probability distributions, want to stop early
- Frequentist: large data, traditional significance testing, need p-values

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
- `--n-bootstrap` (default 2000, range 500–10000): Number of bootstrap resamples for DiD CI

### Cohort / Segment Breakdown

When an aggregate A/B or DiD result is inconclusive, break down results by user segment to find hidden signals:

```bash
cd ~/clawd/agent-causal-decision-tool
PYTHONPATH=. python3 -m src.cli cohort-breakdown --file segments.json
```

**Input format (JSON):**
```json
{
  "experiment_id": "checkout-v3",
  "metric": "conversion_rate",
  "prior_result_id": "dec_20260501_001",
  "prior_decision": "wait",
  "segments": [
    {
      "segment_name": "new_users",
      "segment_definition_note": "Users registered within last 30 days",
      "control_conversions": 21,
      "control_total": 1000,
      "variant_conversions": 67,
      "variant_total": 1000
    },
    {
      "segment_name": "returning_users",
      "segment_definition_note": "Users registered more than 30 days ago",
      "control_conversions": 220,
      "control_total": 4000,
      "variant_conversions": 228,
      "variant_total": 4000
    }
  ]
}
```

**Input format (CSV alternative):**
```
segment_name,segment_definition_note,arm,conversions,total
new_users,Users registered within last 30 days,control,21,1000
new_users,Users registered within last 30 days,variant,67,1000
returning_users,Users registered more than 30 days ago,control,220,4000
returning_users,Users registered more than 30 days ago,variant,228,4000
```

**Parameters:**
- `--file`: Path to JSON or CSV segment file
- `--json`: JSON input string (alternative to `--file`)
- `--format`: Output format `json` (default) or `text`
- `--save`: Save result to experiment history

**Multiple comparison correction:**
- 4+ segments: Benjamini-Hochberg FDR correction applied automatically
- 5+ segments: Also offers Bonferroni as alternative via `--method bonferroni`

**Example output:**
```json
{
  "method": "experiment_cohort_breakdown",
  "cohort_decision_override": true,
  "cohort_override_reason": "Strong positive signal in 'new_users' (lift=219.0%, adj-p=0.0000) contradicts aggregate decision 'wait'",
  "interaction_flag": false,
  "segments": [
    {
      "segment_name": "new_users",
      "control_rate": 0.021,
      "variant_rate": 0.067,
      "relative_lift_pct": 219.05,
      "p_value_raw": 0.0000,
      "p_value_adjusted": 0.0000,
      "decision": "strongly_positive",
      "priority_rank": 1
    }
  ],
  "priority_ranking": [
    {"rank": 1, "segment": "new_users", "rationale": "Strong positive effect (lift=219.1%, adj-p=0.0000). Highest priority."}
  ],
  "summary": "new_users drives the effect. 1 segment(s) positive.",
  "recommended_next_action": "targeted_rollout"
}
```

**When to use cohort breakdown:**
- Aggregate A/B result is `keep_running` or `escalate` — segment analysis may reveal a hidden signal
- One segment is strongly positive while another is strongly negative (interaction flag)
- You want to ship only to specific segments rather than all users

**Key features:**
- Per-segment two-proportion z-test with 95% confidence
- Benjamini-Hochberg FDR correction for 4+ segments (controls false-discovery rate)
- Priority ranking by absolute lift magnitude
- Cohort decision override: fires when a segment contradicts the aggregate decision
- Interaction flag: triggered when segments show opposing strongly-significant directions

### Decision Audit

Reconstruct and explain a previous decision:

```bash
# Save result to file
PYTHONPATH=. python3 -m src.cli ab --control 100/5000 --variant 130/5000 > /tmp/result.json

# Audit it (human-readable)
PYTHONPATH=. python3 -m src.cli audit /tmp/result.json --format text

# Audit with experiment maturity assessment
PYTHONPATH=. python3 -m src.cli audit /tmp/result.json --maturity
```

**Maturity assessment** (with `--maturity` flag):
- Scores experiments 0–100 across 8 checks
- Labels: `mature` (≥90), `adequate` (≥70), `immature` (≥50), `inadequate` (<50)
- Checks: decision path completeness, critical warnings, limitations documented, traffic sufficiency, confidence level, step documentation

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

### Experiment History & Persistence

All commands support `--save` to persist results to local SQLite history:

```bash
# Run and save in one step
PYTHONPATH=. python3 -m src.cli ab --control 100/5000 --variant 130/5000 --save
PYTHONPATH=. python3 -m src.cli did --pre-control 1000 --post-control 1100 --pre-treated 900 --post-treated 1150 --save
PYTHONPATH=. python3 -m src.cli plan --baseline 0.02 --mde 5 --traffic 5000 --save
```

**History commands:**

```bash
# List recent experiments
PYTHONPATH=. python3 -m src.cli history
PYTHONPATH=. python3 -m src.cli history --mode ab_test --limit 10

# Compare multiple experiments by ID
PYTHONPATH=. python3 -m src.cli compare 1 2 3

# Save a prior JSON result file to history
PYTHONPATH=. python3 -m src.cli save /tmp/result.json --name "checkout-v3-test"
```

**History output example:**
```
ID    Date       Mode       Decision   Lift     P-value  Summary
--------------------------------------------------------------------
3     2026-04-30 did        ship       16.67    -        Treatment effect is 150.00...
2     2026-04-30 ab_test    escalate   6.25     0.6947   Results not conclusive...
1     2026-04-30 ab_test    ship       30.00    0.0454   Variant performs 30.00%...
```

**Compare output example:**
```
EXPERIMENT COMPARISON
==================================================
Experiments compared: 3

Summary by decision:
  SHIP: 2 experiment(s)
  ESCALATE: 1 experiment(s)

Summary by mode:
  ab_test: 2 experiment(s)
  did: 1 experiment(s)

Lift summary: max=30.00%, min=6.25%, avg=17.64% (3 experiments)

Attention needed: 2 experiments recommend ship. Review if they test the same metric.
```

**Persistence:**
- SQLite DB stored at `~/.agent-causal/history.db`
- All experiment modes supported: `ab_test`, `did`, `planning`
- Full raw JSON preserved for audit reconstruction
- Filter by mode, limit results, name experiments for later reference

## Decision Reference

| Decision | Meaning | When |
|----------|---------|------|
| `ship` | Deploy variant | p < 0.05 AND positive lift |
| `keep_running` | Continue experiment | p < 0.3, trending positive |
| `reject` | Do not deploy | p < 0.05 AND negative lift |
| `escalate` | Needs human review | Not conclusive or critical warnings |
| `targeted_rollout` | Ship to specific segment only | Strong signal in one segment, aggregate inconclusive |
| `full_rollout` | Ship to all users | All segments positive |
| `abandon_segment` | Do not ship to specific segment | Strong negative in one segment despite aggregate ship |
| `confirm_rejection` | Confirm abandonment | All segments negative |

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
- **INCONCLUSIVE**: Result not statistically significant or strong enough to act on
- **NOT_SIGNIFICANT**: Far from significant; consider stopping the experiment
- **BORDERLINE_P_VALUE**: p-value between 0.05 and 0.10 — weak evidence, not conclusive
- **CORRECTION_CONSERVATIVE**: Multiple comparison correction applied; may increase false negatives
- **SEQUENTIAL_EARLY_STOP**: Experiment stopped early via sequential testing; interpret with caution
- **SEQUENTIAL_CONDITIONS_NOT_MET**: Early stopping conditions not met; normal decision applied
- **MAX_RUNTIME_EXCEEDED**: Hard runtime cap exceeded without strong result; escalating
- **ZERO_BASELINE**: Pre-period values cannot be zero for reliable DiD
- **PARALLEL_TRENDS_VIOLATED**: Control and treated groups show very different pre-to-post ratios (critical)
- **PARALLEL_TRENDS_WEAK**: Ratios diverge somewhat; monitor closely
- **BOTH_GROUPS_GREW**: Both groups grew; cannot separate treatment effect from time trend
- **AGGREGATE_DATA**: Analysis on aggregated data; use individual-level data for robust inference
- **AGGREGATE_DATA_DID**: DiD result with high caution; not equivalent to a randomized experiment
- **SINGLE_PRE_PERIOD**: Only one pre-period observation; parallel trends cannot be assessed
- **SMALL_SAMPLE**: Sample size small; estimates unreliable
- **IMBALANCED_GROUPS**: Treatment/control group sizes very different; may bias DiD estimate
- **LARGE_EFFECT_SMALL_SAMPLE**: Large effect estimate from small sample; prioritize replication
- **PARALLEL_TRENDS_NO_DATA**: No pre-period count provided; parallel trends cannot be assessed
- **BOOTSTRAP_CI_UNRELIABLE**: Bootstrap CI not computed — count < 100 or zero baseline
- **BOOTSTRAP_CI_WIDE**: Bootstrap CI range > 2×|DiD estimate|; point estimate uncertain
- **DID_CI_CROSSES_ZERO**: Bootstrap CI crosses zero; effect direction uncertain
- **SLOW_EXPERIMENT**: Estimated duration > 30 days; seasonal effects may confound results
- **INFEASIBLE_EXPERIMENT**: Duration too long; consider DiD instead
- **SMALL_MDE**: MDE very small; may require impossibly large sample
- **BASELINE_VERY_LOW**: Baseline rate < 0.5%; estimations may be unreliable
- **BASELINE_NEAR_ZERO**: Baseline rate < 0.1%; do not run experiment without careful review
- **PRIOR_DOMINATES**: Very low total traffic; Jeffreys prior dominates posterior; interpret with caution
- **CREDIBLE_INTERVAL_WIDE**: Bayesian credible interval is very wide; estimate uncertain

## Schema Contract

The tool exposes a versioned schema contract for agent consumption:

```bash
cd ~/clawd/agent-causal-decision-tool
PYTHONPATH=. python3 -m src.cli schema
```

This prints `schema.json` — a wrapper containing `schema_version`, `schema_coverage` (`ab`, `did`, `plan`), `schema_coverage_pending` (`bayes`, `cohort`), `severity_contract`, and `definitions` (JSON Schema from Pydantic models).

All output models include `schema_version` field injected from package metadata — never hardcoded.

## Location

- **GitHub:** https://github.com/ZhuMorris/agent-causal-decision-tool
- **Local:** `~/clawd/agent-causal-decision-tool/`

## Dependencies

- Python 3.9+
- click >= 8.1.0
- scipy >= 1.11.0
- numpy >= 1.26.0
- pydantic >= 2.10.0