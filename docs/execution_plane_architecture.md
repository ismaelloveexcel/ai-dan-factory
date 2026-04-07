# AI-DAN Factory Execution Plane Architecture

## Boundary

This repository is the AI-DAN execution plane.

It is responsible for deterministic execution of approved build runs:
- accept BuildBrief v1 payloads
- discover candidate repos/templates
- create repositories
- inject briefs
- execute build/deploy/health/quality steps
- write run artifacts
- emit canonical FactoryRunResult v1 output

This repository is not the business control plane.
Control-plane ownership stays in `aidan-managing-director` (Repo 1).

## Ownership Model

Execution-plane source of truth in this repository:
- execution run status
- execution step status
- repo creation result
- deployment result
- quality result
- execution artifacts for each run

Not owned here (must remain in Repo 1):
- project/business lifecycle truth
- approval policy ownership
- portfolio source of truth
- final scale/optimize/kill authority

Execution scripts in this repo may emit recommendation signals (for example `kill_candidate`), but those are advisory execution signals for Repo 1 to consume.

## Contracts

### Input contract: BuildBrief v1 (required)

BuildBrief v1 is the required execution input for normal and dry-run modes.

Required fields:
- `project_id`
- `product_name`
- `problem`
- `solution`
- `cta`
- `source_type`
- `reference_context`
- `demand_level`
- `monetization_proof`
- `market_saturation`
- `differentiation`

Optional execution fields can be passed through when present (for example `build_complexity`, `speed_to_revenue`).

### Output contract: FactoryRunResult v1 (required)

`factory-response.json` is the canonical artifact and must contain FactoryRunResult v1.

Minimum top-level fields:
- `contract_version` (`FactoryRunResult.v1`)
- `project_id`
- `run_id`
- `run_attempt`
- `workflow_url`
- `timestamp_utc`
- `status` (`success` | `failed`)
- `run_mode` (`tests_only` | `dry_run` | `production`)
- `repo_url`
- `deployment_url`
- `steps` (normalized step results)
- `error` (canonical error object)
- `quality` (normalized quality gate output)
- `result_artifact`

## Orchestration Shape

The execution flow is implemented in Python orchestration stages:
- `input_stage`
- `gate_stage`
- `discovery_stage`
- `repo_stage`
- `build_stage`
- `deploy_stage`
- `quality_stage`
- `report_stage`

GitHub Actions remains intentionally thin:
- checkout
- runtime setup
- invoke orchestrator
- upload artifacts
- emit final workflow status

## Differentiator Protection

Repo discovery and template selection is strategic and remains first-class.
It must not be removed or reduced to placeholder logic.

## Execution Lifecycle Language

References to lifecycle in this repository refer to execution-run lifecycle only (state transitions of a run), not business lifecycle authority.
