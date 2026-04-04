# Operator Control Contract (Single-Operator Mode)

This contract defines exactly what one non-technical operator can do, what is automated, and what decisions are machine-enforced.

## 1) Operator allowed actions

The operator can:
- trigger `factory-build` manually (or let scheduled workflows run)
- set workflow inputs only:
  - `project_id`
  - `build_brief_json`
  - `dry_run`
  - `run_automated_tests_only`
  - `traffic_signal`
  - `activation_metric`
  - `revenue_signal_status`
- read artifacts and summaries

The operator cannot bypass:
- input normalization
- business gate decision
- lifecycle transition rules
- result artifact generation

## 2) Mandatory machine gates

Execution cannot continue if any of these fail:
1. Input contract normalization (`normalize_workflow_inputs.py`)
2. Build brief validation (`validate_brief.py`)
3. Unified business gate (`validate_business_gate.py`)  
   - only `APPROVE` allows build/deploy
4. Lifecycle transition checks (`lifecycle_orchestrator.py`)
5. Deployment health gate (`deploy_health_check.py`) in non-tests runs

## 3) Run modes

- `tests_only`: runs automation checks with no live side effects
- `dry_run`: executes full flow with side effects disabled
- `production`: executes full live flow

## 4) State and audit artifacts

Persistent state:
- `data/lifecycle.sqlite`

Per-run artifacts:
- `factory-response.json` (source of truth)
- step-level JSON files:
  - `normalize_inputs.json`
  - `validate_brief.json`
  - `business_gate.json`
  - `create_repo.json`
  - `inject_brief.json`
  - `business_output_result.json`
  - `deploy.json`
  - `deploy_health.json`
  - `monitoring_decision.json`
  - `portfolio_summary.json`
  - `alert_payload.json` (on failure)

## 5) Decision semantics

Business gate:
- `APPROVE` => continue
- `HOLD` or `REJECT` => stop build/deploy

Monitoring decision:
- `kill_candidate=true` => prune candidate
- `optimize_candidate=true` => iteration candidate
- `scale_candidate=true` => scale candidate

## 6) Failure handling

On failure:
1. read `factory-response.json`
2. inspect `error_summary` and `failure_reason`
3. inspect failed step JSON
4. rerun in `dry_run=true` if diagnosis is needed

Alert payload (`emit_alert.py`) is generated in failed runs for external notification systems.
