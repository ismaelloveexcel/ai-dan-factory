# AI-DAN ↔ Factory Integration Contract

This document defines how AI-DAN should trigger and consume `factory-build` in this repository.

Boundary: this repository is the execution plane only. It returns execution-run results and artifacts, while business/portfolio truth stays in Repo 1 (`aidan-managing-director`).

## Workflow endpoint

- Workflow file: `.github/workflows/factory-build.yml`
- Workflow name: `factory-build`
- Trigger type: `workflow_dispatch`

## Dispatch inputs (contract)

Required input contract: BuildBrief v1 for normal and dry-run execution.

| Input | Type | Required | Notes |
|---|---|---:|---|
| `project_id` | string | yes | Must be a safe slug: lowercase letters, numbers, hyphens (`^[a-z0-9]+(?:-[a-z0-9]+)*$`) |
| `build_brief_json` | string | conditional | Required unless `run_automated_tests_only=true` |
| `dry_run` | string boolean | yes | Recommended values: `"true"` or `"false"` |
| `run_automated_tests_only` | string boolean | no | Default `"false"`. When true, live create/deploy steps are skipped. |
| `test_mode` | string boolean | no | Deprecated alias for `run_automated_tests_only` (kept for backward compatibility) |
| `traffic_signal` | enum string | no | `LOW` / `MEDIUM` / `HIGH` (monitoring decision input) |
| `activation_metric` | enum string | no | `LOW` / `MEDIUM` / `HIGH` (monitoring decision input) |
| `revenue_signal_status` | enum string | no | `NONE` / `WEAK` / `STRONG` (monitoring decision input) |
| `correlation_id` | string | no | End-to-end correlation ID for tracing; returned in callback |
| `callback_url` | string | no | URL to POST build results to (e.g. `https://md.example.com/factory/callback`) |

### Boolean parsing

Accepted true values: `true`, `1`, `yes`, `y`, `on`  
Accepted false values: `false`, `0`, `no`, `n`, `off`, empty string

## Safety / contract guarantees

1. Input contract is normalized before execution (`normalize_inputs` step).
2. `project_id` mismatch between dispatch input and brief is rejected (fail-fast).
3. `run_automated_tests_only=true` always results in `run_mode=tests_only` (no live side effects).
4. Idempotency key is generated from normalized brief and surfaced in final output when available.
5. Unified business gate enforces idea source + demand + score decision before build.
6. If business gate decision is not `APPROVE`, build/deploy are blocked.

## Run modes

- `tests_only`: automated internal tests only, no external actions
- `dry_run`: pipeline executes with side effects disabled
- `production`: live create/inject/deploy path

## Final response contract (factory_response)

Canonical output contract: FactoryRunResult v1.

The workflow emits a structured JSON response in:

1. workflow output: `jobs.build.outputs.factory_response`
2. artifact: `factory-result-<run_id>-<run_attempt>/factory-response.json`

Response shape:

```json
{
  "contract_version": "v1",
  "project_id": "aidan-live-001",
  "run_id": "123456789",
  "run_attempt": "1",
  "workflow_url": "https://github.com/org/repo/actions/runs/123456789",
  "timestamp_utc": "2026-04-04T12:00:00Z",
  "repo_url": "https://github.com/org/aidan-live-001",
  "deployment_url": "https://example.vercel.app",
  "status": "success",
  "run_mode": "production",
  "idempotency_key": "aidan-live-001:abc123def4567890",
  "steps": [],
  "deployment": {
    "status": "triggered",
    "url": "https://example.vercel.app"
  },
  "quality_result": {
    "status": "success",
    "score": 10,
    "decision": "PROCEED",
    "reason": "Quality score 8+ — ready for distribution.",
    "breakdown": {}
  },
  "error_summary": "",
  "failure_reason": "",
  "kill_candidate": false,
  "optimize_candidate": true,
  "scale_candidate": false,
  "result_artifact": {
    "name": "factory-result-123456789-1",
    "path": "factory-response.json"
  }
}
```

### Failure semantics

- `status="failed"` means workflow execution is not successful.
- `error_summary` contains aggregated step-level errors when available.
- `failure_reason` contains a concise primary failure cause (gate, deploy, contract, etc.).
- `steps[]` contains per-step status and error details.

## How AI-DAN should trigger

Example dispatch payload:

```json
{
  "ref": "main",
  "inputs": {
    "project_id": "aidan-live-001",
    "build_brief_json": "{\"project_id\":\"aidan-live-001\",\"product_name\":\"AI-DAN Live Integration Product\",\"problem\":\"AI-DAN needs a reliable first-party way to launch and track factory builds from workflow triggers.\",\"solution\":\"A production-safe placeholder brief used to confirm repo creation, brief injection, and deployment trigger behavior.\",\"cta\":\"Join waitlist\",\"source_type\":\"EXISTING_PRODUCT\",\"reference_context\":\"Modeled from high-performing B2B workflow automation products with active paid plans.\",\"demand_level\":\"HIGH\",\"monetization_proof\":\"YES\",\"market_saturation\":\"MEDIUM\",\"differentiation\":\"STRONG\",\"build_complexity\":\"MEDIUM\",\"speed_to_revenue\":\"FAST\"}",
    "correlation_id": "corr-abc-123",
    "callback_url": "https://md.example.com/factory/callback",
    "dry_run": "false",
    "run_automated_tests_only": "false",
    "test_mode": "false",
    "traffic_signal": "MEDIUM",
    "activation_metric": "MEDIUM",
    "revenue_signal_status": "WEAK"
  }
}
```

The `build_brief_json` can be in either:
- **Factory-native format** (flat JSON with `source_type`, `demand_level`, etc.)
- **Managing Director format** (Pydantic schema with `schema_version`, `idea_id`, `command_bundle`, etc.)

When an MD-format brief is detected (has `idea_id` or `schema_version`), it is automatically adapted to Factory-native format by `scripts/brief_adapter.py`.

## How AI-DAN should poll and read results

Recommended (polling — legacy):

1. Trigger `workflow_dispatch`.
2. Poll run status until completed (`queued`/`in_progress` → `completed`).
3. Download artifact `factory-result-<run_id>-<run_attempt>`.
4. Parse `factory-response.json` as the source of truth.

Recommended (callback — preferred):

1. Trigger `workflow_dispatch` with `callback_url` and `correlation_id`.
2. Factory POSTs results to `callback_url` on completion.
3. Callback is authenticated with `X-Factory-Secret` header (must match `FACTORY_SECRET` secret).

### Callback payload

```json
{
  "project_id": "aidan-live-001",
  "correlation_id": "corr-abc-123",
  "run_id": "123456789",
  "status": "succeeded",
  "deploy_url": "https://example.vercel.app",
  "repo_url": "https://github.com/org/aidan-live-001"
}
```

On failure, an `error` field is included:

```json
{
  "project_id": "aidan-live-001",
  "correlation_id": "corr-abc-123",
  "run_id": "123456789",
  "status": "failed",
  "deploy_url": "",
  "repo_url": "",
  "error": "Factory build failed; check workflow logs"
}
```

This artifact convention is deterministic and machine-friendly.

## Suggested AI-DAN registry fields

Store at least:

- `factory_run_id`
- `factory_run_attempt`
- `factory_workflow_url`
- `factory_timestamp_utc`
- `project_id`
- `run_mode`
- `status`
- `idempotency_key`
- `repo_url`
- `deployment_status`
- `deployment_url`
- `error_summary`
- `failure_reason`
- `kill_candidate`
- `optimize_candidate`
- `scale_candidate`
- `factory_result_artifact_name`

## Example payload files in this repository

- Dry run example: `test_data/aidan_dry_run_brief.json`
- Live example: `test_data/aidan_live_brief.json`
