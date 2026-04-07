# AI-DAN Factory — Execution Plane

This repository is the AI-DAN execution plane. It executes approved BuildBrief payloads, performs deterministic execution stages, and returns canonical execution artifacts.

This repository is not the business control plane. Business/portfolio authority remains in `aidan-managing-director`.

## Overview

The execution plane runs a strict execution pipeline:

```
BuildBrief → Validate → Gate → Economics → Control → Repo Discovery →
Create Repo → Inject → Deploy → Health Check → Quality Gate →
Execution Signals → Distribution Artifacts → FactoryRunResult
```

Execution stages are deterministic and auditable. Repo discovery/template selection remains first-class and can alter the template source when high-confidence external matches are found.

## Architecture

```text
.
├── .github/workflows/
│   ├── factory-build.yml              # Thin workflow wrapper around Python orchestrator
│   ├── factory-autonomous-runner.yml  # Scheduled idea source/score loop
│   ├── factory-ci.yml                 # CI tests on PRs and pushes
│   └── factory-monitor.yml            # Scheduled portfolio monitoring
├── scripts/
│   ├── validate_brief.py              # Phase 1: BuildBrief validation + normalization
│   ├── validate_business_gate.py      # Phase 2: Unified business gate (APPROVE/HOLD/REJECT)
│   ├── scoring_engine.py              # Phase 2: Deterministic scoring (0-10)
│   ├── build_economics.py             # Phase 3: ROI evaluation before build
│   ├── build_control.py               # Phase 4: Rate limiting + queue priority
│   ├── repo_discovery_engine.py       # Phase 4.5: GitHub repo discovery + template selection
│   ├── create_project.py              # Phase 5: GitHub repo creation from template
│   ├── ai_enhance.py                  # Phase 5.5: AI-generated marketing copy (OpenAI)
│   ├── inject_brief.py                # Phase 6: Brief + AI copy injection into product files
│   ├── deploy.py                      # Phase 7: Vercel deployment trigger
│   ├── deploy_health_check.py         # Phase 7.5: Post-deploy health verification
│   ├── quality_gate.py                # Phase 8: Product quality scoring gate (6 dimensions)
│   ├── business_output_engine.py      # Phase 9: Monetization payload generation
│   ├── distribution_engine.py         # Phase 10: Distribution content + outreach
│   ├── monitor_and_decide.py          # Phase 11: Signal evaluation + decisions
│   ├── portfolio_summary.py           # Phase 11.5: Portfolio bucketing
│   ├── lifecycle_orchestrator.py      # Strict execution-run state transitions
│   ├── factory_orchestrator.py        # Main execution orchestrator (stage sequencing)
│   ├── factory_run_contract.py        # BuildBrief/FactoryRunResult contract helpers
│   ├── state_store.py                 # Persistent SQLite lifecycle store
│   ├── idea_source_engine.py          # Autonomous idea selection
│   ├── factory_utils.py               # Shared utilities
│   ├── normalize_workflow_inputs.py   # Workflow input normalization
│   ├── emit_alert.py                  # Failure alert payloads
│   └── run_factory_tests.py           # 9-stage automated test suite
├── templates/saas-template/           # Next.js 14 conversion-optimized landing page
├── test_data/                         # Test payloads and autonomous ideas
├── data/lifecycle.sqlite              # Persistent execution-run state database
├── docs/                              # Integration contracts and checklists
└── .env.example                       # Required environment variables
```

## Setup

### Environment Variables

Copy `.env.example` to `.env` and fill in values. In GitHub Actions, set these as repository secrets:

| Variable | Required | Description |
|----------|----------|-------------|
| `FACTORY_GITHUB_TOKEN` | Yes | PAT with `repo` scope for creating repositories and repo discovery |
| `VERCEL_DEPLOY_HOOK_URL` | Yes | Vercel webhook URL for triggering deployments |
| `OPENAI_API_KEY` | Recommended | OpenAI key for AI-generated copy (headlines, CTAs, descriptions) |
| `TEMPLATE_OWNER` | No | Template repo owner (defaults to current repo owner) |
| `TEMPLATE_REPO` | No | Template repo name (defaults to current repo name) |
| `MAX_BUILDS_PER_DAY` | No | Daily build limit (default: 20) |
| `MAX_PARALLEL_BUILDS` | No | Max parallel builds (default: 3) |
| `MIN_ROI_THRESHOLD` | No | Minimum ROI to approve build (default: 1.5) |

### First Run

1. Set repository secrets: `FACTORY_GITHUB_TOKEN`, `VERCEL_DEPLOY_HOOK_URL`, optionally `OPENAI_API_KEY`
2. Go to **Actions** → **factory-build** → **Run workflow**
3. Inputs:
   - `project_id`: `test-001`
   - `build_brief_json`: paste content from `test_data/live_test_brief.json`
   - `dry_run`: `true` (first time)
4. Verify success, then re-run with `dry_run`: `false`

## Execution Stages

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

### Phase 3 — Build Economics (ROI Gate)
ROI evaluation before build:
- Estimates build cost, expected return, ROI
- Factors: pricing potential, speed to revenue, demand signals
- NEGATIVE ROI → REJECT, LOW ROI → HOLD, HIGH ROI → PRIORITIZE

### Phase 4 — Build Control / Rate Limiting
Rate limiting, queue priority, and duplicate prevention:
- `MAX_BUILDS_PER_DAY` enforcement
- `MAX_PARALLEL_BUILDS` enforcement
- Idempotency checking (no duplicate active builds)
- Priority scoring by revenue score + demand + speed

### Phase 4.5 — Repo Discovery + Template Selection
Before building from scratch, the factory searches GitHub for relevant starter repos/templates:
- **Search intent** is derived from the BuildBrief — core fields (product name, problem, solution) plus optional enrichment fields when available (target\_user, product\_type, stack preference, UI keywords)
- **GitHub Search API** returns candidate repositories ranked by stars
- **Hard exclusion filters** immediately reject:
  - Archived repositories
  - Forks
  - Stale repositories (no updates in the last 365 days)
  - Oversized / over-complex repos (>500 MB or >200 open issues)
  - List-only repositories (awesome-lists, curated resource lists)
- **Deterministic scoring** evaluates each remaining candidate on six dimensions:
  - Relevance (0-30): keyword overlap with the build intent
  - Popularity (0-20): GitHub stars on a log scale
  - Recency (0-15): freshness of last update
  - Template suitability (0-15): is\_template flag, template/starter keywords
  - Tech fit (0-10): programming language match
  - Simplicity (0-10): low issue count, reasonable repo size
- **Selection decisions**:
  - `REUSE_EXTERNAL_TEMPLATE` — best candidate scores ≥ 70; the factory uses this repo as the template source for repo creation instead of the internal template
  - `USE_INTERNAL_TEMPLATE` — no external repo meets threshold; the factory uses its own internal template (default behavior)
  - `BUILD_MINIMAL_INTERNAL` — no external repo and no internal template available; builds a minimal project structure
- **Build path integration**: when `REUSE_EXTERNAL_TEMPLATE` is selected, the create-repo step (Phase 5) overrides its template owner/repo to clone from the selected external template instead of the factory's internal template. This means discovery actually changes the build source.
- **Fallback safety**: if the GitHub API fails or returns no results, the pipeline continues with the internal template — discovery failures never block builds
- Uses `FACTORY_GITHUB_TOKEN` for authenticated API calls (same token as repo creation)

### Phase 5 — Repo Creation
Idempotent GitHub repo creation from template. Retries on transient errors. Skips if repo already exists.

### Phase 5.5 — AI Enhancement (Optional)
When `OPENAI_API_KEY` is set, generates high-quality marketing copy:
- Headline (problem → solution)
- Subheading (value proposition)
- Product description
- CTA button text
- Short pitch
- Benefit bullets

Falls back to deterministic templates when API key is missing (marked as `reduced`).

### Phase 6 — Build Injection
Injects BuildBrief + AI copy into `PRODUCT_BRIEF.md` and `product.config.json`. Atomic writes for safe reruns.

### Phase 7 — Deployment
Triggers Vercel deployment via webhook. Retries on transient failures.

### Phase 7.5 — Deployment Verification
Health check with configurable retries. Fails pipeline if deployment is unreachable (no 404 allowed).

### Phase 8 — Product Quality Gate
Evaluates product quality (0–12) across 6 dimensions:
- Clarity (product messaging)
- Usability (CTA quality)
- UX Simplicity (landing page completeness)
- Perceived Value (monetization signals)
- First Impression (deployment readiness)
- Conversion Readiness (target user + pricing + distribution plan)

Rules: <6 → BLOCK distribution, 6-7 → improve, ≥8 → proceed

### Phase 9 — Monetization Validation
Generates `business_output.json` with: headline, CTA, monetization model, pricing, offer structure, GTM plan, target user, distribution plan.

Every output includes:
- Product idea
- Target user
- Monetization method
- Pricing hint
- Distribution plan

### Phase 10 — Distribution Execution
Generates ready-to-use distribution content:
- Landing page content summary with monetization messaging
- Social media launch post
- 5 outreach targets with personalized messages and audience targeting
- Monetization summary (product, target user, pricing, distribution)
- Tracking structure (impressions, clicks, responses)

### Phase 11 — Auto-Improvement Loop
Monitor + decide engine tracks success patterns: traffic, activation, revenue signals → kill/optimize/scale decisions.

### Phase 11.5 — Portfolio Summary
Buckets all projects into IGNORE / WATCH / SCALE categories based on monitoring signals.

### Phase 12 — Lifecycle Tracking
Persistent SQLite database tracks: run_id, project_id, repo_url, deployment_url, status, timestamps, transitions. Strict state machine prevents invalid transitions.

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
 8.7. Repo discovery + template selection
 9. Lifecycle → building
10. Create repository
11. AI enhancement (generate copy)
12. Inject BuildBrief + AI copy
13. Generate business output
14. Trigger deployment
15. Health check
16. Quality gate (6-dimension scoring)
17. Lifecycle → deployed → monitored
18. Monitor & decide
19. Distribution execution
20. Portfolio summary
21. Finalize response
22. Alert on failure
23. Upload artifacts
```

## Automated Testing

```bash
python3 scripts/run_factory_tests.py
```

10-stage test suite:
1. Script syntax checks (all scripts)
2. Payload schema validation
3. Idea source + scoring tests
4. Business gate + lifecycle tests
5. Full dry-run pipeline simulation
6. Monitor/scale/portfolio tests
7. Negative guard tests
8. Quality gate + economics + distribution + control tests
9. End-to-end pipeline simulation
10. Repo discovery + template selection tests (scoring, exclusion filters, fixture scenarios, CLI)

## Monetization Readiness

Every approved product includes:
- Clear CTA in landing page
- Pricing suggestion in business output
- Target user identification
- Monetization model (subscription/one-time)
- Distribution plan with channel strategy
- 2-channel GTM plan
- Conversion hints
- Ready-to-use outreach content
- AI-enhanced copy (when API key available)

## Product Presentation

Every deployed product landing page includes:
- Conversion-optimized hero section with headline and subheading
- Email capture CTA form
- Benefit bullets (3 key value propositions)
- Pricing section (when pricing data available)
- Bottom CTA for repeat conversion opportunity
- Mobile-friendly responsive layout
- Clean, uncluttered design with readable typography

## Documentation

- [AI-DAN Integration Contract](docs/aidan_integration_contract.md)
- [Operator Control Contract](docs/operator_control_contract.md)
- [Live Run Checklist](docs/live_run_checklist.md)
