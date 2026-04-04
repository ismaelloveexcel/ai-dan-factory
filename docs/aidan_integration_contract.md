# AI-DAN ↔ Factory Integration Contract

This document defines how AI-DAN should trigger and consume `factory-build` in this repository.

## Workflow endpoint

- Workflow file: `.github/workflows/factory-build.yml`
- Workflow name: `factory-build`
- Trigger type: `workflow_dispatch`

## Dispatch inputs (contract)

| Input | Type | Required | Notes |
|---|---|---:|---|
| `project_id` | string | yes | Must be a safe slug: lowercase letters, numbers, hyphens (`^[a-z0-9]+(?:-[a-z0-9]+)*$`) |
| `build_brief_json` | string | conditional | Required unless `run_automated_tests_only=true` |
| `dry_run` | string boolean | yes | Recommended values: `"true"` or `"false"` |
| `run_automated_tests_only` | string boolean | no | Default `"false"`. When true, live create/deploy steps are skipped. |
| `test_mode` | string boolean | no | Deprecated alias for `run_automated_tests_only` (kept for backward compatibility) |

### Boolean parsing

Accepted true values: `true`, `1`, `yes`, `y`, `on`  
Accepted false values: `false`, `0`, `no`, `n`, `off`, empty string

## Safety / contract guarantees

1. Input contract is normalized before execution (`normalize_inputs` step).
2. `project_id` mismatch between dispatch input and brief is rejected (fail-fast).
3. `run_automated_tests_only=true` always results in `run_mode=tests_only` (no live side effects).
4. Idempotency key is generated from normalized brief and surfaced in final output when available.

## Run modes

- `tests_only`: automated internal tests only, no external actions
- `dry_run`: pipeline executes with side effects disabled
- `production`: live create/inject/deploy path

## Final response contract (factory_response)

The workflow emits a structured JSON response in:

1. workflow output: `jobs.build.outputs.factory_response`
2. artifact: `factory-result-<run_id>-<run_attempt>/factory-response.json`

Response shape:

```json
{
  "project_id": "aidan-live-001",
  "repo_url": "https://github.com/org/aidan-live-001",
  "status": "success",
  "steps": [],
  "deployment": {
    "status": "triggered",
    "url": "https://example.vercel.app"
  },
  "idempotency_key": "aidan-live-001:abc123def4567890",
  "run_mode": "production",
  "error_summary": "",
  "result_artifact": {
    "name": "factory-result-123456789-1",
    "path": "factory-response.json"
  }
}
```

### Failure semantics

- `status="failed"` means workflow execution is not successful.
- `error_summary` contains aggregated step-level errors when available.
- `steps[]` contains per-step status and error details.

## How AI-DAN should trigger

Example dispatch payload:

```json
{
  "ref": "main",
  "inputs": {
    "project_id": "aidan-live-001",
    "build_brief_json": "{\"project_id\":\"aidan-live-001\",\"product_name\":\"AI-DAN Live Integration Product\",\"problem\":\"AI-DAN needs a reliable first-party way to launch and track factory builds from workflow triggers.\",\"solution\":\"A production-safe placeholder brief used to confirm repo creation, brief injection, and deployment trigger behavior.\",\"cta\":\"Join waitlist\"}",
    "dry_run": "false",
    "run_automated_tests_only": "false",
    "test_mode": "false"
  }
}
```

## How AI-DAN should poll and read results

Recommended:

1. Trigger `workflow_dispatch`.
2. Poll run status until completed (`queued`/`in_progress` → `completed`).
3. Download artifact `factory-result-<run_id>-<run_attempt>`.
4. Parse `factory-response.json` as the source of truth.

This artifact convention is deterministic and machine-friendly.

## Suggested AI-DAN registry fields

Store at least:

- `factory_run_id`
- `factory_run_attempt`
- `project_id`
- `run_mode`
- `status`
- `idempotency_key`
- `repo_url`
- `deployment_status`
- `deployment_url`
- `error_summary`
- `factory_result_artifact_name`

## Example payload files in this repository

- Dry run example: `test_data/aidan_dry_run_brief.json`
- Live example: `test_data/aidan_live_brief.json`
