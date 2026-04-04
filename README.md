# GitHub Factory (Minimal Production Structure)

This repository is a minimal factory that:
1. Creates a GitHub project repository from a template
2. Validates and normalizes BuildBrief input
3. Injects BuildBrief into placeholder product files
4. Triggers deployment through Vercel API

## Folder Structure

```text
.
├── .github/
│   └── workflows/
│       ├── factory-autonomous-runner.yml
│       ├── factory-build.yml
│       ├── factory-ci.yml
│       └── factory-monitor.yml
├── data/
│   └── lifecycle.sqlite
├── docs/
│   ├── aidan_integration_contract.md
│   ├── live_run_checklist.md
│   └── operator_control_contract.md
├── scripts/
│   ├── business_output_engine.py
│   ├── create_project.py
│   ├── deploy.py
│   ├── deploy_health_check.py
│   ├── emit_alert.py
│   ├── factory_utils.py
│   ├── idea_source_engine.py
│   ├── lifecycle_orchestrator.py
│   ├── monitor_and_decide.py
│   ├── normalize_workflow_inputs.py
│   ├── portfolio_summary.py
│   ├── run_factory_tests.py
│   ├── scoring_engine.py
│   ├── state_store.py
│   ├── validate_brief.py
│   └── validate_business_gate.py
├── test_data/
│   ├── autonomous_ideas.json
│   ├── aidan_dry_run_brief.json
│   ├── aidan_live_brief.json
│   └── live_test_brief.json
└── templates/
    └── saas-template/
        ├── .gitignore
        ├── PRODUCT_BRIEF.md
        ├── app/
        │   ├── api/
        │   │   └── lead/
        │   │       └── route.ts
        │   ├── globals.css
        │   ├── layout.tsx
        │   └── page.tsx
        ├── next-env.d.ts
        ├── next.config.js
        ├── package.json
        ├── product.config.json
        └── tsconfig.json
```

## Template Behavior (`templates/saas-template`)

- Next.js 14 app (App Router)
- Single landing page with one CTA button
- Hero section that reads `PRODUCT_BRIEF.md` and displays:
  - Product name
  - Problem
  - Solution
  - CTA
- API route: `POST /api/lead`

## Scripts (Core)

### `scripts/validate_brief.py`
Validates BuildBrief payloads before execution.

Checks:
- required fields including business-gate metadata:
  - `project_id`, `product_name`, `problem`, `solution`, `cta`
  - `source_type`, `reference_context`
  - `demand_level`, `monetization_proof`, `market_saturation`, `differentiation`
- `project_id` safe slug format
- text field non-empty and length limits
- key normalization (`snake_case` + `camelCase`)

Produces:
- normalized brief JSON file
- idempotency key (`project_id` + hash(normalized brief))

### `scripts/validate_business_gate.py`
Unified execution gate (mandatory before build/deploy):
- validates idea source + demand + differentiation rules
- computes deterministic AI-DAN score (0–10)
- returns decision: `APPROVE | HOLD | REJECT`
- blocks pipeline when decision is not `APPROVE`

Hard rules:
- `LOW` demand => reject
- `monetization_proof=NO` => reject
- `HIGH` saturation + `WEAK` differentiation => reject

### `scripts/scoring_engine.py`
Deterministic scoring module/script used by the business gate:
- score breakdown:
  - market demand
  - competition saturation
  - monetization potential
  - build complexity reverse score
  - speed-to-revenue
- score-based decision:
  - `<6` => `REJECT`
  - `6-7` => `HOLD`
  - `8-10` => `APPROVE`

### `scripts/idea_source_engine.py`
Autonomous idea selection layer:
- loads candidate briefs from `test_data/autonomous_ideas.json`
- validates required fields
- selects a deterministic brief using run-based seed
- emits selected brief artifact for downstream scoring/gating

### `scripts/lifecycle_orchestrator.py`
Enforces strict lifecycle transitions:
`idea -> validated -> scored -> approved/rejected/hold`
`approved -> building -> deployed -> monitored -> scaled/killed`

No step skipping is allowed.

### `scripts/business_output_engine.py`
Generates mandatory monetization payload:
`business_output.json` including:
- headline
- cta
- monetization_model
- pricing_suggestion
- offer_structure
- 2-channel GTM plan
- conversion hints

### `scripts/deploy_health_check.py`
Post-deploy reliability gate:
- retries health probes
- emits failure reason when unhealthy

### `scripts/monitor_and_decide.py` + `scripts/portfolio_summary.py`
Auto-prune/scale layer:
- tracks `traffic_signal`, `activation_metric`, `revenue_signal_status`
- emits `kill_candidate`, `optimize_candidate`, `scale_candidate`
- outputs simplified portfolio buckets: `IGNORE`, `WATCH`, `SCALE` (max 5 each)

### `scripts/state_store.py`
Persistent state backend for lifecycle and monitoring:
- manages lifecycle transitions in SQLite
- stores run-level state and transition history
- stores monitoring decision signals
- database path used across all workflows: `data/lifecycle.sqlite`
- `factory-build` writes to `data/lifecycle.sqlite` and uploads it as a workflow artifact; `factory-monitor` reads from the same path after checkout

### `scripts/create_project.py`
Creates a GitHub repo from a template repo using GitHub API with duplicate protection.

Behavior:
- checks if the target repo already exists (idempotent reruns)
- if repo exists, marks as already created and continues safely
- retries transient GitHub API/network errors
- emits structured JSON logs and optional result JSON file

Example:
```bash
python scripts/create_project.py \
  --project-id acme-saas \
  --org your-org
```

Environment:
- `GITHUB_TOKEN` (required unless `--dry-run`)
- `TEMPLATE_OWNER` / `TEMPLATE_REPO` (optional if `GITHUB_REPOSITORY` is available)

### `scripts/inject_brief.py`
Takes BuildBrief JSON and generates:
- `PRODUCT_BRIEF.md`
- `product.config.json`

Behavior:
- strict required-field checks (no silent placeholder fallback)
- atomic writes for safe reruns
- structured JSON logs + optional result JSON file

Example:
```bash
python scripts/inject_brief.py \
  --project-dir templates/saas-template \
  --brief-json '{"project_id":"acme-saas","product_name":"Acme","problem":"Ops chaos","solution":"Automated workflow","cta":"Join Waitlist"}'
```

### `scripts/deploy.py`
Triggers deployment via Vercel Deploy Hook API.

Behavior:
- dry-run / production mode
- retry transient deployment trigger failures
- structured JSON logs + optional result JSON file

Example:
```bash
python scripts/deploy.py --project-id acme-saas
```

Environment:
- `VERCEL_DEPLOY_HOOK_URL` (required unless `--dry-run`)

## GitHub Workflows

Primary execution:
- `.github/workflows/factory-build.yml` (full lifecycle run)

Autonomous scheduler:
- `.github/workflows/factory-autonomous-runner.yml` (scheduled source->score->gate loop)

Monitoring loop:
- `.github/workflows/factory-monitor.yml` (scheduled portfolio summaries from lifecycle DB)

Manual trigger inputs:
- `project_id` (string, required)
- `build_brief_json` (string, required unless `run_automated_tests_only=true`)
- `dry_run` (`true`/`false`)
- `run_automated_tests_only` (`true`/`false`)
- `test_mode` (`true`/`false`, deprecated alias for `run_automated_tests_only`)

Execution order (non-tests mode):
1. Checkout + setup
2. Normalize input contract
3. Lifecycle state = `idea`
4. Validate brief contract
5. Unified business gate (`validate_business_gate.py`) => APPROVE required
6. Lifecycle state = `building`
7. Create repo
8. Inject brief
9. Generate `business_output.json`
10. Trigger deploy
11. Deploy health check
12. Lifecycle states: `deployed`, then `monitored`
13. Monitor decision output (kill/optimize/scale candidates)
14. Portfolio summary output
15. Final factory response + artifacts

Final workflow response shape:
```json
{
  "project_id": "acme-saas",
  "run_id": "123456789",
  "run_attempt": "1",
  "workflow_url": "https://github.com/org/repo/actions/runs/123456789",
  "timestamp_utc": "2026-04-04T00:00:00Z",
  "repo_url": "https://github.com/org/acme-saas",
  "deployment_url": "https://acme.vercel.app",
  "status": "success",
  "run_mode": "production",
  "idempotency_key": "acme-saas:abc123",
  "error_summary": "",
  "failure_reason": "",
  "kill_candidate": false,
  "optimize_candidate": false,
  "scale_candidate": false,
  "steps": [],
  "deployment": {
    "status": "triggered",
    "url": "https://acme.vercel.app"
  },
  "result_artifact": {
    "name": "factory-result-123-1",
    "path": "factory-response.json"
  }
}
```

## Required GitHub Secrets

- `FACTORY_GITHUB_TOKEN`
- `VERCEL_DEPLOY_HOOK_URL`

## Automated Testing (No Manual Steps)

Run all factory tests with one command:

```bash
python3 scripts/run_factory_tests.py
```

What this automates:
- Python syntax checks for all factory scripts
- BuildBrief payload validity check
- Autonomous idea payload validation + deterministic scoring check
- Negative validation case (invalid brief must fail)
- Full dry-run pipeline simulation:
  - validate brief
  - business gate decision
  - create repo (simulated)
  - inject brief (simulated)
  - generate business output
  - deploy trigger (simulated)
  - deploy health check (simulated)

CI automation:
- `.github/workflows/factory-ci.yml` runs these tests automatically on:
  - pushes to `main`
  - pull requests targeting `main`
  - manual trigger (`workflow_dispatch`)
- Runs are concurrency-cancelled per branch/PR to avoid duplicate compute.
- `factory-build` also supports `run_automated_tests_only=true` for tests-only execution with no external actions.

Recommended merge efficiency setting (GitHub UI):
- Branch protection for `main` should require status check:
  - `factory-ci / test`
- This prevents manual review churn on unverified changes.

## First Live Run

Use this run to verify the first real execution without changing factory logic.

1. Open GitHub → **Actions** → **factory-build** workflow.
2. Click **Run workflow** (recommended branch: `main`).
3. Use these inputs:
   - `project_id`: `test-001`
   - `build_brief_json`: paste contents of `test_data/live_test_brief.json`
   - `dry_run`: `false`
   - `run_automated_tests_only`: `false`

Reference payload:

```json
{
  "project_id":"test-001",
  "product_name":"Test Product",
  "problem":"Users need a simple way to validate the AI-DAN factory live pipeline.",
  "solution":"A minimal placeholder product used only to test live repo creation and deployment.",
  "cta":"Join waitlist",
  "source_type":"TREND",
  "reference_context":"Search demand for lightweight AI product launch kits among indie founders.",
  "demand_level":"HIGH",
  "monetization_proof":"YES",
  "market_saturation":"MEDIUM",
  "differentiation":"STRONG",
  "build_complexity":"LOW",
  "speed_to_revenue":"FAST"
}
```

Recommended first settings:
- Run once with `dry_run=true` if you want one final simulation.
- Run with `dry_run=false` for the first actual live test.

What success looks like:
- Steps `Validate BuildBrief`, `Create project repository`, `Inject BuildBrief`, and `Deploy project` all complete.
- Final summary shows run status as **SUCCESS**.
- Summary includes a repo URL and deployment status.
- Step output includes the structured factory response JSON (`factory_response`).

What to check first on failure:
1. **Validate BuildBrief** step (invalid JSON, missing fields, `project_id` mismatch).
2. **Create project repository** step (token scope/permissions).
3. **Unified business gate** step (decision must be `APPROVE`).
4. **Deploy project** / **Deployment health check** steps.
5. Final `factory_response` JSON in the **Finalize factory response** step.

See the operator checklist: [docs/live_run_checklist.md](docs/live_run_checklist.md)
See AI-DAN contract: [docs/aidan_integration_contract.md](docs/aidan_integration_contract.md)
See operator control contract: [docs/operator_control_contract.md](docs/operator_control_contract.md)

## Fast workflow testing in Actions

To run checks without triggering repo creation/deployment:

1. Open **Actions** → **factory-build**.
2. Click **Run workflow**.
3. Set:
   - `run_automated_tests_only=true`
   - `dry_run=true`
   - `build_brief_json` can be empty
   - `project_id` can stay `test-001`

This executes tests-only mode and guarantees no live repo creation/deployment.
