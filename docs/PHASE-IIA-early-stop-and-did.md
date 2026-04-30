# Agent Causal Decision Tool — Phase II.A/B Addendum

**Scope:** Two incremental capabilities added to the existing decision engine.
**Status:** Draft

---

## 1. Sequential / Early Stopping for A/B

### 1.1 Goal

Allow agents and teams to stop A/B tests earlier when evidence is clearly strong, without encouraging reckless peeking, and always with explicit warnings and audit signals.

**Constraints:**
- Only for frequentist A/B mode.
- Only when explicitly enabled via settings.
- Only when: minimum runtime is met, and minimum sample per arm is met, and no blocking guardrail deterioration is present.

### 1.3 Design principles

- **Conservative by default**: prefer "keep running" over premature stopping.
- **Transparent**: every early stop must be clearly labeled in main output and audit.
- **Configurable**: thresholds and minimum runtime are configurable but safe by default.
- **Method-aligned**: communicate p-values in a sequential context as heuristic thresholds, not as if they came from a fixed-sample design.

### 1.4 New / extended inputs

Extend the existing A/B settings block with:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `sequential_enabled` | boolean | `false` | Opt-in flag for early stopping logic |
| `min_runtime_days` | integer | `7` | Minimum days before early stop is considered |
| `min_sample_per_arm` | integer | `2000` | Minimum sample per arm before early stop is considered |
| `early_stop_p_threshold` | float | `0.01` | p-value threshold (conservative vs standard 0.05) |
| `max_runtime_days` | integer | `null` | Optional hard cap; escalate if exceeded without strong result |

**Example settings block:**
```json
{
  "min_sample": 2000,
  "practical_significance_threshold": 0.01,
  "experiment_start_time": "2026-05-01T00:00:00Z",
  "experiment_end_time": "2026-05-10T00:00:00Z",
  "sequential_enabled": true,
  "min_runtime_days": 7,
  "early_stop_p_threshold": 0.01,
  "max_runtime_days": 28
}
```

### 1.5 Decision logic

1. Compute current A/B statistics: conversion rates, absolute/relative lift, p-value, guardrails.
2. Compute `observed_runtime_days` from `experiment_end_time` − `experiment_start_time`.
3. Compute `observed_sample_per_arm` from visitors per arm.
4. **If `sequential_enabled = false`** → behave as current behavior (backward compatible).
5. **If `sequential_enabled = true`**:
   - If `observed_runtime_days < min_runtime_days` OR `observed_sample_per_arm < min_sample_per_arm` → do **not** early-stop; return normal decision; add warning `sequential_conditions_not_met`.
   - Else if `p_value < early_stop_p_threshold` AND effect directionally favorable AND all guardrails OK → early stop: decision = `ship` (positive) or `reject` (negative); set `early_stop_applied = true`; reason = `p_below_threshold`.
   - Else if `max_runtime_days` is set AND `observed_runtime_days > max_runtime_days` AND still no strong result → decision = `escalate_to_human`; warning `max_runtime_exceeded`.
   - Else → normal behavior, but mark `sequential_reviewed = true`.

### 1.6 Output additions

```json
{
  "sequential_reviewed": true,
  "early_stop_applied": true,
  "sequential_summary": {
    "min_runtime_days": 7,
    "observed_runtime_days": 9,
    "min_sample_per_arm": 2000,
    "observed_sample_per_arm": 2400,
    "early_stop_p_threshold": 0.01,
    "max_runtime_days": 28,
    "reason": "p_below_threshold"
  }
}
```

`reason` values: `conditions_not_met`, `p_below_threshold`, `max_runtime_exceeded`, `no_early_stop`

### 1.7 Audit behavior

`audit_decision` must:
- Show whether `sequential_enabled` was on.
- Report thresholds vs actuals: runtime, sample, p-value at decision.
- State whether early stopping was applied and which condition triggered it.
- Include limitation note: *"Sequential stopping can slightly increase false-positive risk compared to a fixed-sample test; thresholds are set conservatively to mitigate this risk."*

### 1.8 Key user stories

- As an **agent**, I want clear rules for when to stop a test early so I do not guess or overreact to noisy significance.
- As an **agent**, I need early stops to be opt-in and clearly labeled so human reviewers understand the experiment did not run for the full planned duration.
- As a **reviewer**, I want the audit record to show whether the decision used early stopping and what thresholds were applied so I can assess risk.

### 1.9 Acceptance criteria

- `sequential_enabled = false` → outputs identical to current A/B behavior.
- `sequential_enabled = true` with insufficient runtime/sample → no early stop; warning `sequential_conditions_not_met` returned.
- Every early-stop decision has `early_stop_applied = true` and `sequential_summary.reason` = `p_below_threshold` or `max_runtime_exceeded`.
- Audit always includes sequential section when `sequential_enabled = true`.

---

## 2. Stronger DiD Diagnostics & Assumptions

### 2.1 Goal

Make DiD outputs **explicitly cautious** by surfacing diagnostic information and fragility flags, especially around the parallel trends assumption and thin pre-periods, so agents know when to escalate rather than treat DiD as firm proof.

### 2.2 When it applies

For every call to `did_estimate`. Works for:
- Simple two-period summary inputs (one pre / one post per group), and
- Aggregate inputs with multiple pre/post periods (future extension).

### 2.3 Input extensions

```json
{
  "treatment": {"pre": 0.12, "post": 0.20},
  "control": {"pre": 0.10, "post": 0.11},
  "settings": {
    "metric_name": "signup_rate",
    "pre_periods": 1,
    "post_periods": 1,
    "treatment_observation_count": 420,
    "control_observation_count": 410
  }
}
```

New optional settings fields:
| Field | Type | Description |
|-------|------|-------------|
| `pre_periods` | integer | Number of pre-period observations |
| `post_periods` | integer | Number of post-period observations |
| `treatment_observation_count` | integer | Total underlying observations for treatment |
| `control_observation_count` | integer | Total underlying observations for control |
| `notes` | string | Context passed through to audit only |

### 2.4 New diagnostics object

Added to DiD output:

```json
{
  "did_diagnostics": {
    "pre_periods": 1,
    "post_periods": 1,
    "treatment_observation_count": 420,
    "control_observation_count": 410,
    "parallel_trends_evidence": "none",
    "fragility_flags": ["single_pre_period", "small_sample"],
    "recommended_caution_level": "high"
  }
}
```

**`parallel_trends_evidence`:** `none` | `weak` | `moderate` | `strong`

**`recommended_caution_level`:** `low` | `medium` | `high`

**`fragility_flags` values:**
- `single_pre_period` — only one pre-period; parallel trends cannot be verified
- `small_sample` — observation count < 100 in either group
- `imbalanced_groups` — treatment/control ratio > 3x or < 1/3x
- `large_effect_small_sample` — large effect + small sample; may indicate confounding

### 2.5 Heuristic rules

| Condition | Fragility flag(s) | Caution level |
|-----------|-------------------|---------------|
| `pre_periods` ≤ 1 | `single_pre_period` | `high` |
| `treatment_observation_count` or `control_observation_count` < 100 | `small_sample` | ≥ `medium` |
| Ratio of treatment/control observations > 3 or < 1/3 | `imbalanced_groups` | ≥ `medium` |
| `\|did_estimate\|` > 0.05 AND small sample | `large_effect_small_sample` | `high` |

### 2.6 Full DiD output example

```json
{
  "method": "difference_in_differences",
  "decision": "likely_positive",
  "effect": {
    "treatment_change": 0.08,
    "control_change": 0.01,
    "did_estimate": 0.07
  },
  "did_diagnostics": {
    "pre_periods": 1,
    "post_periods": 1,
    "treatment_observation_count": 420,
    "control_observation_count": 410,
    "parallel_trends_evidence": "none",
    "fragility_flags": ["single_pre_period", "small_sample"],
    "recommended_caution_level": "high"
  },
  "warnings": [
    "parallel_trends_not_verified",
    "single_pre_period_only",
    "did_result_should_be_reviewed_by_human"
  ],
  "recommended_next_action": "escalate_to_human",
  "explanation": "Observed uplift appears positive, but the DiD setup is fragile (single pre-period, small sample). Parallel trends cannot be verified; treat this result as indicative only."
}
```

### 2.7 Audit behavior

DiD `audit_decision` must:
- Surface `did_diagnostics` prominently.
- Translate each `fragility_flag` into a plain-text explanation.
- Restate `recommended_caution_level`.
- Include: *"Caution is high; this result should be reviewed by a human. Do not treat this as equivalent to a randomized experiment."*

### 2.8 Key user stories

- As an **agent**, I want DiD results to tell me **how fragile** the setup is so I know when to escalate instead of acting autonomously.
- As a **PM or data person**, I want DiD to be a cautious fallback when we cannot run clean A/B tests, not a replacement for randomized evidence.
- As a **reviewer**, I want to see parallel-trends-related caveats and fragility in the audit record, not hidden behind a single effect estimate.

### 2.9 Acceptance criteria

- All `did_estimate` responses include a `did_diagnostics` object (fields may be `null` if metadata not provided).
- `pre_periods` ≤ 1 always sets `recommended_caution_level` ≥ `high`.
- Small-sample and imbalanced setups generate appropriate fragility flags and warnings.
- DiD audit includes: diagnostics block, explanations for each fragility flag, explicit caution statement.

---

## References

- https://github.com/shansfolder/AB-Test-Early-Stopping
- https://bytepawn.com/early-stopping-in-ab-testing.html
- https://www.evanmiller.org/sequential-ab-testing.html
- https://www.statsig.com/perspectives/sequential-testing-ab-peek
- https://arxiv.org/pdf/2503.13323.pdf
- https://www.aarondefazio.com/tangentially/?p=83
- https://towardsdatascience.com/sequential-testing-the-secret-sauce-for-low-volume-ab-tests-fe62bdf9627b/
- https://blogs.worldbank.org/en/impactevaluations/revisiting-difference-differences-parallel-trends-assumption-part-i-pre-trend
- https://libguides.princeton.edu/stata-did
- https://www.tandfonline.com/doi/full/10.1080/07350015.2024.2308121
