# AI-DAN Factory — Automated Product Factory

A zero-touch product factory that validates ideas, creates repositories, builds products, deploys them, evaluates quality, and generates distribution content — all from a single BuildBrief JSON payload.

## Overview

The factory executes a strict pipeline:

```
BuildBrief → Validate → Score → Approve → Economics → Control → Queue →
Create Repo → Inject → Build → Deploy → Health Check → Quality Gate →
Monitor → Distribute → Track → Learn
```

No step can be skipped. Every decision is deterministic and auditable.

## Architecture

```text
.
├── .github/workflows/
│   ├── factory-build.yml              # Main pipeline (25+ steps)
│   ├── factory-autonomous-runner.yml  # Scheduled idea source/score loop
│   ├── factory-ci.yml                 # CI tests on PRs and pushes
│   └── factory-monitor.yml            # Scheduled portfolio monitoring
├── scripts/
│   ├── validate_brief.py              # Phase 1: BuildBrief validation + normalization
│   ├── validate_business_gate.py      # Phase 2: Unified business gate (APPROVE/HOLD/REJECT)
│   ├── scoring_engine.py              # Phase 2: Deterministic scoring (0-10)
│   ├── build_economics.py             # Phase 8.5: ROI evaluation before build
│   ├── build_control.py               # Phase 8: Rate limiting + queue priority
│   ├── create_project.py              # Phase 3: GitHub repo creation from template
│   ├── inject_brief.py                # Phase 4: Brief injection into product files
│   ├── deploy.py                      # Phase 6: Vercel deployment trigger
│   ├── deploy_health_check.py         # Phase 6.5: Post-deploy health verification
│   ├── quality_gate.py                # Phase 6.65: Product quality scoring gate
│   ├── business_output_engine.py      # Phase 11: Monetization payload generation
│   ├── distribution_engine.py         # Phase 11.5: Distribution content + outreach
│   ├── monitor_and_decide.py          # Phase 7/12: Signal evaluation + decisions
│   ├── portfolio_summary.py           # Phase 7: Portfolio bucketing
│   ├── lifecycle_orchestrator.py      # Phase 9: Strict state machine transitions
│   ├── state_store.py                 # Phase 7: Persistent SQLite lifecycle store
│   ├── idea_source_engine.py          # Phase 13: Autonomous idea selection
│   ├── factory_utils.py               # Shared utilities
│   ├── normalize_workflow_inputs.py   # Workflow input normalization
│   ├── emit_alert.py                  # Failure alert payloads
│   └── run_factory_tests.py           # 9-stage automated test suite
├── templates/saas-template/           # Next.js 14 landing page template
├── test_data/                         # Test payloads and autonomous ideas
├── data/lifecycle.sqlite              # Persistent lifecycle database
├── docs/                              # Integration contracts and checklists
└── .env.example                       # Required environment variables
```

## Setup

### Environment Variables

Copy `.env.example` to `.env` and fill in values. In GitHub Actions, set these as repository secrets:

| Variable | Required | Description |
|----------|----------|-------------|
| `FACTORY_GITHUB_TOKEN` | Yes | PAT with `repo` scope for creating repositories |
| `VERCEL_DEPLOY_HOOK_URL` | Yes | Vercel webhook URL for triggering deployments |
| `TEMPLATE_OWNER` | No | Template repo owner (defaults to current repo owner) |
| `TEMPLATE_REPO` | No | Template repo name (defaults to current repo name) |
| `MAX_BUILDS_PER_DAY` | No | Daily build limit (default: 20) |
| `MAX_PARALLEL_BUILDS` | No | Max parallel builds (default: 3) |
| `MIN_ROI_THRESHOLD` | No | Minimum ROI to approve build (default: 1.5) |

### First Run

1. Set repository secrets: `FACTORY_GITHUB_TOKEN`, `VERCEL_DEPLOY_HOOK_URL`
2. Go to **Actions** → **factory-build** → **Run workflow**
3. Inputs:
   - `project_id`: `test-001`
   - `build_brief_json`: paste content from `test_data/live_test_brief.json`
   - `dry_run`: `true` (first time)
4. Verify success, then re-run with `dry_run`: `false`

## Pipeline Phases

### Phase 1 — BuildBrief Validation
Validates and normalizes input. Required fields:
- `project_id`, `product_name`, `problem`, `solution`, `cta`
- `source_type`, `reference_context`
- `demand_level`, `monetization_proof`, `market_saturation`, `differentiation`

Optional scoring fields preserved: `build_complexity`, `speed_to_revenue`

### Phase 2 — Revenue Scoring Engine
Deterministic scoring (0–10) with hard rules:
- LOW demand → REJECT
- monetization_proof=NO → REJECT
- HIGH saturation + WEAK differentiation → REJECT
- Score <6 → REJECT, 6-7 → HOLD, ≥8 → APPROVE

### Phase 3 — Repo Creation
Idempotent GitHub repo creation from template. Retries on transient errors. Skips if repo already exists.

### Phase 4 — Build Injection
Injects BuildBrief into `PRODUCT_BRIEF.md` and `product.config.json`. Atomic writes for safe reruns.

### Phase 5 — Build Pipeline Hardening
Deterministic builds with retry logic, structured logging, and failure detection at every step.

### Phase 6 — Deployment
Triggers Vercel deployment via webhook. Retries on transient failures.

### Phase 6.5 — Deployment Verification
Health check with configurable retries. Fails pipeline if deployment is unreachable.

### Phase 6.65 — Product Quality Gate
Evaluates product quality (0–10) across 5 dimensions:
- Clarity, Usability, UX Simplicity, Perceived Value, First Impression
- <6 → BLOCK distribution, 6-7 → improve, ≥8 → proceed

### Phase 7 — Tracking System
Persistent SQLite database tracks: run_id, project_id, repo_url, deployment_url, status, timestamps, transitions.

### Phase 8 — Control Layer
Rate limiting, queue priority, and duplicate prevention:
- `MAX_BUILDS_PER_DAY` enforcement
- Idempotency checking (no duplicate active builds)
- Priority scoring by revenue score + demand + speed

### Phase 8.5 — Build Economics
ROI evaluation before build:
- Estimates build cost, expected return, ROI
- NEGATIVE ROI → REJECT, LOW ROI → HOLD, HIGH ROI → PRIORITIZE

### Phase 9 — Idempotency
Idempotency key = `project_id:hash(normalized_brief)`. Enforced at validation, repo creation, and build control.

### Phase 10 — Failure Recovery
Retry logic at every external call (GitHub API, Vercel, health checks). Structured failure alerts with `emit_alert.py`.

### Phase 11 — Monetization Validation
Generates `business_output.json` with: headline, CTA, monetization model, pricing, offer structure, GTM plan, conversion hints.

### Phase 11.5 — Distribution Execution
Generates distribution content:
- Landing page content summary
- Social media launch post
- 5 outreach targets with personalized messages
- Tracking structure (impressions, clicks, responses)

### Phase 12 — Auto-Improvement Loop
Monitor + decide engine tracks success patterns: traffic, activation, revenue signals → kill/optimize/scale decisions.

### Phase 13 — Automation
GitHub Actions workflows:
- `factory-build.yml`: Full pipeline (manual dispatch)
- `factory-autonomous-runner.yml`: Scheduled every 30 min
- `factory-monitor.yml`: Scheduled portfolio monitoring
- `factory-ci.yml`: CI on PRs and pushes

### Phase 14 — Single Operator Simplicity
- No coding required
- Safe defaults for all optional inputs
- Clear JSON outputs at every step
- Operator control contract in `docs/operator_control_contract.md`

## Workflow Execution Order

```
 1. Checkout + setup
 2. Normalize input contract
 3. Run tests only (if enabled)
 4. Initialize lifecycle (idea)
 5. Validate BuildBrief
 6. Business gate (APPROVE required)
 7. Build economics evaluation
 8. Build control check
 9. Lifecycle → building
10. Create repository
11. Inject BuildBrief
12. Generate business output
13. Trigger deployment
14. Health check
15. Quality gate
16. Lifecycle → deployed → monitored
17. Monitor & decide
18. Distribution execution
19. Portfolio summary
20. Finalize response
21. Alert on failure
22. Upload artifacts
```

## Automated Testing

```bash
python3 scripts/run_factory_tests.py
```

9-stage test suite:
1. Script syntax checks (all 20 scripts)
2. Payload schema validation
3. Idea source + scoring tests
4. Business gate + lifecycle tests
5. Full dry-run pipeline simulation
6. Monitor/scale/portfolio tests
7. Negative guard tests
8. Quality gate + economics + distribution + control tests
9. End-to-end pipeline simulation (13 steps)

## Monetization Readiness

Every approved product includes:
- Clear CTA in landing page
- Pricing suggestion in business output
- Monetization model (subscription/one-time)
- 2-channel GTM plan
- Conversion hints
- Distribution content ready for outreach

## Documentation

- [AI-DAN Integration Contract](docs/aidan_integration_contract.md)
- [Operator Control Contract](docs/operator_control_contract.md)
- [Live Run Checklist](docs/live_run_checklist.md)
