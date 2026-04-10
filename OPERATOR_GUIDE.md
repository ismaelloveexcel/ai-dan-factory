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

## Your Active Projects

These are the three products in your venture pipeline. Each has a scored brief in `test_data/product_briefs.json`.

| Project | Status | Priority | Existing Repo |
|---------|--------|----------|---------------|
| **GameForge Digital Gifts** | APPROVED — build now | 🔴 **#1 Priority** | [gameforge-mobile](https://github.com/ismaelloveexcel/gameforge-mobile) |
| **Sparks — Dating Through Games** | APPROVED — validate first | 🟡 #2 Priority | None (concept stage) |
| **EduGate** | HOLD — validate with real users | ⚪ #3 Priority | [EduGate](https://github.com/ismaelloveexcel/EduGate) |

**Start with GameForge.** It has the clearest buyer, fastest path to revenue, and lowest competition. See `test_data/product_briefs.json` for full scoring and next steps.

---

## Getting Your First API Keys

You need at least one AI key to score ideas with intelligence (not just rule-based scoring). Here’s where to get each one, ordered by recommendation.

### 1. ANTHROPIC_API_KEY (Best for idea scoring)
- Go to [console.anthropic.com](https://console.anthropic.com)
- Sign up, then go to **API Keys** → **Create Key**
- Copy the key (you only see it once)
- Best model: `claude-3-5-sonnet-20241022` (already set as default)
- Cost: ~$3 per million tokens — very affordable for scoring

### 2. GROQ_API_KEY (Free tier, very fast)
- Go to [console.groq.com](https://console.groq.com)
- Sign up for free — no credit card required
- Go to **API Keys** → **Create API Key**
- Free tier includes generous daily limits
- Best for: quick scoring runs, high-volume testing

### 3. DEEPSEEK_API_KEY (Cheapest option)
- Go to [platform.deepseek.com](https://platform.deepseek.com)
- Sign up and top up a small amount ($5 goes a long way)
- Go to **API Keys** → **Create new key**
- Cost: ~$0.14 per million tokens — the cheapest quality model available
- Best for: high-volume scoring on a tight budget

### 4. TELEGRAM_BOT_TOKEN (Get notified when builds finish)
Set this up once and you’ll get an instant Telegram message every time a build succeeds, fails, or an idea is approved.

**3-minute setup:**
1. Open Telegram, search **@BotFather**
2. Send `/newbot` and follow the prompts (give your bot any name)
3. BotFather gives you a token like `123456:ABCdefGHIjklMNO` — that’s your `TELEGRAM_BOT_TOKEN`
4. Start a chat with your new bot (search its username, press Start)
5. Open this URL in your browser (replace TOKEN with yours):  
   `https://api.telegram.org/botTOKEN/getUpdates`
6. Find `"chat":{"id":XXXXXXXX}` in the response — that number is your `TELEGRAM_CHAT_ID`

### Where to add your keys

**For the `aidan-managing-director` Vercel deployment:**
1. Go to [vercel.com](https://vercel.com) → your project → **Settings** → **Environment Variables**
2. Add each key as a new variable (name must match exactly, e.g. `ANTHROPIC_API_KEY`)
3. Click **Save**
4. Go to **Deployments** → click the three dots on the latest deployment → **Redeploy**

The system picks up the new keys automatically after redeployment.

**For GitHub Actions (factory workflows):**
1. Go to your `ai-dan-factory` repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret** for each key
3. Workflows automatically use these on the next run

---

## The ONE canonical build path

There is only one way to trigger a real build:

**Actions → `factory-build` → Run workflow**

Inputs:
- `project_id` — slug like `solo-invoicer` (lowercase, hyphens only)
- `build_brief_json` — paste your brief JSON (see template below)
- `dry_run` — `false` for a real build, `true` to test without deploying

That’s it. Do not use any other path.

---

## Minimum viable brief (copy this, fill it in)

```json
{
  "project_id": "your-project-slug",
  "product_name": "Your Product Name",
  "problem": "One sentence: what pain does this solve?",
  "solution": "One sentence: what does it do?",
  "cta": "Start free trial",
  "source_type": "GAP",
  "reference_context": "Brief description of the market gap or trend you identified",
  "demand_level": "MEDIUM",
  "monetization_proof": "YES",
  "market_saturation": "MEDIUM",
  "differentiation": "STRONG"
}
```

**Scoring rules — understand these before writing a brief:**

| Field | Values | Hard reject if... |
|-------|--------|-------------------|
| `demand_level` | `LOW`, `MEDIUM`, `HIGH` | = `LOW` |
| `monetization_proof` | `YES`, `NO` | = `NO` |
| `source_type` | `TREND`, `COMPETITOR`, `GAP`, `EXISTING_PRODUCT` | not one of these |
| `market_saturation` | `LOW`, `MEDIUM`, `HIGH` | `HIGH` + `WEAK` differentiation |
| `differentiation` | `WEAK`, `STRONG` | `WEAK` when `market_saturation` = `HIGH` |

---

## What you get after a build

After the workflow completes:

1. **GitHub repo** — your product code lives here
2. **Vercel URL** — `https://your-project-id.vercel.app` (live within ~2 min)
3. **Artifacts** — download from the workflow run:
   - `LAUNCH_ASSETS.md` — your launch copy (paste, post, sell)
   - `factory-response.json` — full build report

**Always check Artifacts first** after a build. That’s where your launch copy lives.

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
7. **Day 2** — Email signups who didn’t pay — ask what stopped them
8. **Day 3** — Decide: kill, iterate, or scale

**The rule: talk to humans before building more features.**

---

## Troubleshooting

| Problem | What to check |
|---------|---------------|
| Build fails immediately | Check secrets are set: `FACTORY_GITHUB_TOKEN`, `VERCEL_DEPLOY_HOOK_URL` |
| Repo created but no Vercel URL | Check `VERCEL_DEPLOY_HOOK_URL` is the correct hook for the right Vercel project |
| Idea rejected at gate | Check `demand_level` ≠ `LOW` and `monetization_proof` = `YES` |
| Launch assets say “reduced quality” | Set `OPENAI_API_KEY` in repository secrets |
| Callback to Managing Director failing | Check `FACTORY_BASE_URL` and `FACTORY_SECRET` match across both repos |
| No Telegram notifications | Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set in Vercel env vars |

---

## What this system does NOT do (yet)

- It does not source ideas automatically from the internet (you add them manually to `test_data/autonomous_ideas.json`)
- It does not send emails or post to social media automatically
- It does not manage Stripe subscriptions after payment (you must handle fulfillment manually)
- It does not track real visitor/conversion analytics (add Plausible or Simple Analytics to your deployed site)

---

*Last updated: auto-generated by AI-DAN Factory*
