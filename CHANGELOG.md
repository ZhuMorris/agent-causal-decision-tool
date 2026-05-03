# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0] — 2026-05-03

### Added

- **Feature 1 — Versioned JSON Schema Contract**
  - `schema_version` field in all output models (`ABTestOutput`, `DIDOutput`, `PlanningOutput`). Injected at Pydantic model layer via `default_factory` from package metadata.
  - `schema.json` file at repo root: wrapper object with `schema_version`, `schema_coverage`, `schema_coverage_pending`, `severity_contract`, and `definitions` (JSON Schema from Pydantic models).
  - CLI command `agent-causal schema` — reads and prints `schema.json`.
  - CI check: regeneration of `schema.json` must match the file in git; fails if diff found.

- **Feature 2 — Confidence Intervals on All Numeric Outputs**
  - A/B: `lift_ci_95` (renamed from `confidence_interval_95` — clean break), `relative_lift_ci_95`.
  - Bayesian: `expected_lift_hdi_95`, `relative_lift_hdi_95` (HDI on expected absolute lift, relative to observed control rate).
  - DiD: `did_ci_95` via Poisson bootstrap (n_bootstrap, default 2000, CLI flag `--n-bootstrap`); `did_ci_method`, `did_ci_n_bootstrap`, `did_ci_assumption`, `did_ci_disclaimer` always present.
  - Planning: `mde_ci_95` via normal approximation using `SE(p) = sqrt(p*(1-p)/n_traffic)`; `null` if `--traffic` not supplied.

- **Feature 3 — Structured Warning Code Contract**
  - `WarningCode` (`str`, `Enum`) at module level in `schema.py` — 30 canonical codes.
  - `WarningDetail.code` typed as `WarningCode`.
  - All modules migrated: no bare string literals for warning codes.

### Changed

- `confidence_interval_95` → `lift_ci_95` in A/B statistics output (clean break, no alias).
- DiD warning codes migrated: `TRENDS_DIVERGE` → `PARALLEL_TRENDS_VIOLATED`, `TRENDS_SLIGHTLY_DIVERGE` → `PARALLEL_TRENDS_WEAK`, `AMBIGUOUS` → `BOTH_GROUPS_GREW`, `did_result_should_be_reviewed_by_human` → `AGGREGATE_DATA_DID`, `early_stop_applied` → `SEQUENTIAL_EARLY_STOP`.

### Deprecated

- (none)

### Removed

- (none)

### Fixed

- (none)

### Security

- (none)

## [0.7.6] — 2026-04-29

### Added

- SKILL.md: local install as recommended option.
- SECURITY.md: threat model justification.
- Improved test coverage.

### Changed

- Dependency bumps for security hardening.

## Prior Versions

See the git commit history for earlier changelog entries.