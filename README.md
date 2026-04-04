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
│       └── factory-build.yml
├── docs/
│   ├── aidan_integration_contract.md
│   └── live_run_checklist.md
├── scripts/
│   ├── create_project.py
│   ├── factory_utils.py
│   ├── normalize_workflow_inputs.py
│   ├── inject_brief.py
│   ├── deploy.py
│   ├── run_factory_tests.py
│   └── validate_brief.py
├── test_data/
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

## Scripts

### `scripts/validate_brief.py`
Validates BuildBrief payloads before execution.

Checks:
- required fields: `project_id`, `product_name`, `problem`, `solution`, `cta`
- `project_id` safe slug format
- text field non-empty and length limits
- key normalization (`snake_case` + `camelCase`)

Produces:
- normalized brief JSON file
- idempotency key (`project_id` + hash(normalized brief))

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

## GitHub Workflow

Workflow file: `.github/workflows/factory-build.yml`

Manual trigger inputs:
- `project_id` (string, required)
- `build_brief_json` (string, required unless `run_automated_tests_only=true`)
- `dry_run` (`true`/`false`)
- `run_automated_tests_only` (`true`/`false`)
- `test_mode` (`true`/`false`, deprecated alias for `run_automated_tests_only`)

Execution order:
1. Checkout
2. Setup Python
3. Initialize run context (unique temp files, secret masking)
4. Run `validate_brief.py`
5. Run `create_project.py`
6. Run `inject_brief.py`
7. Run `deploy.py`
8. Generate final factory response (JSON + human summary)

Final workflow response shape:
```json
{
  "project_id": "acme-saas",
  "repo_url": "https://github.com/org/acme-saas",
  "status": "success",
  "run_mode": "production",
  "idempotency_key": "acme-saas:abc123",
  "error_summary": "",
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
- Negative validation case (invalid brief must fail)
- Full dry-run pipeline simulation:
  - validate brief
  - create repo (simulated)
  - inject brief (simulated)
  - deploy trigger (simulated)

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
{"project_id":"test-001","product_name":"Test Product","problem":"Users need a simple way to validate the AI-DAN factory live pipeline.","solution":"A minimal placeholder product used only to test live repo creation and deployment.","cta":"Join waitlist"}
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
3. **Deploy project** step (deploy hook URL validity and Vercel access).
4. Final `factory_response` JSON in the **Finalize factory response** step.

See the operator checklist: [docs/live_run_checklist.md](docs/live_run_checklist.md)
See AI-DAN contract: [docs/aidan_integration_contract.md](docs/aidan_integration_contract.md)

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
