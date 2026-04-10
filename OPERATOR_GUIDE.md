# AI-DAN Factory — Operator Guide

> For: Solo founder operating the launch engine.  
> Goal: idea approved → live URL → launch assets → first customer.

---

## How the system works (in plain English)

```
You write a product brief
       ↓
Factory scores it (0–10)
       ↓
Gate decision: APPROVE / REJECT / HOLD
       ↓
If approved: GitHub repo created → Vercel deploy triggered → live URL
       ↓
Launch assets generated (X post, LinkedIn, email copy, checklist)
       ↓
You copy-paste the assets and go sell
```

**Two repos. One job each.**

| Repo | Job |
|------|-----|
| `ai-dan-factory` (this repo) | Scores ideas, builds repos, deploys, generates launch copy |
| `aidan-managing-director` | Tracks portfolio, receives build callbacks, stores idea history |

---

## The ONE canonical build path

There is only one way to trigger a real build:

**Actions → `factory-build` → Run workflow**

Inputs:
- `project_id` — slug like `solo-invoicer` (lowercase, hyphens only)
- `build_brief_json` — paste your brief JSON (see template below)
- `dry_run` — `false` for a real build, `true` to test without deploying

That's it. Do not use any other path.

---

## Minimum viable brief (copy this, fill it in)

```json
{
  "project_id": "your-project-slug",
  "product_name": "Your Product Name",
  "problem": "One sentence: what pain does this solve?",
  "solution": "One sentence: what does it do?",
  "target_audience": "Who pays for this?",
  "pricing": "$X/month or $Y one-time",
  "cta": "Start free trial",
  "demand_level": "MEDIUM",
  "monetization_proof": "YES",
  "competition_saturation": "MEDIUM",
  "differentiation_strength": "STRONG",
  "speed_to_launch_days": 3,
  "template": "saas-template"
}
```

**Scoring rules — understand these before writing a brief:**

| Field | Values | Hard reject if... |
|-------|--------|-------------------|
| `demand_level` | `LOW`, `MEDIUM`, `HIGH` | = `LOW` |
| `monetization_proof` | `YES`, `NO` | = `NO` |
| `competition_saturation` | `LOW`, `MEDIUM`, `HIGH` | `HIGH` + `WEAK` differentiation |
| `differentiation_strength` | `WEAK`, `MODERATE`, `STRONG` | see above |

---

## What you get after a build

After the workflow completes:

1. **GitHub repo** — your product code lives here
2. **Vercel URL** — `https://your-project-id.vercel.app` (live within ~2 min)
3. **Artifacts** — download from the workflow run:
   - `LAUNCH_ASSETS.md` — your launch copy (paste, post, sell)
   - `factory-response.json` — full build report

**Always check Artifacts first** after a build. That's where your launch copy lives.

---

## Daily autonomous mode (score-only)

The runner fires at 08:00 UTC every day. It:
1. Picks an idea from `test_data/autonomous_ideas.json`
2. Scores it
3. Reports the decision — but does NOT build anything

**To trigger a real build from the autonomous runner:**

Actions → `factory-autonomous-runner` → Run workflow → set `live_mode = true`

It will dispatch `factory-build` automatically if the idea passes the gate.

**To add your own ideas to the daily runner:**
Edit `test_data/autonomous_ideas.json` and add your brief JSON to the array.

---

## Required secrets (set these in GitHub → Settings → Secrets)

| Secret | Required for | Where to get it |
|--------|-------------|------------------|
| `FACTORY_GITHUB_TOKEN` | Creating repos | GitHub → Settings → Developer settings → PAT (repo scope) |
| `VERCEL_DEPLOY_HOOK_URL` | Deploying to Vercel | Vercel → Project → Settings → Git → Deploy Hooks |
| `OPENAI_API_KEY` | AI-quality launch copy | platform.openai.com |
| `FACTORY_BASE_URL` | Notifying Managing Director | Your MD deployment URL |
| `FACTORY_SECRET` | Secure callbacks | Any random 32+ char string |

Without `FACTORY_GITHUB_TOKEN` and `VERCEL_DEPLOY_HOOK_URL`, real builds will fail.  
Without `OPENAI_API_KEY`, launch copy will use deterministic templates (still usable, just less sharp).

---

## After the build — what to do in the first 48 hours

The `LAUNCH_ASSETS.md` file in your build artifacts has the exact copy. Use this order:

1. **Hour 1** — Post the X tweet (copy-paste exactly)
2. **Hour 1** — Post on LinkedIn
3. **Hour 2** — DM 10 people in your target audience with the cold email
4. **Hour 3** — Post in 2-3 relevant Reddit communities
5. **Day 1** — Reply to every response personally
6. **Day 1** — Check Stripe — if zero payments, do more outreach (not more posting)
7. **Day 2** — Email signups who didn't pay — ask what stopped them
8. **Day 3** — Decide: kill, iterate, or scale

**The rule: talk to humans before building more features.**

---

## Troubleshooting

| Problem | What to check |
|---------|---------------|
| Build fails immediately | Check secrets are set: `FACTORY_GITHUB_TOKEN`, `VERCEL_DEPLOY_HOOK_URL` |
| Repo created but no Vercel URL | Check `VERCEL_DEPLOY_HOOK_URL` is the correct hook for the right Vercel project |
| Idea rejected at gate | Check `demand_level` ≠ `LOW` and `monetization_proof` = `YES` |
| Launch assets say "reduced quality" | Set `OPENAI_API_KEY` in repository secrets |
| Callback to Managing Director failing | Check `FACTORY_BASE_URL` and `FACTORY_SECRET` match across both repos |

---

## What this system does NOT do (yet)

- It does not source ideas automatically from the internet (you add them manually to `test_data/autonomous_ideas.json`)
- It does not send emails or post to social media automatically
- It does not manage Stripe subscriptions after payment (you must handle fulfillment manually)
- It does not track real visitor/conversion analytics (add Plausible or Simple Analytics to your deployed site)

---

*Last updated: auto-generated by AI-DAN Factory*
