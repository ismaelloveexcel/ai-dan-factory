# AI-DAN Factory — Copilot Instructions

## Architecture Rules

1. **Monetization-First**: Every idea MUST have a clear revenue path before it enters the build pipeline. No revenue path → REJECT.
2. **Validation Gate Mandatory**: All ideas pass through `validate_business_gate.py`. No bypass allowed. Score < 6 → REJECT, 6-7 → HOLD, ≥ 8 → APPROVE.
3. **Strict Lifecycle State Machine**: `idea → validated → scored → approved/rejected/hold → building → deployed → monitored → scaled/killed`. No state may be skipped. Forward-only transitions enforced by `state_store.py`.
4. **Solo-Operator Simplicity**: The system is designed for ONE non-technical user. All workflows run autonomously via GitHub Actions. Zero coding required.
5. **Safe Defaults**: `dry_run=true` by default for new users. Production mode requires explicit opt-in. All secrets masked in logs.
6. **Automation Expectations**: The system runs on cron schedules (every 30 min). Idea generation, scoring, monitoring, and portfolio decisions happen automatically.

## Pipeline Enforcement

- **No pipeline bypass**: Every idea must flow through: Idea Source → Validate Brief → Business Gate → Score → Approve/Reject → Build → Deploy → Monitor → Scale/Kill.
- **Deduplication**: Before approval, `portfolio_memory.py` checks for duplicate or previously-failed ideas. Failed duplicates → REJECT. Successful variants → PRIORITIZE.
- **Monetization Filter**: `monetization_filter.py` prioritizes fast revenue (< 14 days), clear willingness to pay, and simple delivery. Unclear monetization → REJECT.
- **Revenue Loop**: `revenue_loop.py` evaluates post-launch signals. NO_TRACTION → AUTO-KILL. INTEREST_ONLY → ITERATE. REVENUE_CONFIRMED → SCALE.

## Code Conventions

- All scripts are in `scripts/` and use Python 3.12+.
- All scripts emit structured JSON logs via `factory_utils.log_event()`.
- All scripts accept CLI args via `argparse` and support `--dry-run` where applicable.
- State is persisted in SQLite via `state_store.py`. No external databases.
- Idempotency keys follow format: `{project_id}:{sha256_digest[:16]}`.
- Secrets: `FACTORY_GITHUB_TOKEN`, `VERCEL_DEPLOY_HOOK_URL` — never logged, always masked.

## Testing

- All tests run via `scripts/run_factory_tests.py` with zero external side effects.
- CI runs on every push/PR via `factory-ci.yml`.
- Tests must pass before merge. No exceptions.

## Workflow Structure

- `factory-build.yml` — Main 21-step execution pipeline (workflow_dispatch)
- `factory-ci.yml` — Automated test runner (push/PR trigger)
- `factory-autonomous-runner.yml` — Scheduled idea selection + scoring (cron: */30 * * * *)
- `factory-monitor.yml` — Scheduled monitoring + revenue loop + portfolio summary (cron: */30 * * * *)
