# Agent Causal Decision Tool

**Source:** https://github.com/ZhuMorris/agent-causal-decision-tool

---

## What is this?

Agent Causal Decision Tool helps you and your AI agents answer one question from experiment data: "should we ship this change, keep running the test, or roll it back?" It takes in simple A/B or rollout summaries and returns a structured JSON decision, key statistics, and an audit record you can store or review later.

Rather than being a full experimentation platform, it is a **decision engine**. You bring the data (from your logs, BI tool, or CSV); it handles the stats, decision logic, and audit trail.

### Why it exists

In many teams, experiment decisions happen in ad hoc spreadsheets or dashboards. People glance at lift, argue about whether the sample size is enough, and sometimes ship features based on noisy or biased results. Agents make this worse if they are wired to react to any small uplift they see.

This tool wraps a few standard methods into one consistent, agent‑friendly interface:

- **Easy-mode dispatcher (`decide`)** — no need to know which statistical method to use. Paste your numbers and it auto-selects A/B, Bayesian, DiD, or planning from your input fields.
- **Frequentist A/B testing** for classic "control vs variant" questions.
- **Bayesian A/B testing** when you want answers like "there is a 93% chance B is better than A" instead of only p‑values.
- **Difference‑in‑differences (DiD)** for quasi‑experiments like staged rollouts or region‑based launches where you cannot randomize perfectly.
- **Cohort / segment breakdown** when an aggregate result is inconclusive — you can slice by user segment to find hidden signals, with Benjamini-Hochberg correction for 4+ segments.
- **Planning and power checks** so you can see if a test is realistic before you start it.
- **Decision audit** so humans can see what the agent did, why it did it, and how strong the evidence really was.
- **External connectors** — pull experiment data directly from PostHog, normalize it, and run a decision in one step. No manual export needed..

The goal is not to replace your analytics stack, but to give agents a small, reliable decision block they can call inside workflows.

### When to use it

Use this tool whenever you or your agents have experiment or rollout results and need a decision you can defend:

- You ran an A/B test and want to know whether to ship, keep running, or reject the variant.
- You're not sure which method to use — let `decide` auto-detect from your numbers.
- You ran an A/B test and it was inconclusive — you want to know if a specific user segment is driving (or diluting) the effect.
- You rolled out a feature to one region or cohort first and want a DiD estimate of impact compared to a similar control group.
- You prefer a Bayesian summary ("95% chance B is better; expected lift 3–5%") to drive thresholds in automated workflows.
- You need an audit trail with experiment period, traffic size, assumptions, thresholds, and warnings so product, data, or risk teams can review agent decisions later.
- You want to plan an experiment (sample size, minimum detectable effect, expected duration) or compare current results to previous experiments to see which wins are robust.
- Your experiment data lives in PostHog — you want to fetch, normalize, and decide without any manual CSV export.

---

## Features

- **Experiment Planning** — Sample size calculator, MDE, duration estimate, feasibility label
- **Frequentist A/B Testing** — Z-test with decision path and warnings
- **Bayesian A/B Testing** — Beta-Binomial conjugate model with Monte Carlo simulation
- **Difference-in-Differences** — Quasi-experimental analysis for non-randomized settings
- **Cohort Breakdown Analysis** — Segment-level analysis with Benjamini-Hochberg correction and decision override
- **Decision Audit** — Step-by-step audit trail with experiment maturity scoring
- **Persistent History** — SQLite-backed experiment history and comparison.

---

## Agent-Native API (Phase IV)

For AI agent integrations, Agent Causal exposes a **JSON-RPC 2.0 API** over both stdio and HTTP.

### Stdio mode (for agent tools like OpenClaw, Codex, Claude Code)

```bash
python -m src.api stdio
```

### HTTP mode (for external callers)

```bash
python -m src.api http --port 8000
# Or with uvicorn directly:
uvicorn src.api:app --port 8000
```

### Actions

| Action | Description |
|--------|-------------|
| `decide` | **Easy-mode dispatcher** — auto-selects A/B, Bayesian, DiD, or planning from your input fields |
| `decide_ab` | Frequentist A/B test (mode: frequentist) or Bayesian A/B (mode: bayesian) |
| `decide_rollout` | Difference-in-differences for staged rollouts |
| `plan_test` | Experiment planning (sample size, MDE, feasibility) |
| `audit_result` | Full audit of a stored result |
| `save_result` | Persist a decision result to SQLite history |
| `get_result` | Retrieve a stored result by ID |
| `compare_results` | Compare multiple stored experiments |
| `connect` | Fetch experiment data from external connectors (e.g. PostHog) |
| `run_workflow` | **Orchestrator** — fetch + decide + audit + save + notify + compare in one call |

### Request format

```json
{
  "jsonrpc": "2.0",
  "method": "decide_ab",
  "params": {
    "input": {
      "control_conversions": 100,
      "control_total": 5000,
      "variant_conversions": 130,
      "variant_total": 5000
    }
  },
  "id": 1
}
```

### Response format

```json
{
  "jsonrpc": "2.0",
  "result": {
    "decision": "ship",
    "recommended_next_action": "Deploy variant — statistical significance achieved with positive lift.",
    "selected_method": "ab_test",
    "selection_reason": "User requested frequentist A/B test via decide_ab action",
    "confidence": "medium",
    "effect_summary": "Estimated lift: +30.00% (positive)",
    "warnings": [],
    "limitations": ["Binary conversion outcome only", "No multiple testing correction applied"],
    "audit_summary": "ab_test: Decision",
    "source_metadata": null,
    "internal_result": { ... }  # Full ABTestOutput / BayesOutput / DIDOutput / PlanningOutput
  },
  "id": 1
}
```

### Error response

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid A/B test inputs",
    "data": {
      "details": [{"field": "control_total", "issue": "Input should be greater than or equal to 1"}],
      "request_id": null
    }
  },
  "id": 1
}
```

### Using from Python

```python
from src.actions import run_action

resp = run_action("decide_ab", {
    "input": {
        "control_conversions": 100,
        "control_total": 5000,
        "variant_conversions": 130,
        "variant_total": 5000
    }
})
if "error" in resp:
    print(f"Error: {resp['error']['message']}")
else:
    print(f"Decision: {resp['result']['decision']}")
```

---

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

### Easy-mode Dispatcher (`decide`)

**Don't know which method you need?** `decide` auto-detects from your input fields:

```bash
# A/B test (auto-detected from --control/--variant)
PYTHONPATH=. python3 -m src.cli decide --control 100/5000 --variant 130/5000
PYTHONPATH=. python3 -m src.cli decide --control 100/5000 --variant 130/5000 --format text

# Bayesian A/B (--bayesian flag)
PYTHONPATH=. python3 -m src.cli decide --control 100/5000 --variant 130/5000 --bayesian

# DiD / staged rollout (auto-detected from pre/post treated fields)
PYTHONPATH=. python3 -m src.cli decide --pre-control 1000 --post-control 1200 --pre-treated 200 --post-treated 280

# Experiment planning (auto-detected from --baseline + --mde)
PYTHONPATH=. python3 -m src.cli decide --baseline 0.05 --mde 10 --traffic 10000

# JSON-RPC API — same auto-detection
{"jsonrpc":"2.0","method":"decide","params":{"control_conversions":100,"control_total":5000,"variant_conversions":130,"variant_total":5000},"id":"1"}
```

**Auto-detection:**
| You provide... | It runs... |
|---|---|
| `--control` + `--variant` | Frequentist A/B |
| `--control` + `--variant` + `--bayesian` | Bayesian A/B |
| `--pre-control` + `--post-control` + `--pre-treated` + `--post-treated` | DiD (Difference-in-Differences) |
| `--baseline` + `--mde` | Experiment planning |

---

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
if result.recommendation.decision == "ship":
    pass  # Deploy

# Get JSON for storage or logging
result_json = result.model_dump_json(indent=2)

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

## External Connectors (PostHog)

Fetch experiment data directly from PostHog, normalize it, and run a decision — all in one step.

```bash
# Health check (validates credentials, no data fetched)
PYTHONPATH=. python3 -m src.cli connect posthog --dry-run

# Fetch and print normalized data
PYTHONPATH=. python3 -m src.cli connect posthog --experiment-id <id>

# Fetch and run through decision workflow
PYTHONPATH=. python3 -m src.cli connect posthog --experiment-id <id> --decide

# JSON-RPC call
{"jsonrpc":"2.0","method":"connect","params":{"source":"posthog","experiment_id":"<id>"},"id":"1"}
```

**Authentication:**
- `POSTHOG_API_KEY` + `POSTHOG_PROJECT_ID` env vars, OR
- `~/.posthogrc` with `api_key`, `project_id`, `instance_url` fields

**Connector result:**
```json
{
  "data": {
    "control_conversions": 120,
    "control_total": 5000,
    "variant_conversions": 145,
    "variant_total": 5000
  },
  "source_metadata": {
    "connector": "posthog",
    "experiment_id": "...",
    "fetch_timestamp": "..."
  },
  "warnings": []
}
```
---

## Workflow Orchestrator (`run_workflow`)

The `run_workflow` action chains fetch + decide + audit + save + notify + compare in one call:

```bash
# A/B workflow (auto-detect method, save result)
PYTHONPATH=. python3 -m src.cli workflow --control 100/5000 --variant 130/5000

# Dry-run: validate connector + data without running decision
PYTHONPATH=. python3 -m src.cli workflow --control 100/5000 --variant 130/5000 --dry-run

# With notify (fires webhook on ship/reject/escalate; set AGENT_CAUSAL_WEBHOOK_URL env var)
PYTHONPATH=. python3 -m src.cli workflow --control 100/5000 --variant 130/5000 --notify

# Compare with prior experiments
PYTHONPATH=. python3 -m src.cli workflow --control 100/5000 --variant 130/5000 --compare-with 1,3,5
```

**JSON-RPC example:**
```json
{
  "jsonrpc": "2.0",
  "method": "run_workflow",
  "params": {
    "control_conversions": 100,
    "control_total": 5000,
    "variant_conversions": 130,
    "variant_total": 5000,
    "save": true,
    "notify": true,
    "compare_with": [1, 3]
  },
  "id": "1"
}
```

**Response:**
```json
{
  "selected_method": "ab_test",
  "decision_result": { ... },
  "audit_result": { ... },
  "saved_result_id": 42,
  "comparison_summary": { ... },
  "source_metadata": null
}
```

**Flags:**
- `--dry-run` — validate connector + data, skip decision
- `--notify` — fire webhook on ship/reject/escalate (set AGENT_CAUSAL_WEBHOOK_URL env var)
- `--compare-with id1,id2` — compare with prior experiments
- `--save` — persist to SQLite (default: True)


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
