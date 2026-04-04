# AI-DAN Factory

**Autonomous AI product factory** — validates, scores, builds, deploys, and monitors SaaS products from idea to revenue. Zero-touch. One operator. Production-ready.

## Overview

AI-DAN Factory is a GitHub-native autonomous pipeline that turns product ideas into live SaaS landing pages with monetization strategies. Every idea passes through a strict validation gate, scoring engine, and monetization filter before any resources are spent.

**Key Capabilities:**
- 🔒 **Validation Gate** — Blocks weak ideas automatically (demand, monetization, differentiation)
- 📊 **Scoring Engine** — Deterministic 0-10 score; only ≥8 proceeds to build
- 💰 **Monetization Filter** — Prioritizes fast-revenue ideas (<14 days to first dollar)
- 🧠 **Portfolio Memory** — Deduplicates ideas; rejects repeats of failed concepts
- 🚀 **Auto-Deploy** — Creates GitHub repos from template + deploys to Vercel
- 📈 **Revenue Loop** — Post-launch: NO_TRACTION → kill, INTEREST_ONLY → iterate, REVENUE_CONFIRMED → scale
- ⏰ **Autonomous Scheduling** — Runs every 30 minutes on cron (zero manual triggers needed)

## Architecture

```
Idea → Monetization Filter → Dedup Check → Validate → Score → Approve/Reject
                                                                    ↓
                                          Build → Deploy → Health Check → Monitor
                                                                              ↓
                                                        Revenue Loop → Scale / Kill
```

### Lifecycle State Machine (Strict, No Skip)

```
idea → validated → scored → approved / rejected / hold
                                ↓
                    building → deployed → monitored → scaled / killed
```

## Folder Structure

```text
.
├── .github/
│   ├── copilot-instructions.md          # AI-DAN architecture rules
│   └── workflows/
│       ├── factory-build.yml            # Main 24-step pipeline
│       ├── factory-ci.yml               # Automated test runner
│       ├── factory-autonomous-runner.yml # Scheduled idea selection + scoring
│       └── factory-monitor.yml          # Scheduled monitoring + portfolio summary
├── data/
│   └── lifecycle.sqlite                 # Persistent state database
├── docs/
│   ├── aidan_integration_contract.md    # AI-DAN dispatch contract
│   ├── live_run_checklist.md            # Pre-flight checklist
│   └── operator_control_contract.md     # Operator permissions
├── scripts/
│   ├── factory_utils.py                 # Shared utilities
│   ├── state_store.py                   # SQLite lifecycle state machine
│   ├── lifecycle_orchestrator.py        # State transition enforcer
│   ├── validate_brief.py               # Brief normalization + validation
│   ├── scoring_engine.py               # Deterministic 0-10 scoring
│   ├── validate_business_gate.py       # Unified approval gate
│   ├── monetization_filter.py          # Fast-revenue priority filter
│   ├── portfolio_memory.py             # Deduplication + history tracking
│   ├── revenue_loop.py                 # Post-launch revenue outcome loop
│   ├── idea_source_engine.py           # Autonomous idea pool selector
│   ├── business_output_engine.py       # Monetization strategy generator
│   ├── create_project.py               # GitHub repo creation
│   ├── inject_brief.py                 # Brief injection into repo
│   ├── deploy.py                       # Vercel deployment trigger
│   ├── deploy_health_check.py          # Post-deploy health probe
│   ├── monitor_and_decide.py           # Scale/optimize/kill logic
│   ├── portfolio_summary.py            # Portfolio bucketing
│   ├── normalize_workflow_inputs.py    # Input contract validation
│   ├── emit_alert.py                   # Failure alert payload
│   └── run_factory_tests.py            # Comprehensive test suite (10 stages)
├── templates/
│   └── saas-template/                   # Next.js 14 landing page template
└── test_data/
    ├── live_test_brief.json             # Example: HIGH demand, FAST revenue
    ├── aidan_live_brief.json            # Example: EXISTING_PRODUCT source
    ├── aidan_dry_run_brief.json         # Example: LOW complexity
    └── autonomous_ideas.json            # Autonomous idea pool
```

## Pipeline Execution (factory-build.yml — 24 Steps)

| Step | Name | Purpose |
|------|------|---------|
| 1-3 | Setup | Checkout, Python 3.12, initialize run context |
| 4 | Normalize inputs | Parse workflow inputs, resolve run mode |
| 5 | Tests only | (Conditional) Run test suite and exit |
| 6 | Init lifecycle | Seed "idea" state in SQLite |
| 7 | Validate brief | Normalize 11 required fields, compute idempotency key |
| 8 | **Monetization filter** | Reject unclear monetization / slow revenue cycle |
| 9 | **Portfolio memory** | Dedup check against history; reject failed duplicates |
| 10 | **Business gate** | Score 0-10 + hard rules → APPROVE / HOLD / REJECT |
| 11 | Lifecycle → building | Transition state machine |
| 12 | Create project repo | GitHub API template instantiation (idempotent) |
| 13 | Inject brief | Write PRODUCT_BRIEF.md + product.config.json |
| 14 | Business output | Generate monetization strategy JSON |
| 15 | Trigger deployment | POST to Vercel deploy hook |
| 16 | Health check | Retry HTTP GET to deployment URL |
| 17-18 | Lifecycle → deployed → monitored | State transitions |
| 19 | Monitor & decide | Evaluate traffic/activation/revenue signals |
| 20 | **Revenue loop** | Classify: NO_TRACTION / INTEREST_ONLY / REVENUE_CONFIRMED |
| 21 | Portfolio summary | Bucket projects: IGNORE / WATCH / SCALE |
| 22 | Finalize response | Assemble factory-response.json |
| 23 | Alert on failure | Emit structured alert payload |
| 24 | Upload artifacts | Save all JSON logs + lifecycle.sqlite |

## Scoring Engine

**Score Breakdown** (5 factors × 2 points each = 10 max):
- Market Demand: LOW=0, MEDIUM=1, HIGH=2
- Competition Saturation (reverse): HIGH=0, MEDIUM=1, LOW=2
- Monetization Potential: NO=0, YES=2
- Build Complexity (reverse): HIGH=0, MEDIUM=1, LOW=2
- Speed to Revenue: SLOW=0, MEDIUM=1, FAST=2

**Hard Rules (auto-reject):**
- `demand_level=LOW` → REJECT
- `monetization_proof=NO` → REJECT
- `market_saturation=HIGH + differentiation=WEAK` → REJECT

**Decision:**
- Score 0-5 → REJECT
- Score 6-7 → HOLD
- Score ≥8 → APPROVE

## Monetization Flow

1. **Pre-Gate Filter**: Prioritize fast revenue (<14 days), clear willingness to pay, simple delivery
2. **Business Output**: Generate pricing, GTM channels, CTA optimization, offer structure
3. **Revenue Loop**: Post-deploy tracking classifies outcomes:
   - `NO_TRACTION` → AUTO-KILL (traffic LOW + revenue NONE)
   - `INTEREST_ONLY` → ITERATE (interest but no conversion)
   - `REVENUE_CONFIRMED` → SCALE (strong revenue signal)

**Signal-Based Pricing:**
- HIGH demand + STRONG differentiation → "$19/mo starter, $49/mo growth"
- HIGH saturation → "$29 launch offer + $9 upsell"
- Default → "$9/mo entry, $29/mo pro"

**GTM Channels by Source:**
- TREND: SEO + X/Twitter
- COMPETITOR: Google Ads + Reddit
- GAP: Product Hunt + Email
- EXISTING_PRODUCT: LinkedIn + YouTube Shorts

## Environment Variables & Secrets

| Variable | Required | Purpose |
|----------|----------|---------|
| `FACTORY_GITHUB_TOKEN` | Yes | GitHub API auth for repo creation (fine-grained token) |
| `VERCEL_DEPLOY_HOOK_URL` | Yes | Vercel deployment trigger URL |

Set these in GitHub → Settings → Secrets → Actions.

## Quick Start (Non-Technical)

### 1. Fast Test (No Side Effects)

1. Go to **Actions** → **factory-build** → **Run workflow**
2. Set: `run_automated_tests_only=true`, `dry_run=true`
3. Leave `build_brief_json` empty, `project_id` = `test-001`
4. Click **Run** — all 10 test stages execute with zero side effects

### 2. Dry Run (Simulated Pipeline)

1. Go to **Actions** → **factory-build** → **Run workflow**
2. Set: `dry_run=true`, `run_automated_tests_only=false`
3. Paste the JSON brief below into `build_brief_json`
4. Click **Run** — full pipeline simulated, no repos created, no deployments

### 3. Live Run (Full Execution)

1. Go to **Actions** → **factory-build** → **Run workflow**
2. Set: `dry_run=false`, `run_automated_tests_only=false`
3. Paste this into `build_brief_json`:

```json
{
  "project_id": "test-001",
  "product_name": "Test Product",
  "problem": "Users need a simple way to validate the AI-DAN factory live pipeline.",
  "solution": "A minimal placeholder product used only to test live repo creation and deployment.",
  "cta": "Join waitlist",
  "source_type": "TREND",
  "reference_context": "Search demand for lightweight AI product launch kits among indie founders.",
  "demand_level": "HIGH",
  "monetization_proof": "YES",
  "market_saturation": "MEDIUM",
  "differentiation": "STRONG",
  "build_complexity": "LOW",
  "speed_to_revenue": "FAST"
}
```

4. Click **Run** — creates repo, deploys to Vercel, generates monetization strategy

### What Success Looks Like

- All steps complete green ✅
- `factory-response.json` shows `"status": "success"`
- Repo URL and deployment URL populated
- Business output generated with pricing and GTM plan

### What to Check on Failure

1. **Monetization filter** — does the idea have clear revenue path?
2. **Business gate** — is the score ≥8?
3. **Create project** — is `FACTORY_GITHUB_TOKEN` set with correct scopes?
4. **Deploy** — is `VERCEL_DEPLOY_HOOK_URL` pointing to the right project?
5. Check `factory-response.json` in workflow artifacts for full error details

## Automated Testing

```bash
python3 scripts/run_factory_tests.py
```

**10 Test Stages:**
1. Script syntax validation (all 20 scripts)
2. Payload schema check
3. Idea source + scoring tests
4. Business gate + lifecycle state machine
5. Happy-path dry-run pipeline
6. Monitor/scale/portfolio tests
7. Negative guard tests
8. Portfolio memory + deduplication
9. Revenue loop (NO_TRACTION / INTEREST_ONLY / REVENUE_CONFIRMED)
10. Monetization filter (pass/fail scenarios)

**CI runs automatically** on every push and pull request via `factory-ci.yml`.

## Deployment

- **Template**: Next.js 14 (App Router) — single landing page with CTA + lead capture
- **Platform**: Vercel (via deploy hook)
- **Health Check**: Retry HTTP probe (3 attempts, 5-sec delay)
- **Idempotency**: SHA-256 fingerprint prevents duplicate repos and deployments

## Tracking Contract

Every execution exposes:

```json
{
  "run_id": "123456789",
  "run_attempt": "1",
  "workflow_url": "https://github.com/org/repo/actions/runs/123456789",
  "timestamp_utc": "2026-04-04T00:00:00Z",
  "repo_url": "https://github.com/org/acme-saas",
  "deployment_url": "https://acme.vercel.app",
  "status": "success"
}
```

## Documentation

- [Live Run Checklist](docs/live_run_checklist.md) — Pre-flight validation
- [AI-DAN Integration Contract](docs/aidan_integration_contract.md) — Dispatch specification
- [Operator Control Contract](docs/operator_control_contract.md) — Permissions & gates

## License

MIT — Copyright 2026 Ismael
